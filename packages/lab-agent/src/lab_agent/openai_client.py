"""OpenAI Chat Completions client using only the standard library.

Translates the neutral types from ``lab_agent.model`` to the API's JSON and back.
Works with any OpenAI-compatible server via ``base_url``. Errors never include
the API key or the conversation, which may contain sensitive data.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Sequence
from typing import Any, Final

from lab_agent.model import (
    AssistantMessage,
    Message,
    ModelError,
    SystemMessage,
    ToolCall,
    ToolMessage,
    UserMessage,
)
from lab_agent.registry import Tool

DEFAULT_BASE_URL: Final[str] = "https://api.openai.com/v1"
# Any tool-calling chat model works; override with OPENAI_MODEL.
DEFAULT_MODEL: Final[str] = "gpt-4.1-mini"
DEFAULT_TIMEOUT_SECONDS: Final[float] = 30.0


class OpenAIChatClient:
    """``ModelClient`` implementation for ``POST {base_url}/chat/completions``."""

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._api_key = api_key
        self.model = model
        self.base_url = base_url
        self.timeout = timeout

    @classmethod
    def from_env(cls) -> OpenAIChatClient:
        """Build a client from OPENAI_API_KEY, OPENAI_MODEL and OPENAI_BASE_URL.

        Raises:
            ModelError: If OPENAI_API_KEY is not set.
        """
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ModelError("OPENAI_API_KEY is not set.")
        return cls(
            api_key=api_key,
            model=os.environ.get("OPENAI_MODEL", DEFAULT_MODEL),
            base_url=os.environ.get("OPENAI_BASE_URL", DEFAULT_BASE_URL),
        )

    def complete(
        self, messages: Sequence[Message], tools: Sequence[Tool]
    ) -> AssistantMessage:
        body = build_request_body(self.model, messages, tools)
        request = urllib.request.Request(
            f"{self.base_url.rstrip('/')}/chat/completions",
            data=json.dumps(body).encode(),
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            raise ModelError(f"HTTP {exc.code}: {_api_error_message(exc)}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise ModelError(f"Model API request failed: {exc}") from exc

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ModelError("Model API response is not JSON.") from exc
        return parse_response(payload)


def build_request_body(
    model: str, messages: Sequence[Message], tools: Sequence[Tool]
) -> dict[str, Any]:
    """Build the Chat Completions request body."""
    body: dict[str, Any] = {
        "model": model,
        "messages": [_to_openai_message(message) for message in messages],
    }
    if tools:  # the API rejects an empty tools list
        body["tools"] = [_to_openai_tool(tool) for tool in tools]
    return body


def parse_response(payload: Any) -> AssistantMessage:
    """Extract the assistant turn from a Chat Completions response.

    Raises:
        ModelError: If the payload does not have the expected shape.
    """
    try:
        message = payload["choices"][0]["message"]
        content = message.get("content")
        if content is not None and not isinstance(content, str):
            raise TypeError("content must be a string")
        tool_calls = tuple(
            ToolCall(
                id=call["id"],
                name=call["function"]["name"],
                arguments=call["function"]["arguments"],
            )
            for call in message.get("tool_calls") or ()
        )
    except (KeyError, IndexError, TypeError, AttributeError) as exc:
        raise ModelError(f"Unexpected response from model API: {exc!r}") from exc
    return AssistantMessage(content=content, tool_calls=tool_calls)


def _to_openai_tool(tool: Tool) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
            # Ask the API to make arguments match the schema exactly. The agent
            # still validates them: compatible servers may ignore this flag.
            "strict": True,
        },
    }


def _to_openai_message(message: Message) -> dict[str, Any]:
    if isinstance(message, SystemMessage):
        return {"role": "system", "content": message.content}
    if isinstance(message, UserMessage):
        return {"role": "user", "content": message.content}
    if isinstance(message, ToolMessage):
        # The API has no error flag for tool results; errors are in the JSON.
        return {
            "role": "tool",
            "tool_call_id": message.tool_call_id,
            "content": message.content,
        }
    result: dict[str, Any] = {"role": "assistant", "content": message.content}
    if message.tool_calls:
        result["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": call.arguments},
            }
            for call in message.tool_calls
        ]
    return result


def _api_error_message(error: urllib.error.HTTPError) -> str:
    """Return the API's error message, or the HTTP reason if there is none."""
    try:
        return str(json.loads(error.read())["error"]["message"])
    except (ValueError, KeyError, TypeError):
        return str(error.reason)
