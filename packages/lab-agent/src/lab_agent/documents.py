"""Synthetic laboratory documents used by the lab agent tools.

All data here is fictional: patient references use the ``SYN-`` prefix and do not
identify real people. Values are plausible but invented for exercises and tests.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LabResult:
    """A single analyte measurement within a lab document."""

    analyte: str
    value: float
    unit: str
    reference_range: str


@dataclass(frozen=True)
class LabDocument:
    """A laboratory report with searchable metadata and its results."""

    document_id: str
    title: str
    description: str
    collected_on: str  # ISO 8601 date
    patient_ref: str  # synthetic pseudonym, never a real identifier
    results: tuple[LabResult, ...]


LAB_DOCUMENTS: tuple[LabDocument, ...] = (
    LabDocument(
        document_id="LAB-1001",
        title="Complete blood count",
        description="Routine CBC with hemoglobin, white blood cells and platelets.",
        collected_on="2026-03-02",
        patient_ref="SYN-0001",
        results=(
            LabResult("Hemoglobin", 13.8, "g/dL", "12.0-16.0"),
            LabResult("White blood cells", 6.4, "10^9/L", "4.0-10.0"),
            LabResult("Platelets", 251.0, "10^9/L", "150-400"),
        ),
    ),
    LabDocument(
        document_id="LAB-1002",
        title="Lipid panel",
        description="Fasting total cholesterol, LDL, HDL and triglycerides.",
        collected_on="2026-03-02",
        patient_ref="SYN-0001",
        results=(
            LabResult("Total cholesterol", 5.6, "mmol/L", "< 5.2"),
            LabResult("LDL cholesterol", 3.7, "mmol/L", "< 3.0"),
            LabResult("HDL cholesterol", 1.4, "mmol/L", "> 1.0"),
            LabResult("Triglycerides", 1.3, "mmol/L", "< 1.7"),
        ),
    ),
    LabDocument(
        document_id="LAB-1003",
        title="HbA1c follow-up",
        description="Glycated hemoglobin (HbA1c) for long-term blood glucose control.",
        collected_on="2026-04-15",
        patient_ref="SYN-0002",
        results=(LabResult("HbA1c", 6.9, "%", "< 5.7"),),
    ),
    LabDocument(
        document_id="LAB-1004",
        title="Thyroid function",
        description="TSH screening with free T4 (thyroxine).",
        collected_on="2026-05-20",
        patient_ref="SYN-0003",
        results=(
            LabResult("TSH", 5.9, "mU/L", "0.4-4.0"),
            LabResult("Free T4", 10.1, "pmol/L", "12-22"),
        ),
    ),
    LabDocument(
        document_id="LAB-1005",
        title="Kidney function panel",
        description="Serum creatinine, eGFR and urea for renal function.",
        collected_on="2026-06-08",
        patient_ref="SYN-0002",
        results=(
            LabResult("Creatinine", 88.0, "umol/L", "45-90"),
            LabResult("eGFR", 74.0, "mL/min/1.73m2", "> 60"),
            LabResult("Urea", 6.1, "mmol/L", "2.5-7.8"),
        ),
    ),
    LabDocument(
        document_id="LAB-1006",
        title="Liver enzymes",
        description="ALT, AST and gamma-GT to assess liver function.",
        collected_on="2026-07-11",
        patient_ref="SYN-0004",
        results=(
            LabResult("ALT", 31.0, "U/L", "< 35"),
            LabResult("AST", 28.0, "U/L", "< 35"),
            LabResult("Gamma-GT", 52.0, "U/L", "< 40"),
        ),
    ),
)
