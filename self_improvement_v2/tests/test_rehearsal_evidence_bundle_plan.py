"""Tests for #137: Rehearsal evidence bundle plan.

Verifies the evidence bundle plan artifact exists, has required sections,
references approval tokens, defines checksum/integrity expectations,
expects sanitised paths, and defines missing-evidence failure behaviour.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import ClassVar

EVIDENCE_PLAN_PATH = Path(__file__).resolve().parent.parent / "rehearsal" / "rehearsal_evidence_bundle_plan.md"


# ──────────────────────────────────────────────
# Artifact existence
# ──────────────────────────────────────────────


class TestEvidencePlanArtifactExists:
    """The evidence bundle plan markdown must exist."""

    def test_plan_file_exists(self) -> None:
        assert EVIDENCE_PLAN_PATH.is_file(), (
            f"Evidence plan file not found: {EVIDENCE_PLAN_PATH}"
        )

    def test_plan_file_nonempty(self) -> None:
        text = EVIDENCE_PLAN_PATH.read_text(encoding="utf-8")
        assert len(text) > 500, "Evidence plan file is too short"


# ──────────────────────────────────────────────
# Required sections
# ──────────────────────────────────────────────


class TestEvidencePlanRequiredSections:
    """The evidence plan must contain specific sections."""

    REQUIRED_HEADERS: ClassVar[list[str]] = [
        "Purpose",
        "Evidence Categories",
        "Required Evidence Fields",
        "Integrity Requirements",
        "Sanitisation Rules",
        "Missing-Evidence Behaviour",
        "Approval Reference",
        "No-Collection Statement",
    ]

    def test_all_required_headers_present(self) -> None:
        text = EVIDENCE_PLAN_PATH.read_text(encoding="utf-8")
        for header in self.REQUIRED_HEADERS:
            assert re.search(rf"## \d+\.\s*{re.escape(header)}\s*$", text, re.MULTILINE), (
                f"Required header '{header}' not found in evidence plan"
            )


# ──────────────────────────────────────────────
# Required evidence fields
# ──────────────────────────────────────────────


class TestEvidencePlanRequiredFields:
    """The evidence plan must define required fields for each record."""

    REQUIRED_FIELD_NAMES: ClassVar[list[str]] = [
        "id",
        "category",
        "collected_at",
        "collected_by",
        "source",
        "content_hash",
        "sanitized_path",
        "approval_reference",
        "rehearsal_proposal_id",
        "checksum_verified",
    ]

    def test_all_required_fields_mentioned(self) -> None:
        text = EVIDENCE_PLAN_PATH.read_text(encoding="utf-8")
        for field in self.REQUIRED_FIELD_NAMES:
            assert field in text, f"Required field '{field}' not mentioned in evidence plan"


# ──────────────────────────────────────────────
# Integrity / checksum
# ──────────────────────────────────────────────


class TestEvidencePlanIntegrity:
    """The evidence plan must define integrity expectations."""

    def test_sha256_mentioned(self) -> None:
        text = EVIDENCE_PLAN_PATH.read_text(encoding="utf-8")
        assert "SHA-256" in text, "Missing SHA-256 integrity requirement"

    def test_content_hash_mentioned(self) -> None:
        text = EVIDENCE_PLAN_PATH.read_text(encoding="utf-8")
        assert "content_hash" in text or "hash" in text.lower(), (
            "Missing content hash requirement"
        )

    def test_integrity_manifest_mentioned(self) -> None:
        text = EVIDENCE_PLAN_PATH.read_text(encoding="utf-8")
        assert "integrity" in text.lower() and "manifest" in text.lower(), (
            "Missing integrity manifest requirement"
        )


# ──────────────────────────────────────────────
# Sanitisation
# ──────────────────────────────────────────────


class TestEvidencePlanSanitisation:
    """The evidence plan must define sanitisation rules for paths."""

    def test_sanitisation_rules_present(self) -> None:
        text = EVIDENCE_PLAN_PATH.read_text(encoding="utf-8")
        assert "Sanitisation" in text or "sanitised" in text.lower() or "sanitized" in text.lower(), (
            "Missing sanitisation rules"
        )

    def test_sanitized_path_flag_mentioned(self) -> None:
        text = EVIDENCE_PLAN_PATH.read_text(encoding="utf-8")
        assert "sanitized_path" in text.lower(), (
            "Missing sanitized_path field expectation"
        )


# ──────────────────────────────────────────────
# Missing-evidence behaviour
# ──────────────────────────────────────────────


class TestEvidencePlanMissingEvidence:
    """The evidence plan must define fail-closed behaviour for missing evidence."""

    def test_missing_evidence_behaviour_defined(self) -> None:
        text = EVIDENCE_PLAN_PATH.read_text(encoding="utf-8")
        assert "Missing-Evidence" in text or "missing" in text.lower(), (
            "Missing missing-evidence behaviour section"
        )

    def test_red_verdict_for_missing_mandatory(self) -> None:
        text = EVIDENCE_PLAN_PATH.read_text(encoding="utf-8")
        assert "RED" in text, "Missing RED verdict for missing evidence"

    def test_no_proceed_without_evidence(self) -> None:
        text = EVIDENCE_PLAN_PATH.read_text(encoding="utf-8")
        assert "Do not proceed" in text or "escalate" in text.lower(), (
            "Missing fail-closed language for missing evidence"
        )


# ──────────────────────────────────────────────
# Approval reference
# ──────────────────────────────────────────────


class TestEvidencePlanApprovalRef:
    """The evidence plan must reference approval tokens."""

    def test_approval_reference_mentioned(self) -> None:
        text = EVIDENCE_PLAN_PATH.read_text(encoding="utf-8")
        assert "approval_reference" in text.lower() or "approval token" in text.lower(), (
            "Missing approval reference requirement"
        )


# ──────────────────────────────────────────────
# No-collection statement
# ──────────────────────────────────────────────


class TestEvidencePlanNoCollection:
    """The evidence plan must state it does not collect evidence now."""

    def test_no_collection_statement_present(self) -> None:
        text = EVIDENCE_PLAN_PATH.read_text(encoding="utf-8")
        assert "plan" in text.lower() and "future" in text.lower(), (
            "Missing 'plan for future collection' statement"
        )

    def test_not_an_approval_statement(self) -> None:
        text = EVIDENCE_PLAN_PATH.read_text(encoding="utf-8")
        assert "not" in text.lower() and ("approve" in text.lower() or "authorise" in text.lower()), (
            "Missing non-approval disclaimer"
        )
