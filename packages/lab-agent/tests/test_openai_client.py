"""Tests for the OpenAI Chat Completions client, with HTTP patched out."""

import io
import json
import urllib.error
import urllib.request
from typing import Any

import pytest

from lab_agent import openai_client
from lab_agent.model import (
    AssistantMessage,
    Message,
    ModelError,
    SystemMessage,
    ToolCall,
    ToolMessage,
    UserMessage,
)
from lab_agent.openai_client import (
    OpenAIChatClient,
    build_request_body,
    parse_response,
)
from lab_agent.registry import LAB_TOOLS

TOOL_CALL_RESPONSE: dict[str, Any] = {
    "choices": [
        {
            "finish_reason": "tool_calls",
            "message": {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_abc",
                        "type": "function",
                        "function": {
                            "name": "search_lab_documents",
                            "arguments": '{"query": "lipid"}',
                        },
                    }
                ],
            },
        }
    ]
}

ANSWER_RESPONSE: dict[str, Any] = {
    "choices": [
        {
            "finish_reason": "stop",
            "message": {"role": "assistant", "content": "LDL is 3.7 mmol/L."},
        }
    ]
}


class FakeResponse(io.BytesIO):
    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def test_request_body_translates_tools() -> None:
    body = build_request_body("test-model", [UserMessage("Hi")], LAB_TOOLS[:1])

    assert body["model"] == "test-model"
    assert body["tools"] == [
        {
            "type": "function",
            "function": {
                "name": "search_lab_documents",
                "description": LAB_TOOLS[0].description,
                "parameters": LAB_TOOLS[0].parameters,
                "strict": True,
            },
        }
    ]


def test_request_body_translates_every_message_type() -> None:
    messages: list[Message] = [
        SystemMessage("Be careful."),
        UserMessage("Lipids?"),
        AssistantMessage(
            tool_calls=(ToolCall("call_abc", "search_lab_documents", "{}"),)
        ),
        ToolMessage("call_abc", '{"error": "x"}', is_error=True),
        AssistantMessage(content="Done."),
    ]

    body = build_request_body("m", messages, [])

    assert body["messages"] == [
        {"role": "system", "content": "Be careful."},
        {"role": "user", "content": "Lipids?"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_abc",
                    "type": "function",
                    "function": {"name": "search_lab_documents", "arguments": "{}"},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call_abc", "content": '{"error": "x"}'},
        {"role": "assistant", "content": "Done."},
    ]
    assert "tools" not in body


def test_parse_tool_call_response() -> None:
    assert parse_response(TOOL_CALL_RESPONSE) == AssistantMessage(
        content=None,
        tool_calls=(
            ToolCall("call_abc", "search_lab_documents", '{"query": "lipid"}'),
        ),
    )


def test_parse_answer_response() -> None:
    assert parse_response(ANSWER_RESPONSE) == AssistantMessage("LDL is 3.7 mmol/L.")


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"choices": []},
        {"choices": [{"message": {"tool_calls": [{"id": "x"}]}}]},
        {"choices": [{"message": {"content": 5}}]},
    ],
)
def test_parse_malformed_response_raises_model_error(body: dict[str, Any]) -> None:
    with pytest.raises(ModelError, match="Unexpected response"):
        parse_response(body)


def test_complete_posts_to_chat_completions(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[urllib.request.Request] = []

    def fake_urlopen(request: urllib.request.Request, timeout: float) -> FakeResponse:
        sent.append(request)
        return FakeResponse(json.dumps(ANSWER_RESPONSE).encode())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    client = OpenAIChatClient(api_key="sk-test", model="m", base_url="http://x/v1/")

    reply = client.complete([UserMessage("Hi")], LAB_TOOLS)

    assert reply.content == "LDL is 3.7 mmol/L."
    (request,) = sent
    assert request.full_url == "http://x/v1/chat/completions"
    assert request.get_header("Authorization") == "Bearer sk-test"
    assert isinstance(request.data, bytes)
    assert json.loads(request.data)["model"] == "m"


def test_http_error_becomes_model_error_with_api_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(request: urllib.request.Request, timeout: float) -> FakeResponse:
        body = io.BytesIO(b'{"error": {"message": "Invalid API key"}}')
        raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", {}, body)  # type: ignore[arg-type]

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(ModelError, match="HTTP 401: Invalid API key") as excinfo:
        OpenAIChatClient(api_key="sk-secret").complete([UserMessage("Hi")], [])
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
        OpenAIChatClient(api_key="k").complete([UserMessage("Hi")], [])


def test_non_json_body_becomes_model_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        urllib.request, "urlopen", lambda request, timeout: FakeResponse(b"<html>")
    )

    with pytest.raises(ModelError, match="not JSON"):
        OpenAIChatClient(api_key="k").complete([UserMessage("Hi")], [])


def test_from_env_reads_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env")
    monkeypatch.setenv("OPENAI_MODEL", "env-model")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:11434/v1")

    client = OpenAIChatClient.from_env()

    assert client.model == "env-model"
    assert client.base_url == "http://localhost:11434/v1"


def test_from_env_uses_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env")
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)

    client = OpenAIChatClient.from_env()

    assert client.model == openai_client.DEFAULT_MODEL
    assert client.base_url == openai_client.DEFAULT_BASE_URL


def test_from_env_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(ModelError, match="OPENAI_API_KEY"):
        OpenAIChatClient.from_env()
