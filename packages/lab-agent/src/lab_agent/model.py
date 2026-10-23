"""Provider-neutral conversation types and the model client interface.

The agent loop only talks to ``ModelClient``. A concrete client (see
``openai_client``) translates these types to and from its API's JSON, so the
loop and the tools never depend on a specific provider.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, Union

from lab_agent.registry import Tool


class ModelError(Exception):
    """Raised when the model API fails or returns an unusable response."""


@dataclass(frozen=True)
class ToolCall:
    """A tool invocation requested by the model.

    ``arguments`` is the raw JSON text the model generated. It is parsed and
    validated by the agent, because it may be malformed.
    """

    id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class SystemMessage:
    content: str


@dataclass(frozen=True)
class UserMessage:
    content: str


@dataclass(frozen=True)
class AssistantMessage:
    """A model turn: a final answer (``content``) or tool calls, or both."""

    content: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()


@dataclass(frozen=True)
class ToolMessage:
    """The JSON result (or error) of one tool call, sent back to the model."""

    tool_call_id: str
    content: str
    is_error: bool = False


# Union instead of `|`: this alias is evaluated at runtime on Python 3.10.
Message = Union[SystemMessage, UserMessage, AssistantMessage, ToolMessage]


class ModelClient(Protocol):
    """Anything that can produce the next assistant turn for a conversation."""

    def complete(
        self, messages: Sequence[Message], tools: Sequence[Tool]
    ) -> AssistantMessage:
        """Return the model's next turn.

        Raises:
            ModelError: If the API call fails or the response cannot be parsed.
        """
        ...
