"""State and conversation persistence using standard library SQLite.

Provides a storage abstraction (``StateStore``) and concrete implementations
for SQLite and in-memory storage, decoupling durability from agent logic.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol

from lab_agent.model import Message
from lab_agent.state import (
    AgentState,
    message_from_dict,
    message_to_dict,
)


class StorageError(Exception):
    """Raised when a storage operation fails."""


class StateStore(Protocol):
    """Protocol for persisting and loading agent states and conversation histories."""

    def save_state(self, state: AgentState) -> None:
        """Persist or update the given agent state."""
        ...

    def load_state(self, task_id: str) -> AgentState | None:
        """Load an agent state by task ID, or return None if not found."""
        ...

    def save_messages(self, task_id: str, messages: Sequence[Message]) -> None:
        """Persist the conversation messages for a task."""
        ...

    def load_messages(self, task_id: str) -> list[Message]:
        """Load all conversation messages for a task in sequential order."""
        ...

    def save_checkpoint(self, state: AgentState, messages: Sequence[Message]) -> None:
        """Atomically persist both state and conversation transcript."""
        ...

    def load_checkpoint(self, task_id: str) -> tuple[AgentState, list[Message]] | None:
        """Load both state and messages as a consistent checkpoint."""
        ...

    def list_tasks(self) -> list[dict[str, Any]]:
        """List summary records of all persisted tasks."""
        ...

    def delete_task(self, task_id: str) -> bool:
        """Delete a task and its conversation history. Return True if deleted."""
        ...

    def close(self) -> None:
        """Close any open storage resources."""
        ...


class SQLiteStateStore:
    """SQLite-backed state store using the standard library sqlite3."""

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self.db_path = str(db_path)
        try:
            self._conn = sqlite3.connect(self.db_path)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA foreign_keys = ON;")
            self._init_tables()
        except sqlite3.Error as exc:
            raise StorageError(
                f"Failed to initialize SQLite database '{self.db_path}': {exc}"
            ) from exc

    def _init_tables(self) -> None:
        with self._conn:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_states (
                    task_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    document_id TEXT,
                    state_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS conversation_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    sequence_num INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    message_json TEXT NOT NULL,
                    FOREIGN KEY (task_id)
                        REFERENCES agent_states(task_id)
                        ON DELETE CASCADE
                );
                """
            )
            self._conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_messages_task_seq
                ON conversation_messages(task_id, sequence_num);
                """
            )

    def save_state(self, state: AgentState) -> None:
        try:
            state_json = json.dumps(state.to_dict())
            with self._conn:
                self._conn.execute(
                    """
                    INSERT INTO agent_states (
                        task_id, status, document_id, state_json, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(task_id) DO UPDATE SET
                        status = excluded.status,
                        document_id = excluded.document_id,
                        state_json = excluded.state_json,
                        updated_at = excluded.updated_at;
                    """,
                    (
                        state.task_id,
                        str(
                            state.status.value
                            if hasattr(state.status, "value")
                            else state.status
                        ),
                        state.document_id,
                        state_json,
                        state.created_at,
                        state.updated_at,
                    ),
                )
        except sqlite3.Error as exc:
            raise StorageError(
                f"Failed to save state for task '{state.task_id}': {exc}"
            ) from exc

    def load_state(self, task_id: str) -> AgentState | None:
        try:
            cur = self._conn.execute(
                "SELECT state_json FROM agent_states WHERE task_id = ?;", (task_id,)
            )
            row = cur.fetchone()
            if row is None:
                return None
            data = json.loads(row["state_json"])
            return AgentState.from_dict(data)
        except (sqlite3.Error, json.JSONDecodeError) as exc:
            raise StorageError(
                f"Failed to load state for task '{task_id}': {exc}"
            ) from exc

    def save_messages(self, task_id: str, messages: Sequence[Message]) -> None:
        try:
            with self._conn:
                self._conn.execute(
                    """
                    INSERT INTO agent_states (
                        task_id, status, state_json, created_at, updated_at
                    )
                    VALUES (?, 'pending', '{}', datetime('now'), datetime('now'))
                    ON CONFLICT(task_id) DO NOTHING;
                    """,
                    (task_id,),
                )
                self._conn.execute(
                    "DELETE FROM conversation_messages WHERE task_id = ?;", (task_id,)
                )
                for seq, msg in enumerate(messages):
                    msg_dict = message_to_dict(msg)
                    self._conn.execute(
                        """
                        INSERT INTO conversation_messages (
                            task_id, sequence_num, role, message_json
                        )
                        VALUES (?, ?, ?, ?);
                        """,
                        (task_id, seq, msg_dict["role"], json.dumps(msg_dict)),
                    )
        except (sqlite3.Error, TypeError) as exc:
            raise StorageError(
                f"Failed to save messages for task '{task_id}': {exc}"
            ) from exc

    def load_messages(self, task_id: str) -> list[Message]:
        try:
            cur = self._conn.execute(
                """
                SELECT message_json FROM conversation_messages
                WHERE task_id = ?
                ORDER BY sequence_num ASC;
                """,
                (task_id,),
            )
            rows = cur.fetchall()
            return [message_from_dict(json.loads(row["message_json"])) for row in rows]
        except (sqlite3.Error, json.JSONDecodeError, ValueError) as exc:
            raise StorageError(
                f"Failed to load messages for task '{task_id}': {exc}"
            ) from exc

    def save_checkpoint(self, state: AgentState, messages: Sequence[Message]) -> None:
        try:
            state_json = json.dumps(state.to_dict())
            with self._conn:
                self._conn.execute(
                    """
                    INSERT INTO agent_states (
                        task_id, status, document_id, state_json, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(task_id) DO UPDATE SET
                        status = excluded.status,
                        document_id = excluded.document_id,
                        state_json = excluded.state_json,
                        updated_at = excluded.updated_at;
                    """,
                    (
                        state.task_id,
                        str(
                            state.status.value
                            if hasattr(state.status, "value")
                            else state.status
                        ),
                        state.document_id,
                        state_json,
                        state.created_at,
                        state.updated_at,
                    ),
                )
                self._conn.execute(
                    "DELETE FROM conversation_messages WHERE task_id = ?;",
                    (state.task_id,),
                )
                for seq, msg in enumerate(messages):
                    msg_dict = message_to_dict(msg)
                    self._conn.execute(
                        """
                        INSERT INTO conversation_messages (
                            task_id, sequence_num, role, message_json
                        )
                        VALUES (?, ?, ?, ?);
                        """,
                        (state.task_id, seq, msg_dict["role"], json.dumps(msg_dict)),
                    )
        except (sqlite3.Error, TypeError) as exc:
            raise StorageError(
                f"Failed to save checkpoint for task '{state.task_id}': {exc}"
            ) from exc

    def load_checkpoint(self, task_id: str) -> tuple[AgentState, list[Message]] | None:
        state = self.load_state(task_id)
        if state is None:
            return None
        messages = self.load_messages(task_id)
        return state, messages

    def list_tasks(self) -> list[dict[str, Any]]:
        try:
            cur = self._conn.execute(
                """
                SELECT task_id, status, document_id, created_at, updated_at
                FROM agent_states
                ORDER BY updated_at DESC;
                """
            )
            return [dict(row) for row in cur.fetchall()]
        except sqlite3.Error as exc:
            raise StorageError(f"Failed to list tasks: {exc}") from exc

    def delete_task(self, task_id: str) -> bool:
        try:
            with self._conn:
                self._conn.execute(
                    "DELETE FROM conversation_messages WHERE task_id = ?;", (task_id,)
                )
                cur = self._conn.execute(
                    "DELETE FROM agent_states WHERE task_id = ?;", (task_id,)
                )
                return cur.rowcount > 0
        except sqlite3.Error as exc:
            raise StorageError(f"Failed to delete task '{task_id}': {exc}") from exc

    def close(self) -> None:
        try:
            self._conn.close()
        except sqlite3.Error:
            pass

    def __enter__(self) -> SQLiteStateStore:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()


class InMemoryStateStore:
    """In-memory state store for fast tests and ephemeral sessions."""

    def __init__(self) -> None:
        self._states: dict[str, AgentState] = {}
        self._messages: dict[str, list[Message]] = {}

    def save_state(self, state: AgentState) -> None:
        # Clone to prevent in-place mutation side effects
        self._states[state.task_id] = AgentState.from_dict(state.to_dict())

    def load_state(self, task_id: str) -> AgentState | None:
        state = self._states.get(task_id)
        if state is None:
            return None
        return AgentState.from_dict(state.to_dict())

    def save_messages(self, task_id: str, messages: Sequence[Message]) -> None:
        self._messages[task_id] = list(messages)

    def load_messages(self, task_id: str) -> list[Message]:
        return list(self._messages.get(task_id, []))

    def save_checkpoint(self, state: AgentState, messages: Sequence[Message]) -> None:
        self.save_state(state)
        self.save_messages(state.task_id, messages)

    def load_checkpoint(self, task_id: str) -> tuple[AgentState, list[Message]] | None:
        state = self.load_state(task_id)
        if state is None:
            return None
        messages = self.load_messages(task_id)
        return state, messages

    def list_tasks(self) -> list[dict[str, Any]]:
        return [
            {
                "task_id": state.task_id,
                "status": state.status.value
                if hasattr(state.status, "value")
                else str(state.status),
                "document_id": state.document_id,
                "created_at": state.created_at,
                "updated_at": state.updated_at,
            }
            for state in sorted(
                self._states.values(), key=lambda s: s.updated_at, reverse=True
            )
        ]

    def delete_task(self, task_id: str) -> bool:
        existed = task_id in self._states or task_id in self._messages
        self._states.pop(task_id, None)
        self._messages.pop(task_id, None)
        return existed

    def close(self) -> None:
        self._states.clear()
        self._messages.clear()

    def __enter__(self) -> InMemoryStateStore:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()
