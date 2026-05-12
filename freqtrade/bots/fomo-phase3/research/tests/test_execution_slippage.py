"""Tests for execution: slippage, position sizing, funding, trailing stop."""
import numpy as np
import pandas as pd
import pytest

from fomo_phase3.config import StrategyConfig
from fomo_phase3.execution import (
    OpenPosition,
    apply_entry_slippage,
    apply_exit_slippage,
    direction_sign,
    is_funding_timestamp,
    process_funding,
    reset_position_counter,
    update_trailing_stop,
)


@pytest.fixture(autouse=True)
def reset_pos_counter():
    reset_position_counter()
    yield


@pytest.fixture
def cfg() -> StrategyConfig:
    return StrategyConfig()


class TestDirectionSign:

    def test_long_is_positive(self):
        assert direction_sign("LONG") == 1

    def test_short_is_negative(self):
        assert direction_sign("SHORT") == -1


class TestSlippage:

    @pytest.mark.parametrize("direction,price,expected_mult", [
        ("LONG", 100.0, 1.001),   # +0.1%
        ("SHORT", 100.0, 0.999),  # -0.1%
    ])
    def test_entry_slippage_direction(self, direction, price, expected_mult, cfg):
        result = apply_entry_slippage(price, direction, cfg)
        assert result == pytest.approx(price * expected_mult)

    @pytest.mark.parametrize("direction,price,expected_mult", [
        ("LONG", 100.0, 0.999),   # -0.1%
        ("SHORT", 100.0, 1.001),  # +0.1%
    ])
    def test_exit_slippage_direction(self, direction, price, expected_mult, cfg):
        result = apply_exit_slippage(price, direction, cfg)
        assert result == pytest.approx(price * expected_mult)


class TestIsFundingTimestamp:

    @pytest.mark.parametrize("hour", [0, 8, 16])
    def test_funding_hours_recognized(self, hour, cfg):
        ts = pd.Timestamp(f"2024-01-01 {hour:02d}:00:00", tz="UTC")
        assert is_funding_timestamp(ts, cfg)

    @pytest.mark.parametrize("hour", [1, 4, 9, 15, 23])
    def test_non_funding_hours_ignored(self, hour, cfg):
        ts = pd.Timestamp(f"2024-01-01 {hour:02d}:00:00", tz="UTC")
        assert not is_funding_timestamp(ts, cfg)

    def test_simulate_funding_disabled(self, cfg):
        cfg_no_funding = StrategyConfig(simulate_funding=False)
        ts = pd.Timestamp("2024-01-01 00:00:00", tz="UTC")
        assert not is_funding_timestamp(ts, cfg_no_funding)


class TestProcessFunding:

    def test_long_pays_positive_funding(self, cfg):
        """With positive funding, long pays (equity decreases)."""
        pos = OpenPosition(
            direction="LONG", entry_idx=0,
            entry_time=pd.Timestamp("2024-01-01", tz="UTC"),
            entry_price=100.0, qty=1.0, remaining_qty=1.0,
            sl=99.0, tp1=102.0, tp2=105.0, atr=1.0,
        )
        row = pd.Series({
            "timestamp": "2024-01-01 00:00:00+00:00",
            "close": 100.0,
            "funding_rate": 0.001,  # positive = longs pay shorts
        })
        equity = 10000.0
        new_equity, funding_pnl = process_funding(pos, row, equity, cfg)
        assert funding_pnl < 0  # long pays
        assert new_equity < equity
        assert pos.funding_pnl_accumulated < 0

    def test_short_receives_positive_funding(self, cfg):
        """With positive funding, short receives (equity increases)."""
        pos = OpenPosition(
            direction="SHORT", entry_idx=0,
            entry_time=pd.Timestamp("2024-01-01", tz="UTC"),
            entry_price=100.0, qty=1.0, remaining_qty=1.0,
            sl=101.0, tp1=98.0, tp2=95.0, atr=1.0,
        )
        row = pd.Series({
            "timestamp": "2024-01-01 00:00:00+00:00",
            "close": 100.0,
            "funding_rate": 0.001,  # positive = shorts receive
        })
        equity = 10000.0
        new_equity, funding_pnl = process_funding(pos, row, equity, cfg)
        assert funding_pnl > 0  # short receives
        assert new_equity > equity
        assert pos.funding_pnl_accumulated > 0

    def test_no_funding_on_wrong_hour(self, cfg):
        pos = OpenPosition(
            direction="LONG", entry_idx=0,
            entry_time=pd.Timestamp("2024-01-01", tz="UTC"),
            entry_price=100.0, qty=1.0, remaining_qty=1.0,
            sl=99.0, tp1=102.0, tp2=105.0, atr=1.0,
        )
        row = pd.Series({
            "timestamp": "2024-01-01 03:00:00+00:00",
            "close": 100.0,
            "funding_rate": 0.001,
        })
        equity = 10000.0
        new_equity, funding_pnl = process_funding(pos, row, equity, cfg)
        assert funding_pnl == 0.0
        assert new_equity == equity


class TestUpdateTrailingStop:

    def test_trailing_not_active_before_tp1(self, cfg):
        """Trailing should only activate after TP1."""
        pos = OpenPosition(
            direction="LONG", entry_idx=0,
            entry_time=pd.Timestamp("2024-01-01", tz="UTC"),
            entry_price=100.0, qty=1.0, remaining_qty=0.4,  # after TP1
            sl=99.0, tp1=102.0, tp2=105.0, atr=1.0,
            tp1_done=False,
        )
        original_sl = pos.sl
        row = pd.Series({"close": 103.0})
        update_trailing_stop(pos, row, cfg)
        assert pos.sl == original_sl  # unchanged because tp1_done=False

    def test_trailing_raises_sl_after_tp1_long(self, cfg):
        """After TP1, trailing should raise SL as price goes up."""
        pos = OpenPosition(
            direction="LONG", entry_idx=0,
            entry_time=pd.Timestamp("2024-01-01", tz="UTC"),
            entry_price=100.0, qty=1.0, remaining_qty=0.4,
            sl=100.5, tp1=102.0, tp2=105.0, atr=1.0,
            tp1_done=True,
        )
        # Price rose to 104, trail = 104 - 0.8*1.0 = 103.2
        row = pd.Series({"close": 104.0})
        update_trailing_stop(pos, row, cfg)
        assert pos.sl == pytest.approx(104.0 - 0.8 * 1.0)

    def test_trailing_does_not_lower_sl_long(self, cfg):
        """Trailing should never lower the SL below current level."""
        pos = OpenPosition(
            direction="LONG", entry_idx=0,
            entry_time=pd.Timestamp("2024-01-01", tz="UTC"),
            entry_price=100.0, qty=1.0, remaining_qty=0.4,
            sl=101.0, tp1=102.0, tp2=105.0, atr=1.0,
            tp1_done=True,
        )
        row = pd.Series({"close": 101.5})
        update_trailing_stop(pos, row, cfg)
        # trail = 101.5 - 0.8 = 100.7, which is below current SL of 101.0
        assert pos.sl == 101.0  # unchanged
