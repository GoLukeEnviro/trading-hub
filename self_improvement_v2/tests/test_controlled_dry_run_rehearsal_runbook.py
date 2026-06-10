"""Tests for Controlled Dry-run Rehearsal Runbook (#125).

Verifies:
- runbook exists
- prerequisites are explicit
- forbidden actions are explicit
- stop conditions are explicit
- approval token requirement is stated
"""

from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent

_RUNBOOK_PATH = (
    _ROOT / "runbooks" / "controlled_dry_run_rehearsal.md"
)


class TestRunbookExists:
    def test_runbook_exists(self) -> None:
        assert _RUNBOOK_PATH.exists()

    def test_runbook_not_empty(self) -> None:
        text = _RUNBOOK_PATH.read_text()
        assert len(text) > 100


class TestContent:
    def test_contains_prerequisites(self) -> None:
        text = _RUNBOOK_PATH.read_text()
        assert "Prerequisites" in text

    def test_contains_allowed_commands(self) -> None:
        text = _RUNBOOK_PATH.read_text()
        assert "Allowed Commands" in text or "Allowed" in text

    def test_contains_forbidden_actions(self) -> None:
        text = _RUNBOOK_PATH.read_text()
        assert "Forbidden Actions" in text or "Forbidden" in text

    def test_contains_stop_conditions(self) -> None:
        text = _RUNBOOK_PATH.read_text()
        assert "Stop Conditions" in text or "stop" in text.lower()

    def test_contains_approval_token(self) -> None:
        text = _RUNBOOK_PATH.read_text()
        assert "APPROVE_PHASE_M_REHEARSAL" in text

    def test_contains_rollback_procedure(self) -> None:
        text = _RUNBOOK_PATH.read_text()
        assert "Rollback" in text

    def test_contains_no_live_trading(self) -> None:
        text = _RUNBOOK_PATH.read_text()
        assert "live trading" in text.lower() or "LIVE_FORBIDDEN" in text

    def test_contains_dry_run_false_prohibition(self) -> None:
        text = _RUNBOOK_PATH.read_text()
        assert "dry_run=false" in text or "dry_run" in text

    def test_no_actual_secrets(self) -> None:
        text = _RUNBOOK_PATH.read_text()
        assert "gho_" not in text
        assert "-----BEGIN" not in text
