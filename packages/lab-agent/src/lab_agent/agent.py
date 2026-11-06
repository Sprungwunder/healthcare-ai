"""The agent loop: ask the model, run requested tools, repeat until it answers.

Error policy:
- Errors the model can fix (unknown tool, bad arguments, missing document) are
  sent back to it as tool results with ``is_error=True`` and the loop goes on.
- Errors it cannot fix (API failures, unusable responses, too many iterations)
  raise and end the run.
"""

from __future__ import annotations

import json
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


def run_agent(
    request: str,
    client: ModelClient,
    tools: Sequence[Tool] = LAB_TOOLS,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
) -> AgentResult:
    """Answer ``request`` by letting the model call ``tools``.

    Each iteration is one model call. If the model asks for tools, every call
    is executed and its result appended before the next iteration.

    Raises:
        ValueError: If ``max_iterations`` is less than 1.
        ModelError: If the client fails or the model returns an empty turn.
        MaxIterationsExceededError: If there is no final answer in time.
    """
    if max_iterations < 1:
        raise ValueError("max_iterations must be at least 1.")

    tools_by_name = {tool.name: tool for tool in tools}
    messages: list[Message] = [SystemMessage(SYSTEM_PROMPT), UserMessage(request)]

    for iteration in range(1, max_iterations + 1):
        reply: AssistantMessage = client.complete(messages, tools)
        messages.append(reply)

        if not reply.tool_calls:
            if not reply.content or not reply.content.strip():
                raise ModelError("Model returned neither tool calls nor an answer.")
            return AgentResult(reply.content, tuple(messages), iteration)

        for tool_call in reply.tool_calls:
            messages.append(execute_tool_call(tool_call, tools_by_name))

    raise MaxIterationsExceededError(
        f"No final answer after {max_iterations} iterations."
    )


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
