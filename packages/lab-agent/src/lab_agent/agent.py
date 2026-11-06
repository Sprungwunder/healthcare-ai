"""The agent loop: ask the model, run requested tools, repeat until it answers.

Maintains explicit AgentState and conversation history, supporting atomic
checkpointing to a StateStore and task resumption across restarts.

Error policy:
- Errors the model can fix (unknown tool, bad arguments, missing document) are
  sent back to it as tool results with ``is_error=True`` and the loop goes on.
- Errors it cannot fix (API failures, unusable responses, too many iterations)
  raise, update task status (FAILED / INTERRUPTED) and persist state before ending.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

from lab_agent.model import (
    AssistantMessage,
    Message,
    ModelClient,
    ModelError,
    SystemMessage,
    ToolCall,
    ToolMessage,
    UserMessage,
)
from lab_agent.registry import LAB_TOOLS, Tool, validate_arguments
from lab_agent.state import AgentState, TaskStatus
from lab_agent.storage import StateStore
from lab_agent.tools import ToolError

DEFAULT_MAX_ITERATIONS: Final[int] = 5

SYSTEM_PROMPT: Final[str] = (
    "You answer questions about laboratory documents. Use the tools to find "
    "documents and read their results; never invent documents or values. Cite "
    "document IDs. If the tools return nothing relevant, say so. You do not "
    "give diagnoses or treatment advice."
)


class MaxIterationsExceededError(Exception):
    """Raised when the model has not given a final answer within the limit."""


@dataclass(frozen=True)
class AgentResult:
    answer: str
    messages: tuple[Message, ...]  # full transcript, for inspection and tests
    iterations: int  # number of model calls
    state: AgentState | None = None
    task_id: str | None = None


def run_agent(
    request: str,
    client: ModelClient,
    tools: Sequence[Tool] = LAB_TOOLS,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    task_id: str | None = None,
    store: StateStore | None = None,
    initial_state: AgentState | None = None,
    resume: bool = False,
) -> AgentResult:
    """Answer ``request`` by letting the model call ``tools``.

    Each iteration is one model call. If the model asks for tools, every call
    is executed and its result appended before the next iteration.

    When ``store`` is provided, state and conversation transcript are checkpointed
    after every step and iteration.

    Raises:
        ValueError: If ``max_iterations`` is less than 1 or if resume arguments
            are invalid.
        ModelError: If the client fails or the model returns an empty turn.
        MaxIterationsExceededError: If there is no final answer in time.
    """
    if max_iterations < 1:
        raise ValueError("max_iterations must be at least 1.")

    tools_by_name = {tool.name: tool for tool in tools}

    if resume:
        if not task_id:
            raise ValueError("task_id is required to resume a task.")
        if store is None:
            raise ValueError("A StateStore is required to resume a task.")
        checkpoint = store.load_checkpoint(task_id)
        if checkpoint is None:
            raise ValueError(f"No checkpoint found for task '{task_id}'.")
        state, restored_messages = checkpoint
        messages: list[Message] = list(restored_messages)

        if state.status == TaskStatus.COMPLETED:
            last_ans = next(
                (
                    m.content
                    for m in reversed(messages)
                    if isinstance(m, AssistantMessage) and m.content
                ),
                "",
            )
            return AgentResult(
                answer=last_ans or "",
                messages=tuple(messages),
                iterations=0,
                state=state,
                task_id=task_id,
            )

        state.update_status(TaskStatus.IN_PROGRESS)
        store.save_checkpoint(state, messages)
    else:
        if task_id is None:
            task_id = (
                initial_state.task_id
                if initial_state is not None
                else str(uuid.uuid4())
            )
        if initial_state is not None:
            state = initial_state
            state.task_id = task_id
            state.update_status(TaskStatus.IN_PROGRESS)
        else:
            state = AgentState(
                task_id=task_id,
                status=TaskStatus.IN_PROGRESS,
                metadata={"request": request},
            )
        messages = [SystemMessage(SYSTEM_PROMPT), UserMessage(request)]
        if store is not None:
            store.save_checkpoint(state, messages)

    # Recover any incomplete tool calls from the last turn if interrupted mid-turn
    _recover_pending_tool_calls(messages, state, tools_by_name, store)

    try:
        for iteration in range(1, max_iterations + 1):
            reply: AssistantMessage = client.complete(messages, tools)
            messages.append(reply)
            if store is not None:
                store.save_checkpoint(state, messages)

            if not reply.tool_calls:
                if not reply.content or not reply.content.strip():
                    raise ModelError("Model returned neither tool calls nor an answer.")
                state.mark_step_completed("generate_summary", result=reply.content)
                state.update_status(TaskStatus.COMPLETED)
                if store is not None:
                    store.save_checkpoint(state, messages)
                return AgentResult(
                    answer=reply.content,
                    messages=tuple(messages),
                    iterations=iteration,
                    state=state,
                    task_id=task_id,
                )

            for tool_call in reply.tool_calls:
                tool_msg = execute_tool_call(tool_call, tools_by_name)
                messages.append(tool_msg)
                _update_state_from_tool_result(state, tool_call.name, tool_msg)

            if store is not None:
                store.save_checkpoint(state, messages)

        state.update_status(
            TaskStatus.INTERRUPTED,
            error=f"No final answer after {max_iterations} iterations.",
        )
        if store is not None:
            store.save_checkpoint(state, messages)
        raise MaxIterationsExceededError(
            f"No final answer after {max_iterations} iterations."
        )

    except Exception as exc:
        if not (
            isinstance(state.status, TaskStatus)
            and state.status == TaskStatus.COMPLETED
        ):
            err_status = (
                TaskStatus.INTERRUPTED
                if isinstance(exc, MaxIterationsExceededError)
                else TaskStatus.FAILED
            )
            state.update_status(err_status, error=str(exc))
            if store is not None:
                store.save_checkpoint(state, messages)
        raise


def resume_agent(
    task_id: str,
    client: ModelClient,
    store: StateStore,
    tools: Sequence[Tool] = LAB_TOOLS,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
) -> AgentResult:
    """Resume an existing, persisted agent task from its last checkpoint."""
    return run_agent(
        request="",
        client=client,
        tools=tools,
        max_iterations=max_iterations,
        task_id=task_id,
        store=store,
        resume=True,
    )


def _recover_pending_tool_calls(
    messages: list[Message],
    state: AgentState,
    tools_by_name: Mapping[str, Tool],
    store: StateStore | None,
) -> None:
    """Execute and append tool calls from the latest turn lacking results."""
    last_assistant_idx: int | None = None
    for idx in range(len(messages) - 1, -1, -1):
        if isinstance(messages[idx], AssistantMessage):
            last_assistant_idx = idx
            break

    if last_assistant_idx is None:
        return

    last_assistant = messages[last_assistant_idx]
    if (
        not isinstance(last_assistant, AssistantMessage)
        or not last_assistant.tool_calls
    ):
        return

    executed_call_ids = {
        msg.tool_call_id
        for msg in messages[last_assistant_idx + 1 :]
        if isinstance(msg, ToolMessage)
    }

    pending_calls = [
        call for call in last_assistant.tool_calls if call.id not in executed_call_ids
    ]

    if not pending_calls:
        return

    for tool_call in pending_calls:
        tool_msg = execute_tool_call(tool_call, tools_by_name)
        messages.append(tool_msg)
        _update_state_from_tool_result(state, tool_call.name, tool_msg)

    if store is not None:
        store.save_checkpoint(state, messages)


def _update_state_from_tool_result(
    state: AgentState, tool_name: str, tool_msg: ToolMessage
) -> None:
    """Update structured AgentState based on successful tool output."""
    if tool_msg.is_error:
        return

    try:
        data: Any = json.loads(tool_msg.content)
    except json.JSONDecodeError:
        return

    if tool_name == "search_lab_documents":
        state.intermediate_results["search_results"] = data
        state.mark_step_completed("search_document", result=data)
    elif tool_name == "get_document_details":
        if isinstance(data, dict):
            state.document_id = data.get("document_id")
            if "results" in data and isinstance(data["results"], list):
                state.extracted_values = list(data["results"])
            state.intermediate_results["document_details"] = data
            state.mark_step_completed("extract_values", result=data)
    elif tool_name == "evaluate_lab_results":
        if isinstance(data, dict):
            state.intermediate_results["evaluation"] = data
            state.mark_step_completed("evaluate_values", result=data)


def execute_tool_call(
    tool_call: ToolCall, tools_by_name: Mapping[str, Tool]
) -> ToolMessage:
    """Validate and run one tool call; expected failures become error results.

    Unexpected exceptions from a tool are bugs and propagate unchanged.
    """
    tool = tools_by_name.get(tool_call.name)
    if tool is None:
        available = ", ".join(sorted(tools_by_name))
        return _error(tool_call, f"Unknown tool '{tool_call.name}'. Use: {available}.")

    try:
        arguments: Any = json.loads(tool_call.arguments or "{}")
    except json.JSONDecodeError:
        return _error(tool_call, "Arguments are not valid JSON.")
    if not isinstance(arguments, dict):
        return _error(tool_call, "Arguments must be a JSON object.")

    try:
        validate_arguments(tool, arguments)
        result = tool.function(**arguments)
    except ToolError as exc:
        return _error(tool_call, str(exc))

    return ToolMessage(tool_call.id, json.dumps(result))


def _error(tool_call: ToolCall, message: str) -> ToolMessage:
    return ToolMessage(tool_call.id, json.dumps({"error": message}), is_error=True)
