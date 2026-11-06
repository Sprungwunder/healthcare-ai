"""Tests for the command-line entry point."""

from collections.abc import Sequence
from pathlib import Path

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


def test_anthropic_provider_reads_its_own_api_key(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    assert main(["--provider", "anthropic", "Hi"]) == 1
    assert "ANTHROPIC_API_KEY is not set" in capsys.readouterr().err


def test_cli_list_tasks_requires_db(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--list-tasks"]) == 1
    assert "--db is required to list tasks" in capsys.readouterr().err


def test_cli_show_state_validations(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Missing db or task-id
    assert main(["--show-state"]) == 1
    assert "--db and --task-id are required" in capsys.readouterr().err

    # Task not found
    db_file = str(tmp_path / "cli_val.db")
    assert main(["--db", db_file, "--task-id", "non-existent", "--show-state"]) == 1
    assert "not found" in capsys.readouterr().err


def test_cli_resume_validations(capsys: pytest.CaptureFixture[str]) -> None:
    # Missing task-id
    assert main(["--resume"]) == 1
    assert "--task-id is required to resume" in capsys.readouterr().err

    # Missing db
    assert main(["--task-id", "t-1", "--resume"]) == 1
    assert "--db is required to resume" in capsys.readouterr().err


def test_cli_invalid_db_path(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--db", "/invalid_dir/db.sqlite", "--list-tasks"]) == 1
    assert "Failed to initialize SQLite" in capsys.readouterr().err
