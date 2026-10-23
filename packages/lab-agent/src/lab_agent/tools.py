"""Lab document tools: plain Python functions with no knowledge of any LLM.

The agent exposes these to a model, but they can be called and tested directly.
They return JSON-serializable data and signal expected failures with
``ToolError`` subclasses, which the agent reports back to the model.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict
from typing import Any

from lab_agent.documents import LAB_DOCUMENTS, LabDocument


class ToolError(Exception):
    """Base class for expected tool failures the model may be able to correct."""


class InvalidQueryError(ToolError, ValueError):
    """Raised when a search query is empty or blank."""


class DocumentNotFoundError(ToolError, LookupError):
    """Raised when no document has the requested ID."""


def search_lab_documents(
    query: str, documents: Sequence[LabDocument] = LAB_DOCUMENTS
) -> list[dict[str, str]]:
    """Search document titles and descriptions for the words in ``query``.

    Matching is case-insensitive per word. A document matches if it contains at
    least one query word; results are ordered by how many words matched (stable
    for ties). Only summaries are returned; use ``get_document_details`` for
    the results.

    Raises:
        InvalidQueryError: If the query contains no words.
    """
    terms = query.lower().split()
    if not terms:
        raise InvalidQueryError("Query must contain at least one search term.")

    scored: list[tuple[int, LabDocument]] = []
    for doc in documents:
        text = f"{doc.title} {doc.description}".lower()
        score = sum(term in text for term in terms)
        if score:
            scored.append((score, doc))
    scored.sort(key=lambda item: item[0], reverse=True)

    return [
        {
            "document_id": doc.document_id,
            "title": doc.title,
            "description": doc.description,
            "collected_on": doc.collected_on,
        }
        for _, doc in scored
    ]


def get_document_details(
    document_id: str, documents: Sequence[LabDocument] = LAB_DOCUMENTS
) -> dict[str, Any]:
    """Return the full document, including all lab results, for ``document_id``.

    Raises:
        DocumentNotFoundError: If no document has this ID.
    """
    wanted = document_id.strip()
    for doc in documents:
        if doc.document_id == wanted:
            details = asdict(doc)
            details["results"] = [asdict(result) for result in doc.results]
            return details
    raise DocumentNotFoundError(f"No lab document with ID '{wanted}'.")
