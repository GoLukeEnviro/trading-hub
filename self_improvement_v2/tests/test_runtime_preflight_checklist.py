"""Tests for the Runtime Preflight Checklist Report (#129).

Verifies that the checklist document exists and contains all required sections.
"""

from __future__ import annotations

from pathlib import Path

CHECKLIST_PATH = Path(__file__).resolve().parent.parent / "governance" / "runtime_preflight_checklist.md"

REQUIRED_SECTIONS: list[str] = [
    "Preflight Status",
    "Forbidden Conditions",
    "Explicit Approval Fields",
    "Verification Commands",
    "Escalation Rules",
]

REQUIRED_FORBIDDEN_CONDITIONS: list[str] = [
    "dry_run=false",
    "LIVE_APPROVED",
    "LIVE_ACTIVE",
    "Exchange API keys",
    "SI_V2_ENABLE_REAL_ADAPTERS",
    "forcebuy",
    "RiskGuard",
    "ShadowLogger",
]

REQUIRED_PREFLIGHT_CHECKS: list[str] = [
    "test_live_trading_invariants",
    "test_dry_run_evidence_schema",
    "pytest",
    "ruff",
    "compileall",
]

SAFETY_PHRASES: list[str] = [
    "not an approval to trade live",
    "strictly prohibited",
    "stop and escalate",
]


class TestRuntimePreflightChecklist:
    """Tests for the Runtime Preflight Checklist Report."""

    def test_checklist_exists(self) -> None:
        """The checklist document must exist."""
        assert CHECKLIST_PATH.is_file(), f"Checklist not found: {CHECKLIST_PATH}"

    def test_has_all_required_sections(self) -> None:
        """All required section headers must be present."""
        content = CHECKLIST_PATH.read_text(encoding="utf-8")
        for section in REQUIRED_SECTIONS:
            assert section in content, f"Missing required section: {section}"

    def test_has_all_forbidden_conditions(self) -> None:
        """All forbidden conditions must be documented."""
        content = CHECKLIST_PATH.read_text(encoding="utf-8")
        for condition in REQUIRED_FORBIDDEN_CONDITIONS:
            assert condition in content, f"Missing forbidden condition: {condition}"

    def test_has_all_preflight_checks(self) -> None:
        """All preflight checks must be referenced."""
        content = CHECKLIST_PATH.read_text(encoding="utf-8")
        for check in REQUIRED_PREFLIGHT_CHECKS:
            assert check in content, f"Missing preflight check reference: {check}"

    def test_contains_safety_phrases(self) -> None:
        """Document must contain clear safety disclaimers."""
        content = CHECKLIST_PATH.read_text(encoding="utf-8")
        for phrase in SAFETY_PHRASES:
            assert phrase.lower() in content.lower(), f"Missing safety phrase: {phrase}"

    def test_has_approval_fields(self) -> None:
        """Document must have explicit approval fields section."""
        content = CHECKLIST_PATH.read_text(encoding="utf-8")
        assert "Preflight Verifier" in content
        assert "Preflight Verdict" in content
        assert "Rehearsal Approval Token" in content
        assert "Signature" in content
