"""Tests for Human Approval Gate Checklist (#122).

Verifies:
- checklist exists
- required artifacts are listed
- non-go conditions are explicit
- no-live-trading boundary is stated
- approval fields are clear
"""

from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent

_CHECKLIST_PATH = (
    _ROOT / "governance" / "human_approval_gate_checklist.md"
)


class TestChecklistExists:
    def test_checklist_exists(self) -> None:
        assert _CHECKLIST_PATH.exists()

    def test_checklist_not_empty(self) -> None:
        text = _CHECKLIST_PATH.read_text()
        assert len(text) > 100


class TestContent:
    def test_contains_required_artifacts(self) -> None:
        text = _CHECKLIST_PATH.read_text()
        assert "Required Offline Artifacts" in text

    def test_contains_test_evidence(self) -> None:
        text = _CHECKLIST_PATH.read_text()
        assert "Required Test Evidence" in text

    def test_contains_approval_fields(self) -> None:
        text = _CHECKLIST_PATH.read_text()
        assert "Manual Approval Fields" in text

    def test_contains_non_go_conditions(self) -> None:
        text = _CHECKLIST_PATH.read_text()
        assert "Non-Go Conditions" in text or "BLOCKED" in text

    def test_contains_no_live_trading(self) -> None:
        text = _CHECKLIST_PATH.read_text()
        assert "live trading" in text.lower()
        assert "dry_run=false" in text or "dry_run.*false" in text

    def test_contains_approval_token(self) -> None:
        text = _CHECKLIST_PATH.read_text()
        assert "APPROVE" in text

    def test_contains_no_actual_secrets(self) -> None:
        """Must not contain actual secret values."""
        text = _CHECKLIST_PATH.read_text()
        # These are check items referencing the concept, not actual secrets
        # But actual secret VALUES must not be present
        assert "gho_" not in text  # GitHub token prefix
        assert "-----BEGIN" not in text  # Private key marker
        assert "xoxb-" not in text  # Slack token prefix
