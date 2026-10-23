"""Tests for the lab document tools (plain Python, no LLM involved)."""

import json

import pytest

from lab_agent.documents import LAB_DOCUMENTS, LabDocument, LabResult
from lab_agent.tools import (
    DocumentNotFoundError,
    InvalidQueryError,
    ToolError,
    get_document_details,
    search_lab_documents,
)

DOCUMENTS = (
    LabDocument(
        document_id="LAB-T1",
        title="Lipid panel",
        description="Total cholesterol, LDL and HDL after fasting.",
        collected_on="2026-01-01",
        patient_ref="SYN-T1",
        results=(LabResult("LDL cholesterol", 2.9, "mmol/L", "< 3.0"),),
    ),
    LabDocument(
        document_id="LAB-T2",
        title="Thyroid function",
        description="TSH screening with free T4.",
        collected_on="2026-01-02",
        patient_ref="SYN-T2",
        results=(LabResult("TSH", 1.8, "mU/L", "0.4-4.0"),),
    ),
)


def test_sample_documents_are_synthetic_and_unique() -> None:
    ids = [doc.document_id for doc in LAB_DOCUMENTS]
    assert len(ids) >= 5
    assert len(set(ids)) == len(ids)
    assert all(doc.patient_ref.startswith("SYN-") for doc in LAB_DOCUMENTS)


def test_search_matches_title_case_insensitively() -> None:
    hits = search_lab_documents("LIPID", DOCUMENTS)
    assert [hit["document_id"] for hit in hits] == ["LAB-T1"]


def test_search_matches_description() -> None:
    hits = search_lab_documents("tsh", DOCUMENTS)
    assert [hit["document_id"] for hit in hits] == ["LAB-T2"]


def test_search_ranks_documents_by_number_of_matching_terms() -> None:
    hits = search_lab_documents("fasting thyroid cholesterol", DOCUMENTS)
    assert [hit["document_id"] for hit in hits] == ["LAB-T1", "LAB-T2"]


def test_search_returns_summaries_without_results() -> None:
    (hit,) = search_lab_documents("lipid", DOCUMENTS)
    assert hit == {
        "document_id": "LAB-T1",
        "title": "Lipid panel",
        "description": "Total cholesterol, LDL and HDL after fasting.",
        "collected_on": "2026-01-01",
    }


def test_search_without_matches_returns_empty_list() -> None:
    assert search_lab_documents("ferritin", DOCUMENTS) == []


@pytest.mark.parametrize("query", ["", "   "])
def test_search_rejects_blank_query(query: str) -> None:
    with pytest.raises(InvalidQueryError):
        search_lab_documents(query, DOCUMENTS)


def test_search_defaults_to_sample_documents() -> None:
    assert search_lab_documents("hba1c")


def test_get_document_details_returns_full_document() -> None:
    details = get_document_details("LAB-T2", DOCUMENTS)
    assert details["title"] == "Thyroid function"
    assert details["patient_ref"] == "SYN-T2"
    assert details["results"] == [
        {
            "analyte": "TSH",
            "value": 1.8,
            "unit": "mU/L",
            "reference_range": "0.4-4.0",
        }
    ]


def test_get_document_details_is_json_serializable() -> None:
    json.dumps(get_document_details("LAB-T1", DOCUMENTS))


def test_get_document_details_ignores_surrounding_whitespace() -> None:
    assert get_document_details(" LAB-T1 ", DOCUMENTS)["document_id"] == "LAB-T1"


def test_get_document_details_unknown_id_raises_tool_error() -> None:
    with pytest.raises(DocumentNotFoundError, match="LAB-404") as excinfo:
        get_document_details("LAB-404", DOCUMENTS)
    assert isinstance(excinfo.value, ToolError)
