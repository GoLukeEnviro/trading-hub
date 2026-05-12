"""
FleetGuard v1 Unit Tests
Tests entry guard logic including pair/side loss locks and drawdown protection.
"""
import sys
import unittest

sys.path.insert(0, "/home/hermes/projects/trading/freqtrade/shared")
from fleetguard_v1 import FleetGuard, FleetGuardConfig, REASON_CODES


class TestFleetGuardBasic(unittest.TestCase):
    """Basic entry checks — empty context."""

    def setUp(self):
        self.fg = FleetGuard(FleetGuardConfig(
            max_open_trades=3,
            max_open_shorts=2,
            max_open_longs=2,
            pair_loss_lock_after_losses=3,
            side_loss_lock_after_losses=2,
            daily_drawdown_soft_limit=0.03,
            daily_drawdown_hard_limit=0.05,
        ))

    def test_pass_with_no_trades(self):
        allowed, reason = self.fg.check_entry(
            pair="BTC/USDT:USDT", side="long",
            open_trades=[], recent_closed_trades=[], current_drawdown_pct=0.0
        )
        self.assertTrue(allowed)
        self.assertEqual(reason, "fleetguard_pass")

    def test_max_open_trades(self):
        trades = [{"pair": "X", "is_short": False}] * 3
        allowed, reason = self.fg.check_entry(
            pair="BTC/USDT:USDT", side="long",
            open_trades=trades, recent_closed_trades=[], current_drawdown_pct=0.0
        )
        self.assertFalse(allowed)
        self.assertIn("max_open_trades", reason)

    def test_max_open_shorts(self):
        trades = [{"pair": "X", "is_short": True}, {"pair": "Y", "is_short": True}]
        allowed, reason = self.fg.check_entry(
            pair="BTC/USDT:USDT", side="short",
            open_trades=trades, recent_closed_trades=[], current_drawdown_pct=0.0
        )
        self.assertFalse(allowed)
        self.assertIn("max_open_shorts", reason)

    def test_max_open_longs(self):
        trades = [{"pair": "X", "is_short": False}, {"pair": "Y", "is_short": False}]
        allowed, reason = self.fg.check_entry(
            pair="BTC/USDT:USDT", side="long",
            open_trades=trades, recent_closed_trades=[], current_drawdown_pct=0.0
        )
        self.assertFalse(allowed)
        self.assertIn("max_open_longs", reason)


class TestFleetGuardPairLossLock(unittest.TestCase):
    """pair_loss_lock triggers after N recent losses on the same pair."""

    def setUp(self):
        self.fg = FleetGuard(FleetGuardConfig(
            max_open_trades=10,
            max_open_shorts=5,
            max_open_longs=5,
            pair_loss_lock_after_losses=3,
            side_loss_lock_after_losses=10,  # high to isolate pair test
        ))

    def test_pair_loss_lock_triggers(self):
        """3 losses on same pair triggers pair_loss_lock."""
        recent_closed = [
            {"pair": "BTC/USDT:USDT", "is_short": False, "close_profit": -0.02},
            {"pair": "BTC/USDT:USDT", "is_short": True, "close_profit": -0.03},
            {"pair": "BTC/USDT:USDT", "is_short": False, "close_profit": -0.01},
        ]
        allowed, reason = self.fg.check_entry(
            pair="BTC/USDT:USDT", side="long",
            open_trades=[], recent_closed_trades=recent_closed, current_drawdown_pct=0.0
        )
        self.assertFalse(allowed)
        self.assertIn("pair_loss_lock", reason)
        self.assertIn("3_losses", reason)

    def test_pair_loss_lock_does_not_trigger_with_wins(self):
        """Mix of wins and losses under threshold should pass."""
        recent_closed = [
            {"pair": "BTC/USDT:USDT", "is_short": False, "close_profit": -0.02},
            {"pair": "BTC/USDT:USDT", "is_short": False, "close_profit": 0.01},
            {"pair": "BTC/USDT:USDT", "is_short": False, "close_profit": -0.01},
        ]
        allowed, reason = self.fg.check_entry(
            pair="BTC/USDT:USDT", side="long",
            open_trades=[], recent_closed_trades=recent_closed, current_drawdown_pct=0.0
        )
        self.assertTrue(allowed)
        self.assertEqual(reason, "fleetguard_pass")

    def test_pair_loss_lock_different_pair(self):
        """Losses on a different pair should not lock this pair."""
        recent_closed = [
            {"pair": "ETH/USDT:USDT", "is_short": False, "close_profit": -0.02},
            {"pair": "ETH/USDT:USDT", "is_short": True, "close_profit": -0.03},
            {"pair": "ETH/USDT:USDT", "is_short": False, "close_profit": -0.01},
        ]
        allowed, reason = self.fg.check_entry(
            pair="BTC/USDT:USDT", side="long",
            open_trades=[], recent_closed_trades=recent_closed, current_drawdown_pct=0.0
        )
        self.assertTrue(allowed)


class TestFleetGuardSideLossLock(unittest.TestCase):
    """side_loss_lock triggers after N recent losses on the same side."""

    def setUp(self):
        self.fg = FleetGuard(FleetGuardConfig(
            max_open_trades=10,
            max_open_shorts=5,
            max_open_longs=5,
            pair_loss_lock_after_losses=10,  # high to isolate side test
            side_loss_lock_after_losses=2,
        ))

    def test_side_loss_lock_triggers_for_short(self):
        """2 short losses triggers side_loss_lock for short side."""
        recent_closed = [
            {"pair": "BTC/USDT:USDT", "is_short": True, "close_profit": -0.02},
            {"pair": "ETH/USDT:USDT", "is_short": True, "close_profit": -0.03},
        ]
        allowed, reason = self.fg.check_entry(
            pair="SOL/USDT:USDT", side="short",
            open_trades=[], recent_closed_trades=recent_closed, current_drawdown_pct=0.0
        )
        self.assertFalse(allowed)
        self.assertIn("side_loss_lock", reason)
        self.assertIn("2_losses", reason)

    def test_side_loss_lock_triggers_for_long(self):
        """2 long losses triggers side_loss_lock for long side."""
        recent_closed = [
            {"pair": "BTC/USDT:USDT", "is_short": False, "close_profit": -0.02},
            {"pair": "ETH/USDT:USDT", "is_short": False, "close_profit": -0.03},
        ]
        allowed, reason = self.fg.check_entry(
            pair="SOL/USDT:USDT", side="long",
            open_trades=[], recent_closed_trades=recent_closed, current_drawdown_pct=0.0
        )
        self.assertFalse(allowed)
        self.assertIn("side_loss_lock", reason)

    def test_side_loss_lock_does_not_block_opposite_side(self):
        """Short losses should NOT block long entry."""
        recent_closed = [
            {"pair": "BTC/USDT:USDT", "is_short": True, "close_profit": -0.02},
            {"pair": "ETH/USDT:USDT", "is_short": True, "close_profit": -0.03},
        ]
        allowed, reason = self.fg.check_entry(
            pair="SOL/USDT:USDT", side="long",
            open_trades=[], recent_closed_trades=recent_closed, current_drawdown_pct=0.0
        )
        self.assertTrue(allowed)

    def test_side_loss_lock_allows_with_wins_mixed(self):
        """1 loss + 1 win on same side should NOT trigger side_loss_lock."""
        recent_closed = [
            {"pair": "BTC/USDT:USDT", "is_short": True, "close_profit": -0.02},
            {"pair": "ETH/USDT:USDT", "is_short": True, "close_profit": 0.01},
        ]
        allowed, reason = self.fg.check_entry(
            pair="SOL/USDT:USDT", side="short",
            open_trades=[], recent_closed_trades=recent_closed, current_drawdown_pct=0.0
        )
        self.assertTrue(allowed)


class TestFleetGuardDrawdown(unittest.TestCase):
    """Drawdown guard — soft warning vs hard block."""

    def setUp(self):
        self.fg = FleetGuard(FleetGuardConfig(
            max_open_trades=10,
            daily_drawdown_soft_limit=0.03,
            daily_drawdown_hard_limit=0.05,
        ))

    def test_drawdown_hard_blocks(self):
        allowed, reason = self.fg.check_entry(
            pair="BTC/USDT:USDT", side="long",
            open_trades=[], recent_closed_trades=[], current_drawdown_pct=0.06
        )
        self.assertFalse(allowed)
        self.assertIn("drawdown_hard", reason)

    def test_drawdown_soft_allows(self):
        allowed, reason = self.fg.check_entry(
            pair="BTC/USDT:USDT", side="long",
            open_trades=[], recent_closed_trades=[], current_drawdown_pct=0.04
        )
        self.assertTrue(allowed)
        self.assertEqual(reason, "fleetguard_pass")

    def test_no_drawdown_allows(self):
        allowed, reason = self.fg.check_entry(
            pair="BTC/USDT:USDT", side="long",
            open_trades=[], recent_closed_trades=[], current_drawdown_pct=0.0
        )
        self.assertTrue(allowed)


class TestFleetGuardVolatility(unittest.TestCase):
    """Volatility ATR guard."""

    def setUp(self):
        self.fg = FleetGuard(FleetGuardConfig(
            max_open_trades=10,
            volatility_atr_min_pct=0.001,
            volatility_atr_max_pct=0.08,
        ))

    def test_volatility_too_low(self):
        allowed, reason = self.fg.check_entry(
            pair="BTC/USDT:USDT", side="long",
            open_trades=[], recent_closed_trades=[], current_drawdown_pct=0.0,
            atr_pct=0.0005
        )
        self.assertFalse(allowed)
        self.assertIn("volatility_too_low", reason)

    def test_volatility_too_high(self):
        allowed, reason = self.fg.check_entry(
            pair="BTC/USDT:USDT", side="long",
            open_trades=[], recent_closed_trades=[], current_drawdown_pct=0.0,
            atr_pct=0.10
        )
        self.assertFalse(allowed)
        self.assertIn("volatility_too_high", reason)

    def test_volatility_ok(self):
        allowed, reason = self.fg.check_entry(
            pair="BTC/USDT:USDT", side="long",
            open_trades=[], recent_closed_trades=[], current_drawdown_pct=0.0,
            atr_pct=0.03
        )
        self.assertTrue(allowed)

    def test_no_atr_passes(self):
        """Without atr_pct, volatility check is skipped."""
        allowed, reason = self.fg.check_entry(
            pair="BTC/USDT:USDT", side="long",
            open_trades=[], recent_closed_trades=[], current_drawdown_pct=0.0
        )
        self.assertTrue(allowed)


class TestFleetGuardDisabled(unittest.TestCase):
    """Disabled FleetGuard passes everything."""

    def test_disabled_passes(self):
        fg = FleetGuard(FleetGuardConfig(enabled=False))
        allowed, reason = fg.check_entry(
            pair="BTC/USDT:USDT", side="long",
            open_trades=[], recent_closed_trades=[], current_drawdown_pct=0.99
        )
        self.assertTrue(allowed)
        self.assertEqual(reason, "fleetguard_disabled")


class TestReasonCodes(unittest.TestCase):
    """Verify REASON_CODES dict exists and has expected keys."""

    def test_reason_codes_has_expected_keys(self):
        expected = [
            "fleetguard_pass", "fleetguard_disabled", "max_open_trades",
            "max_open_shorts", "max_open_longs", "pair_loss_lock",
            "side_loss_lock", "drawdown_hard", "drawdown_soft",
            "volatility_too_low", "volatility_too_high",
        ]
        for key in expected:
            self.assertIn(key, REASON_CODES, f"Missing REASON_CODES key: {key}")
            self.assertIsInstance(REASON_CODES[key], str)
            self.assertTrue(len(REASON_CODES[key]) > 0)


if __name__ == "__main__":
    unittest.main()
