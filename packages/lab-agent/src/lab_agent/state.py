"""Structured agent execution state, lifecycle tracking, and transcript serialization.

Distinguishes conversation history (the transcript sent to the LLM) from
agent execution state (domain variables, lifecycle status, extracted values,
and intermediate step outputs).
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from lab_agent.model import (
    AssistantMessage,
    Message,
    SystemMessage,
    ToolCall,
    ToolMessage,
    UserMessage,
)


class TaskStatus(str, Enum):
    """Lifecycle states for agent tasks."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


DEFAULT_PIPELINE_STEPS: tuple[str, ...] = (
    "search_document",
    "extract_values",
    "evaluate_values",
    "generate_summary",
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class AgentState:
    """Explicit, structured representation of the agent's execution state."""

    task_id: str
    status: TaskStatus | str = TaskStatus.PENDING
    document_id: str | None = None
    extracted_values: list[dict[str, Any]] = field(default_factory=list)
    completed_steps: list[str] = field(default_factory=list)
    pending_steps: list[str] = field(
        default_factory=lambda: list(DEFAULT_PIPELINE_STEPS)
    )
    intermediate_results: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_utc_now_iso)
    updated_at: str = field(default_factory=_utc_now_iso)
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.status, str) and not isinstance(self.status, TaskStatus):
            try:
                self.status = TaskStatus(self.status)
            except ValueError:
                pass

    def mark_step_completed(self, step: str, result: Any = None) -> None:
        """Mark a process step as completed and record its intermediate result."""
        if step in self.pending_steps:
            self.pending_steps = [s for s in self.pending_steps if s != step]
        if step not in self.completed_steps:
            self.completed_steps.append(step)
        if result is not None:
            self.intermediate_results[step] = result
        self.updated_at = _utc_now_iso()

    def update_status(self, status: TaskStatus | str, error: str | None = None) -> None:
        """Update task lifecycle status and optional error explanation."""
        if isinstance(status, str) and not isinstance(status, TaskStatus):
            try:
                status = TaskStatus(status)
            except ValueError:
                pass
        self.status = status
        self.error = error
        self.updated_at = _utc_now_iso()

    def is_step_completed(self, step: str) -> bool:
        """Return True if the specified step is recorded as completed."""
        return step in self.completed_steps

    def to_dict(self) -> dict[str, Any]:
        """Convert state to a JSON-serializable dictionary."""
        data = asdict(self)
        if isinstance(self.status, TaskStatus):
            data["status"] = self.status.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentState:
        """Create an AgentState instance from a dictionary."""
        status_val = data.get("status", TaskStatus.PENDING)
        if isinstance(status_val, str):
            try:
                status_val = TaskStatus(status_val)
            except ValueError:
                pass

        return cls(
            task_id=data["task_id"],
            status=status_val,
            document_id=data.get("document_id"),
            extracted_values=list(data.get("extracted_values", [])),
            completed_steps=list(data.get("completed_steps", [])),
            pending_steps=list(data.get("pending_steps", list(DEFAULT_PIPELINE_STEPS))),
            intermediate_results=dict(data.get("intermediate_results", {})),
            created_at=data.get("created_at", _utc_now_iso()),
            updated_at=data.get("updated_at", _utc_now_iso()),
            error=data.get("error"),
            metadata=dict(data.get("metadata", {})),
        )


def message_to_dict(message: Message) -> dict[str, Any]:
    """Serialize a conversation Message instance to a dictionary."""
    if isinstance(message, SystemMessage):
        return {"role": "system", "content": message.content}
    if isinstance(message, UserMessage):
        return {"role": "user", "content": message.content}
    if isinstance(message, AssistantMessage):
        tool_calls = [
            {"id": call.id, "name": call.name, "arguments": call.arguments}
            for call in message.tool_calls
        ]
        payload: dict[str, Any] = {
            "role": "assistant",
            "content": message.content,
            "tool_calls": tool_calls,
        }
        if message.provider_data is not None:
            payload["provider_data"] = message.provider_data
        return payload
    if isinstance(message, ToolMessage):
        return {
            "role": "tool",
            "tool_call_id": message.tool_call_id,
            "content": message.content,
            "is_error": message.is_error,
        }
    raise TypeError(f"Unsupported message type: {type(message)}")


def message_from_dict(data: dict[str, Any]) -> Message:
    """Deserialize a dictionary to a conversation Message instance."""
    role = data.get("role")
    if role == "system":
        return SystemMessage(content=str(data.get("content", "")))
    if role == "user":
        return UserMessage(content=str(data.get("content", "")))
    if role == "assistant":
        calls_data = data.get("tool_calls", [])
        tool_calls = tuple(
            ToolCall(
                id=c["id"],
                name=c["name"],
                arguments=c.get("arguments", "{}"),
            )
            for c in calls_data
        )
        return AssistantMessage(
            content=data.get("content"),
            tool_calls=tool_calls,
            provider_data=data.get("provider_data"),
        )
    if role == "tool":
        return ToolMessage(
            tool_call_id=str(data.get("tool_call_id", "")),
            content=str(data.get("content", "")),
            is_error=bool(data.get("is_error", False)),
        )
    raise ValueError(f"Unknown message role: {role}")


def messages_to_json(messages: Sequence[Message]) -> str:
    """Serialize a sequence of Messages to a JSON string."""
    return json.dumps([message_to_dict(m) for m in messages])


def messages_from_json(json_str: str) -> list[Message]:
    """Deserialize a JSON string to a list of Messages."""
    data = json.loads(json_str)
    if not isinstance(data, list):
        raise ValueError("Serialized messages must be a JSON array.")
    return [message_from_dict(item) for item in data]
