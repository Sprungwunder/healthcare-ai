"""Tests for the command-line entry point."""

from collections.abc import Sequence

import pytest

from lab_agent.__main__ import main
from lab_agent.model import AssistantMessage, Message, ModelError, ToolCall
from lab_agent.registry import Tool


class ScriptedClient:
    def __init__(self, *replies: AssistantMessage) -> None:
        self._replies = list(replies)

    def complete(
        self, messages: Sequence[Message], tools: Sequence[Tool]
    ) -> AssistantMessage:
        return self._replies.pop(0)


def test_prints_answer(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["Hi"], client=ScriptedClient(AssistantMessage("Hello.")))

    assert exit_code == 0
    assert capsys.readouterr().out == "Hello.\n"


def test_trace_prints_tool_calls_and_results(
    capsys: pytest.CaptureFixture[str],
) -> None:
    client = ScriptedClient(
        AssistantMessage(
            tool_calls=(ToolCall("c1", "search_lab_documents", '{"query": "tsh"}'),)
        ),
        AssistantMessage("LAB-1004."),
    )

    assert main(["--trace", "TSH?"], client=client) == 0

    err = capsys.readouterr().err
    assert 'search_lab_documents({"query": "tsh"})' in err
    assert "LAB-1004" in err


def test_iteration_limit_is_reported(capsys: pytest.CaptureFixture[str]) -> None:
    looping = AssistantMessage(
        tool_calls=(ToolCall("c1", "search_lab_documents", '{"query": "x"}'),)
    )

    exit_code = main(["--max-iterations", "1", "Loop"], client=ScriptedClient(looping))

    assert exit_code == 1
    assert "No final answer after 1 iterations" in capsys.readouterr().err


def test_missing_api_key_is_reported(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    assert main(["Hi"]) == 1
    assert "OPENAI_API_KEY is not set" in capsys.readouterr().err


def test_model_error_is_reported(capsys: pytest.CaptureFixture[str]) -> None:
    class FailingClient:
        def complete(
            self, messages: Sequence[Message], tools: Sequence[Tool]
        ) -> AssistantMessage:
            raise ModelError("HTTP 500: boom")

    assert main(["Hi"], client=FailingClient()) == 1
    assert "HTTP 500: boom" in capsys.readouterr().err
