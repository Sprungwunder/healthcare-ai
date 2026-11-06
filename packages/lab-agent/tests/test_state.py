"""Unit tests for AgentState and conversation message serialization."""

import json

import pytest

from lab_agent.model import (
    AssistantMessage,
    SystemMessage,
    ToolCall,
    ToolMessage,
    UserMessage,
)
from lab_agent.state import (
    AgentState,
    TaskStatus,
    message_from_dict,
    message_to_dict,
    messages_from_json,
    messages_to_json,
)


def test_agent_state_defaults() -> None:
    state = AgentState(task_id="task-123")
    assert state.task_id == "task-123"
    assert state.status == TaskStatus.PENDING
    assert state.document_id is None
    assert state.extracted_values == []
    assert state.completed_steps == []
    assert "search_document" in state.pending_steps
    assert "extract_values" in state.pending_steps
    assert "evaluate_values" in state.pending_steps
    assert "generate_summary" in state.pending_steps
    assert state.intermediate_results == {}
    assert state.created_at is not None
    assert state.updated_at is not None
    assert state.error is None
    assert state.metadata == {}


def test_agent_state_step_transitions() -> None:
    state = AgentState(task_id="task-123", status=TaskStatus.IN_PROGRESS)

    state.mark_step_completed("search_document", result=[{"doc": "LAB-1"}])
    assert state.is_step_completed("search_document")
    assert "search_document" not in state.pending_steps
    assert "search_document" in state.completed_steps
    assert state.intermediate_results["search_document"] == [{"doc": "LAB-1"}]

    state.mark_step_completed("extract_values", result={"results": [1, 2]})
    assert state.is_step_completed("extract_values")
    assert "extract_values" not in state.pending_steps
    assert state.completed_steps == ["search_document", "extract_values"]

    # Marking the same step completed again is idempotent
    state.mark_step_completed("extract_values")
    assert state.completed_steps == ["search_document", "extract_values"]


def test_agent_state_status_update() -> None:
    state = AgentState(task_id="task-123")
    state.update_status(TaskStatus.FAILED, error="Connection timeout")
    assert state.status == TaskStatus.FAILED
    assert state.error == "Connection timeout"

    state.update_status("completed")
    assert state.status == TaskStatus.COMPLETED


def test_agent_state_serialization_roundtrip() -> None:
    state = AgentState(
        task_id="task-456",
        status=TaskStatus.IN_PROGRESS,
        document_id="LAB-1002",
        extracted_values=[{"analyte": "TSH", "value": 5.9}],
        completed_steps=["search_document", "extract_values"],
        pending_steps=["evaluate_values", "generate_summary"],
        intermediate_results={"search_document": [{"document_id": "LAB-1002"}]},
        error=None,
        metadata={"user": "tester"},
    )

    data = state.to_dict()
    assert isinstance(data, dict)
    assert data["status"] == "in_progress"
    assert data["task_id"] == "task-456"

    restored = AgentState.from_dict(data)
    assert restored.task_id == state.task_id
    assert restored.status == TaskStatus.IN_PROGRESS
    assert restored.document_id == "LAB-1002"
    assert restored.extracted_values == [{"analyte": "TSH", "value": 5.9}]
    assert restored.completed_steps == ["search_document", "extract_values"]
    assert restored.pending_steps == ["evaluate_values", "generate_summary"]
    assert restored.intermediate_results == state.intermediate_results
    assert restored.metadata == {"user": "tester"}


def test_message_serialization_all_types() -> None:
    messages = [
        SystemMessage("System prompt"),
        UserMessage("User question"),
        AssistantMessage(
            content="Thinking...",
            tool_calls=(
                ToolCall(
                    id="c1", name="search_lab_documents", arguments='{"query": "TSH"}'
                ),
            ),
            provider_data={"thinking": "internal"},
        ),
        ToolMessage(
            tool_call_id="c1",
            content=json.dumps([{"document_id": "LAB-1004"}]),
            is_error=False,
        ),
        ToolMessage(
            tool_call_id="c2",
            content=json.dumps({"error": "Not found"}),
            is_error=True,
        ),
        AssistantMessage(content="Final response text."),
    ]

    json_str = messages_to_json(messages)
    assert isinstance(json_str, str)

    restored = messages_from_json(json_str)
    assert len(restored) == len(messages)

    assert isinstance(restored[0], SystemMessage)
    assert restored[0].content == "System prompt"

    assert isinstance(restored[1], UserMessage)
    assert restored[1].content == "User question"

    assert isinstance(restored[2], AssistantMessage)
    assert restored[2].content == "Thinking..."
    assert len(restored[2].tool_calls) == 1
    assert restored[2].tool_calls[0].id == "c1"
    assert restored[2].tool_calls[0].name == "search_lab_documents"
    assert restored[2].tool_calls[0].arguments == '{"query": "TSH"}'
    assert restored[2].provider_data == {"thinking": "internal"}

    assert isinstance(restored[3], ToolMessage)
    assert restored[3].tool_call_id == "c1"
    assert not restored[3].is_error

    assert isinstance(restored[4], ToolMessage)
    assert restored[4].tool_call_id == "c2"
    assert restored[4].is_error

    assert isinstance(restored[5], AssistantMessage)
    assert restored[5].content == "Final response text."
    assert restored[5].tool_calls == ()


def test_agent_state_unknown_status_fallback() -> None:
    state = AgentState(task_id="t-unknown", status="custom_unknown_status")
    assert state.status == "custom_unknown_status"

    state.update_status("another_unknown")
    assert state.status == "another_unknown"

    restored = AgentState.from_dict({"task_id": "t-1", "status": "unknown_val"})
    assert restored.status == "unknown_val"


def test_message_serialization_errors() -> None:
    with pytest.raises(TypeError, match="Unsupported message type"):
        message_to_dict("not a message")  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="Unknown message role"):
        message_from_dict({"role": "invalid_role", "content": "text"})

    with pytest.raises(ValueError, match="JSON array"):
        messages_from_json('{"key": "value"}')
