"""Tool definitions: what the model is told about each tool, and argument checks.

A ``Tool`` pairs a Python function with a name, description and JSON Schema for
its arguments. The schema is provider-neutral; each model client translates it
into its API's format. ``validate_arguments`` enforces the small schema subset
used here, so model-generated arguments are checked before any function runs.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from lab_agent.tools import ToolError, get_document_details, search_lab_documents

# JSON Schema type names supported by ``validate_arguments``.
_JSON_TYPES: dict[str, type] = {"string": str}


class InvalidArgumentsError(ToolError, ValueError):
    """Raised when tool arguments do not match the tool's schema."""


@dataclass(frozen=True)
class Tool:
    """A callable exposed to the model."""

    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema of an object with string properties
    function: Callable[..., Any]


def validate_arguments(tool: Tool, arguments: dict[str, Any]) -> None:
    """Check ``arguments`` against ``tool.parameters``.

    Supports the subset the lab tools need: ``required`` keys, no extra keys
    (``additionalProperties: false``) and per-property ``type`` from
    ``_JSON_TYPES``.

    Raises:
        InvalidArgumentsError: On the first mismatch found.
    """
    properties: dict[str, Any] = tool.parameters["properties"]
    for name in tool.parameters.get("required", []):
        if name not in arguments:
            raise InvalidArgumentsError(f"Missing required argument '{name}'.")
    for name, value in arguments.items():
        if name not in properties:
            raise InvalidArgumentsError(f"Unexpected argument '{name}'.")
        type_name = properties[name]["type"]
        if not isinstance(value, _JSON_TYPES[type_name]):
            raise InvalidArgumentsError(
                f"Argument '{name}' must be of type {type_name}."
            )


def _string_parameter(name: str, description: str) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {name: {"type": "string", "description": description}},
        "required": [name],
        "additionalProperties": False,
    }


LAB_TOOLS: tuple[Tool, ...] = (
    Tool(
        name="search_lab_documents",
        description=(
            "Search lab documents by words in their title and description. "
            "Returns matching document summaries (ID, title, description, date), "
            "best match first, without the lab results."
        ),
        parameters=_string_parameter(
            "query", "Search words, e.g. 'cholesterol' or 'thyroid TSH'."
        ),
        function=search_lab_documents,
    ),
    Tool(
        name="get_document_details",
        description=(
            "Get one lab document by its ID, including all lab results with "
            "values, units and reference ranges."
        ),
        parameters=_string_parameter(
            "document_id", "Document ID from a search result, e.g. 'LAB-1002'."
        ),
        function=get_document_details,
    ),
)
