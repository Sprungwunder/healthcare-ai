"""Tests for the Anthropic Messages API client, with HTTP patched out."""

import io
import json
import urllib.error
import urllib.request
from typing import Any

import pytest

from lab_agent import anthropic_client
from lab_agent.anthropic_client import (
    AnthropicMessagesClient,
    build_request_body,
    parse_response,
)
from lab_agent.model import (
    AssistantMessage,
    Message,
    ModelError,
    SystemMessage,
    ToolCall,
    ToolMessage,
    UserMessage,
)
from lab_agent.registry import LAB_TOOLS

THINKING_BLOCK: dict[str, Any] = {"type": "thinking", "thinking": "", "signature": "s"}

TOOL_USE_RESPONSE: dict[str, Any] = {
    "type": "message",
    "role": "assistant",
    "stop_reason": "tool_use",
    "content": [
        THINKING_BLOCK,
        {"type": "text", "text": "Searching."},
        {
            "type": "tool_use",
            "id": "toolu_1",
            "name": "search_lab_documents",
            "input": {"query": "lipid"},
        },
        {
            "type": "tool_use",
            "id": "toolu_2",
            "name": "get_document_details",
            "input": {"document_id": "LAB-1002"},
        },
    ],
}

ANSWER_RESPONSE: dict[str, Any] = {
    "type": "message",
    "role": "assistant",
    "stop_reason": "end_turn",
    "content": [{"type": "text", "text": "LDL is 3.7 mmol/L (LAB-1002)."}],
}


class FakeResponse(io.BytesIO):
    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def test_request_body_translates_tools_and_options() -> None:
    body = build_request_body("test-model", [UserMessage("Hi")], LAB_TOOLS[:1])

    assert body["model"] == "test-model"
    assert body["max_tokens"] == anthropic_client.DEFAULT_MAX_TOKENS
    assert body["output_config"] == {"effort": anthropic_client.DEFAULT_EFFORT}
    assert body["fallbacks"] == "default"
    assert body["tools"] == [
        {
            "name": "search_lab_documents",
            "description": LAB_TOOLS[0].description,
            "input_schema": LAB_TOOLS[0].parameters,
            "strict": True,
        }
    ]


def test_request_body_omits_optional_fields() -> None:
    body = build_request_body(
        "m", [UserMessage("Hi")], [], effort=None, server_side_fallback=False
    )

    assert set(body) == {"model", "max_tokens", "messages"}


def test_request_body_translates_every_message_type() -> None:
    messages: list[Message] = [
        SystemMessage("Be careful."),
        UserMessage("Lipids?"),
        AssistantMessage(
            content="Looking.",
            tool_calls=(
                ToolCall("t1", "search_lab_documents", '{"query": "lipid"}'),
                ToolCall("t2", "get_document_details", "not json"),
            ),
        ),
        ToolMessage("t1", "[]"),
        ToolMessage("t2", '{"error": "x"}', is_error=True),
        AssistantMessage(content="Done."),
    ]

    body = build_request_body("m", messages, [])

    assert body["system"] == "Be careful."
    assert body["messages"] == [
        {"role": "user", "content": "Lipids?"},
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "Looking."},
                {
                    "type": "tool_use",
                    "id": "t1",
                    "name": "search_lab_documents",
                    "input": {"query": "lipid"},
                },
                {
                    "type": "tool_use",
                    "id": "t2",
                    "name": "get_document_details",
                    "input": {},
                },
            ],
        },
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "t1", "content": "[]"},
                {
                    "type": "tool_result",
                    "tool_use_id": "t2",
                    "content": '{"error": "x"}',
                    "is_error": True,
                },
            ],
        },
        {"role": "assistant", "content": [{"type": "text", "text": "Done."}]},
    ]
    assert "tools" not in body


def test_parse_tool_use_response() -> None:
    reply = parse_response(TOOL_USE_RESPONSE)

    assert reply == AssistantMessage(
        content="Searching.",
        tool_calls=(
            ToolCall("toolu_1", "search_lab_documents", '{"query": "lipid"}'),
            ToolCall("toolu_2", "get_document_details", '{"document_id": "LAB-1002"}'),
        ),
    )


def test_own_turn_is_replayed_unchanged_including_thinking() -> None:
    reply = parse_response(TOOL_USE_RESPONSE)

    body = build_request_body("m", [UserMessage("Q"), reply], [])

    assert body["messages"][1] == {
        "role": "assistant",
        "content": TOOL_USE_RESPONSE["content"],
    }


def test_parse_answer_response() -> None:
    reply = parse_response(ANSWER_RESPONSE)

    assert reply == AssistantMessage("LDL is 3.7 mmol/L (LAB-1002).")


def test_fallback_drops_declined_blocks_except_text() -> None:
    payload = {
        "stop_reason": "end_turn",
        "content": [
            {"type": "text", "text": "Partial. "},
            THINKING_BLOCK,
            {"type": "tool_use", "id": "old", "name": "x", "input": {}},
            {"type": "fallback", "from": {"model": "a"}, "to": {"model": "b"}},
            {"type": "text", "text": "Answer."},
        ],
    }

    reply = parse_response(payload)

    assert reply.content == "Partial. Answer."
    assert reply.tool_calls == ()
    assert reply.provider_data == [
        {"type": "text", "text": "Partial. "},
        {"type": "text", "text": "Answer."},
    ]


def test_refusal_becomes_model_error() -> None:
    payload = {
        "stop_reason": "refusal",
        "stop_details": {"type": "refusal", "category": "bio"},
        "content": [],
    }

    with pytest.raises(ModelError, match="declined.*bio"):
        parse_response(payload)


def test_truncated_response_becomes_model_error() -> None:
    with pytest.raises(ModelError, match="cut off"):
        parse_response({"stop_reason": "max_tokens", "content": []})


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"content": "text"},
        {"content": [{"type": "tool_use", "id": "x"}]},
        {"content": [{"type": "tool_use", "id": "x", "name": "n", "input": "{}"}]},
        {"content": [{"type": "text", "text": 5}]},
        [],
    ],
)
def test_parse_malformed_response_raises_model_error(body: Any) -> None:
    with pytest.raises(ModelError, match="Unexpected response"):
        parse_response(body)


def test_complete_posts_to_messages(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[urllib.request.Request] = []

    def fake_urlopen(request: urllib.request.Request, timeout: float) -> FakeResponse:
        sent.append(request)
        return FakeResponse(json.dumps(ANSWER_RESPONSE).encode())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    client = AnthropicMessagesClient(api_key="sk-test", model="m", base_url="http://x/")

    reply = client.complete([UserMessage("Hi")], LAB_TOOLS)

    assert reply.content == "LDL is 3.7 mmol/L (LAB-1002)."
    (request,) = sent
    assert request.full_url == "http://x/v1/messages"
    # urllib stores header names capitalized
    assert request.get_header("X-api-key") == "sk-test"
    assert request.get_header("Anthropic-version") == anthropic_client.API_VERSION
    assert request.get_header("Anthropic-beta") == anthropic_client.FALLBACK_BETA
    assert isinstance(request.data, bytes)
    assert json.loads(request.data)["model"] == "m"


def test_complete_without_fallback_sends_no_beta_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[urllib.request.Request] = []

    def fake_urlopen(request: urllib.request.Request, timeout: float) -> FakeResponse:
        sent.append(request)
        return FakeResponse(json.dumps(ANSWER_RESPONSE).encode())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    AnthropicMessagesClient(api_key="k", server_side_fallback=False).complete(
        [UserMessage("Hi")], []
    )

    assert sent[0].get_header("Anthropic-beta") is None


def test_http_error_becomes_model_error_with_api_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(request: urllib.request.Request, timeout: float) -> FakeResponse:
        body = io.BytesIO(
            b'{"type": "error", "error": {"type": "authentication_error",'
            b' "message": "invalid x-api-key"}}'
        )
        raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", {}, body)  # type: ignore[arg-type]

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(ModelError, match="HTTP 401: invalid x-api-key") as excinfo:
        AnthropicMessagesClient(api_key="sk-secret").complete([UserMessage("Hi")], [])
    assert "sk-secret" not in str(excinfo.value)


@pytest.mark.parametrize(
    "error",
    [urllib.error.URLError("no route"), TimeoutError("timed out")],
)
def test_network_error_becomes_model_error(
    monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    def fake_urlopen(request: urllib.request.Request, timeout: float) -> FakeResponse:
        raise error

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(ModelError, match="request failed"):
        AnthropicMessagesClient(api_key="k").complete([UserMessage("Hi")], [])


def test_non_json_body_becomes_model_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        urllib.request, "urlopen", lambda request, timeout: FakeResponse(b"<html>")
    )

    with pytest.raises(ModelError, match="not JSON"):
        AnthropicMessagesClient(api_key="k").complete([UserMessage("Hi")], [])


def test_from_env_reads_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-env")
    monkeypatch.setenv("ANTHROPIC_MODEL", "env-model")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://localhost:8080")

    client = AnthropicMessagesClient.from_env()

    assert client.model == "env-model"
    assert client.base_url == "http://localhost:8080"


def test_from_env_uses_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-env")
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)

    client = AnthropicMessagesClient.from_env()

    assert client.model == anthropic_client.DEFAULT_MODEL
    assert client.base_url == anthropic_client.DEFAULT_BASE_URL


def test_from_env_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    with pytest.raises(ModelError, match="ANTHROPIC_API_KEY"):
        AnthropicMessagesClient.from_env()
