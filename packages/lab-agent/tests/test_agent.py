"""Control-flow tests for the agent loop with a scripted, offline model."""

import json
from collections.abc import Sequence

import pytest

from lab_agent.agent import MaxIterationsExceededError, run_agent
from lab_agent.model import (
    AssistantMessage,
    Message,
    ModelError,
    SystemMessage,
    ToolCall,
    ToolMessage,
    UserMessage,
)
from lab_agent.registry import LAB_TOOLS, Tool


class ScriptedClient:
    """Fake model client: returns prepared replies and records each request."""

    def __init__(self, *replies: AssistantMessage | Exception) -> None:
        self._replies = list(replies)
        self.requests: list[list[Message]] = []

    def complete(
        self, messages: Sequence[Message], tools: Sequence[Tool]
    ) -> AssistantMessage:
        self.requests.append(list(messages))
        reply = self._replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def call(name: str, arguments: str, call_id: str = "call-1") -> AssistantMessage:
    return AssistantMessage(tool_calls=(ToolCall(call_id, name, arguments),))


def answer(text: str) -> AssistantMessage:
    return AssistantMessage(content=text)


def tool_messages(messages: Sequence[Message]) -> list[ToolMessage]:
    return [msg for msg in messages if isinstance(msg, ToolMessage)]


def test_final_answer_without_tools_ends_loop() -> None:
    client = ScriptedClient(answer("Hello."))

    result = run_agent("Hi", client)

    assert result.answer == "Hello."
    assert result.iterations == 1
    (request,) = client.requests
    assert isinstance(request[0], SystemMessage)
    assert request[1] == UserMessage("Hi")


def test_tool_result_is_sent_back_to_model() -> None:
    client = ScriptedClient(
        call("search_lab_documents", '{"query": "lipid"}'),
        answer("Found LAB-1002."),
    )

    result = run_agent("Find my lipid panel", client)

    assert result.answer == "Found LAB-1002."
    assert result.iterations == 2
    second_request = client.requests[1]
    assert second_request[2] == call("search_lab_documents", '{"query": "lipid"}')
    tool_msg = second_request[3]
    assert isinstance(tool_msg, ToolMessage)
    assert tool_msg.tool_call_id == "call-1"
    assert not tool_msg.is_error
    assert json.loads(tool_msg.content)[0]["document_id"] == "LAB-1002"


def test_multi_step_search_then_details() -> None:
    client = ScriptedClient(
        call("search_lab_documents", '{"query": "thyroid"}', "c1"),
        call("get_document_details", '{"document_id": "LAB-1004"}', "c2"),
        answer("TSH is 5.9 mU/L."),
    )

    result = run_agent("What was my TSH?", client)

    assert result.answer == "TSH is 5.9 mU/L."
    assert result.iterations == 3
    details = json.loads(tool_messages(result.messages)[1].content)
    assert details["results"][0] == {
        "analyte": "TSH",
        "value": 5.9,
        "unit": "mU/L",
        "reference_range": "0.4-4.0",
    }


def test_parallel_tool_calls_each_get_a_result() -> None:
    client = ScriptedClient(
        AssistantMessage(
            tool_calls=(
                ToolCall("a", "get_document_details", '{"document_id": "LAB-1001"}'),
                ToolCall("b", "get_document_details", '{"document_id": "LAB-1002"}'),
            )
        ),
        answer("Done."),
    )

    result = run_agent("Show both", client)

    assert [msg.tool_call_id for msg in tool_messages(result.messages)] == ["a", "b"]


@pytest.mark.parametrize(
    ("name", "arguments", "error"),
    [
        ("delete_documents", "{}", "Unknown tool 'delete_documents'"),
        ("search_lab_documents", "not json", "Arguments are not valid JSON"),
        ("search_lab_documents", '["lipid"]', "Arguments must be a JSON object"),
        ("search_lab_documents", '{"q": "lipid"}', "Missing required argument"),
        ("search_lab_documents", '{"query": " "}', "at least one search term"),
        ("get_document_details", '{"document_id": "LAB-9"}', "No lab document"),
    ],
)
def test_tool_errors_are_reported_to_model_and_loop_continues(
    name: str, arguments: str, error: str
) -> None:
    client = ScriptedClient(call(name, arguments), answer("Sorry, I could not."))

    result = run_agent("Do something", client)

    assert result.answer == "Sorry, I could not."
    (tool_msg,) = tool_messages(client.requests[1])
    assert tool_msg.is_error
    assert error in json.loads(tool_msg.content)["error"]


def test_model_can_recover_after_tool_error() -> None:
    client = ScriptedClient(
        call("get_document_details", '{"document_id": "LAB-9"}', "c1"),
        call("search_lab_documents", '{"query": "kidney"}', "c2"),
        answer("Kidney panel is LAB-1005."),
    )

    result = run_agent("Kidney results?", client)

    first, second = tool_messages(result.messages)
    assert first.is_error and not second.is_error
    assert result.answer == "Kidney panel is LAB-1005."


def test_iteration_limit_stops_endless_tool_calls() -> None:
    client = ScriptedClient(
        *[call("search_lab_documents", '{"query": "lipid"}') for _ in range(3)]
    )

    with pytest.raises(MaxIterationsExceededError, match="3"):
        run_agent("Loop forever", client, max_iterations=3)
    assert len(client.requests) == 3


def test_max_iterations_must_be_positive() -> None:
    with pytest.raises(ValueError):
        run_agent("Hi", ScriptedClient(), max_iterations=0)


def test_model_error_propagates() -> None:
    client = ScriptedClient(ModelError("HTTP 503"))

    with pytest.raises(ModelError, match="HTTP 503"):
        run_agent("Hi", client)


def test_empty_final_answer_is_a_model_error() -> None:
    with pytest.raises(ModelError, match="neither"):
        run_agent("Hi", ScriptedClient(AssistantMessage(content="  ")))


def test_only_given_tools_are_callable() -> None:
    search_only = tuple(t for t in LAB_TOOLS if t.name == "search_lab_documents")
    client = ScriptedClient(
        call("get_document_details", '{"document_id": "LAB-1001"}'),
        answer("Not allowed."),
    )

    result = run_agent("Details please", client, tools=search_only)

    assert tool_messages(result.messages)[0].is_error
