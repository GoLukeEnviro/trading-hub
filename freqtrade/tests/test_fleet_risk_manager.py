"""
FleetRiskManager Unit Tests
Tests state initialization, direction bias, and entry gate behavior.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))

from fleet_risk_manager import FleetRiskManager  # noqa: E402


class TestFleetRiskManagerInit(unittest.TestCase):
    """Verify the manager constructs without error and self.state exists."""

    def _make_mgr(self, state: dict | None = None) -> FleetRiskManager:
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

    def test_init_does_not_raise(self) -> None:
        """The primary bug: constructing a FleetRiskManager must not raise AttributeError."""
        mgr = self._make_mgr()
        self.assertIsNotNone(mgr.state)
        self.assertIsInstance(mgr.state, dict)

    def test_init_with_state_file_missing(self) -> None:
        """When the state file does not exist, the manager should fall back to default state."""
        with tempfile.TemporaryDirectory() as tmp:
            missing = os.path.join(tmp, "does_not_exist.json")
            mgr = FleetRiskManager(state_file=missing)
            self.assertIsNotNone(mgr.state)
            self.assertIn("open_trades", mgr.state)
            self.assertEqual(mgr.state.get("open_trades"), [])

    def test_init_with_invalid_state_file(self) -> None:
        """When the state file contains invalid JSON, the manager should fall back to default."""
        with tempfile.TemporaryDirectory() as tmp:
            bad = os.path.join(tmp, "bad.json")
            with open(bad, "w") as f:
                f.write("not valid json")
            mgr = FleetRiskManager(state_file=bad)
            self.assertIsNotNone(mgr.state)
            self.assertEqual(mgr.state.get("open_trades"), [])

    def test_init_with_valid_state_file(self) -> None:
        """When the state file contains valid JSON, the manager should load it."""
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

    def test_check_entry_allowed_handles_missing_state(self) -> None:
        """Regression: _check_direction_bias must not crash if self.state is missing."""
        mgr = FleetRiskManager.__new__(FleetRiskManager)
        # Intentionally do NOT call __init__ — this simulates the edge case
        # where self.state was never set (pickle/unpickle, race condition).
        mgr.state_file = "/dev/null"
        result = mgr._check_direction_bias("long")
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)


class TestFleetRiskManagerDirectionBias(unittest.TestCase):
    """Direction bias gate — this method crashed before the fix."""

    def _make_mgr(self, state: dict | None = None) -> FleetRiskManager:
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

    def test_direction_bias_does_not_raise(self) -> None:
        """_check_direction_bias must not raise AttributeError even with no open trades."""
        mgr = self._make_mgr()
        ok, reason = mgr._check_direction_bias("long")
        self.assertTrue(ok)
        self.assertIn("OK", reason)

    def test_direction_bias_passes_with_few_trades(self) -> None:
        """With fewer than 2 open trades, bias check should pass."""
        state = {
            "open_trades": [{"pair": "BTC/USDT", "direction": "long"}],
            "trade_history": [],
            "portfolio": {},
            "last_update": None,
        }
        mgr = self._make_mgr(state)
        ok, reason = mgr._check_direction_bias("long")
        self.assertTrue(ok)
        self.assertIn("OK", reason)

    def test_direction_bias_blocks_excessive_long(self) -> None:
        """>70% long trades should be blocked."""
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
        mgr = self._make_mgr(state)
        ok, reason = mgr._check_direction_bias("long")
        self.assertFalse(ok)
        self.assertIn("Bias", reason)

    def test_direction_bias_blocks_excessive_short(self) -> None:
        """>70% short trades should be blocked."""
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
        mgr = self._make_mgr(state)
        ok, reason = mgr._check_direction_bias("short")
        self.assertFalse(ok)
        self.assertIn("Bias", reason)

    def test_direction_bias_ok_with_mixed_directions(self) -> None:
        """A balanced 50:50 split should pass."""
        state = {
            "open_trades": [
                {"pair": "A/USDT", "direction": "long"},
                {"pair": "B/USDT", "direction": "short"},
            ],
            "trade_history": [],
            "portfolio": {},
            "last_update": None,
        }
        mgr = self._make_mgr(state)
        ok_long, _ = mgr._check_direction_bias("long")
        ok_short, _ = mgr._check_direction_bias("short")
        self.assertTrue(ok_long)
        self.assertTrue(ok_short)


class TestFleetRiskManagerCheckEntryAllowed(unittest.TestCase):
    """Integration-style tests for check_entry_allowed."""

    def _make_mgr_with_state(self, state: dict) -> FleetRiskManager:
        """Create a FleetRiskManager backed by a temp file with the given state."""
        tmp = tempfile.mkdtemp()
        path = os.path.join(tmp, "state.json")
        with open(path, "w") as f:
            json.dump(state, f)
        return FleetRiskManager(state_file=path)

    def test_check_entry_allowed_does_not_raise(self) -> None:
        """check_entry_allowed must not raise AttributeError — the full signal path."""
        state = {"open_trades": [], "trade_history": [], "portfolio": {}, "last_update": None}
        mgr = self._make_mgr_with_state(state)
        ok, reason = mgr.check_entry_allowed("BTC/USDT:USDT", "long")
        self.assertIsInstance(ok, bool)
        self.assertIsInstance(reason, str)

    def test_check_entry_allowed_pass_no_trades(self) -> None:
        """With no trades and no drawdown, entry should be allowed."""
        state = {"open_trades": [], "trade_history": [], "portfolio": {}, "last_update": None}
        mgr = self._make_mgr_with_state(state)
        ok, reason = mgr.check_entry_allowed("ETH/USDT:USDT", "short")
        self.assertTrue(ok)

    def test_check_entry_allowed_fail_closed_on_high_drawdown(self) -> None:
        """When the state file records drawdown > emergency threshold, entry should be blocked."""
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
        mgr = self._make_mgr_with_state(state)
        ok, reason = mgr.check_entry_allowed("SOL/USDT:USDT", "long")
        self.assertFalse(ok)
        self.assertIn("EMERGENCY", reason)


class TestFleetRiskManagerRefreshFromDisk(unittest.TestCase):
    """refresh_from_disk should update self.state."""

    def _make_mgr_with_state(self, state: dict) -> tuple[FleetRiskManager, str]:
        """Create a FleetRiskManager backed by a temp file. Returns (mgr, dir)."""
        tmp = tempfile.mkdtemp()
        path = os.path.join(tmp, "state.json")
        with open(path, "w") as f:
            json.dump(state, f)
        return FleetRiskManager(state_file=path), tmp

    def test_refresh_from_disk_updates_state(self) -> None:
        """After refresh_from_disk, self.state should be updated."""
        state = {
            "open_trades": [{"pair": "TEST/USDT", "direction": "long"}],
            "trade_history": [],
            "portfolio": {},
            "last_update": "2026-06-10T12:00:00",
        }
        mgr, tmp = self._make_mgr_with_state(state)
        self.assertEqual(len(mgr.state.get("open_trades", [])), 1)
        self.assertEqual(mgr.state["open_trades"][0]["pair"], "TEST/USDT")

        # Modify file
        state["open_trades"][0]["pair"] = "MODIFIED/USDT"
        with open(os.path.join(tmp, "state.json"), "w") as f:
            json.dump(state, f)

        mgr.refresh_from_disk()
        self.assertEqual(len(mgr.state.get("open_trades", [])), 1)
        self.assertEqual(mgr.state["open_trades"][0]["pair"], "MODIFIED/USDT")


if __name__ == "__main__":
    unittest.main()
