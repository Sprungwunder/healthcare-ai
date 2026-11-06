"""Anthropic Messages API (Claude) client using only the standard library.

Translates the neutral types from ``lab_agent.model`` to the API's JSON and back.
Errors never include the API key or the conversation, which may contain
sensitive data.

Differences from Chat Completions that this module handles:
- The system prompt is a top-level ``system`` field, not a message.
- Tool calls are ``tool_use`` content blocks whose ``input`` is a JSON object;
  results go back as ``tool_result`` blocks in a ``user`` message, all results
  of one turn in the same message, with a real ``is_error`` flag.
- Claude may return ``thinking`` blocks. They must be sent back unchanged, so
  the raw content of each turn is kept in ``AssistantMessage.provider_data``.
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

# Same convention as the official SDKs: the base URL has no "/v1".
DEFAULT_BASE_URL: Final[str] = "https://api.anthropic.com"
DEFAULT_MODEL: Final[str] = "claude-opus-5-5"
API_VERSION: Final[str] = "2026-10-21"
DEFAULT_MAX_TOKENS: Final[int] = 16000
# Thinking depth and token spend; "low" | "medium" | "high" | "xhigh" | "max".
DEFAULT_EFFORT: Final[str] = "medium"
# With thinking, a single turn can take longer than a Chat Completions call.
DEFAULT_TIMEOUT_SECONDS: Final[float] = 120.0
# If a safety classifier declines a request, the API retries it on a fallback
# model that Anthropic picks, inside the same call.
FALLBACK_BETA: Final[str] = "server-side-fallback-2026-07-01"


class AnthropicMessagesClient:
    """``ModelClient`` implementation for ``POST {base_url}/v1/messages``."""

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        base_url: str = DEFAULT_BASE_URL,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        effort: str | None = DEFAULT_EFFORT,
        server_side_fallback: bool = True,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._api_key = api_key
        self.model = model
        self.base_url = base_url
        self.max_tokens = max_tokens
        self.effort = effort  # None: omit it (for models without effort support)
        self.server_side_fallback = server_side_fallback
        self.timeout = timeout

    @classmethod
    def from_env(cls) -> AnthropicMessagesClient:
        """Build a client from ANTHROPIC_API_KEY, ANTHROPIC_MODEL, ANTHROPIC_BASE_URL.

        Raises:
            ModelError: If ANTHROPIC_API_KEY is not set.
        """
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ModelError("ANTHROPIC_API_KEY is not set.")
        return cls(
            api_key=api_key,
            model=os.environ.get("ANTHROPIC_MODEL", DEFAULT_MODEL),
            base_url=os.environ.get("ANTHROPIC_BASE_URL", DEFAULT_BASE_URL),
        )

    def complete(
        self, messages: Sequence[Message], tools: Sequence[Tool]
    ) -> AssistantMessage:
        body = build_request_body(
            self.model,
            messages,
            tools,
            max_tokens=self.max_tokens,
            effort=self.effort,
            server_side_fallback=self.server_side_fallback,
        )
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": API_VERSION,
            "content-type": "application/json",
        }
        if self.server_side_fallback:
            headers["anthropic-beta"] = FALLBACK_BETA
        request = urllib.request.Request(
            f"{self.base_url.rstrip('/')}/v1/messages",
            data=json.dumps(body).encode(),
            headers=headers,
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
    model: str,
    messages: Sequence[Message],
    tools: Sequence[Tool],
    max_tokens: int = DEFAULT_MAX_TOKENS,
    effort: str | None = DEFAULT_EFFORT,
    server_side_fallback: bool = True,
) -> dict[str, Any]:
    """Build the Messages API request body."""
    system = "\n\n".join(m.content for m in messages if isinstance(m, SystemMessage))
    body: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": _to_anthropic_messages(messages),
    }
    if system:
        body["system"] = system
    if tools:
        body["tools"] = [_to_anthropic_tool(tool) for tool in tools]
    if effort is not None:
        body["output_config"] = {"effort": effort}
    if server_side_fallback:
        body["fallbacks"] = "default"
    return body


def parse_response(payload: Any) -> AssistantMessage:
    """Extract the assistant turn from a Messages API response.

    Raises:
        ModelError: If the model declined, was cut off, or the payload does not
            have the expected shape.
    """
    try:
        stop_reason = payload.get("stop_reason")
        if stop_reason == "refusal":
            details = payload.get("stop_details") or {}
            category = details.get("category") or "unspecified"
            raise ModelError(f"Model declined the request (category: {category}).")
        if stop_reason in ("max_tokens", "model_context_window_exceeded"):
            raise ModelError(f"Model response was cut off ({stop_reason}).")

        blocks = _replayable_blocks(payload["content"])
        texts: list[str] = []
        tool_calls: list[ToolCall] = []
        for block in blocks:
            if block["type"] == "text":
                if not isinstance(block["text"], str):
                    raise TypeError("text must be a string")
                texts.append(block["text"])
            elif block["type"] == "tool_use":
                if not isinstance(block["input"], dict):
                    raise TypeError("tool input must be an object")
                tool_calls.append(
                    ToolCall(
                        id=str(block["id"]),
                        name=str(block["name"]),
                        arguments=json.dumps(block["input"]),
                    )
                )
            # thinking and other blocks are not shown, only replayed
    except (KeyError, TypeError, AttributeError) as exc:
        raise ModelError(f"Unexpected response from model API: {exc!r}") from exc

    content = "".join(texts) or None
    return AssistantMessage(
        content=content, tool_calls=tuple(tool_calls), provider_data=blocks
    )


def _replayable_blocks(content: Any) -> list[dict[str, Any]]:
    """Return the content blocks to act on and send back next turn.

    After a server-side fallback, the API marks the switch with a ``fallback``
    block; only text from before the last marker may be echoed back, and only
    tool calls after it belong to the model that is answering.
    """
    if not isinstance(content, list):
        raise TypeError("content must be a list")
    boundary = max(
        (i for i, block in enumerate(content) if block["type"] == "fallback"),
        default=None,
    )
    if boundary is None:
        return list(content)
    before = [block for block in content[:boundary] if block["type"] == "text"]
    return before + list(content[boundary + 1 :])


def _to_anthropic_tool(tool: Tool) -> dict[str, Any]:
    return {
        "name": tool.name,
        "description": tool.description,
        "input_schema": tool.parameters,
        # Ask the API to make input match the schema exactly. The agent still
        # validates it: model output is untrusted input.
        "strict": True,
    }


def _to_anthropic_messages(messages: Sequence[Message]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for message in messages:
        if isinstance(message, SystemMessage):
            continue  # sent as the top-level "system" field
        if isinstance(message, UserMessage):
            result.append({"role": "user", "content": message.content})
        elif isinstance(message, ToolMessage):
            block: dict[str, Any] = {
                "type": "tool_result",
                "tool_use_id": message.tool_call_id,
                "content": message.content,
            }
            if message.is_error:
                block["is_error"] = True
            # All results for one assistant turn belong in a single user message.
            previous = result[-1] if result else None
            if previous is not None and _is_tool_result_message(previous):
                previous["content"].append(block)
            else:
                result.append({"role": "user", "content": [block]})
        else:
            blocks = _assistant_blocks(message)
            if blocks:
                result.append({"role": "assistant", "content": blocks})
    return result


def _is_tool_result_message(message: dict[str, Any]) -> bool:
    content = message["content"]
    return (
        message["role"] == "user"
        and isinstance(content, list)
        and all(block["type"] == "tool_result" for block in content)
    )


def _assistant_blocks(message: AssistantMessage) -> list[dict[str, Any]]:
    if isinstance(message.provider_data, list):
        return message.provider_data  # this client's own turn: replay unchanged
    blocks: list[dict[str, Any]] = []
    if message.content:
        blocks.append({"type": "text", "text": message.content})
    for call in message.tool_calls:
        blocks.append(
            {
                "type": "tool_use",
                "id": call.id,
                "name": call.name,
                "input": _arguments_object(call.arguments),
            }
        )
    return blocks


def _arguments_object(arguments: str) -> dict[str, Any]:
    try:
        parsed = json.loads(arguments or "{}")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _api_error_message(error: urllib.error.HTTPError) -> str:
    """Return the API's error message, or the HTTP reason if there is none."""
    try:
        return str(json.loads(error.read())["error"]["message"])
    except (ValueError, KeyError, TypeError):
        return str(error.reason)
