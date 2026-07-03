"""Tests for bridge/hermes_primo_bridge.py — signal validation and helpers.

DECOMMISSIONED — Issue #465
---------------------------
Bridge was decommissioned in Phase 44-45 (replaced by SI-v2 autonomous loop).
These tests are retained as regression coverage for the still-existing
``bridge/hermes_primo_bridge.py`` module, but are SKIPPED by default.
They will be removed when the bridge/ directory is cleaned up.

Covers validate_signal() edge cases and pure helper functions.
No HTTP, no real filesystem outside tmp_path.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.skip(reason="Bridge decommissioned (Phase 44-45, ADR-2026-07-01) — Issue #465")


# =========================================================================
# _pair_to_filename
# =========================================================================

class TestPairToFilename:
    def test_standard_pair(self) -> None:
        from bridge.hermes_primo_bridge import _pair_to_filename
        assert _pair_to_filename("BTC/USDT:USDT") == "BTC_USDT_USDT.json"

    def test_eth_pair(self) -> None:
        from bridge.hermes_primo_bridge import _pair_to_filename
        assert _pair_to_filename("ETH/USDT:USDT") == "ETH_USDT_USDT.json"

    def test_sol_pair(self) -> None:
        from bridge.hermes_primo_bridge import _pair_to_filename
        assert _pair_to_filename("SOL/USDT:USDT") == "SOL_USDT_USDT.json"


# =========================================================================
# validate_signal
# =========================================================================

class TestValidateSignal:
    def _valid_signal(self) -> dict[str, Any]:
        return {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "pair": "BTC/USDT:USDT",
            "direction": "long",
            "confidence": 0.75,
            "veto": False,
            "risk_cap_percent": 0.5,
        }

    def test_valid_signal_passes(self) -> None:
        from bridge.hermes_primo_bridge import validate_signal
        assert validate_signal(self._valid_signal()) is True

    def test_not_a_dict(self) -> None:
        from bridge.hermes_primo_bridge import validate_signal
        assert validate_signal("not a dict") is False
        assert validate_signal(None) is False
        assert validate_signal(42) is False

    def test_stale_timestamp(self) -> None:
        from bridge.hermes_primo_bridge import validate_signal, SIGNAL_FRESHNESS
        signal = self._valid_signal()
        # Set timestamp far in the past
        old_ts = datetime.now(timezone.utc).timestamp() - SIGNAL_FRESHNESS - 100
        signal["timestamp_utc"] = datetime.fromtimestamp(old_ts, tz=timezone.utc).isoformat()
        assert validate_signal(signal) is False

    def test_invalid_timestamp_format(self) -> None:
        from bridge.hermes_primo_bridge import validate_signal
        signal = self._valid_signal()
        signal["timestamp_utc"] = "not-a-timestamp"
        assert validate_signal(signal) is False

    def test_missing_timestamp(self) -> None:
        from bridge.hermes_primo_bridge import validate_signal
        signal = self._valid_signal()
        del signal["timestamp_utc"]
        assert validate_signal(signal) is False

    def test_pair_not_allowed(self) -> None:
        from bridge.hermes_primo_bridge import validate_signal
        signal = self._valid_signal()
        signal["pair"] = "DOGE/USDT:USDT"
        assert validate_signal(signal) is False

    def test_missing_pair(self) -> None:
        from bridge.hermes_primo_bridge import validate_signal
        signal = self._valid_signal()
        del signal["pair"]
        assert validate_signal(signal) is False

    def test_invalid_direction(self) -> None:
        from bridge.hermes_primo_bridge import validate_signal
        signal = self._valid_signal()
        signal["direction"] = "short"
        assert validate_signal(signal) is False

    def test_missing_direction(self) -> None:
        from bridge.hermes_primo_bridge import validate_signal
        signal = self._valid_signal()
        del signal["direction"]
        assert validate_signal(signal) is False

    def test_confidence_too_low(self) -> None:
        from bridge.hermes_primo_bridge import validate_signal
        signal = self._valid_signal()
        signal["confidence"] = -0.1
        assert validate_signal(signal) is False

    def test_confidence_too_high(self) -> None:
        from bridge.hermes_primo_bridge import validate_signal
        signal = self._valid_signal()
        signal["confidence"] = 1.5
        assert validate_signal(signal) is False

    def test_confidence_non_numeric(self) -> None:
        from bridge.hermes_primo_bridge import validate_signal
        signal = self._valid_signal()
        signal["confidence"] = "not-a-number"
        assert validate_signal(signal) is False

    def test_veto_true(self) -> None:
        from bridge.hermes_primo_bridge import validate_signal
        signal = self._valid_signal()
        signal["veto"] = True
        assert validate_signal(signal) is False

    def test_risk_cap_exceeds_one(self) -> None:
        from bridge.hermes_primo_bridge import validate_signal
        signal = self._valid_signal()
        signal["risk_cap_percent"] = 2.0
        assert validate_signal(signal) is False

    def test_risk_cap_non_numeric(self) -> None:
        from bridge.hermes_primo_bridge import validate_signal
        signal = self._valid_signal()
        signal["risk_cap_percent"] = "not-a-number"
        assert validate_signal(signal) is True  # non-critical field, passes

    def test_direction_none_passes(self) -> None:
        from bridge.hermes_primo_bridge import validate_signal
        signal = self._valid_signal()
        signal["direction"] = "none"
        assert validate_signal(signal) is True

    def test_confidence_zero_passes(self) -> None:
        from bridge.hermes_primo_bridge import validate_signal
        signal = self._valid_signal()
        signal["confidence"] = 0.0
        assert validate_signal(signal) is True

    def test_confidence_one_passes(self) -> None:
        from bridge.hermes_primo_bridge import validate_signal
        signal = self._valid_signal()
        signal["confidence"] = 1.0
        assert validate_signal(signal) is True


# =========================================================================
# _set_error / _clear_error
# =========================================================================

class TestErrorState:
    def test_set_error(self) -> None:
        from bridge.hermes_primo_bridge import _set_error, _state
        _state["last_error"] = None
        _state["last_error_time"] = None
        _set_error("test error")
        assert _state["last_error"] == "test error"
        assert _state["last_error_time"] is not None

    def test_clear_error(self) -> None:
        from bridge.hermes_primo_bridge import _set_error, _clear_error, _state
        _set_error("test error")
        _clear_error()
        assert _state["last_error"] is None
        assert _state["last_error_time"] is None
