"""Tests for multi-step task execution, persistence, and task resumption."""

import json
from collections.abc import Sequence
from pathlib import Path

import pytest

from lab_agent.__main__ import main as cli_main
from lab_agent.agent import (
    MaxIterationsExceededError,
    resume_agent,
    run_agent,
)
from lab_agent.model import (
    AssistantMessage,
    Message,
    ModelError,
    ToolCall,
)
from lab_agent.registry import Tool
from lab_agent.state import AgentState, TaskStatus
from lab_agent.storage import InMemoryStateStore, SQLiteStateStore


class ScriptedClient:
    """Fake model client: returns prepared replies and records each request."""

    def __init__(self, *replies: AssistantMessage | Exception) -> None:
        self._replies = list(replies)
        self.requests: list[list[Message]] = []

    def complete(
        self, messages: Sequence[Message], tools: Sequence[Tool]
    ) -> AssistantMessage:
        self.requests.append(list(messages))
        if not self._replies:
            raise RuntimeError("ScriptedClient ran out of prepared replies.")
        reply = self._replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def call(name: str, arguments: str, call_id: str = "call-1") -> AssistantMessage:
    return AssistantMessage(tool_calls=(ToolCall(call_id, name, arguments),))


def answer(text: str) -> AssistantMessage:
    return AssistantMessage(content=text)


def test_full_multi_step_healthcare_analysis_flow(tmp_path: Path) -> None:
    """Demonstrate a full 4-step healthcare document analysis workflow:
    1. Search for synthetic laboratory document
    2. Extract laboratory values
    3. Evaluate extracted values
    4. Generate clinical analysis summary
    """
    db_file = tmp_path / "agent_multi.db"
    store = SQLiteStateStore(db_file)

    client = ScriptedClient(
        call("search_lab_documents", '{"query": "thyroid"}', "c1"),
        call("get_document_details", '{"document_id": "LAB-1004"}', "c2"),
        call("evaluate_lab_results", '{"document_id": "LAB-1004"}', "c3"),
        answer(
            "Analysis Summary for LAB-1004 (Thyroid function, SYN-0003):\n"
            "- TSH: 5.9 mU/L (Elevated above reference range 0.4-4.0)\n"
            "- Free T4: 10.1 pmol/L (Below reference range 12-22)\n"
            "Overall: 2 abnormal results consistent with primary hypothyroidism."
        ),
    )

    result = run_agent(
        request="Analyze my thyroid lab report.",
        client=client,
        task_id="thyroid-task-1",
        store=store,
    )

    assert result.iterations == 4
    assert result.state is not None
    assert result.state.status == TaskStatus.COMPLETED
    assert result.state.document_id == "LAB-1004"
    assert len(result.state.extracted_values) == 2
    assert "search_document" in result.state.completed_steps
    assert "extract_values" in result.state.completed_steps
    assert "evaluate_values" in result.state.completed_steps
    assert "generate_summary" in result.state.completed_steps
    assert result.state.pending_steps == []

    # Verify intermediate results are stored
    assert "search_results" in result.state.intermediate_results
    assert "document_details" in result.state.intermediate_results
    assert "evaluation" in result.state.intermediate_results
    assert result.state.intermediate_results["evaluation"]["abnormal_count"] == 2

    # Verify state was saved to SQLite
    persisted_state = store.load_state("thyroid-task-1")
    assert persisted_state is not None
    assert persisted_state.status == TaskStatus.COMPLETED
    assert persisted_state.document_id == "LAB-1004"


def test_interruption_and_task_resumption_after_restart(tmp_path: Path) -> None:
    """Test scenario:
    1. First agent instance runs steps 1 & 2 (search + extract) but gets interrupted.
    2. Application restarts (new agent instance, new client).
    3. Second agent instance resumes the task using the task_id.
    4. Completed steps are restored from the database and not repeated.
    5. Remaining steps (evaluate + summary) are executed to completion.
    """
    db_file = tmp_path / "restart_test.db"
    store = SQLiteStateStore(db_file)
    task_id = "interrupted-task-42"

    # Phase 1: First agent instance executes up to step 2 with max_iterations=2
    client_phase1 = ScriptedClient(
        call("search_lab_documents", '{"query": "lipid"}', "c1"),
        call("get_document_details", '{"document_id": "LAB-1002"}', "c2"),
    )

    with pytest.raises(MaxIterationsExceededError):
        run_agent(
            request="Check my lipid results",
            client=client_phase1,
            task_id=task_id,
            store=store,
            max_iterations=2,
        )

    # Check intermediate state persisted before restart
    saved_state = store.load_state(task_id)
    assert saved_state is not None
    assert saved_state.status == TaskStatus.INTERRUPTED
    assert saved_state.document_id == "LAB-1002"
    assert len(saved_state.extracted_values) == 4
    assert saved_state.completed_steps == ["search_document", "extract_values"]

    # Phase 2: Application restart! Fresh client, new agent instance
    client_phase2 = ScriptedClient(
        call("evaluate_lab_results", '{"document_id": "LAB-1002"}', "c3"),
        answer("Lipid evaluation: Total cholesterol and LDL are elevated."),
    )

    resume_result = resume_agent(
        task_id=task_id,
        client=client_phase2,
        store=store,
        max_iterations=5,
    )

    assert (
        resume_result.answer
        == "Lipid evaluation: Total cholesterol and LDL are elevated."
    )
    assert resume_result.state is not None
    assert resume_result.state.status == TaskStatus.COMPLETED
    assert "evaluate_values" in resume_result.state.completed_steps
    assert "generate_summary" in resume_result.state.completed_steps

    # Verify the second client did not receive requests to repeat search
    # Restored conversation history is passed to client_phase2
    first_request_msgs = client_phase2.requests[0]
    # Check that previous tool messages exist in history
    tool_call_ids = [
        m.tool_call_id for m in first_request_msgs if hasattr(m, "tool_call_id")
    ]
    assert "c1" in tool_call_ids
    assert "c2" in tool_call_ids


def test_resume_recovers_unexecuted_tool_call_mid_turn(tmp_path: Path) -> None:
    """Test scenario where application was terminated after a tool call."""
    db_file = tmp_path / "mid_turn.db"
    store = SQLiteStateStore(db_file)
    task_id = "mid-turn-task"

    # Simulate saved checkpoint with unexecuted tool call in last turn
    initial_messages = [
        AssistantMessage(
            tool_calls=(
                ToolCall(
                    "call-mid", "get_document_details", '{"document_id": "LAB-1003"}'
                ),
            )
        )
    ]
    initial_state = AgentState(
        task_id=task_id,
        status=TaskStatus.IN_PROGRESS,
        metadata={"request": "Check HbA1c"},
    )
    store.save_checkpoint(initial_state, initial_messages)

    # Now simulate a second run resuming and answering
    client_resume = ScriptedClient(answer("HbA1c is 6.9% in LAB-1003."))
    result = resume_agent(task_id=task_id, client=client_resume, store=store)

    assert result.answer == "HbA1c is 6.9% in LAB-1003."
    assert result.state is not None
    assert result.state.status == TaskStatus.COMPLETED
    assert result.state.document_id == "LAB-1003"
    assert len(result.state.extracted_values) == 1
    assert "extract_values" in result.state.completed_steps


def test_resume_recovers_partially_executed_multi_tool_turn(tmp_path: Path) -> None:
    """Test scenario where a turn has multiple tool calls and fails mid-execution.

    Verifies that on resume:
    1. The already-executed tool call is not repeated.
    2. The unexecuted tool call is executed and its result appended.
    3. The model client receives complete tool results for all tool calls in the turn.
    """
    from lab_agent.anthropic_client import _to_anthropic_messages
    from lab_agent.model import ToolMessage, UserMessage

    db_file = tmp_path / "multi_tool_partial.db"
    store = SQLiteStateStore(db_file)
    task_id = "multi-partial-task"

    # Turn with 2 tool calls: get_document_details and evaluate_lab_results
    turn_with_two_tools = AssistantMessage(
        tool_calls=(
            ToolCall("toolu_1", "get_document_details", '{"document_id": "LAB-1002"}'),
            ToolCall("toolu_2", "evaluate_lab_results", '{"document_id": "LAB-1002"}'),
        )
    )
    # Simulate: toolu_1 executed before crash, but toolu_2 crashed/was not executed
    partial_messages = [
        UserMessage("Analyze lipid results"),
        turn_with_two_tools,
        ToolMessage(
            tool_call_id="toolu_1",
            content=json.dumps({"document_id": "LAB-1002", "results": []}),
        ),
    ]
    initial_state = AgentState(
        task_id=task_id,
        status=TaskStatus.FAILED,
        error="Simulated tool error on toolu_2",
        completed_steps=["search_document", "extract_values"],
        pending_steps=["evaluate_values", "generate_summary"],
    )
    store.save_checkpoint(initial_state, partial_messages)

    client = ScriptedClient(answer("Lipid analysis complete."))
    result = resume_agent(task_id=task_id, client=client, store=store)

    assert result.answer == "Lipid analysis complete."
    assert result.state is not None
    assert result.state.status == TaskStatus.COMPLETED
    assert "evaluate_values" in result.state.completed_steps

    # Verify that the request sent to client has both tool results
    sent_messages = client.requests[0]
    tool_msgs = [m for m in sent_messages if isinstance(m, ToolMessage)]
    assert len(tool_msgs) == 2
    assert {m.tool_call_id for m in tool_msgs} == {"toolu_1", "toolu_2"}

    # Verify Anthropic message converter produces matching tool_results for tool_use
    anthropic_msgs = _to_anthropic_messages(sent_messages)
    # Expected Anthropic messages:
    # 0: user message ("Analyze lipid results")
    # 1: assistant message with 2 tool_use blocks (toolu_1, toolu_2)
    # 2: user message with 2 tool_result blocks (toolu_1, toolu_2)
    assert len(anthropic_msgs) == 3
    assert anthropic_msgs[1]["role"] == "assistant"
    tool_use_ids = {
        b["id"] for b in anthropic_msgs[1]["content"] if b["type"] == "tool_use"
    }
    assert tool_use_ids == {"toolu_1", "toolu_2"}

    assert anthropic_msgs[2]["role"] == "user"
    tool_result_ids = {
        b["tool_use_id"]
        for b in anthropic_msgs[2]["content"]
        if b["type"] == "tool_result"
    }
    assert tool_result_ids == {"toolu_1", "toolu_2"}


def test_resuming_completed_task_returns_immediately(tmp_path: Path) -> None:
    store = InMemoryStateStore()
    client = ScriptedClient(answer("Already finished."))

    result1 = run_agent("Question", client, task_id="comp-1", store=store)
    assert result1.answer == "Already finished."

    # Resuming completed task does not make extra model calls
    empty_client = ScriptedClient()
    result2 = resume_agent("comp-1", empty_client, store=store)
    assert result2.answer == "Already finished."
    assert len(empty_client.requests) == 0


def test_resume_validation_errors() -> None:
    store = InMemoryStateStore()
    client = ScriptedClient()

    with pytest.raises(ValueError, match="task_id is required"):
        run_agent("", client, task_id=None, store=store, resume=True)

    with pytest.raises(ValueError, match="StateStore is required"):
        run_agent("", client, task_id="t-1", store=None, resume=True)

    with pytest.raises(ValueError, match="No checkpoint found"):
        resume_agent("non-existent-task", client, store=store)


def test_failure_records_failed_status_in_checkpoint(tmp_path: Path) -> None:
    db_file = tmp_path / "failed.db"
    store = SQLiteStateStore(db_file)
    task_id = "fail-task"

    client = ScriptedClient(ModelError("HTTP 500 server error"))

    with pytest.raises(ModelError):
        run_agent("Test failure", client, task_id=task_id, store=store)

    saved_state = store.load_state(task_id)
    assert saved_state is not None
    assert saved_state.status == TaskStatus.FAILED
    assert "HTTP 500" in (saved_state.error or "")


def test_cli_integration(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db_file = str(tmp_path / "cli_test.db")
    client = ScriptedClient(
        call("search_lab_documents", '{"query": "liver"}', "c1"),
        answer("Liver panel found."),
    )

    # 1. Run via CLI
    ret = cli_main(
        ["--db", db_file, "--task-id", "cli-task-1", "Find liver results"],
        client=client,
    )
    assert ret == 0
    captured = capsys.readouterr()
    assert "Liver panel found." in captured.out

    # 2. List tasks via CLI
    ret = cli_main(["--db", db_file, "--list-tasks"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "cli-task-1" in captured.out

    # 3. Show state via CLI
    ret = cli_main(["--db", db_file, "--task-id", "cli-task-1", "--show-state"])
    assert ret == 0
    captured = capsys.readouterr()
    state_json = json.loads(captured.out)
    assert state_json["task_id"] == "cli-task-1"
    assert state_json["status"] == "completed"

    # 4. Resume via CLI
    client_res = ScriptedClient()
    ret = cli_main(
        ["--db", db_file, "--task-id", "cli-task-1", "--resume"],
        client=client_res,
    )
    assert ret == 0
    captured = capsys.readouterr()
    assert "Liver panel found." in captured.out
