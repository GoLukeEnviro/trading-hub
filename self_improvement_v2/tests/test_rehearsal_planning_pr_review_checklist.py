"""Tests for #147: Merge-readiness review checklist.

Verifies the checklist artifact exists, defines required PR metadata,
CI and validation requirements, GREEN/YELLOW/RED verdicts, hard blockers,
and acceptable residual risks.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import ClassVar

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CHECKLIST_PATH = (
    PROJECT_ROOT
    / "governance"
    / "rehearsal_planning_pr_review_checklist.md"
)


# ──────────────────────────────────────────────
# Artifact existence
# ──────────────────────────────────────────────


class TestChecklistArtifactExists:
    """The review checklist markdown must exist."""

    def test_checklist_file_exists(self) -> None:
        assert CHECKLIST_PATH.is_file(), f"Checklist not found: {CHECKLIST_PATH}"

    def test_checklist_file_nonempty(self) -> None:
        text = CHECKLIST_PATH.read_text(encoding="utf-8")
        assert len(text) > 500, "Checklist file is too short"


# ──────────────────────────────────────────────
# Required sections
# ──────────────────────────────────────────────


class TestChecklistRequiredSections:
    """The checklist must contain specific sections."""

    REQUIRED_HEADERS: ClassVar[list[str]] = [
        "Required PR Metadata",
        "CI and Validation Requirements",
        "Review Verdicts",
        "Hard Blockers",
        "Safety Review",
        "Acceptable Residual Risks",
        "Final Sign-Off",
    ]

    def test_all_required_headers_present(self) -> None:
        text = CHECKLIST_PATH.read_text(encoding="utf-8")
        for header in self.REQUIRED_HEADERS:
            assert re.search(rf"## \d+\.\s*{re.escape(header)}\s*$", text, re.MULTILINE), (
                f"Required header '{header}' not found in checklist"
            )


# ──────────────────────────────────────────────
# Review verdicts
# ──────────────────────────────────────────────


class TestChecklistVerdicts:
    """The checklist must define GREEN/YELLOW/RED verdicts."""

    def test_green_verdict_defined(self) -> None:
        text = CHECKLIST_PATH.read_text(encoding="utf-8")
        assert "GREEN" in text, "Missing GREEN verdict"

    def test_yellow_verdict_defined(self) -> None:
        text = CHECKLIST_PATH.read_text(encoding="utf-8")
        assert "YELLOW" in text, "Missing YELLOW verdict"

    def test_red_verdict_defined(self) -> None:
        text = CHECKLIST_PATH.read_text(encoding="utf-8")
        assert "RED" in text, "Missing RED verdict"


# ──────────────────────────────────────────────
# Hard blockers
# ──────────────────────────────────────────────


class TestChecklistHardBlockers:
    """The checklist must define hard blockers with conditions."""

    HARD_BLOCKER_PATTERNS: ClassVar[list[str]] = [
        "dry_run",
        "credentials",
        "API key",
        "Docker",
        "Freqtrade",
        "compile",
        "test",
        "lint",
        "CI",
        "BLOCKED",
    ]

    def test_hard_blockers_section_exists(self) -> None:
        text = CHECKLIST_PATH.read_text(encoding="utf-8")
        assert "Hard Blockers" in text, "Missing Hard Blockers section"

    def test_hard_blocker_conditions_mentioned(self) -> None:
        text = CHECKLIST_PATH.read_text(encoding="utf-8")
        for pattern in self.HARD_BLOCKER_PATTERNS:
            assert re.search(pattern, text, re.IGNORECASE), (
                f"Hard blocker condition '{pattern}' not mentioned"
            )


# ──────────────────────────────────────────────
# CI / Validation requirements
# ──────────────────────────────────────────────


class TestChecklistValidation:
    """The checklist must list CI and validation requirements."""

    def test_compileall_mentioned(self) -> None:
        text = CHECKLIST_PATH.read_text(encoding="utf-8")
        assert "compileall" in text.lower() or "compile" in text.lower()

    def test_pytest_mentioned(self) -> None:
        text = CHECKLIST_PATH.read_text(encoding="utf-8")
        assert "pytest" in text.lower()

    def test_ruff_mentioned(self) -> None:
        text = CHECKLIST_PATH.read_text(encoding="utf-8")
        assert "ruff" in text.lower()

    def test_json_validation_mentioned(self) -> None:
        text = CHECKLIST_PATH.read_text(encoding="utf-8")
        assert "JSON" in text

    def test_offline_smoke_mentioned(self) -> None:
        text = CHECKLIST_PATH.read_text(encoding="utf-8")
        assert "offline-smoke" in text or "offline" in text.lower()


# ──────────────────────────────────────────────
# Safety review
# ──────────────────────────────────────────────


class TestChecklistSafetyReview:
    """The checklist must include safety review items."""

    def test_safety_review_section_exists(self) -> None:
        text = CHECKLIST_PATH.read_text(encoding="utf-8")
        assert "Safety Review" in text, "Missing Safety Review section"

    def test_no_runtime_mentioned(self) -> None:
        text = CHECKLIST_PATH.read_text(encoding="utf-8")
        assert "runtime" in text.lower()

    def test_no_production_trading_mentioned(self) -> None:
        text = CHECKLIST_PATH.read_text(encoding="utf-8")
        assert "production" in text.lower() or "trading" in text.lower()

    def test_fail_closed_mentioned(self) -> None:
        text = CHECKLIST_PATH.read_text(encoding="utf-8")
        assert "fail" in text.lower() and "closed" in text.lower()


# ──────────────────────────────────────────────
# Residual risks
# ──────────────────────────────────────────────


class TestChecklistResidualRisks:
    """The checklist must document acceptable residual risks."""

    def test_residual_risks_section_exists(self) -> None:
        text = CHECKLIST_PATH.read_text(encoding="utf-8")
        assert "Residual Risks" in text, "Missing Residual Risks section"

    def test_governance_only_mentioned(self) -> None:
        text = CHECKLIST_PATH.read_text(encoding="utf-8")
        assert "governance" in text.lower()


# ──────────────────────────────────────────────
# Sign-off
# ──────────────────────────────────────────────


class TestChecklistSignOff:
    """The checklist must have a final sign-off section."""

    def test_sign_off_section_exists(self) -> None:
        text = CHECKLIST_PATH.read_text(encoding="utf-8")
        assert "Sign-Off" in text or "Sign Off" in text

    def test_verdict_field_exists(self) -> None:
        text = CHECKLIST_PATH.read_text(encoding="utf-8")
        assert "Verdict" in text

    def test_approval_token_field_exists(self) -> None:
        text = CHECKLIST_PATH.read_text(encoding="utf-8")
        assert "Approval Token" in text or "approval" in text.lower()
