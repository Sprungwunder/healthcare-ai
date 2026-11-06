"""Tests for laboratory results evaluation tool and reference range parsing."""

import pytest

from lab_agent.tools import (
    DocumentNotFoundError,
    _evaluate_range,
    evaluate_lab_results,
)


def test_evaluate_range_operators() -> None:
    # Less than (<)
    assert _evaluate_range(5.0, "< 5.2") == "normal"
    assert _evaluate_range(5.6, "< 5.2") == "high"

    # Greater than (>)
    assert _evaluate_range(1.4, "> 1.0") == "normal"
    assert _evaluate_range(0.8, "> 1.0") == "low"

    # Interval (low-high)
    assert _evaluate_range(13.8, "12.0-16.0") == "normal"
    assert _evaluate_range(11.5, "12.0-16.0") == "low"
    assert _evaluate_range(17.2, "12.0-16.0") == "high"

    # Invalid range strings
    assert _evaluate_range(10.0, "invalid") == "indeterminate"
    assert _evaluate_range(10.0, "< invalid") == "indeterminate"
    assert _evaluate_range(10.0, "> invalid") == "indeterminate"
    assert _evaluate_range(10.0, "a-b") == "indeterminate"


def test_evaluate_lab_results_lipid_panel() -> None:
    # LAB-1002 has high Total cholesterol and high LDL cholesterol
    result = evaluate_lab_results("LAB-1002")

    assert result["document_id"] == "LAB-1002"
    assert result["total_results"] == 4
    assert result["abnormal_count"] == 2
    assert result["normal_count"] == 2

    findings = {e["analyte"]: e["status"] for e in result["evaluations"]}
    assert findings["Total cholesterol"] == "high"
    assert findings["LDL cholesterol"] == "high"
    assert findings["HDL cholesterol"] == "normal"
    assert findings["Triglycerides"] == "normal"


def test_evaluate_lab_results_thyroid() -> None:
    # LAB-1004 has high TSH and low Free T4
    result = evaluate_lab_results("LAB-1004")

    assert result["document_id"] == "LAB-1004"
    assert result["total_results"] == 2
    assert result["abnormal_count"] == 2
    assert result["normal_count"] == 0

    findings = {e["analyte"]: e["status"] for e in result["evaluations"]}
    assert findings["TSH"] == "high"
    assert findings["Free T4"] == "low"


def test_evaluate_lab_results_normal_panel() -> None:
    # LAB-1001 (CBC) is completely normal
    result = evaluate_lab_results("LAB-1001")

    assert result["document_id"] == "LAB-1001"
    assert result["abnormal_count"] == 0
    assert result["normal_count"] == 3


def test_evaluate_lab_results_missing_doc_raises() -> None:
    with pytest.raises(DocumentNotFoundError):
        evaluate_lab_results("LAB-9999")
