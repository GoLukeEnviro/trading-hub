"""Tests for kill_switch_proof.py — read-only kill-switch verification.

Covers:
  1. Both layers NORMAL → GREEN
  2. Both layers HALT_NEW → YELLOW
  3. Both layers EMERGENCY → YELLOW
  4. Host missing → RED
  5. Container missing → RED
  6. Both missing → RED
  7. Corrupt JSON (host) → RED
  8. Corrupt JSON (container) → RED
  9. Mode mismatch → YELLOW
  10. Stale non-NORMAL → YELLOW
  11. Fresh non-NORMAL → YELLOW (not stale)
  12. Auto-clear expired → YELLOW
  13. Invalid mode string → RED
  14. JSON output format
  15. Custom paths
  16. Custom stale threshold
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from datetime import datetime, timezone, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "orchestrator" / "scripts"))
import kill_switch_proof as ksp  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def normal_state() -> dict:
    return {
        "mode": "NORMAL",
        "reason": "normal operation",
        "triggered_at": "2026-07-06T14:14:23.270420+00:00",
        "triggered_by": "operator",
        "auto_clear_at": "",
    }


@pytest.fixture
def halt_state() -> dict:
    # Relative timestamp (now - 10 min): state is always "fresh" (within any
    # realistic threshold) regardless of test-run date. Replaces the fixed
    # 2026-07-06 timestamp which became >48h stale and time-bombed the
    # within-threshold assertions. Production _is_stale is unchanged.
    triggered_at = (datetime.now(tz=timezone.utc) - timedelta(minutes=10)).isoformat()
    return {
        "mode": "HALT_NEW",
        "reason": "manual halt",
        "triggered_at": triggered_at,
        "triggered_by": "operator",
        "auto_clear_at": "",
    }


@pytest.fixture
def emergency_state() -> dict:
    return {
        "mode": "EMERGENCY",
        "reason": "drawdown breach",
        "triggered_at": "2026-07-06T14:14:23.270420+00:00",
        "triggered_by": "operator",
        "auto_clear_at": "",
    }


@pytest.fixture
def stale_halt_state() -> dict:
    return {
        "mode": "HALT_NEW",
        "reason": "old halt",
        "triggered_at": "2026-07-04T15:14:23.270420+00:00",
        "triggered_by": "operator",
        "auto_clear_at": "",
    }


@pytest.fixture
def auto_clear_expired_state() -> dict:
    return {
        "mode": "EMERGENCY",
        "reason": "emergency with auto-clear",
        "triggered_at": "2026-07-06T14:14:23.270420+00:00",
        "triggered_by": "operator",
        "auto_clear_at": "2026-07-06T14:14:23.270420+00:00",
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2))


def _write_corrupt(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("not valid json{{{")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestVerifyKillSwitch:
    def test_both_normal_green(self, tmp_path: Path, normal_state: dict) -> None:
        host = tmp_path / "host.json"
        container = tmp_path / "container.json"
        _write_state(host, normal_state)
        _write_state(container, normal_state)
        result = ksp.verify_kill_switch(host_path=host, container_path=container)
        assert result["verdict"] == "GREEN"
        assert result["consistent"] is True
        assert result["errors"] == []
        assert result["warnings"] == []

    def test_both_halt_yellow(self, tmp_path: Path, halt_state: dict) -> None:
        host = tmp_path / "host.json"
        container = tmp_path / "container.json"
        _write_state(host, halt_state)
        _write_state(container, halt_state)
        result = ksp.verify_kill_switch(host_path=host, container_path=container)
        assert result["verdict"] == "YELLOW"
        assert result["consistent"] is True
        assert result["host_mode"] == "HALT_NEW"

    def test_both_emergency_yellow(self, tmp_path: Path, emergency_state: dict) -> None:
        host = tmp_path / "host.json"
        container = tmp_path / "container.json"
        _write_state(host, emergency_state)
        _write_state(container, emergency_state)
        result = ksp.verify_kill_switch(host_path=host, container_path=container)
        assert result["verdict"] == "YELLOW"
        assert result["consistent"] is True
        assert result["host_mode"] == "EMERGENCY"

    def test_host_missing_red(self, tmp_path: Path, normal_state: dict) -> None:
        host = tmp_path / "host.json"  # not created
        container = tmp_path / "container.json"
        _write_state(container, normal_state)
        result = ksp.verify_kill_switch(host_path=host, container_path=container)
        assert result["verdict"] == "RED"
        assert len(result["errors"]) == 1
        assert "Host" in result["errors"][0]

    def test_container_missing_red(self, tmp_path: Path, normal_state: dict) -> None:
        host = tmp_path / "host.json"
        container = tmp_path / "container.json"  # not created
        _write_state(host, normal_state)
        result = ksp.verify_kill_switch(host_path=host, container_path=container)
        assert result["verdict"] == "RED"
        assert len(result["errors"]) == 1
        assert "Container" in result["errors"][0]

    def test_both_missing_red(self, tmp_path: Path) -> None:
        host = tmp_path / "host.json"
        container = tmp_path / "container.json"
        result = ksp.verify_kill_switch(host_path=host, container_path=container)
        assert result["verdict"] == "RED"
        assert len(result["errors"]) == 2

    def test_host_corrupt_red(self, tmp_path: Path, normal_state: dict) -> None:
        host = tmp_path / "host.json"
        container = tmp_path / "container.json"
        _write_corrupt(host)
        _write_state(container, normal_state)
        result = ksp.verify_kill_switch(host_path=host, container_path=container)
        assert result["verdict"] == "RED"
        assert len(result["errors"]) == 1

    def test_container_corrupt_red(self, tmp_path: Path, normal_state: dict) -> None:
        host = tmp_path / "host.json"
        container = tmp_path / "container.json"
        _write_state(host, normal_state)
        _write_corrupt(container)
        result = ksp.verify_kill_switch(host_path=host, container_path=container)
        assert result["verdict"] == "RED"
        assert len(result["errors"]) == 1

    def test_mode_mismatch_yellow(self, tmp_path: Path, normal_state: dict, halt_state: dict) -> None:
        host = tmp_path / "host.json"
        container = tmp_path / "container.json"
        _write_state(host, normal_state)
        _write_state(container, halt_state)
        result = ksp.verify_kill_switch(host_path=host, container_path=container)
        assert result["verdict"] == "YELLOW"
        assert result["consistent"] is False
        assert len(result["warnings"]) >= 1

    def test_stale_non_normal_yellow(self, tmp_path: Path, stale_halt_state: dict) -> None:
        host = tmp_path / "host.json"
        container = tmp_path / "container.json"
        _write_state(host, stale_halt_state)
        _write_state(container, stale_halt_state)
        result = ksp.verify_kill_switch(host_path=host, container_path=container)
        assert result["verdict"] == "YELLOW"
        assert result["stale"] is True

    def test_fresh_non_normal_not_stale(self, tmp_path: Path, halt_state: dict) -> None:
        host = tmp_path / "host.json"
        container = tmp_path / "container.json"
        _write_state(host, halt_state)
        _write_state(container, halt_state)
        result = ksp.verify_kill_switch(host_path=host, container_path=container)
        assert result["verdict"] == "YELLOW"
        assert result["stale"] is False

    def test_auto_clear_expired_yellow(self, tmp_path: Path, auto_clear_expired_state: dict) -> None:
        host = tmp_path / "host.json"
        container = tmp_path / "container.json"
        _write_state(host, auto_clear_expired_state)
        _write_state(container, auto_clear_expired_state)
        result = ksp.verify_kill_switch(host_path=host, container_path=container)
        assert result["verdict"] == "YELLOW"
        assert result["auto_clear_expired"] is True

    def test_invalid_mode_red(self, tmp_path: Path) -> None:
        host = tmp_path / "host.json"
        container = tmp_path / "container.json"
        _write_state(host, {"mode": "INVALID_MODE"})
        _write_state(container, {"mode": "NORMAL"})
        result = ksp.verify_kill_switch(host_path=host, container_path=container)
        assert result["verdict"] == "RED"
        assert len(result["errors"]) >= 1

    def test_json_output(self, tmp_path: Path, normal_state: dict) -> None:
        host = tmp_path / "host.json"
        container = tmp_path / "container.json"
        _write_state(host, normal_state)
        _write_state(container, normal_state)
        result = ksp.verify_kill_switch(host_path=host, container_path=container)
        # JSON output should have the expected keys
        assert "verdict" in result
        assert "host_mode" in result
        assert "container_mode" in result
        assert "errors" in result
        assert "warnings" in result

    def test_custom_stale_threshold(self, tmp_path: Path, stale_halt_state: dict) -> None:
        host = tmp_path / "host.json"
        container = tmp_path / "container.json"
        _write_state(host, stale_halt_state)
        _write_state(container, stale_halt_state)
        # Use a very high threshold so the stale state is not considered stale
        result = ksp.verify_kill_switch(
            host_path=host, container_path=container, stale_threshold_hours=9999
        )
        assert result["stale"] is False

    def test_normal_state_never_stale(self, tmp_path: Path, normal_state: dict) -> None:
        host = tmp_path / "host.json"
        container = tmp_path / "container.json"
        _write_state(host, normal_state)
        _write_state(container, normal_state)
        result = ksp.verify_kill_switch(host_path=host, container_path=container)
        assert result["stale"] is False
        assert result["verdict"] == "GREEN"


# ---------------------------------------------------------------------------
# Unit: _is_stale
# ---------------------------------------------------------------------------


class TestIsStale:
    def test_normal_never_stale(self, normal_state: dict) -> None:
        assert ksp._is_stale(normal_state) is False

    def test_halt_within_threshold(self, halt_state: dict) -> None:
        assert ksp._is_stale(halt_state, threshold_hours=48) is False

    def test_halt_beyond_threshold(self, stale_halt_state: dict) -> None:
        assert ksp._is_stale(stale_halt_state, threshold_hours=1) is True

    def test_missing_timestamp_stale(self) -> None:
        state = {"mode": "HALT_NEW", "triggered_at": ""}
        assert ksp._is_stale(state) is True

    def test_invalid_timestamp_stale(self) -> None:
        state = {"mode": "HALT_NEW", "triggered_at": "not-a-timestamp"}
        assert ksp._is_stale(state) is True


# ---------------------------------------------------------------------------
# Unit: _is_auto_clear_expired
# ---------------------------------------------------------------------------


class TestIsAutoClearExpired:
    def test_no_auto_clear(self, normal_state: dict) -> None:
        assert ksp._is_auto_clear_expired(normal_state) is False

    def test_auto_clear_in_future(self) -> None:
        state = {"auto_clear_at": "2099-01-01T00:00:00+00:00"}
        assert ksp._is_auto_clear_expired(state) is False

    def test_auto_clear_in_past(self, auto_clear_expired_state: dict) -> None:
        assert ksp._is_auto_clear_expired(auto_clear_expired_state) is True

    def test_invalid_auto_clear(self) -> None:
        state = {"auto_clear_at": "garbage"}
        assert ksp._is_auto_clear_expired(state) is False
