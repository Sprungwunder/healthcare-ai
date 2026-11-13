"""Integration tests for lab-agent using a mock ModelClient.

Tests the full happy path workflow:
Step 1: LLM requests document search -> search tool is invoked
Step 2: Search returns lab_123 -> results are incorporated into transcript and state
Step 3: LLM requests extraction for lab_123 -> extraction tool is invoked
Step 4: Extraction returns laboratory values -> values are incorporated into state
Step 5: LLM provides final answer -> agent completes execution
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from lab_agent.agent import AgentResult, run_agent
from lab_agent.documents import LabDocument, LabResult
from lab_agent.model import (
    AssistantMessage,
    Message,
    SystemMessage,
    ToolCall,
    ToolMessage,
    UserMessage,
)
from lab_agent.registry import LAB_TOOLS, Tool
from lab_agent.state import TaskStatus
from lab_agent.storage import SQLiteStateStore
from lab_agent.tools import get_document_details, search_lab_documents


class MockModelClient:
    """Mock implementation of ModelClient Protocol for integration tests.

    Records the sequence of conversation messages passed to `complete` and returns
    scripted AssistantMessages.
    """

    def __init__(self, responses: Sequence[AssistantMessage]) -> None:
        self._responses = list(responses)
        self.recorded_calls: list[list[Message]] = []

    def complete(
        self, messages: Sequence[Message], tools: Sequence[Tool]
    ) -> AssistantMessage:
        self.recorded_calls.append(list(messages))
        if not self._responses:
            raise RuntimeError("MockModelClient has no more scripted responses.")
        return self._responses.pop(0)


# Synthetic test document for lab_123
SAMPLE_LAB_123 = LabDocument(
    document_id="lab_123",
    title="General blood test",
    description="Blood panel report lab_123 with glucose, hemoglobin and creatinine.",
    collected_on="2026-05-15",
    patient_ref="SYN-0123",
    results=(
        LabResult(
            analyte="Hemoglobin",
            value=14.5,
            unit="g/dL",
            reference_range="12.0-16.0",
        ),
        LabResult(
            analyte="Glucose",
            value=95.0,
            unit="mg/dL",
            reference_range="70-99",
        ),
        LabResult(
            analyte="Creatinine",
            value=0.9,
            unit="mg/dL",
            reference_range="0.6-1.2",
        ),
    ),
)


def _string_param(name: str, desc: str) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {name: {"type": "string", "description": desc}},
        "required": [name],
        "additionalProperties": False,
    }


def _create_lab_123_tools() -> tuple[Tool, ...]:
    """Create tools operating over synthetic documents including lab_123."""
    docs = (SAMPLE_LAB_123,)
    return (
        Tool(
            name="search_lab_documents",
            description="Search lab documents by keywords in title and description.",
            parameters=_string_param("query", "Search terms, e.g. 'blood lab_123'"),
            function=lambda query: search_lab_documents(query, documents=docs),
        ),
        Tool(
            name="get_document_details",
            description="Get full document details and lab results by document ID.",
            parameters=_string_param("document_id", "Document ID, e.g. 'lab_123'"),
            function=lambda document_id: get_document_details(
                document_id, documents=docs
            ),
        ),
    )


def test_integration_happy_path_lab_123() -> None:
    """Test the complete 5-step happy path with mock ModelClient:

    Step 1: LLM requests document search -> tool called
    Step 2: Search returns lab_123 -> result adopted
    Step 3: LLM requests extraction for lab_123 -> extraction called
    Step 4: Extraction returns lab values -> values adopted
    Step 5: LLM provides answer -> agent completes workflow
    """
    tools = _create_lab_123_tools()

    # Define the scripted turns representing the LLM in each iteration
    mock_client = MockModelClient(
        [
            # Step 1: LLM requests document search
            AssistantMessage(
                tool_calls=(
                    ToolCall(
                        id="call_search_1",
                        name="search_lab_documents",
                        arguments='{"query": "blood lab_123"}',
                    ),
                )
            ),
            # Step 3: After receiving search results (Step 2), LLM requests extraction
            AssistantMessage(
                tool_calls=(
                    ToolCall(
                        id="call_extract_1",
                        name="get_document_details",
                        arguments='{"document_id": "lab_123"}',
                    ),
                )
            ),
            # Step 5: After receiving extracted values (Step 4),
            # LLM returns final answer
            AssistantMessage(
                content=(
                    "Lab report lab_123 contains the following values:\n"
                    "- Hemoglobin: 14.5 g/dL (normal: 12.0-16.0)\n"
                    "- Glucose: 95.0 mg/dL (normal: 70-99)\n"
                    "- Creatinine: 0.9 mg/dL (normal: 0.6-1.2)"
                )
            ),
        ]
    )

    result: AgentResult = run_agent(
        request="Find document lab_123 and extract its laboratory measurements.",
        client=mock_client,
        tools=tools,
    )

    # --- Verification of Step 1 & Step 2: Document search tool call & result ---
    # First model call should contain system prompt + user request
    first_turn_messages = mock_client.recorded_calls[0]
    assert isinstance(first_turn_messages[0], SystemMessage)
    assert isinstance(first_turn_messages[1], UserMessage)
    assert "lab_123" in first_turn_messages[1].content

    # Second model call should contain the search tool call and its ToolMessage result
    second_turn_messages = mock_client.recorded_calls[1]
    assert len(second_turn_messages) == 4
    search_assistant_msg = second_turn_messages[2]
    assert isinstance(search_assistant_msg, AssistantMessage)
    assert len(search_assistant_msg.tool_calls) == 1
    assert search_assistant_msg.tool_calls[0].name == "search_lab_documents"

    search_tool_msg = second_turn_messages[3]
    assert isinstance(search_tool_msg, ToolMessage)
    assert search_tool_msg.tool_call_id == "call_search_1"
    assert not search_tool_msg.is_error
    search_data = json.loads(search_tool_msg.content)
    assert isinstance(search_data, list)
    assert len(search_data) == 1
    assert search_data[0]["document_id"] == "lab_123"

    # --- Verification of Step 3 & Step 4: Extraction tool call & lab values ---
    # Third model call should contain the extraction tool call & ToolMessage result
    third_turn_messages = mock_client.recorded_calls[2]
    assert len(third_turn_messages) == 6
    extract_assistant_msg = third_turn_messages[4]
    assert isinstance(extract_assistant_msg, AssistantMessage)
    assert len(extract_assistant_msg.tool_calls) == 1
    assert extract_assistant_msg.tool_calls[0].name == "get_document_details"
    assert json.loads(extract_assistant_msg.tool_calls[0].arguments) == {
        "document_id": "lab_123"
    }

    extract_tool_msg = third_turn_messages[5]
    assert isinstance(extract_tool_msg, ToolMessage)
    assert extract_tool_msg.tool_call_id == "call_extract_1"
    assert not extract_tool_msg.is_error
    extract_data = json.loads(extract_tool_msg.content)
    assert extract_data["document_id"] == "lab_123"
    assert len(extract_data["results"]) == 3
    assert extract_data["results"][0] == {
        "analyte": "Hemoglobin",
        "value": 14.5,
        "unit": "g/dL",
        "reference_range": "12.0-16.0",
    }

    # --- Verification of Step 5: Final LLM answer & completion ---
    assert result.iterations == 3
    assert "Lab report lab_123 contains the following values:" in result.answer
    assert "Hemoglobin: 14.5 g/dL" in result.answer
    assert "Glucose: 95.0 mg/dL" in result.answer

    # State verification
    assert result.state is not None
    assert result.state.status == TaskStatus.COMPLETED
    assert result.state.document_id == "lab_123"
    assert len(result.state.extracted_values) == 3
    assert result.state.is_step_completed("search_document")
    assert result.state.is_step_completed("extract_values")
    assert result.state.is_step_completed("generate_summary")
    assert result.state.intermediate_results["search_results"] == search_data
    assert result.state.intermediate_results["document_details"] == extract_data


def test_integration_happy_path_with_state_persistence(tmp_path: Path) -> None:
    """Test happy path integration with SQLite state store persistence."""
    tools = _create_lab_123_tools()
    db_file = tmp_path / "integration_test.db"
    store = SQLiteStateStore(db_file)

    mock_client = MockModelClient(
        [
            AssistantMessage(
                tool_calls=(
                    ToolCall(
                        id="c1",
                        name="search_lab_documents",
                        arguments='{"query": "blood"}',
                    ),
                )
            ),
            AssistantMessage(
                tool_calls=(
                    ToolCall(
                        id="c2",
                        name="get_document_details",
                        arguments='{"document_id": "lab_123"}',
                    ),
                )
            ),
            AssistantMessage(content="Extracted values for lab_123 successfully."),
        ]
    )

    task_id = "integration-task-happy-path"
    result = run_agent(
        request="Analyze lab_123.",
        client=mock_client,
        tools=tools,
        task_id=task_id,
        store=store,
    )

    assert result.answer == "Extracted values for lab_123 successfully."
    assert result.state is not None
    assert result.state.status == TaskStatus.COMPLETED

    # Verify persisted state from SQLite store
    loaded_state = store.load_state(task_id)
    assert loaded_state is not None
    assert loaded_state.status == TaskStatus.COMPLETED
    assert loaded_state.document_id == "lab_123"
    assert len(loaded_state.extracted_values) == 3
    assert "search_document" in loaded_state.completed_steps
    assert "extract_values" in loaded_state.completed_steps
    assert "generate_summary" in loaded_state.completed_steps


def test_integration_happy_path_default_lab_tools() -> None:
    """Test happy path with default LAB_TOOLS using synthetic LAB-1002."""
    mock_client = MockModelClient(
        [
            AssistantMessage(
                tool_calls=(
                    ToolCall(
                        id="c1",
                        name="search_lab_documents",
                        arguments='{"query": "lipid"}',
                    ),
                )
            ),
            AssistantMessage(
                tool_calls=(
                    ToolCall(
                        id="c2",
                        name="get_document_details",
                        arguments='{"document_id": "LAB-1002"}',
                    ),
                )
            ),
            AssistantMessage(
                content="Lipid panel summary: Total cholesterol 5.6 mmol/L."
            ),
        ]
    )

    result = run_agent(
        request="Find my lipid panel and extract its values.",
        client=mock_client,
        tools=LAB_TOOLS,
    )

    assert result.iterations == 3
    assert "Lipid panel summary" in result.answer
    assert result.state is not None
    assert result.state.status == TaskStatus.COMPLETED
    assert result.state.document_id == "LAB-1002"
    assert len(result.state.extracted_values) == 4
    assert result.state.is_step_completed("search_document")
    assert result.state.is_step_completed("extract_values")
    assert result.state.is_step_completed("generate_summary")
