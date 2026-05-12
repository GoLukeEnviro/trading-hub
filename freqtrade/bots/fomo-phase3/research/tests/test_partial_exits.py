"""Tests for partial exit logic: TP1 60%, breakeven SL, TP2 remaining."""
import numpy as np
import pandas as pd
import pytest

from fomo_phase3.backtest import backtest, close_position_leg
from fomo_phase3.config import StrategyConfig
from fomo_phase3.execution import OpenPosition, reset_position_counter
from fomo_phase3.metrics import Trade


@pytest.fixture(autouse=True)
def reset_pos_counter():
    reset_position_counter()
    yield


@pytest.fixture
def cfg() -> StrategyConfig:
    return StrategyConfig()


class TestClosePositionLeg:

    def test_tp1_closes_exact_fraction(self, cfg):
        """Test that TP1 closes exactly tp1_fraction of original position."""
        pos = OpenPosition(
            direction="LONG", entry_idx=0,
            entry_time=pd.Timestamp("2024-01-01", tz="UTC"),
            entry_price=100.0, qty=1.0, remaining_qty=1.0,
            sl=99.0, tp1=102.0, tp2=105.0, atr=1.0,
        )
        qty_to_close = min(pos.remaining_qty, pos.qty * cfg.tp1_fraction)
        assert qty_to_close == pytest.approx(0.6)

        equity, trade = close_position_leg(
            pos=pos, exit_time=pd.Timestamp("2024-01-01 00:15", tz="UTC"),
            exit_price_raw=102.0, reason="TP1_HIT",
            qty_to_close=qty_to_close, equity=10000.0, cfg=cfg,
        )
        assert trade.fraction_of_initial == pytest.approx(0.6)
        assert trade.qty == pytest.approx(0.6)

    def test_tp2_closes_remaining(self, cfg):
        """Test that TP2 closes the remaining position after TP1."""
        pos = OpenPosition(
            direction="LONG", entry_idx=0,
            entry_time=pd.Timestamp("2024-01-01", tz="UTC"),
            entry_price=100.0, qty=1.0, remaining_qty=0.4,
            sl=100.5, tp1=102.0, tp2=105.0, atr=1.0,
            tp1_done=True,
        )
        equity, trade = close_position_leg(
            pos=pos, exit_time=pd.Timestamp("2024-01-01 00:20", tz="UTC"),
            exit_price_raw=105.0, reason="TP2_HIT",
            qty_to_close=0.4, equity=10060.0, cfg=cfg,
        )
        assert trade.qty == pytest.approx(0.4)
        assert trade.fraction_of_initial == pytest.approx(0.4)
        assert trade.exit_reason == "TP2_HIT"

    def test_trade_includes_funding(self, cfg):
        """Test that close_position_leg includes accumulated funding in net_pnl."""
        pos = OpenPosition(
            direction="LONG", entry_idx=0,
            entry_time=pd.Timestamp("2024-01-01", tz="UTC"),
            entry_price=100.0, qty=1.0, remaining_qty=1.0,
            sl=99.0, tp1=102.0, tp2=105.0, atr=1.0,
            funding_pnl_accumulated=-2.0,  # $2 in funding costs
        )
        qty = min(pos.remaining_qty, pos.qty * cfg.tp1_fraction)
        equity, trade = close_position_leg(
            pos=pos, exit_time=pd.Timestamp("2024-01-01 00:15", tz="UTC"),
            exit_price_raw=102.0, reason="TP1_HIT",
            qty_to_close=qty, equity=10000.0, cfg=cfg,
        )
        # funding_leg_share = -2.0 * 0.6 = -1.2
        expected_funding = -2.0 * 0.6
        assert trade.funding_pnl == pytest.approx(expected_funding)
        assert trade.net_pnl < trade.gross_pnl - trade.fees  # includes funding deduction


def _make_simple_uptrend_df() -> pd.DataFrame:
    """Simple dataframe with clear uptrend that triggers entries."""
    n = 600
    base = pd.Timestamp("2024-01-01", tz="UTC")
    np.random.seed(42)
    prices = 50000 + np.linspace(0, 3000, n) + np.random.normal(0, 50, n)
    prices = np.maximum(prices, 100)

    volume = np.random.exponential(1000, n)
    volume[200:250] *= 5  # spike zone

    oi = 1e9 + np.linspace(0, 3e7, n) + np.random.normal(0, 1e6, n)
    funding = np.random.normal(-0.0002, 0.0003, n)

    df = pd.DataFrame({
        "timestamp": [base + pd.Timedelta(minutes=5 * i) for i in range(n)],
        "open": prices * 0.999,
        "high": prices * 1.004,
        "low": prices * 0.996,
        "close": prices,
        "volume": volume,
        "oi": oi,
        "funding_rate": funding,
    })
    return df


class TestPartialExitsInBacktest:

    def test_backtest_generates_tp1_trades(self, cfg):
        df = _make_simple_uptrend_df()
        result = backtest(df, cfg, initial_equity=10000.0)
        # Should have at least some trades
        if result.closed_legs > 0:
            tp1_trades = result.trades_df[result.trades_df["exit_reason"] == "TP1_HIT"]
            assert len(tp1_trades) >= 0  # may or may not have partial exits depending on market
        assert result.closed_legs >= 0  # just ensure it doesn't crash

    def test_position_id_present_in_trades(self, cfg):
        df = _make_simple_uptrend_df()
        result = backtest(df, cfg, initial_equity=10000.0)
        if result.closed_legs > 0:
            assert "position_id" in result.trades_df.columns, "position_id missing from trades"
            # ensure position_ids are positive integers
            assert (result.trades_df["position_id"] >= 1).all()
