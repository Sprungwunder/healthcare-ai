"""Tests for SQLite and InMemory StateStore implementations."""

from pathlib import Path

import pytest

from lab_agent.model import AssistantMessage, SystemMessage, ToolCall, UserMessage
from lab_agent.state import AgentState, TaskStatus
from lab_agent.storage import (
    InMemoryStateStore,
    SQLiteStateStore,
    StateStore,
    StorageError,
)


@pytest.fixture(params=["sqlite", "in_memory"])
def store(request: pytest.FixtureRequest, tmp_path: Path) -> StateStore:
    if request.param == "sqlite":
        db_file = tmp_path / "test_agent.db"
        return SQLiteStateStore(db_file)
    return InMemoryStateStore()


def test_save_and_load_state(store: StateStore) -> None:
    state = AgentState(
        task_id="t-1",
        status=TaskStatus.IN_PROGRESS,
        document_id="LAB-1001",
        extracted_values=[{"analyte": "Hemoglobin", "value": 13.8}],
        completed_steps=["search_document"],
        pending_steps=["extract_values", "evaluate_values", "generate_summary"],
        intermediate_results={"search_results": [{"document_id": "LAB-1001"}]},
    )

    store.save_state(state)
    loaded = store.load_state("t-1")

    assert loaded is not None
    assert loaded.task_id == "t-1"
    assert loaded.status == TaskStatus.IN_PROGRESS
    assert loaded.document_id == "LAB-1001"
    assert loaded.extracted_values == [{"analyte": "Hemoglobin", "value": 13.8}]
    assert loaded.completed_steps == ["search_document"]
    assert loaded.pending_steps == [
        "extract_values",
        "evaluate_values",
        "generate_summary",
    ]


def test_load_non_existent_state_returns_none(store: StateStore) -> None:
    assert store.load_state("non-existent") is None
    assert store.load_checkpoint("non-existent") is None


def test_save_and_load_messages(store: StateStore) -> None:
    messages = [
        SystemMessage("System prompt"),
        UserMessage("Query"),
        AssistantMessage(
            tool_calls=(ToolCall("c1", "search_lab_documents", '{"query": "cbc"}'),)
        ),
    ]

    store.save_messages("t-2", messages)
    loaded = store.load_messages("t-2")

    assert len(loaded) == 3
    assert isinstance(loaded[0], SystemMessage)
    assert isinstance(loaded[1], UserMessage)
    assert isinstance(loaded[2], AssistantMessage)
    assert loaded[2].tool_calls[0].name == "search_lab_documents"


def test_atomic_checkpoint_save_and_load(store: StateStore) -> None:
    state = AgentState(
        task_id="t-3",
        status=TaskStatus.IN_PROGRESS,
        document_id="LAB-1003",
    )
    messages = [SystemMessage("Sys"), UserMessage("HbA1c?")]

    store.save_checkpoint(state, messages)

    checkpoint = store.load_checkpoint("t-3")
    assert checkpoint is not None
    loaded_state, loaded_messages = checkpoint

    assert loaded_state.task_id == "t-3"
    assert loaded_state.document_id == "LAB-1003"
    assert len(loaded_messages) == 2


def test_checkpoint_update_overwrites_cleanly(store: StateStore) -> None:
    state = AgentState(task_id="t-4", status=TaskStatus.IN_PROGRESS)
    messages = [SystemMessage("Sys"), UserMessage("Initial")]
    store.save_checkpoint(state, messages)

    # Update state and messages
    state.mark_step_completed("search_document", result=[{"id": "LAB-1004"}])
    state.document_id = "LAB-1004"
    messages.append(AssistantMessage("Found LAB-1004"))
    store.save_checkpoint(state, messages)

    checkpoint = store.load_checkpoint("t-4")
    assert checkpoint is not None
    loaded_state, loaded_messages = checkpoint

    assert loaded_state.document_id == "LAB-1004"
    assert loaded_state.completed_steps == ["search_document"]
    assert len(loaded_messages) == 3


def test_list_and_delete_tasks(store: StateStore) -> None:
    state1 = AgentState(task_id="t-a", status=TaskStatus.COMPLETED)
    state2 = AgentState(task_id="t-b", status=TaskStatus.FAILED)

    store.save_state(state1)
    store.save_state(state2)

    tasks = store.list_tasks()
    task_ids = [t["task_id"] for t in tasks]
    assert "t-a" in task_ids
    assert "t-b" in task_ids

    deleted = store.delete_task("t-a")
    assert deleted is True
    assert store.load_state("t-a") is None

    deleted_again = store.delete_task("t-a")
    assert deleted_again is False


def test_sqlite_context_manager(tmp_path: Path) -> None:
    db_file = tmp_path / "ctx.db"
    with SQLiteStateStore(db_file) as s:
        s.save_state(AgentState(task_id="ctx-1"))
        assert s.load_state("ctx-1") is not None


def test_sqlite_invalid_db_path() -> None:
    with pytest.raises(StorageError):
        SQLiteStateStore("/invalid_dir/no_permission/sub/db.sqlite")


def test_sqlite_corrupt_data_handling(tmp_path: Path) -> None:
    db_file = tmp_path / "corrupt.db"
    store = SQLiteStateStore(db_file)

    # Insert raw invalid JSON directly
    with store._conn:
        store._conn.execute(
            "INSERT INTO agent_states VALUES "
            "('c-1', 'pending', NULL, 'invalid-json', 'now', 'now')"
        )
        store._conn.execute(
            "INSERT INTO conversation_messages "
            "(task_id, sequence_num, role, message_json) "
            "VALUES ('c-1', 0, 'user', 'invalid-json')"
        )

    with pytest.raises(StorageError, match="Failed to load state"):
        store.load_state("c-1")

    with pytest.raises(StorageError, match="Failed to load messages"):
        store.load_messages("c-1")
