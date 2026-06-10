"""Tests for #140: Rehearsal readiness decision record.

Verifies the readiness decision record template exists, references
all prerequisite issues #135-#139, defines GREEN/YELLOW/RED verdicts,
includes residual risk fields, production-trading exclusion, and
next-action choices.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import ClassVar

DECISION_RECORD_PATH = Path(__file__).resolve().parent.parent / "rehearsal" / "rehearsal_readiness_decision_record.md"


# ──────────────────────────────────────────────
# Artifact existence
# ──────────────────────────────────────────────


class TestDecisionRecordArtifactExists:
    """The decision record markdown must exist."""

    def test_record_file_exists(self) -> None:
        assert DECISION_RECORD_PATH.is_file(), (
            f"Decision record not found: {DECISION_RECORD_PATH}"
        )

    def test_record_file_nonempty(self) -> None:
        text = DECISION_RECORD_PATH.read_text(encoding="utf-8")
        assert len(text) > 500, "Decision record file is too short"


# ──────────────────────────────────────────────
# Required sections
# ──────────────────────────────────────────────


class TestDecisionRecordRequiredSections:
    """The decision record must contain specific sections."""

    REQUIRED_HEADERS: ClassVar[list[str]] = [
        "Proposal Reference",
        "Prerequisite Status",
        "Stop-Condition Evaluation",
        "Overall Readiness Verdict",
        "Residual Risks",
        "Production-Trading Exclusion",
        "Next-Action Choices",
        "Sign-Off",
    ]

    def test_all_required_headers_present(self) -> None:
        text = DECISION_RECORD_PATH.read_text(encoding="utf-8")
        for header in self.REQUIRED_HEADERS:
            assert re.search(rf"## \d+\.\s*{re.escape(header)}\s*$", text, re.MULTILINE), (
                f"Required header '{header}' not found in decision record"
            )


# ──────────────────────────────────────────────
# Prerequisite references (#135-#139)
# ──────────────────────────────────────────────


class TestDecisionRecordPrerequisiteRefs:
    """The record must reference all planning layer issues."""

    def test_references_135(self) -> None:
        text = DECISION_RECORD_PATH.read_text(encoding="utf-8")
        assert "#135" in text, "Missing reference to #135"

    def test_references_136(self) -> None:
        text = DECISION_RECORD_PATH.read_text(encoding="utf-8")
        assert "#136" in text, "Missing reference to #136"

    def test_references_137(self) -> None:
        text = DECISION_RECORD_PATH.read_text(encoding="utf-8")
        assert "#137" in text, "Missing reference to #137"

    def test_references_138(self) -> None:
        text = DECISION_RECORD_PATH.read_text(encoding="utf-8")
        assert "#138" in text, "Missing reference to #138"

    def test_references_139(self) -> None:
        text = DECISION_RECORD_PATH.read_text(encoding="utf-8")
        assert "#139" in text, "Missing reference to #139"


# ──────────────────────────────────────────────
# Verdict fields
# ──────────────────────────────────────────────


class TestDecisionRecordVerdicts:
    """The record must define GREEN/YELLOW/RED verdicts."""

    def test_green_verdict_defined(self) -> None:
        text = DECISION_RECORD_PATH.read_text(encoding="utf-8")
        assert "GREEN" in text, "Missing GREEN verdict"

    def test_yellow_verdict_defined(self) -> None:
        text = DECISION_RECORD_PATH.read_text(encoding="utf-8")
        assert "YELLOW" in text, "Missing YELLOW verdict"

    def test_red_verdict_defined(self) -> None:
        text = DECISION_RECORD_PATH.read_text(encoding="utf-8")
        assert "RED" in text, "Missing RED verdict"

    def test_verdict_meanings_defined(self) -> None:
        text = DECISION_RECORD_PATH.read_text(encoding="utf-8")
        assert "**GREEN**" in text, "Missing GREEN meaning description"


# ──────────────────────────────────────────────
# Residual risk fields
# ──────────────────────────────────────────────


class TestDecisionRecordResidualRisks:
    """The record must include residual risk documentation."""

    def test_residual_risks_section_exists(self) -> None:
        text = DECISION_RECORD_PATH.read_text(encoding="utf-8")
        assert "Residual Risks" in text, "Missing Residual Risks section"

    def test_risk_severity_defined(self) -> None:
        text = DECISION_RECORD_PATH.read_text(encoding="utf-8")
        assert "Severity" in text, "Missing risk severity field"

    def test_risk_mitigation_field(self) -> None:
        text = DECISION_RECORD_PATH.read_text(encoding="utf-8")
        assert "Mitigation" in text, "Missing risk mitigation field"


# ──────────────────────────────────────────────
# Production-trading exclusion
# ──────────────────────────────────────────────


class TestDecisionRecordProductionExclusion:
    """The record must exclude production-trading readiness assessment."""

    def test_production_trading_exclusion_section_exists(self) -> None:
        text = DECISION_RECORD_PATH.read_text(encoding="utf-8")
        assert "Production-Trading" in text or "production" in text.lower(), (
            "Missing Production-Trading Exclusion section"
        )

    def test_not_for_production_trading_stated(self) -> None:
        text = DECISION_RECORD_PATH.read_text(encoding="utf-8")
        assert "not" in text.lower() and "production" in text.lower(), (
            "Missing 'not for production' disclaimer"
        )

    def test_live_trading_not_authorised(self) -> None:
        text = DECISION_RECORD_PATH.read_text(encoding="utf-8")
        assert "does not authorise" in text.lower() or "not authorise" in text.lower(), (
            "Missing 'does not authorise live trading' language"
        )


# ──────────────────────────────────────────────
# Next-action choices
# ──────────────────────────────────────────────


class TestDecisionRecordNextActions:
    """The record must define at least 4 next-action choices."""

    def test_next_action_choices_section_exists(self) -> None:
        text = DECISION_RECORD_PATH.read_text(encoding="utf-8")
        assert "Next-Action" in text or "Next Action" in text, (
            "Missing Next-Action Choices section"
        )

    def test_proceed_to_rehearsal_choice(self) -> None:
        text = DECISION_RECORD_PATH.read_text(encoding="utf-8")
        assert "Proceed" in text and "rehearsal" in text.lower(), (
            "Missing 'Proceed to rehearsal' choice"
        )

    def test_revise_proposal_choice(self) -> None:
        text = DECISION_RECORD_PATH.read_text(encoding="utf-8")
        assert "Revise" in text, "Missing 'Revise proposal' choice"

    def test_do_not_proceed_choice(self) -> None:
        text = DECISION_RECORD_PATH.read_text(encoding="utf-8")
        assert "Do not proceed" in text, "Missing 'Do not proceed' choice"

    def test_escalate_choice(self) -> None:
        text = DECISION_RECORD_PATH.read_text(encoding="utf-8")
        assert "Escalate" in text, "Missing 'Escalate' choice"


# ──────────────────────────────────────────────
# Sign-off
# ──────────────────────────────────────────────


class TestDecisionRecordSignOff:
    """The record must have a sign-off section."""

    def test_sign_off_section_exists(self) -> None:
        text = DECISION_RECORD_PATH.read_text(encoding="utf-8")
        assert "Sign-Off" in text or "Sign Off" in text, (
            "Missing Sign-Off section"
        )

    def test_assessed_by_field(self) -> None:
        text = DECISION_RECORD_PATH.read_text(encoding="utf-8")
        assert "Assessed By" in text, "Missing 'Assessed By' field"

    def test_assessment_date_field(self) -> None:
        text = DECISION_RECORD_PATH.read_text(encoding="utf-8")
        assert "Assessment Date" in text, "Missing 'Assessment Date' field"
