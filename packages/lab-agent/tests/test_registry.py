"""Tests for tool definitions and argument validation."""

from typing import Any

import pytest

from lab_agent.registry import LAB_TOOLS, InvalidArgumentsError, validate_arguments
from lab_agent.tools import ToolError, get_document_details, search_lab_documents

TOOLS = {tool.name: tool for tool in LAB_TOOLS}


def test_lab_tools_expose_both_functions() -> None:
    assert TOOLS["search_lab_documents"].function is search_lab_documents
    assert TOOLS["get_document_details"].function is get_document_details


@pytest.mark.parametrize("tool", LAB_TOOLS, ids=lambda tool: tool.name)
def test_tool_schemas_are_strict_objects(tool: Any) -> None:
    assert tool.description
    assert tool.parameters["type"] == "object"
    assert tool.parameters["additionalProperties"] is False
    assert set(tool.parameters["required"]) == set(tool.parameters["properties"])


def test_valid_arguments_pass() -> None:
    validate_arguments(TOOLS["search_lab_documents"], {"query": "lipid"})


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ({}, "Missing required argument 'query'"),
        ({"query": "lipid", "limit": 3}, "Unexpected argument 'limit'"),
        ({"query": 42}, "Argument 'query' must be of type string"),
        ({"query": None}, "Argument 'query' must be of type string"),
    ],
)
def test_invalid_arguments_are_rejected(
    arguments: dict[str, Any], message: str
) -> None:
    with pytest.raises(InvalidArgumentsError, match=message) as excinfo:
        validate_arguments(TOOLS["search_lab_documents"], arguments)
    assert isinstance(excinfo.value, ToolError)
