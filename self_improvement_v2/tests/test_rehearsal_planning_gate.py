"""Tests for #135: Controlled rehearsal planning gate.

Verifies the planning gate artifact exists, contains required fields,
references prerequisite PRs #127-#132, has forbidden conditions,
and defines planning verdicts.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import ClassVar

REHEARSAL_DIR = Path(__file__).resolve().parent.parent / "rehearsal"
GATE_PATH = REHEARSAL_DIR / "controlled_rehearsal_planning_gate.md"


# ──────────────────────────────────────────────
# Artifact existence
# ──────────────────────────────────────────────


class TestGateArtifactExists:
    """The planning gate markdown file must exist."""

    def test_gate_file_exists(self) -> None:
        assert GATE_PATH.is_file(), f"Gate file not found: {GATE_PATH}"

    def test_gate_file_nonempty(self) -> None:
        text = GATE_PATH.read_text(encoding="utf-8")
        assert len(text) > 500, "Gate file is too short"


# ──────────────────────────────────────────────
# Required sections
# ──────────────────────────────────────────────


class TestGateRequiredSections:
    """The gate document must contain specific required sections."""

    REQUIRED_HEADERS: ClassVar[list[str]] = [
        "Purpose",
        "Prerequisite Dependencies",
        "Required Planning Fields",
        "Forbidden Conditions",
        "Gate Verdicts",
        "Escalation",
        "No-Approval Statement",
    ]

    def test_all_required_headers_present(self) -> None:
        text = GATE_PATH.read_text(encoding="utf-8")
        for header in self.REQUIRED_HEADERS:
            # Headers use numbered format "## N. Section Name"
            assert re.search(rf"## \d+\.\s*{re.escape(header)}\s*$", text, re.MULTILINE), (
                f"Required header '{header}' not found in gate document"
            )

    def test_has_127_reference(self) -> None:
        text = GATE_PATH.read_text(encoding="utf-8")
        assert "#127" in text or "127" in text, "Missing reference to #127"

    def test_has_128_reference(self) -> None:
        text = GATE_PATH.read_text(encoding="utf-8")
        assert "#128" in text or "128" in text, "Missing reference to #128"

    def test_has_129_reference(self) -> None:
        text = GATE_PATH.read_text(encoding="utf-8")
        assert "#129" in text or "129" in text, "Missing reference to #129"

    def test_has_130_reference(self) -> None:
        text = GATE_PATH.read_text(encoding="utf-8")
        assert "#130" in text or "130" in text, "Missing reference to #130"

    def test_has_131_reference(self) -> None:
        text = GATE_PATH.read_text(encoding="utf-8")
        assert "#131" in text or "131" in text, "Missing reference to #131"

    def test_has_132_reference(self) -> None:
        text = GATE_PATH.read_text(encoding="utf-8")
        assert "#132" in text or "132" in text, "Missing reference to #132"


# ──────────────────────────────────────────────
# Forbidden conditions
# ──────────────────────────────────────────────


class TestGateForbiddenConditions:
    """The gate must list forbidden conditions that block proposal creation."""

    FORBIDDEN_PATTERNS: ClassVar[list[str]] = [
        r"dry_run.*false",
        r"LIVE_APPROVED",
        r"LIVE_ACTIVE",
        r"API\s*key",
        r"secret",
        r"credential",
        r"SI_V2_ENABLE_REAL_ADAPTERS",
        r"RiskGuard.*unavailable",
        r"ShadowLogger.*unavailable",
        r"runtime action",
        r"financial exposure",
    ]

    def test_forbidden_conditions_section_exists(self) -> None:
        text = GATE_PATH.read_text(encoding="utf-8")
        assert "Forbidden" in text, "Missing Forbidden Conditions section"

    def test_forbidden_patterns_mentioned(self) -> None:
        text = GATE_PATH.read_text(encoding="utf-8")
        for pat_str in self.FORBIDDEN_PATTERNS:
            assert re.search(pat_str, text, re.IGNORECASE), (
                f"Forbidden pattern '{pat_str}' not found in gate document"
            )


# ──────────────────────────────────────────────
# Gate verdicts
# ──────────────────────────────────────────────


class TestGateVerdicts:
    """The gate must define GREEN/YELLOW/RED verdicts."""

    def test_green_verdict_defined(self) -> None:
        text = GATE_PATH.read_text(encoding="utf-8")
        assert "GREEN" in text, "Missing GREEN verdict"

    def test_yellow_verdict_defined(self) -> None:
        text = GATE_PATH.read_text(encoding="utf-8")
        assert "YELLOW" in text, "Missing YELLOW verdict"

    def test_red_verdict_defined(self) -> None:
        text = GATE_PATH.read_text(encoding="utf-8")
        assert "RED" in text, "Missing RED verdict"


# ──────────────────────────────────────────────
# No-approval statement
# ──────────────────────────────────────────────


class TestGateNoApproval:
    """The gate must state it does not approve rehearsal execution."""

    def test_no_approval_statement_present(self) -> None:
        text = GATE_PATH.read_text(encoding="utf-8")
        assert "does not approve" in text.lower(), (
            "Missing 'does not approve' statement"
        )

    def test_live_trading_prohibited(self) -> None:
        text = GATE_PATH.read_text(encoding="utf-8")
        assert "strictly prohibited" in text.lower() or "not approve" in text.lower(), (
            "Missing live trading prohibition"
        )
