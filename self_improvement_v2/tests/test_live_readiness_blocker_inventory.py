"""Tests for Live-Readiness Blocker Inventory (#124).

Verifies:
- blocker inventory exists
- live-trading blockers are explicit
- dry-run prerequisites are listed
- manual approval requirement is stated
- no-go conditions are clear
"""

from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent

_INVENTORY_PATH = (
    _ROOT / "governance" / "live_readiness_blocker_inventory.md"
)


class TestInventoryExists:
    def test_inventory_exists(self) -> None:
        assert _INVENTORY_PATH.exists()

    def test_inventory_not_empty(self) -> None:
        text = _INVENTORY_PATH.read_text()
        assert len(text) > 100


class TestContent:
    def test_contains_hard_blockers(self) -> None:
        text = _INVENTORY_PATH.read_text()
        assert "Hard Blockers" in text

    def test_contains_required_offline_artifacts(self) -> None:
        text = _INVENTORY_PATH.read_text()
        assert "Required Offline Artifacts" in text

    def test_contains_required_dry_run_evidence(self) -> None:
        text = _INVENTORY_PATH.read_text()
        assert "Required Dry-Run Evidence" in text

    def test_contains_approval_blockers(self) -> None:
        text = _INVENTORY_PATH.read_text()
        assert "Manual Approval Blockers" in text

    def test_contains_no_go_states(self) -> None:
        text = _INVENTORY_PATH.read_text()
        assert "No-Go States" in text

    def test_contains_live_trading_prohibition(self) -> None:
        text = _INVENTORY_PATH.read_text()
        assert "LIVE_FORBIDDEN" in text
        assert "strictly prohibited" in text.lower()

    def test_contains_dry_run_false_blocker(self) -> None:
        text = _INVENTORY_PATH.read_text()
        assert "dry_run=false" in text or "dry_run.*false" in text

    def test_no_actual_secrets(self) -> None:
        text = _INVENTORY_PATH.read_text()
        # References to concepts are fine, but no actual secret values
        assert "gho_" not in text
        assert "-----BEGIN" not in text
