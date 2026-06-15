"""Tests for the trading pipeline kill-switch integration.

Tests cover:
    - NORMAL mode: signals pass through unchanged
    - HALT_NEW mode: all signals forced to WATCH_ONLY
    - EMERGENCY mode: WATCH_ONLY + exit_signal flag
    - Edge cases: empty signal list, missing pair keys, dict-vs-list input
    - Import guard: fallback when kill_switch module unavailable
"""
from __future__ import annotations

import pytest

from si_v2.loop.trading_pipeline import (
    VERDICT_WATCH_ONLY,
    _check_kill_switch,
    process_signals,
)

# ── Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture
def normal_ks() -> dict:
    """Kill-switch check result for NORMAL mode."""
    return {
        "kill_override": False,
        "emergency": False,
        "kill_mode": "NORMAL",
        "forced_verdict": None,
        "exit_signal": False,
    }


@pytest.fixture
def halt_new_ks() -> dict:
    """Kill-switch check result for HALT_NEW mode."""
    return {
        "kill_override": True,
        "emergency": False,
        "kill_mode": "HALT_NEW",
        "forced_verdict": VERDICT_WATCH_ONLY,
        "exit_signal": False,
    }


@pytest.fixture
def emergency_ks() -> dict:
    """Kill-switch check result for EMERGENCY mode."""
    return {
        "kill_override": True,
        "emergency": True,
        "kill_mode": "EMERGENCY",
        "forced_verdict": VERDICT_WATCH_ONLY,
        "exit_signal": True,
    }


@pytest.fixture
def sample_signals() -> list[dict]:
    """A realistic set of trading signals."""
    return [
        {
            "pair": "BTC/USDT",
            "confidence": 0.82,
            "bias": "bullish",
            "action": "long",
            "quantity": 0.001,
        },
        {
            "pair": "ETH/USDT",
            "confidence": 0.45,
            "bias": "bearish",
            "action": "short",
            "quantity": 0.1,
        },
    ]


@pytest.fixture
def sample_signals_dict() -> dict:
    """Signals wrapped in a dict with a ``pairs`` key."""
    return {
        "pairs": [
            {
                "pair": "BTC/USDT",
                "confidence": 0.82,
                "bias": "bullish",
                "action": "long",
                "quantity": 0.001,
            },
        ],
        "generated_at": "2026-06-15T12:00:00+00:00",
    }


# ── NORMAL mode tests ───────────────────────────────────────────────────


class TestNormalMode:
    """When kill-switch is NORMAL, signals should pass through unchanged."""

    def test_signals_pass_through(
        self,
        sample_signals: list[dict],
        normal_ks: dict,
    ) -> None:
        """All signals keep their original verdict and fields."""
        result = process_signals(sample_signals, kill_switch_check=normal_ks)

        assert result["override_active"] is False
        assert result["kill_mode"] == "NORMAL"
        assert result["exit_signal"] is False
        assert len(result["pairs"]) == len(sample_signals)

        for i, entry in enumerate(result["pairs"]):
            assert entry["kill_switched"] is False
            assert entry["kill_mode"] == "NORMAL"
            # Original values preserved
            assert entry["confidence"] == sample_signals[i].get("confidence")
            assert entry["action"] == sample_signals[i].get("action")
            assert entry["pair"] == sample_signals[i].get("pair")

    def test_empty_signals_normal(self, normal_ks: dict) -> None:
        """Empty signal list returns empty pairs."""
        result = process_signals([], kill_switch_check=normal_ks)
        assert result["override_active"] is False
        assert result["pairs"] == []

    def test_dict_input_with_pairs(
        self,
        sample_signals_dict: dict,
        normal_ks: dict,
    ) -> None:
        """Dict with ``pairs`` key is unpacked correctly."""
        result = process_signals(sample_signals_dict, kill_switch_check=normal_ks)
        assert len(result["pairs"]) == 1
        assert result["pairs"][0]["pair"] == "BTC/USDT"


# ── HALT_NEW mode tests ────────────────────────────────────────────────


class TestHaltNewMode:
    """When kill-switch is HALT_NEW, all signals become WATCH_ONLY."""

    def test_all_signals_forced_watch_only(
        self,
        sample_signals: list[dict],
        halt_new_ks: dict,
    ) -> None:
        """Every signal gets forced WATCH_ONLY verdict."""
        result = process_signals(sample_signals, kill_switch_check=halt_new_ks)

        assert result["override_active"] is True
        assert result["kill_mode"] == "HALT_NEW"
        assert result["exit_signal"] is False  # EMERGENCY-only

        for entry in result["pairs"]:
            assert entry["verdict"] == VERDICT_WATCH_ONLY
            assert entry["action"] == "HOLD"
            assert entry["kill_switched"] is True
            assert entry["confidence"] == 0.0
            assert entry["quantity"] == 0.0
            assert entry["allow_long_bias"] is False
            assert entry["allow_short_bias"] is False
            # Original confidence preserved for traceability
            assert "original_confidence" in entry

    def test_no_exit_signal_in_halt_new(
        self,
        sample_signals: list[dict],
        halt_new_ks: dict,
    ) -> None:
        """HALT_NEW does NOT set exit_signal."""
        result = process_signals(sample_signals, kill_switch_check=halt_new_ks)
        for entry in result["pairs"]:
            assert entry.get("exit_signal") is not True
            assert entry.get("exit_reason") is None

    def test_summary_halt_new(self, halt_new_ks: dict) -> None:
        """Summary correctly describes HALT_NEW state."""
        result = process_signals([{"pair": "BTC/USDT"}], kill_switch_check=halt_new_ks)
        assert "HALT_NEW" in result["summary"]
        assert "WATCH_ONLY" in result["summary"]


# ── EMERGENCY mode tests ────────────────────────────────────────────────


class TestEmergencyMode:
    """When kill-switch is EMERGENCY, signals get WATCH_ONLY + exit flags."""

    def test_emergency_forces_watch_only(
        self,
        sample_signals: list[dict],
        emergency_ks: dict,
    ) -> None:
        """EMERGENCY mode forces WATCH_ONLY."""
        result = process_signals(sample_signals, kill_switch_check=emergency_ks)

        assert result["override_active"] is True
        assert result["kill_mode"] == "EMERGENCY"
        assert result["exit_signal"] is True

        for entry in result["pairs"]:
            assert entry["verdict"] == VERDICT_WATCH_ONLY
            assert entry["action"] == "HOLD"
            assert entry["kill_switched"] is True

    def test_emergency_sets_exit_signal(
        self,
        sample_signals: list[dict],
        emergency_ks: dict,
    ) -> None:
        """EMERGENCY mode sets exit_signal=True and exit_reason."""
        result = process_signals(sample_signals, kill_switch_check=emergency_ks)
        for entry in result["pairs"]:
            assert entry.get("exit_signal") is True
            assert entry.get("exit_reason") == "kill_switch_emergency"

    def test_summary_emergency(self, emergency_ks: dict) -> None:
        """Summary correctly describes EMERGENCY state."""
        result = process_signals([{"pair": "BTC/USDT"}], kill_switch_check=emergency_ks)
        assert "EMERGENCY" in result["summary"]
        assert "exit signal" in result["summary"]


# ── Edge cases ──────────────────────────────────────────────────────────


class TestEdgeCases:
    """Edge cases: empty, missing keys, type variants."""

    def test_missing_pair_key(self, halt_new_ks: dict) -> None:
        """Signals without a 'pair' key still get a WATCH_ONLY entry."""
        signals: list[dict] = [{"confidence": 0.9}]
        result = process_signals(signals, kill_switch_check=halt_new_ks)
        assert len(result["pairs"]) == 1
        assert result["pairs"][0]["pair"] == "unknown"

    def test_non_list_non_dict_input(self, halt_new_ks: dict) -> None:
        """Non-list, non-dict input (e.g. empty dict with no pairs) yields empty pairs."""
        result = process_signals({}, kill_switch_check=halt_new_ks)
        assert result["pairs"] == []

    def test_signals_key_variant(self, halt_new_ks: dict) -> None:
        """Dict with 'signals' key is unpacked correctly."""
        result = process_signals(
            {"signals": [{"pair": "SOL/USDT"}]},
            kill_switch_check=halt_new_ks,
        )
        assert len(result["pairs"]) == 1
        assert result["pairs"][0]["pair"] == "SOL/USDT"

    def test_single_signal_dict_falls_through(self, halt_new_ks: dict) -> None:
        """A bare signal dict (not wrapped in list/pairs) yields no pairs."""
        result = process_signals(
            {"pair": "BTC/USDT", "confidence": 0.9},
            kill_switch_check=halt_new_ks,
        )
        assert result["pairs"] == []

    def test_normal_does_not_mutate_original(
        self,
        sample_signals: list[dict],
        normal_ks: dict,
    ) -> None:
        """NORMAL mode does not mutate the caller's signal dicts."""
        original_confidence = sample_signals[0].get("confidence")
        _ = process_signals(sample_signals, kill_switch_check=normal_ks)
        assert sample_signals[0].get("confidence") == original_confidence
        assert "kill_switched" not in sample_signals[0]
        assert "kill_mode" not in sample_signals[0]


# ── _check_kill_switch structure ────────────────────────────────────────


class TestCheckKillSwitch:
    """The internal helper produces the expected shape."""

    def test_result_keys(self) -> None:
        """_check_kill_switch returns dict with all expected keys."""
        result = _check_kill_switch()
        expected_keys = {
            "kill_override",
            "emergency",
            "kill_mode",
            "forced_verdict",
            "exit_signal",
        }
        assert set(result.keys()) == expected_keys


# ── Import guard ────────────────────────────────────────────────────────


class TestImportGuard:
    """When kill_switch module cannot be imported, fallback values are used."""

    def test_kill_switch_disabled_fallback(self) -> None:
        """Fallback functions return safe defaults when kill_switch unreachable."""
        import si_v2.loop.trading_pipeline as pipeline

        assert pipeline._is_kill_active() is False
        assert pipeline._is_emergency() is False
        assert pipeline._get_kill_mode() == "NORMAL"
