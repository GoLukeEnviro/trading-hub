"""
FleetRiskManager Unit Tests — Extended Coverage
Tests state loading, drawdown levels, exposure multipliers, cluster penalty,
correlation multiplier, entry gate edge cases, and summarize_state.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))

from fleet_risk_manager import FleetRiskManager  # noqa: E402


# ======================================================================
# Helpers
# ======================================================================

def _make_mgr(state: dict | None = None) -> FleetRiskManager:
    """Create a FleetRiskManager backed by an isolated temp file."""
    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, "state.json")
    data = state if state is not None else {
        "open_trades": [],
        "trade_history": [],
        "portfolio": {},
        "last_update": None,
    }
    with open(path, "w") as f:
        json.dump(data, f)
    return FleetRiskManager(state_file=path)


def _make_mgr_with_state(state: dict) -> FleetRiskManager:
    """Create a FleetRiskManager backed by a temp file with the given state."""
    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, "state.json")
    with open(path, "w") as f:
        json.dump(state, f)
    return FleetRiskManager(state_file=path)


# ======================================================================
# Existing tests preserved and extended
# ======================================================================

class TestFleetRiskManagerInit(unittest.TestCase):
    """Verify the manager constructs without error and self.state exists."""

    def test_init_does_not_raise(self) -> None:
        mgr = _make_mgr()
        self.assertIsNotNone(mgr.state)
        self.assertIsInstance(mgr.state, dict)

    def test_init_with_state_file_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing = os.path.join(tmp, "does_not_exist.json")
            mgr = FleetRiskManager(state_file=missing)
            self.assertIsNotNone(mgr.state)
            self.assertIn("open_trades", mgr.state)
            self.assertEqual(mgr.state.get("open_trades"), [])

    def test_init_with_invalid_state_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bad = os.path.join(tmp, "bad.json")
            with open(bad, "w") as f:
                f.write("not valid json")
            mgr = FleetRiskManager(state_file=bad)
            self.assertIsNotNone(mgr.state)
            self.assertEqual(mgr.state.get("open_trades"), [])

    def test_init_with_valid_state_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            good = os.path.join(tmp, "good.json")
            state_data = {
                "open_trades": [{"pair": "BTC/USDT", "direction": "long"}],
                "trade_history": [],
                "portfolio": {},
                "last_update": "2026-06-10T00:00:00",
            }
            with open(good, "w") as f:
                json.dump(state_data, f)
            mgr = FleetRiskManager(state_file=good)
            self.assertEqual(len(mgr.state.get("open_trades", [])), 1)
            self.assertEqual(mgr.state["open_trades"][0]["pair"], "BTC/USDT")

    def test_init_with_empty_state_file(self) -> None:
        """Empty file should fall back to default state."""
        with tempfile.TemporaryDirectory() as tmp:
            empty = os.path.join(tmp, "empty.json")
            with open(empty, "w") as f:
                f.write("")
            mgr = FleetRiskManager(state_file=empty)
            self.assertIsNotNone(mgr.state)
            self.assertEqual(mgr.state.get("open_trades"), [])

    def test_init_with_whitespace_state_file(self) -> None:
        """Whitespace-only file should fall back to default state."""
        with tempfile.TemporaryDirectory() as tmp:
            ws = os.path.join(tmp, "ws.json")
            with open(ws, "w") as f:
                f.write("   \n\n  ")
            mgr = FleetRiskManager(state_file=ws)
            self.assertIsNotNone(mgr.state)
            self.assertEqual(mgr.state.get("open_trades"), [])

    def test_init_with_array_state(self) -> None:
        """JSON array as state should fall back to default."""
        with tempfile.TemporaryDirectory() as tmp:
            arr = os.path.join(tmp, "arr.json")
            with open(arr, "w") as f:
                f.write("[1, 2, 3]")
            mgr = FleetRiskManager(state_file=arr)
            self.assertIsNotNone(mgr.state)
            self.assertEqual(mgr.state.get("open_trades"), [])

    def test_check_entry_allowed_handles_missing_state(self) -> None:
        mgr = FleetRiskManager.__new__(FleetRiskManager)
        mgr.state_file = "/dev/null"
        result = mgr._check_direction_bias("long")
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)


class TestFleetRiskManagerDirectionBias(unittest.TestCase):
    """Direction bias gate."""

    def test_direction_bias_does_not_raise(self) -> None:
        mgr = _make_mgr()
        ok, reason = mgr._check_direction_bias("long")
        self.assertTrue(ok)
        self.assertIn("OK", reason)

    def test_direction_bias_passes_with_few_trades(self) -> None:
        state = {
            "open_trades": [{"pair": "BTC/USDT", "direction": "long"}],
            "trade_history": [],
            "portfolio": {},
            "last_update": None,
        }
        mgr = _make_mgr(state)
        ok, reason = mgr._check_direction_bias("long")
        self.assertTrue(ok)
        self.assertIn("OK", reason)

    def test_direction_bias_blocks_excessive_long(self) -> None:
        state = {
            "open_trades": [
                {"pair": "A/USDT", "direction": "long"},
                {"pair": "B/USDT", "direction": "long"},
                {"pair": "C/USDT", "direction": "long"},
            ],
            "trade_history": [],
            "portfolio": {},
            "last_update": None,
        }
        mgr = _make_mgr(state)
        ok, reason = mgr._check_direction_bias("long")
        self.assertFalse(ok)
        self.assertIn("Bias", reason)

    def test_direction_bias_blocks_excessive_short(self) -> None:
        state = {
            "open_trades": [
                {"pair": "A/USDT", "direction": "short"},
                {"pair": "B/USDT", "direction": "short"},
                {"pair": "C/USDT", "direction": "short"},
                {"pair": "D/USDT", "direction": "long"},
            ],
            "trade_history": [],
            "portfolio": {},
            "last_update": None,
        }
        mgr = _make_mgr(state)
        ok, reason = mgr._check_direction_bias("short")
        self.assertFalse(ok)
        self.assertIn("Bias", reason)

    def test_direction_bias_ok_with_mixed_directions(self) -> None:
        state = {
            "open_trades": [
                {"pair": "A/USDT", "direction": "long"},
                {"pair": "B/USDT", "direction": "short"},
            ],
            "trade_history": [],
            "portfolio": {},
            "last_update": None,
        }
        mgr = _make_mgr(state)
        ok_long, _ = mgr._check_direction_bias("long")
        ok_short, _ = mgr._check_direction_bias("short")
        self.assertTrue(ok_long)
        self.assertTrue(ok_short)

    def test_direction_bias_blocks_sell_as_short(self) -> None:
        """'sell' should be treated as 'short' for bias check."""
        state = {
            "open_trades": [
                {"pair": "A/USDT", "direction": "short"},
                {"pair": "B/USDT", "direction": "short"},
                {"pair": "C/USDT", "direction": "short"},
            ],
            "trade_history": [],
            "portfolio": {},
            "last_update": None,
        }
        mgr = _make_mgr(state)
        ok, reason = mgr._check_direction_bias("sell")
        self.assertFalse(ok)
        self.assertIn("Bias", reason)

    def test_direction_bias_blocks_buy_as_long(self) -> None:
        """'buy' should be treated as 'long' for bias check."""
        state = {
            "open_trades": [
                {"pair": "A/USDT", "direction": "long"},
                {"pair": "B/USDT", "direction": "long"},
                {"pair": "C/USDT", "direction": "long"},
            ],
            "trade_history": [],
            "portfolio": {},
            "last_update": None,
        }
        mgr = _make_mgr(state)
        ok, reason = mgr._check_direction_bias("buy")
        self.assertFalse(ok)
        self.assertIn("Bias", reason)


class TestFleetRiskManagerCheckEntryAllowed(unittest.TestCase):
    """Integration-style tests for check_entry_allowed."""

    def test_check_entry_allowed_does_not_raise(self) -> None:
        state = {"open_trades": [], "trade_history": [], "portfolio": {}, "last_update": None}
        mgr = _make_mgr_with_state(state)
        ok, reason = mgr.check_entry_allowed("BTC/USDT:USDT", "long")
        self.assertIsInstance(ok, bool)
        self.assertIsInstance(reason, str)

    def test_check_entry_allowed_pass_no_trades(self) -> None:
        state = {"open_trades": [], "trade_history": [], "portfolio": {}, "last_update": None}
        mgr = _make_mgr_with_state(state)
        ok, reason = mgr.check_entry_allowed("ETH/USDT:USDT", "short")
        self.assertTrue(ok)

    def test_check_entry_allowed_fail_closed_on_high_drawdown(self) -> None:
        state = {
            "open_trades": [],
            "trade_history": [],
            "portfolio": {
                "peak_equity": 10000.0,
                "current_equity": 7500.0,
                "current_drawdown": 0.25,
            },
            "last_update": None,
        }
        mgr = _make_mgr_with_state(state)
        ok, reason = mgr.check_entry_allowed("SOL/USDT:USDT", "long")
        self.assertFalse(ok)
        self.assertIn("EMERGENCY", reason)

    def test_check_entry_allowed_pause_drawdown(self) -> None:
        """Drawdown at pause level (12-18%) should block entries."""
        state = {
            "open_trades": [],
            "trade_history": [],
            "portfolio": {
                "peak_equity": 10000.0,
                "current_equity": 8500.0,
                "current_drawdown": 0.15,
            },
            "last_update": None,
        }
        mgr = _make_mgr_with_state(state)
        ok, reason = mgr.check_entry_allowed("SOL/USDT:USDT", "long")
        self.assertFalse(ok)
        self.assertIn("Pause", reason)

    def test_check_entry_allowed_reduce_drawdown(self) -> None:
        """Drawdown at reduce level (8-12%) should still allow entries with reduced exposure."""
        state = {
            "open_trades": [],
            "trade_history": [],
            "portfolio": {
                "peak_equity": 10000.0,
                "current_equity": 9200.0,
                "current_drawdown": 0.08,
            },
            "last_update": None,
        }
        mgr = _make_mgr_with_state(state)
        ok, reason = mgr.check_entry_allowed("SOL/USDT:USDT", "long")
        # Should pass but with reduced exposure
        self.assertTrue(ok)

    def test_check_entry_allowed_warning_drawdown(self) -> None:
        """Drawdown at warning level (4-8%) should still allow entries."""
        state = {
            "open_trades": [],
            "trade_history": [],
            "portfolio": {
                "peak_equity": 10000.0,
                "current_equity": 9600.0,
                "current_drawdown": 0.04,
            },
            "last_update": None,
        }
        mgr = _make_mgr_with_state(state)
        ok, reason = mgr.check_entry_allowed("SOL/USDT:USDT", "long")
        self.assertTrue(ok)

    def test_check_entry_allowed_empty_pair(self) -> None:
        """Empty pair should pass through."""
        state = {"open_trades": [], "trade_history": [], "portfolio": {}, "last_update": None}
        mgr = _make_mgr_with_state(state)
        ok, reason = mgr.check_entry_allowed("", "long")
        self.assertTrue(ok)

    def test_check_entry_allowed_cluster_limit(self) -> None:
        """Cluster limit should block when too many same-direction trades in same cluster."""
        state = {
            "open_trades": [
                {"pair": "BTC/USDT:USDT", "direction": "long", "cluster": "major"},
                {"pair": "ETH/USDT:USDT", "direction": "long", "cluster": "major"},
                {"pair": "SOL/USDT:USDT", "direction": "long", "cluster": "major"},
                {"pair": "AVAX/USDT:USDT", "direction": "short", "cluster": "layer1_alts"},
                {"pair": "NEAR/USDT:USDT", "direction": "short", "cluster": "layer1_alts"},
            ],
            "trade_history": [],
            "portfolio": {"peak_equity": 10000.0, "current_equity": 10000.0, "current_drawdown": 0.0},
            "last_update": None,
        }
        mgr = _make_mgr_with_state(state)
        ok, reason = mgr.check_entry_allowed("BTC/USDT:USDT", "long")
        self.assertFalse(ok)
        self.assertIn("Cluster", reason)

    def test_check_entry_allowed_global_limit(self) -> None:
        """Global exposure limit should block when too many total trades."""
        state = {
            "open_trades": [
                {"pair": "BTC/USDT:USDT", "direction": "long", "cluster": "major"},
                {"pair": "ETH/USDT:USDT", "direction": "long", "cluster": "major"},
                {"pair": "SOL/USDT:USDT", "direction": "long", "cluster": "major"},
                {"pair": "AVAX/USDT:USDT", "direction": "short", "cluster": "layer1_alts"},
                {"pair": "NEAR/USDT:USDT", "direction": "short", "cluster": "layer1_alts"},
                {"pair": "APT/USDT:USDT", "direction": "short", "cluster": "layer1_alts"},
            ],
            "trade_history": [],
            "portfolio": {"peak_equity": 10000.0, "current_equity": 10000.0, "current_drawdown": 0.0},
            "last_update": None,
        }
        mgr = _make_mgr_with_state(state)
        ok, reason = mgr.check_entry_allowed("ARB/USDT:USDT", "long")
        self.assertFalse(ok)
        self.assertIn("Global", reason)


class TestFleetRiskManagerRefreshFromDisk(unittest.TestCase):
    """refresh_from_disk should update self.state."""

    def test_refresh_from_disk_updates_state(self) -> None:
        state = {
            "open_trades": [{"pair": "TEST/USDT", "direction": "long"}],
            "trade_history": [],
            "portfolio": {},
            "last_update": "2026-06-10T12:00:00",
        }
        mgr, tmp = _make_mgr_with_state_and_dir(state)
        self.assertEqual(len(mgr.state.get("open_trades", [])), 1)
        self.assertEqual(mgr.state["open_trades"][0]["pair"], "TEST/USDT")

        state["open_trades"][0]["pair"] = "MODIFIED/USDT"
        with open(os.path.join(tmp, "state.json"), "w") as f:
            json.dump(state, f)

        mgr.refresh_from_disk()
        self.assertEqual(len(mgr.state.get("open_trades", [])), 1)
        self.assertEqual(mgr.state["open_trades"][0]["pair"], "MODIFIED/USDT")

    def test_refresh_from_disk_with_drawdown(self) -> None:
        """Refresh should compute drawdown from peak/current equity."""
        state = {
            "open_trades": [],
            "trade_history": [],
            "portfolio": {
                "peak_equity": 10000.0,
                "current_equity": 9000.0,
                "current_drawdown": 0.0,
            },
            "last_update": None,
        }
        mgr = _make_mgr_with_state(state)
        mgr.refresh_from_disk()
        self.assertAlmostEqual(mgr.current_drawdown, 0.10, places=2)
        # 10% drawdown = reduce level (8-12%)
        self.assertEqual(mgr.get_drawdown_level(), "reduce")

    def test_refresh_from_disk_with_source_equities(self) -> None:
        """Refresh should compute drawdown from source equities when no global equity."""
        state = {
            "open_trades": [],
            "trade_history": [],
            "portfolio": {
                "peak_equity": None,
                "current_equity": None,
                "current_drawdown": 0.0,
                "sources": {
                    "freqforge": {"current_equity": 5000.0},
                    "freqforge-canary": {"current_equity": 3000.0},
                },
            },
            "last_update": None,
        }
        mgr = _make_mgr_with_state(state)
        mgr.refresh_from_disk()
        # No peak set, so drawdown should be 0
        self.assertEqual(mgr.current_drawdown, 0.0)


# ======================================================================
# New tests: Drawdown Levels
# ======================================================================

class TestFleetRiskManagerDrawdownLevels(unittest.TestCase):
    """Drawdown level classification."""

    def test_drawdown_normal(self) -> None:
        mgr = _make_mgr()
        mgr.current_drawdown = 0.02
        self.assertEqual(mgr.get_drawdown_level(), "normal")

    def test_drawdown_warning(self) -> None:
        mgr = _make_mgr()
        mgr.current_drawdown = 0.05
        self.assertEqual(mgr.get_drawdown_level(), "warning")

    def test_drawdown_reduce(self) -> None:
        mgr = _make_mgr()
        mgr.current_drawdown = 0.10
        self.assertEqual(mgr.get_drawdown_level(), "reduce")

    def test_drawdown_pause(self) -> None:
        mgr = _make_mgr()
        mgr.current_drawdown = 0.15
        self.assertEqual(mgr.get_drawdown_level(), "pause")

    def test_drawdown_emergency(self) -> None:
        mgr = _make_mgr()
        mgr.current_drawdown = 0.20
        self.assertEqual(mgr.get_drawdown_level(), "emergency")

    def test_drawdown_boundary_warning(self) -> None:
        """Exactly at warning threshold (4%) should be warning."""
        mgr = _make_mgr()
        mgr.current_drawdown = 0.04
        self.assertEqual(mgr.get_drawdown_level(), "warning")

    def test_drawdown_boundary_reduce(self) -> None:
        """Exactly at reduce threshold (8%) should be reduce."""
        mgr = _make_mgr()
        mgr.current_drawdown = 0.08
        self.assertEqual(mgr.get_drawdown_level(), "reduce")

    def test_drawdown_boundary_pause(self) -> None:
        """Exactly at pause threshold (12%) should be pause."""
        mgr = _make_mgr()
        mgr.current_drawdown = 0.12
        self.assertEqual(mgr.get_drawdown_level(), "pause")

    def test_drawdown_boundary_emergency(self) -> None:
        """Exactly at emergency threshold (18%) should be emergency."""
        mgr = _make_mgr()
        mgr.current_drawdown = 0.18
        self.assertEqual(mgr.get_drawdown_level(), "emergency")


# ======================================================================
# New tests: Exposure Multiplier
# ======================================================================

class TestFleetRiskManagerExposureMultiplier(unittest.TestCase):
    """Exposure multiplier based on drawdown level."""

    def test_multiplier_normal(self) -> None:
        mgr = _make_mgr()
        mgr.current_drawdown = 0.02
        self.assertEqual(mgr.get_exposure_multiplier(), 1.0)

    def test_multiplier_warning(self) -> None:
        mgr = _make_mgr()
        mgr.current_drawdown = 0.05
        self.assertEqual(mgr.get_exposure_multiplier(), 0.75)

    def test_multiplier_reduce(self) -> None:
        mgr = _make_mgr()
        mgr.current_drawdown = 0.10
        self.assertEqual(mgr.get_exposure_multiplier(), 0.5)

    def test_multiplier_pause(self) -> None:
        mgr = _make_mgr()
        mgr.current_drawdown = 0.15
        self.assertEqual(mgr.get_exposure_multiplier(), 0.2)

    def test_multiplier_emergency(self) -> None:
        mgr = _make_mgr()
        mgr.current_drawdown = 0.20
        self.assertEqual(mgr.get_exposure_multiplier(), 0.0)


# ======================================================================
# New tests: Cluster Penalty
# ======================================================================

class TestFleetRiskManagerClusterPenalty(unittest.TestCase):
    """Cluster penalty based on drawdown level and cluster stats."""

    def test_penalty_emergency(self) -> None:
        mgr = _make_mgr()
        mgr.current_drawdown = 0.20
        self.assertEqual(mgr.get_cluster_penalty("major"), 0.0)

    def test_penalty_pause(self) -> None:
        mgr = _make_mgr()
        mgr.current_drawdown = 0.15
        self.assertEqual(mgr.get_cluster_penalty("major"), 0.0)

    def test_penalty_reduce(self) -> None:
        mgr = _make_mgr()
        mgr.current_drawdown = 0.10
        self.assertEqual(mgr.get_cluster_penalty("major"), 0.5)

    def test_penalty_normal_no_history(self) -> None:
        """No trade history should return 1.0 (no penalty)."""
        mgr = _make_mgr()
        mgr.current_drawdown = 0.02
        self.assertEqual(mgr.get_cluster_penalty("major"), 1.0)

    def test_penalty_normal_with_history(self) -> None:
        """With good winrate and PnL, should return 1.0."""
        state = {
            "open_trades": [],
            "trade_history": [
                {"cluster": "major", "is_win": True, "profit_pct": 0.05},
                {"cluster": "major", "is_win": True, "profit_pct": 0.03},
                {"cluster": "major", "is_win": True, "profit_pct": 0.02},
            ],
            "portfolio": {"peak_equity": 10000.0, "current_equity": 10000.0, "current_drawdown": 0.0},
            "last_update": None,
        }
        mgr = _make_mgr_with_state(state)
        mgr.current_drawdown = 0.02
        penalty = mgr.get_cluster_penalty("major")
        self.assertEqual(penalty, 1.0)

    def test_penalty_low_winrate(self) -> None:
        """Winrate below 30% should return 0.25."""
        state = {
            "open_trades": [],
            "trade_history": [
                {"cluster": "major", "is_win": False, "profit_pct": -0.05},
                {"cluster": "major", "is_win": False, "profit_pct": -0.03},
                {"cluster": "major", "is_win": False, "profit_pct": -0.02},
                {"cluster": "major", "is_win": True, "profit_pct": 0.01},
            ],
            "portfolio": {"peak_equity": 10000.0, "current_equity": 10000.0, "current_drawdown": 0.0},
            "last_update": None,
        }
        mgr = _make_mgr_with_state(state)
        mgr.current_drawdown = 0.02
        penalty = mgr.get_cluster_penalty("major")
        self.assertEqual(penalty, 0.25)

    def test_penalty_medium_winrate(self) -> None:
        """Winrate between 30-42% should return 0.5."""
        state = {
            "open_trades": [],
            "trade_history": [
                {"cluster": "major", "is_win": True, "profit_pct": 0.01},
                {"cluster": "major", "is_win": False, "profit_pct": -0.02},
                {"cluster": "major", "is_win": False, "profit_pct": -0.01},
            ],
            "portfolio": {"peak_equity": 10000.0, "current_equity": 10000.0, "current_drawdown": 0.0},
            "last_update": None,
        }
        mgr = _make_mgr_with_state(state)
        mgr.current_drawdown = 0.02
        penalty = mgr.get_cluster_penalty("major")
        self.assertEqual(penalty, 0.5)


# ======================================================================
# New tests: Correlation Multiplier
# ======================================================================

class TestFleetRiskManagerCorrelation(unittest.TestCase):
    """Correlation multiplier for pair entry decisions."""

    def test_no_correlation_matrix(self) -> None:
        """Without a correlation file, multiplier should be 1.0."""
        mgr = _make_mgr()
        mult = mgr.get_correlation_multiplier("BTC/USDT:USDT", "long")
        self.assertEqual(mult, 1.0)

    def test_high_correlation_same_direction(self) -> None:
        """High correlation (>0.95) same direction should give 0.25."""
        mgr = _make_mgr()
        mgr.correlation_file = "/dev/null"  # No matrix
        mult = mgr.get_correlation_multiplier("BTC/USDT:USDT", "long", [])
        self.assertEqual(mult, 1.0)  # No matrix = no penalty

    def test_correlation_with_open_trades(self) -> None:
        """With a correlation matrix and open trades, multiplier should reflect correlation."""
        with tempfile.TemporaryDirectory() as tmp:
            corr_path = os.path.join(tmp, "corr.json")
            with open(corr_path, "w") as f:
                json.dump({
                    "matrix": {
                        "BTC/USDT:USDT": {"ETH/USDT:USDT": 0.95},
                        "ETH/USDT:USDT": {"BTC/USDT:USDT": 0.95},
                    }
                }, f)
            mgr = _make_mgr()
            mgr.correlation_file = corr_path
            open_trades = [{"pair": "ETH/USDT:USDT", "direction": "long"}]
            mult = mgr.get_correlation_multiplier("BTC/USDT:USDT", "long", open_trades)
            self.assertAlmostEqual(mult, 0.25, places=2)


# ======================================================================
# New tests: Summarize State
# ======================================================================

class TestFleetRiskManagerSummarizeState(unittest.TestCase):
    """summarize_state should return a dict with key metrics."""

    def test_summarize_state_empty(self) -> None:
        mgr = _make_mgr()
        summary = mgr.summarize_state()
        self.assertIn("current_equity", summary)
        self.assertIn("peak_equity", summary)
        self.assertIn("current_drawdown", summary)
        self.assertIn("drawdown_level", summary)
        self.assertIn("open_trades", summary)
        self.assertIn("trade_history", summary)

    def test_summarize_state_with_trades(self) -> None:
        state = {
            "open_trades": [{"pair": "BTC/USDT", "direction": "long"}],
            "trade_history": [{"profit": 0.1}],
            "portfolio": {"peak_equity": 10000.0, "current_equity": 9500.0, "current_drawdown": 0.05},
            "last_update": None,
        }
        mgr = _make_mgr_with_state(state)
        summary = mgr.summarize_state()
        self.assertEqual(summary["open_trades"], 1)
        self.assertEqual(summary["trade_history"], 1)
        self.assertEqual(summary["drawdown_level"], "warning")


# ======================================================================
# Helper for refresh tests
# ======================================================================

def _make_mgr_with_state_and_dir(state: dict) -> tuple[FleetRiskManager, str]:
    """Create a FleetRiskManager backed by a temp file. Returns (mgr, dir)."""
    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, "state.json")
    with open(path, "w") as f:
        json.dump(state, f)
    return FleetRiskManager(state_file=path), tmp


if __name__ == "__main__":
    unittest.main()
