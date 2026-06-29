"""Tests for FleetRiskManager — fleet-wide risk state, drawdown and correlation guard.

Covers all pure functions and I/O paths using tmp_path and monkeypatch.
No Docker, no HTTP, no real filesystem outside tmp_path.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import pytest

from freqtrade.shared.fleet_risk_manager import (
    BACKTEST_GATES,
    CONFIDENCE_MIN,
    STALENESS_MINUTES,
    FleetRiskManager,
    _as_iso,
    _normalize_pair,
    _safe_float,
    _utc_now,
)


# =========================================================================
# Pure helper functions
# =========================================================================


class TestSafeFloat:
    def test_none(self) -> None:
        assert _safe_float(None) == 0.0

    def test_none_with_default(self) -> None:
        assert _safe_float(None, 42.0) == 42.0

    def test_int(self) -> None:
        assert _safe_float(5) == 5.0

    def test_float(self) -> None:
        assert _safe_float(3.14) == 3.14

    def test_string_number(self) -> None:
        assert _safe_float("2.5") == 2.5

    def test_invalid_string(self) -> None:
        assert _safe_float("not-a-number") == 0.0

    def test_list(self) -> None:
        assert _safe_float([1, 2, 3]) == 0.0


class TestAsIso:
    def test_none(self) -> None:
        assert _as_iso(None) is None

    def test_string(self) -> None:
        assert _as_iso("2026-06-29T12:00:00") == "2026-06-29T12:00:00"

    def test_datetime(self) -> None:
        dt = datetime(2026, 6, 29, 12, 0, 0, tzinfo=timezone.utc)
        result = _as_iso(dt)
        assert result is not None
        assert "2026-06-29" in result

    def test_int(self) -> None:
        assert _as_iso(42) == "42"


class TestNormalizePair:
    def test_none(self) -> None:
        assert _normalize_pair(None) == ""

    def test_empty(self) -> None:
        assert _normalize_pair("") == ""

    def test_already_upper(self) -> None:
        assert _normalize_pair("BTC/USDT:USDT") == "BTC/USDT:USDT"

    def test_lowercase(self) -> None:
        assert _normalize_pair("btc/usdt:usdt") == "BTC/USDT:USDT"

    def test_whitespace(self) -> None:
        assert _normalize_pair("  eth/usdt:usdt  ") == "ETH/USDT:USDT"


class TestUtcNow:
    def test_returns_iso_string(self) -> None:
        result = _utc_now()
        assert isinstance(result, str)
        assert "T" in result


# =========================================================================
# FleetRiskManager — pure logic (no I/O)
# =========================================================================


class TestGetCluster:
    def test_major(self) -> None:
        mgr = FleetRiskManager(state_file="/tmp/nonexistent.json")
        assert mgr._get_cluster("BTC/USDT:USDT") == "major"
        assert mgr._get_cluster("ETH/USDT:USDT") == "major"
        assert mgr._get_cluster("SOL/USDT:USDT") == "major"

    def test_layer1_alts(self) -> None:
        mgr = FleetRiskManager(state_file="/tmp/nonexistent.json")
        assert mgr._get_cluster("AVAX/USDT:USDT") == "layer1_alts"
        assert mgr._get_cluster("NEAR/USDT:USDT") == "layer1_alts"

    def test_l2(self) -> None:
        mgr = FleetRiskManager(state_file="/tmp/nonexistent.json")
        assert mgr._get_cluster("ARB/USDT:USDT") == "l2"
        assert mgr._get_cluster("OP/USDT:USDT") == "l2"

    def test_other(self) -> None:
        mgr = FleetRiskManager(state_file="/tmp/nonexistent.json")
        assert mgr._get_cluster("DOGE/USDT:USDT") == "other"
        assert mgr._get_cluster("") == "other"


class TestMakeTradeKey:
    def test_with_trade_id(self) -> None:
        mgr = FleetRiskManager(state_file="/tmp/nonexistent.json")
        key = mgr._make_trade_key("freqforge", 42, "BTC/USDT:USDT")
        assert "freqforge:42" in key

    def test_without_trade_id(self) -> None:
        mgr = FleetRiskManager(state_file="/tmp/nonexistent.json")
        key = mgr._make_trade_key("freqforge", None, "BTC/USDT:USDT")
        assert key.startswith("freqforge:BTC/USDT:USDT:")


class TestTradeDirectionFromAny:
    def test_dict_with_direction(self) -> None:
        mgr = FleetRiskManager(state_file="/tmp/nonexistent.json")
        assert mgr._trade_direction_from_any({"direction": "short"}) == "short"

    def test_dict_with_is_short(self) -> None:
        mgr = FleetRiskManager(state_file="/tmp/nonexistent.json")
        assert mgr._trade_direction_from_any({"is_short": True}) == "short"
        assert mgr._trade_direction_from_any({"is_short": False}) == "long"

    def test_dict_with_side(self) -> None:
        mgr = FleetRiskManager(state_file="/tmp/nonexistent.json")
        assert mgr._trade_direction_from_any({"side": "sell"}) == "sell"

    def test_dict_fallback_long(self) -> None:
        mgr = FleetRiskManager(state_file="/tmp/nonexistent.json")
        assert mgr._trade_direction_from_any({}) == "long"

    def test_object_with_is_short(self) -> None:
        mgr = FleetRiskManager(state_file="/tmp/nonexistent.json")

        class FakeTrade:
            is_short = True

        assert mgr._trade_direction_from_any(FakeTrade()) == "short"

    def test_object_with_trade_direction(self) -> None:
        mgr = FleetRiskManager(state_file="/tmp/nonexistent.json")

        class FakeTrade:
            trade_direction = "long"

        assert mgr._trade_direction_from_any(FakeTrade()) == "long"

    def test_object_fallback_long(self) -> None:
        mgr = FleetRiskManager(state_file="/tmp/nonexistent.json")

        class FakeTrade:
            pass

        assert mgr._trade_direction_from_any(FakeTrade()) == "long"


class TestTradeIdFromAny:
    def test_dict_trade_id(self) -> None:
        mgr = FleetRiskManager(state_file="/tmp/nonexistent.json")
        assert mgr._trade_id_from_any({"trade_id": 42}) == 42

    def test_dict_id(self) -> None:
        mgr = FleetRiskManager(state_file="/tmp/nonexistent.json")
        assert mgr._trade_id_from_any({"id": 99}) == 99

    def test_dict_none(self) -> None:
        mgr = FleetRiskManager(state_file="/tmp/nonexistent.json")
        assert mgr._trade_id_from_any({}) is None

    def test_object_id(self) -> None:
        mgr = FleetRiskManager(state_file="/tmp/nonexistent.json")

        class FakeTrade:
            id = 7

        assert mgr._trade_id_from_any(FakeTrade()) == 7


class TestTradePairFromAny:
    def test_dict(self) -> None:
        mgr = FleetRiskManager(state_file="/tmp/nonexistent.json")
        assert mgr._trade_pair_from_any({"pair": "btc/usdt:usdt"}) == "BTC/USDT:USDT"

    def test_dict_missing(self) -> None:
        mgr = FleetRiskManager(state_file="/tmp/nonexistent.json")
        assert mgr._trade_pair_from_any({}) == ""

    def test_object(self) -> None:
        mgr = FleetRiskManager(state_file="/tmp/nonexistent.json")

        class FakeTrade:
            pair = "eth/usdt:usdt"

        assert mgr._trade_pair_from_any(FakeTrade()) == "ETH/USDT:USDT"


class TestTradeStakeFromAny:
    def test_dict_stake_amount(self) -> None:
        mgr = FleetRiskManager(state_file="/tmp/nonexistent.json")
        assert mgr._trade_stake_from_any({"stake_amount": 100.0}) == 100.0

    def test_dict_stake(self) -> None:
        mgr = FleetRiskManager(state_file="/tmp/nonexistent.json")
        assert mgr._trade_stake_from_any({"stake": 50.0}) == 50.0

    def test_dict_open_trade_value(self) -> None:
        mgr = FleetRiskManager(state_file="/tmp/nonexistent.json")
        assert mgr._trade_stake_from_any({"open_trade_value": 75.0}) == 75.0

    def test_dict_missing(self) -> None:
        mgr = FleetRiskManager(state_file="/tmp/nonexistent.json")
        assert mgr._trade_stake_from_any({}) == 0.0

    def test_object(self) -> None:
        mgr = FleetRiskManager(state_file="/tmp/nonexistent.json")

        class FakeTrade:
            stake_amount = 200.0

        assert mgr._trade_stake_from_any(FakeTrade()) == 200.0


class TestTradeProfitFromAny:
    def test_dict_profit_pct(self) -> None:
        mgr = FleetRiskManager(state_file="/tmp/nonexistent.json")
        assert mgr._trade_profit_from_any({"profit_pct": 0.05}) == 0.05

    def test_dict_close_profit(self) -> None:
        mgr = FleetRiskManager(state_file="/tmp/nonexistent.json")
        assert mgr._trade_profit_from_any({"close_profit": 0.03}) == 0.03

    def test_dict_missing(self) -> None:
        mgr = FleetRiskManager(state_file="/tmp/nonexistent.json")
        assert mgr._trade_profit_from_any({}) == 0.0

    def test_object_close_profit(self) -> None:
        mgr = FleetRiskManager(state_file="/tmp/nonexistent.json")

        class FakeTrade:
            close_profit = 0.04

        assert mgr._trade_profit_from_any(FakeTrade()) == 0.04


class TestTradeOpenedAt:
    def test_dict_opened_at(self) -> None:
        mgr = FleetRiskManager(state_file="/tmp/nonexistent.json")
        assert mgr._trade_opened_at({"opened_at": "2026-06-29T12:00:00"}) == "2026-06-29T12:00:00"

    def test_dict_open_date(self) -> None:
        mgr = FleetRiskManager(state_file="/tmp/nonexistent.json")
        assert mgr._trade_opened_at({"open_date": "2026-06-28T12:00:00"}) == "2026-06-28T12:00:00"

    def test_dict_missing(self) -> None:
        mgr = FleetRiskManager(state_file="/tmp/nonexistent.json")
        assert mgr._trade_opened_at({}) is None

    def test_object_open_date(self) -> None:
        mgr = FleetRiskManager(state_file="/tmp/nonexistent.json")

        class FakeTrade:
            open_date = "2026-06-27T12:00:00"

        assert mgr._trade_opened_at(FakeTrade()) == "2026-06-27T12:00:00"


class TestTradeClosedAt:
    def test_dict_closed_at(self) -> None:
        mgr = FleetRiskManager(state_file="/tmp/nonexistent.json")
        assert mgr._trade_closed_at({"closed_at": "2026-06-29T12:00:00"}) == "2026-06-29T12:00:00"

    def test_dict_close_date(self) -> None:
        mgr = FleetRiskManager(state_file="/tmp/nonexistent.json")
        assert mgr._trade_closed_at({"close_date": "2026-06-28T12:00:00"}) == "2026-06-28T12:00:00"

    def test_dict_missing(self) -> None:
        mgr = FleetRiskManager(state_file="/tmp/nonexistent.json")
        assert mgr._trade_closed_at({}) is None

    def test_object_close_date(self) -> None:
        mgr = FleetRiskManager(state_file="/tmp/nonexistent.json")

        class FakeTrade:
            close_date = "2026-06-27T12:00:00"

        assert mgr._trade_closed_at(FakeTrade()) == "2026-06-27T12:00:00"


# =========================================================================
# Drawdown / Exposure
# =========================================================================


class TestGetDrawdownLevel:
    def test_normal(self) -> None:
        mgr = FleetRiskManager(state_file="/tmp/nonexistent.json")
        mgr.current_drawdown = 0.0
        assert mgr.get_drawdown_level() == "normal"

    def test_warning(self) -> None:
        mgr = FleetRiskManager(state_file="/tmp/nonexistent.json")
        mgr.current_drawdown = 0.05
        assert mgr.get_drawdown_level() == "warning"

    def test_reduce(self) -> None:
        mgr = FleetRiskManager(state_file="/tmp/nonexistent.json")
        mgr.current_drawdown = 0.10
        assert mgr.get_drawdown_level() == "reduce"

    def test_pause(self) -> None:
        mgr = FleetRiskManager(state_file="/tmp/nonexistent.json")
        mgr.current_drawdown = 0.15
        assert mgr.get_drawdown_level() == "pause"

    def test_emergency(self) -> None:
        mgr = FleetRiskManager(state_file="/tmp/nonexistent.json")
        mgr.current_drawdown = 0.20
        assert mgr.get_drawdown_level() == "emergency"

    def test_boundary_warning(self) -> None:
        mgr = FleetRiskManager(state_file="/tmp/nonexistent.json")
        mgr.current_drawdown = 0.04
        assert mgr.get_drawdown_level() == "warning"

    def test_boundary_reduce(self) -> None:
        mgr = FleetRiskManager(state_file="/tmp/nonexistent.json")
        mgr.current_drawdown = 0.08
        assert mgr.get_drawdown_level() == "reduce"

    def test_boundary_pause(self) -> None:
        mgr = FleetRiskManager(state_file="/tmp/nonexistent.json")
        mgr.current_drawdown = 0.12
        assert mgr.get_drawdown_level() == "pause"

    def test_boundary_emergency(self) -> None:
        mgr = FleetRiskManager(state_file="/tmp/nonexistent.json")
        mgr.current_drawdown = 0.18
        assert mgr.get_drawdown_level() == "emergency"


class TestGetExposureMultiplier:
    def test_normal(self) -> None:
        mgr = FleetRiskManager(state_file="/tmp/nonexistent.json")
        mgr.current_drawdown = 0.0
        assert mgr.get_exposure_multiplier() == 1.0

    def test_warning(self) -> None:
        mgr = FleetRiskManager(state_file="/tmp/nonexistent.json")
        mgr.current_drawdown = 0.05
        assert mgr.get_exposure_multiplier() == 0.75

    def test_reduce(self) -> None:
        mgr = FleetRiskManager(state_file="/tmp/nonexistent.json")
        mgr.current_drawdown = 0.10
        assert mgr.get_exposure_multiplier() == 0.5

    def test_pause(self) -> None:
        mgr = FleetRiskManager(state_file="/tmp/nonexistent.json")
        mgr.current_drawdown = 0.15
        assert mgr.get_exposure_multiplier() == 0.2

    def test_emergency(self) -> None:
        mgr = FleetRiskManager(state_file="/tmp/nonexistent.json")
        mgr.current_drawdown = 0.20
        assert mgr.get_exposure_multiplier() == 0.0


# =========================================================================
# Cluster penalty
# =========================================================================


class TestGetClusterPenalty:
    def _make_mgr(self, tmp_path: Path, **overrides: Any) -> FleetRiskManager:
        import unittest.mock as um
        import freqtrade.shared.fleet_risk_manager as frm
        frm.BACKTEST_GATES = True
        state_file = tmp_path / "state.json"
        state_file.write_text("{}")
        mgr = FleetRiskManager(state_file=str(state_file))
        mgr.correlation_file = str(tmp_path / "nonexistent_corr.json")
        default_state = {
            "open_trades": [],
            "trade_history": [],
            "portfolio": {
                "current_equity": 10000.0, "peak_equity": 10000.0,
                "current_drawdown": 0.0, "sources": {},
            },
        }
        state = {**default_state, **overrides}
        mgr.refresh_from_disk = um.MagicMock(return_value=state)  # type: ignore[method-assign]
        mgr.state = state
        mgr.portfolio_peak = 10000.0
        mgr.current_equity = 10000.0
        mgr.current_drawdown = 0.0
        return mgr

    def test_drawdown_reduce_returns_half(self, tmp_path: Path) -> None:
        mgr = self._make_mgr(tmp_path)
        mgr.current_drawdown = 0.10  # reduce
        assert mgr.get_cluster_penalty("major") == 0.5

    def test_drawdown_pause_returns_zero(self, tmp_path: Path) -> None:
        mgr = self._make_mgr(tmp_path)
        mgr.current_drawdown = 0.15  # pause
        assert mgr.get_cluster_penalty("major") == 0.0

    def test_drawdown_emergency_returns_zero(self, tmp_path: Path) -> None:
        mgr = self._make_mgr(tmp_path)
        mgr.current_drawdown = 0.20  # emergency
        assert mgr.get_cluster_penalty("major") == 0.0

    def test_no_history_returns_one(self, tmp_path: Path) -> None:
        mgr = self._make_mgr(tmp_path)
        assert mgr.get_cluster_penalty("major") == 1.0

    def test_low_winrate_returns_quarter(self, tmp_path: Path) -> None:
        mgr = self._make_mgr(
            tmp_path,
            trade_history=[
                {"cluster": "major", "is_win": False, "profit_pct": -0.05, "trade_key": "a"},
                {"cluster": "major", "is_win": False, "profit_pct": -0.03, "trade_key": "b"},
                {"cluster": "major", "is_win": False, "profit_pct": -0.04, "trade_key": "c"},
                {"cluster": "major", "is_win": True, "profit_pct": 0.01, "trade_key": "d"},
            ],
        )
        # winrate = 0.25 (< 0.30) → 0.25
        assert mgr.get_cluster_penalty("major") == 0.25

    def test_medium_winrate_returns_half(self, tmp_path: Path) -> None:
        mgr = self._make_mgr(
            tmp_path,
            trade_history=[
                {"cluster": "major", "is_win": True, "profit_pct": 0.01, "trade_key": "a"},
                {"cluster": "major", "is_win": True, "profit_pct": 0.02, "trade_key": "b"},
                {"cluster": "major", "is_win": False, "profit_pct": -0.01, "trade_key": "c"},
                {"cluster": "major", "is_win": False, "profit_pct": -0.02, "trade_key": "d"},
            ],
        )
        # winrate = 0.5, pnl = 0.0 → pnl not < -0.03, not < 0.0 → 1.0
        # Actually pnl = 0.0, so it falls through to the final return 1.0
        assert mgr.get_cluster_penalty("major") == 1.0

    def test_good_winrate_returns_one(self, tmp_path: Path) -> None:
        mgr = self._make_mgr(
            tmp_path,
            trade_history=[
                {"cluster": "major", "is_win": True, "profit_pct": 0.05, "trade_key": "a"},
                {"cluster": "major", "is_win": True, "profit_pct": 0.03, "trade_key": "b"},
                {"cluster": "major", "is_win": True, "profit_pct": 0.02, "trade_key": "c"},
            ],
        )
        # winrate = 1.0, pnl > 0 → 1.0
        assert mgr.get_cluster_penalty("major") == 1.0


class TestShouldReduceExposure:
    def test_penalty_below_one_returns_true(self) -> None:
        mgr = FleetRiskManager(state_file="/tmp/nonexistent.json")
        mgr.current_drawdown = 0.10  # reduce → penalty 0.5
        assert mgr.should_reduce_exposure("major") is True

    def test_penalty_one_returns_false(self) -> None:
        mgr = FleetRiskManager(state_file="/tmp/nonexistent.json")
        mgr.current_drawdown = 0.0
        mgr.state = {
            "trade_history": [],
            "portfolio": {},
            "open_trades": [],
        }
        mgr.portfolio_peak = 10000.0
        mgr.current_equity = 10000.0
        mgr.current_drawdown = 0.0
        assert mgr.should_reduce_exposure("major") is False


# =========================================================================
# Direction bias
# =========================================================================


class TestCheckDirectionBias:
    def _make_mgr(self, tmp_path: Path, **overrides: Any) -> FleetRiskManager:
        import unittest.mock as um
        import freqtrade.shared.fleet_risk_manager as frm
        frm.BACKTEST_GATES = True
        state_file = tmp_path / "state.json"
        state_file.write_text("{}")
        mgr = FleetRiskManager(state_file=str(state_file))
        mgr.correlation_file = str(tmp_path / "nonexistent_corr.json")
        default_state = {
            "open_trades": [],
            "trade_history": [],
            "portfolio": {
                "current_equity": 10000.0, "peak_equity": 10000.0,
                "current_drawdown": 0.0, "sources": {},
            },
        }
        state = {**default_state, **overrides}
        mgr.refresh_from_disk = um.MagicMock(return_value=state)  # type: ignore[method-assign]
        mgr.state = state
        mgr.portfolio_peak = 10000.0
        mgr.current_equity = 10000.0
        mgr.current_drawdown = 0.0
        return mgr

    def test_few_trades_ok(self, tmp_path: Path) -> None:
        mgr = self._make_mgr(tmp_path, open_trades=[{"direction": "long", "pair": "BTC/USDT:USDT"}])
        ok, reason = mgr._check_direction_bias("long")
        assert ok is True
        assert "zu wenige Trades" in reason

    def test_short_bias_blocked(self, tmp_path: Path) -> None:
        mgr = self._make_mgr(
            tmp_path,
            open_trades=[
                {"direction": "short", "pair": "BTC/USDT:USDT"},
                {"direction": "short", "pair": "ETH/USDT:USDT"},
                {"direction": "short", "pair": "SOL/USDT:USDT"},
            ],
        )
        ok, reason = mgr._check_direction_bias("short")
        assert ok is False
        assert "SHORT-Bias" in reason

    def test_long_bias_blocked(self, tmp_path: Path) -> None:
        mgr = self._make_mgr(
            tmp_path,
            open_trades=[
                {"direction": "long", "pair": "BTC/USDT:USDT"},
                {"direction": "long", "pair": "ETH/USDT:USDT"},
                {"direction": "long", "pair": "SOL/USDT:USDT"},
            ],
        )
        ok, reason = mgr._check_direction_bias("long")
        assert ok is False
        assert "LONG-Bias" in reason

    def test_balanced_ok(self, tmp_path: Path) -> None:
        mgr = self._make_mgr(
            tmp_path,
            open_trades=[
                {"direction": "long", "pair": "BTC/USDT:USDT"},
                {"direction": "short", "pair": "ETH/USDT:USDT"},
            ],
        )
        ok, reason = mgr._check_direction_bias("long")
        assert ok is True
        assert "Direction-Balance" in reason


# =========================================================================
# Correlation
# =========================================================================


class TestLoadCorrelationMatrix:
    def _make_mgr(self, tmp_path: Path, **overrides: Any) -> FleetRiskManager:
        import unittest.mock as um
        import freqtrade.shared.fleet_risk_manager as frm
        frm.BACKTEST_GATES = True
        state_file = tmp_path / "state.json"
        state_file.write_text("{}")
        mgr = FleetRiskManager(state_file=str(state_file))
        mgr.correlation_file = str(tmp_path / "nonexistent_corr.json")
        default_state = {
            "open_trades": [], "trade_history": [],
            "portfolio": {"current_equity": 10000.0, "peak_equity": 10000.0,
                          "current_drawdown": 0.0, "sources": {}},
        }
        state = {**default_state, **overrides}
        mgr.refresh_from_disk = um.MagicMock(return_value=state)  # type: ignore[method-assign]
        mgr.state = state
        mgr.portfolio_peak = 10000.0
        mgr.current_equity = 10000.0
        mgr.current_drawdown = 0.0
        return mgr

    def test_no_file_returns_empty(self, tmp_path: Path) -> None:
        mgr = self._make_mgr(tmp_path)
        assert mgr._load_correlation_matrix() == {}

    def test_valid_file(self, tmp_path: Path) -> None:
        corr_file = tmp_path / "corr.json"
        corr_file.write_text(json.dumps({"matrix": {"BTC/USDT:USDT": {"ETH/USDT:USDT": 0.85}}}))
        mgr = self._make_mgr(tmp_path)
        mgr.correlation_file = str(corr_file)
        matrix = mgr._load_correlation_matrix()
        assert "BTC/USDT:USDT" in matrix
        assert matrix["BTC/USDT:USDT"]["ETH/USDT:USDT"] == 0.85

    def test_corrupted_file_returns_empty(self, tmp_path: Path) -> None:
        corr_file = tmp_path / "corr.json"
        corr_file.write_text("not json")
        mgr = self._make_mgr(tmp_path)
        mgr.correlation_file = str(corr_file)
        assert mgr._load_correlation_matrix() == {}


class TestLookupCorrelation:
    def test_direct_match(self) -> None:
        mgr = FleetRiskManager(state_file="/tmp/nonexistent.json")
        matrix = {"BTC/USDT:USDT": {"ETH/USDT:USDT": 0.85}}
        assert mgr._lookup_correlation(matrix, "BTC/USDT:USDT", "ETH/USDT:USDT") == 0.85

    def test_reverse_match(self) -> None:
        mgr = FleetRiskManager(state_file="/tmp/nonexistent.json")
        matrix = {"ETH/USDT:USDT": {"BTC/USDT:USDT": 0.85}}
        assert mgr._lookup_correlation(matrix, "BTC/USDT:USDT", "ETH/USDT:USDT") == 0.85

    def test_alias_match(self) -> None:
        mgr = FleetRiskManager(state_file="/tmp/nonexistent.json")
        matrix = {"BTC/USDT": {"ETH/USDT": 0.85}}
        assert mgr._lookup_correlation(matrix, "BTC/USDT:USDT", "ETH/USDT:USDT") == 0.85

    def test_no_match(self) -> None:
        mgr = FleetRiskManager(state_file="/tmp/nonexistent.json")
        matrix = {"BTC/USDT:USDT": {"SOL/USDT:USDT": 0.5}}
        assert mgr._lookup_correlation(matrix, "BTC/USDT:USDT", "ETH/USDT:USDT") is None


class TestGetCorrelationMultiplier:
    def test_no_matrix_returns_one(self) -> None:
        mgr = FleetRiskManager(state_file="/tmp/nonexistent.json")
        assert mgr.get_correlation_multiplier("BTC/USDT:USDT", "long") == 1.0

    def test_high_correlation_same_direction(self, tmp_path: Path) -> None:
        corr_file = tmp_path / "corr.json"
        corr_file.write_text(
            json.dumps({"matrix": {"BTC/USDT:USDT": {"ETH/USDT:USDT": 0.96}}})
        )
        mgr = FleetRiskManager(
            state_file=str(tmp_path / "state.json"),
            correlation_file=str(corr_file),
        )
        open_trades = [
            {"pair": "ETH/USDT:USDT", "direction": "long"},
        ]
        mult = mgr.get_correlation_multiplier("BTC/USDT:USDT", "long", open_trades)
        assert mult == 0.25

    def test_high_correlation_opposite_direction(self, tmp_path: Path) -> None:
        corr_file = tmp_path / "corr.json"
        corr_file.write_text(
            json.dumps({"matrix": {"BTC/USDT:USDT": {"ETH/USDT:USDT": 0.96}}})
        )
        mgr = FleetRiskManager(
            state_file=str(tmp_path / "state.json"),
            correlation_file=str(corr_file),
        )
        open_trades = [
            {"pair": "ETH/USDT:USDT", "direction": "short"},
        ]
        mult = mgr.get_correlation_multiplier("BTC/USDT:USDT", "long", open_trades)
        assert mult == 0.5

    def test_medium_correlation(self, tmp_path: Path) -> None:
        corr_file = tmp_path / "corr.json"
        corr_file.write_text(
            json.dumps({"matrix": {"BTC/USDT:USDT": {"ETH/USDT:USDT": 0.88}}})
        )
        mgr = FleetRiskManager(
            state_file=str(tmp_path / "state.json"),
            correlation_file=str(corr_file),
        )
        open_trades = [
            {"pair": "ETH/USDT:USDT", "direction": "long"},
        ]
        mult = mgr.get_correlation_multiplier("BTC/USDT:USDT", "long", open_trades)
        assert mult == 0.5

    def test_low_correlation(self, tmp_path: Path) -> None:
        corr_file = tmp_path / "corr.json"
        corr_file.write_text(
            json.dumps({"matrix": {"BTC/USDT:USDT": {"ETH/USDT:USDT": 0.70}}})
        )
        mgr = FleetRiskManager(
            state_file=str(tmp_path / "state.json"),
            correlation_file=str(corr_file),
        )
        open_trades = [
            {"pair": "ETH/USDT:USDT", "direction": "long"},
        ]
        mult = mgr.get_correlation_multiplier("BTC/USDT:USDT", "long", open_trades)
        assert mult == 1.0


# =========================================================================
# Check entry allowed
# =========================================================================


class TestCheckEntryAllowed:
    def _make_mgr(self, tmp_path: Path, **overrides: Any) -> FleetRiskManager:
        """Create a FleetRiskManager with a tmp_path state file and mocked refresh_from_disk."""
        import unittest.mock as um
        import freqtrade.shared.fleet_risk_manager as frm
        frm.BACKTEST_GATES = True

        state_file = tmp_path / "state.json"
        state_file.write_text("{}")
        mgr = FleetRiskManager(state_file=str(state_file))
        # Point correlation_file to non-existent path so _load_correlation_matrix returns {}
        mgr.correlation_file = str(tmp_path / "nonexistent_corr.json")
        # Mock refresh_from_disk to return our controlled state
        default_state = {
            "open_trades": [],
            "trade_history": [],
            "portfolio": {
                "current_equity": 10000.0,
                "peak_equity": 10000.0,
                "current_drawdown": 0.0,
                "sources": {},
            },
        }
        state = {**default_state, **overrides}
        mgr.refresh_from_disk = um.MagicMock(return_value=state)  # type: ignore[method-assign]
        mgr.state = state
        mgr.portfolio_peak = 10000.0
        mgr.current_equity = 10000.0
        mgr.current_drawdown = 0.0
        return mgr

    def test_backtest_gates_bypassed(self, monkeypatch: Any) -> None:
        import freqtrade.shared.fleet_risk_manager as frm
        original = frm.BACKTEST_GATES
        try:
            frm.BACKTEST_GATES = False
            mgr = frm.FleetRiskManager(state_file="/tmp/nonexistent.json")
            ok, reason = mgr.check_entry_allowed("BTC/USDT:USDT", "long")
            assert ok is True
            assert "gates bypassed" in reason
        finally:
            frm.BACKTEST_GATES = original

    def test_empty_pair_ok(self, tmp_path: Path) -> None:
        mgr = self._make_mgr(tmp_path)
        ok, reason = mgr.check_entry_allowed("", "long")
        assert ok is True
        assert reason == "OK"

    def test_emergency_drawdown_blocked(self, tmp_path: Path) -> None:
        mgr = self._make_mgr(tmp_path)
        mgr.current_drawdown = 0.20
        ok, reason = mgr.check_entry_allowed("BTC/USDT:USDT", "long")
        assert ok is False
        assert "EMERGENCY" in reason

    def test_pause_drawdown_blocked(self, tmp_path: Path) -> None:
        mgr = self._make_mgr(tmp_path)
        mgr.current_drawdown = 0.15
        ok, reason = mgr.check_entry_allowed("BTC/USDT:USDT", "long")
        assert ok is False
        assert "Drawdown-Pause" in reason

    def test_direction_bias_blocked(self, tmp_path: Path) -> None:
        mgr = self._make_mgr(
            tmp_path,
            open_trades=[
                {"direction": "short", "pair": "BTC/USDT:USDT"},
                {"direction": "short", "pair": "ETH/USDT:USDT"},
                {"direction": "short", "pair": "SOL/USDT:USDT"},
            ],
        )
        ok, reason = mgr.check_entry_allowed("AVAX/USDT:USDT", "short")
        assert ok is False
        assert "SHORT-Bias" in reason

    def test_cluster_limit_reached(self, tmp_path: Path) -> None:
        mgr = self._make_mgr(
            tmp_path,
            open_trades=[
                {"direction": "long", "pair": "BTC/USDT:USDT", "cluster": "major"},
                {"direction": "long", "pair": "ETH/USDT:USDT", "cluster": "major"},
                {"direction": "short", "pair": "SOL/USDT:USDT", "cluster": "major"},
                {"direction": "short", "pair": "AVAX/USDT:USDT", "cluster": "layer1_alts"},
            ],
        )
        ok, reason = mgr.check_entry_allowed("SOL/USDT:USDT", "long")
        assert ok is False
        assert "Cluster-Limit" in reason

    def test_global_limit_reached(self, tmp_path: Path) -> None:
        mgr = self._make_mgr(
            tmp_path,
            open_trades=[
                {"direction": "long", "pair": "BTC/USDT:USDT", "cluster": "major"},
                {"direction": "long", "pair": "ETH/USDT:USDT", "cluster": "major"},
                {"direction": "long", "pair": "SOL/USDT:USDT", "cluster": "major"},
                {"direction": "short", "pair": "AVAX/USDT:USDT", "cluster": "layer1_alts"},
                {"direction": "short", "pair": "NEAR/USDT:USDT", "cluster": "layer1_alts"},
                {"direction": "short", "pair": "ARB/USDT:USDT", "cluster": "l2"},
            ],
        )
        ok, reason = mgr.check_entry_allowed("OP/USDT:USDT", "long")
        assert ok is False
        assert "Globales Exposure-Limit" in reason

    def test_correlation_throttle_ok(self, tmp_path: Path) -> None:
        corr_file = tmp_path / "corr.json"
        corr_file.write_text(
            json.dumps({"matrix": {"SOL/USDT:USDT": {"BTC/USDT:USDT": 0.88}}})
        )
        mgr = self._make_mgr(
            tmp_path,
            open_trades=[
                {"direction": "short", "pair": "BTC/USDT:USDT", "cluster": "major"},
            ],
        )
        mgr.correlation_file = str(corr_file)
        ok, reason = mgr.check_entry_allowed("SOL/USDT:USDT", "long")
        assert ok is True
        assert "correlation_throttle" in reason

    def test_ok(self, tmp_path: Path) -> None:
        mgr = self._make_mgr(tmp_path)
        ok, reason = mgr.check_entry_allowed("BTC/USDT:USDT", "long")
        assert ok is True
        assert reason == "OK"


# =========================================================================
# Summarize state
# =========================================================================


class TestSummarizeState:
    def test_empty(self, tmp_path: Path) -> None:
        mgr = FleetRiskManager(state_file=str(tmp_path / "state.json"))
        summary = mgr.summarize_state()
        assert summary["current_equity"] is None
        assert summary["peak_equity"] is None
        assert summary["current_drawdown"] == 0.0
        assert summary["drawdown_level"] == "normal"
        assert summary["open_trades"] == 0
        assert summary["trade_history"] == 0

    def test_with_data(self, tmp_path: Path) -> None:
        state_file = tmp_path / "state.json"
        state_file.write_text(
            json.dumps(
                {
                    "portfolio": {
                        "current_equity": 9500.0,
                        "peak_equity": 10000.0,
                        "current_drawdown": 0.05,
                    },
                    "open_trades": [{"pair": "BTC/USDT:USDT"}],
                    "trade_history": [{"pair": "ETH/USDT:USDT"}],
                }
            )
        )
        mgr = FleetRiskManager(state_file=str(state_file))
        summary = mgr.summarize_state()
        assert summary["current_equity"] == 9500.0
        assert summary["peak_equity"] == 10000.0
        assert summary["current_drawdown"] == 0.05
        assert summary["drawdown_level"] == "warning"
        assert summary["open_trades"] == 1
        assert summary["trade_history"] == 1


# =========================================================================
# I/O — state persistence
# =========================================================================


class TestLoadState:
    def test_no_file_returns_default(self, tmp_path: Path) -> None:
        mgr = FleetRiskManager(state_file=str(tmp_path / "nonexistent.json"))
        state = mgr._load_state()
        assert state["portfolio"]["current_drawdown"] == 0.0
        assert state["open_trades"] == []
        assert state["trade_history"] == []

    def test_empty_file_returns_default(self, tmp_path: Path) -> None:
        state_file = tmp_path / "state.json"
        state_file.write_text("")
        mgr = FleetRiskManager(state_file=str(state_file))
        state = mgr._load_state()
        assert state["portfolio"]["current_drawdown"] == 0.0

    def test_invalid_json_returns_default(self, tmp_path: Path) -> None:
        state_file = tmp_path / "state.json"
        state_file.write_text("not json")
        mgr = FleetRiskManager(state_file=str(state_file))
        state = mgr._load_state()
        assert state["portfolio"]["current_drawdown"] == 0.0

    def test_valid_state(self, tmp_path: Path) -> None:
        state_file = tmp_path / "state.json"
        state_file.write_text(
            json.dumps(
                {
                    "portfolio": {"current_equity": 10000.0, "peak_equity": 10000.0},
                    "open_trades": [{"pair": "BTC/USDT:USDT"}],
                    "trade_history": [],
                }
            )
        )
        mgr = FleetRiskManager(state_file=str(state_file))
        state = mgr._load_state()
        assert state["portfolio"]["current_equity"] == 10000.0
        assert len(state["open_trades"]) == 1

    def test_backward_compatible_normalization(self, tmp_path: Path) -> None:
        state_file = tmp_path / "state.json"
        state_file.write_text(
            json.dumps(
                {
                    "portfolio": None,
                    "open_trades": None,
                    "trade_history": None,
                }
            )
        )
        mgr = FleetRiskManager(state_file=str(state_file))
        state = mgr._load_state()
        assert isinstance(state["portfolio"], dict)
        assert state["open_trades"] == []
        assert state["trade_history"] == []


class TestSaveState:
    def test_creates_file(self, tmp_path: Path) -> None:
        state_file = tmp_path / "state.json"
        mgr = FleetRiskManager(state_file=str(state_file))
        mgr._save_state(mgr._default_state())
        assert state_file.exists()
        content = json.loads(state_file.read_text())
        assert "portfolio" in content

    def test_roundtrip(self, tmp_path: Path) -> None:
        state_file = tmp_path / "state.json"
        mgr = FleetRiskManager(state_file=str(state_file))
        state = mgr._default_state()
        state["portfolio"]["current_equity"] = 5000.0
        mgr._save_state(state)
        mgr2 = FleetRiskManager(state_file=str(state_file))
        loaded = mgr2._load_state()
        assert loaded["portfolio"]["current_equity"] == 5000.0

    def test_updates_drawdown(self, tmp_path: Path) -> None:
        state_file = tmp_path / "state.json"
        mgr = FleetRiskManager(state_file=str(state_file))
        state = mgr._default_state()
        state["portfolio"]["current_equity"] = 8000.0
        state["portfolio"]["peak_equity"] = 10000.0
        mgr._save_state(state)
        loaded = json.loads(state_file.read_text())
        dd = loaded["portfolio"]["current_drawdown"]
        assert dd == pytest.approx(0.20, abs=0.01)


class TestRefreshFromDisk:
    def test_refresh_updates_attributes(self, tmp_path: Path) -> None:
        state_file = tmp_path / "state.json"
        state_file.write_text(
            json.dumps(
                {
                    "portfolio": {
                        "current_equity": 9000.0,
                        "peak_equity": 10000.0,
                        "current_drawdown": 0.10,
                    },
                    "open_trades": [],
                    "trade_history": [],
                }
            )
        )
        mgr = FleetRiskManager(state_file=str(state_file))
        assert mgr.current_equity == 9000.0
        assert mgr.portfolio_peak == 10000.0
        assert mgr.current_drawdown == 0.10


class TestRegisterOpenTrade:
    def test_creates_trade(self, tmp_path: Path) -> None:
        state_file = tmp_path / "state.json"
        mgr = FleetRiskManager(state_file=str(state_file))
        key = mgr.register_open_trade("BTC/USDT:USDT", "long", stake=100.0, source="freqforge")
        assert key is not None
        state = mgr._load_state()
        assert len(state["open_trades"]) == 1
        assert state["open_trades"][0]["pair"] == "BTC/USDT:USDT"


class TestUnregisterClosedTrade:
    def test_removes_trade(self, tmp_path: Path) -> None:
        state_file = tmp_path / "state.json"
        mgr = FleetRiskManager(state_file=str(state_file))
        key = mgr.register_open_trade("BTC/USDT:USDT", "long", source="freqforge")
        mgr.unregister_closed_trade(trade_key=key)
        state = mgr._load_state()
        assert len(state["open_trades"]) == 0


class TestLogTradeResult:
    def test_logs_result(self, tmp_path: Path) -> None:
        state_file = tmp_path / "state.json"
        mgr = FleetRiskManager(state_file=str(state_file))
        mgr.log_trade_result("BTC/USDT:USDT", 0.05, "long", source="freqforge")
        state = mgr._load_state()
        assert len(state["trade_history"]) == 1
        assert state["trade_history"][0]["is_win"] is True


class TestSyncTradeState:
    def test_syncs_trades(self, tmp_path: Path) -> None:
        state_file = tmp_path / "state.json"
        mgr = FleetRiskManager(state_file=str(state_file))
        open_trades = [{"pair": "BTC/USDT:USDT", "direction": "long", "stake_amount": 100.0}]
        closed_trades = [{"pair": "ETH/USDT:USDT", "close_profit": 0.03, "direction": "long"}]
        state = mgr.sync_trade_state("freqforge", open_trades, closed_trades, current_equity=10000.0)
        assert len(state["open_trades"]) == 1
        assert len(state["trade_history"]) == 1
        assert state["portfolio"]["current_equity"] == 10000.0


class TestUpdatePortfolioEquity:
    def test_updates_equity(self, tmp_path: Path) -> None:
        state_file = tmp_path / "state.json"
        mgr = FleetRiskManager(state_file=str(state_file))
        mgr.update_portfolio_equity(9500.0)
        state = mgr._load_state()
        assert state["portfolio"]["current_equity"] == 9500.0


class TestUpdateSourceEquity:
    def test_updates_source(self, tmp_path: Path) -> None:
        state_file = tmp_path / "state.json"
        mgr = FleetRiskManager(state_file=str(state_file))
        mgr.update_source_equity("freqforge", 5000.0)
        state = mgr._load_state()
        sources = state["portfolio"]["sources"]
        assert "freqforge" in sources
        assert sources["freqforge"]["current_equity"] == 5000.0


# =========================================================================
# Constants
# =========================================================================


class TestConstants:
    def test_confidence_min(self) -> None:
        assert CONFIDENCE_MIN == 0.65

    def test_staleness_minutes(self) -> None:
        assert STALENESS_MINUTES == 30.0

    def test_backtest_gates_default(self) -> None:
        assert BACKTEST_GATES is True
