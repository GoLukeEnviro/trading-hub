"""Tests for funding accounting: position-level accumulation, per-leg attribution."""
import numpy as np
import pandas as pd
import pytest

from fomo_phase3.backtest import backtest
from fomo_phase3.config import StrategyConfig
from fomo_phase3.execution import OpenPosition, reset_position_counter


@pytest.fixture(autouse=True)
def reset_pos_counter():
    reset_position_counter()
    yield


@pytest.fixture
def cfg() -> StrategyConfig:
    return StrategyConfig(
        fomo_entry=1.0,
        roc_long=0.0005,
        roc_short=-0.0005,
        oi_price_alignment_thresh=-0.1,
        oi_alignment_window=72,
        noise_atr_pct=0.05,     # relaxed for synthetic test data
    )


class TestFundingAccounting:

    def test_funding_accumulates_in_position(self, cfg):
        """Check that funding accumulates correctly in an OpenPosition."""
        pos = OpenPosition(
            direction="LONG", entry_idx=0,
            entry_time=pd.Timestamp("2024-01-01", tz="UTC"),
            entry_price=100.0, qty=1.0, remaining_qty=1.0,
            sl=99.0, tp1=102.0, tp2=105.0, atr=1.0,
        )
        # Manually add funding via process_funding (import and use it)
        from fomo_phase3.execution import process_funding

        equity = 10000.0
        # Funding at 00:00
        row = pd.Series({"timestamp": "2024-01-01 00:00:00+00:00", "close": 100.0, "funding_rate": 0.001})
        equity, _ = process_funding(pos, row, equity, cfg)
        assert pos.funding_pnl_accumulated == pytest.approx(-1 * 0.001 * 100.0 * 1.0)  # -sign * rate * notional

        # Funding at 08:00 — remaining_qty still 1.0
        row2 = pd.Series({"timestamp": "2024-01-01 08:00:00+00:00", "close": 101.0, "funding_rate": 0.001})
        equity, _ = process_funding(pos, row2, equity, cfg)
        expected_total = -0.001 * 100.0 * 1.0 + -0.001 * 101.0 * 1.0
        assert pos.funding_pnl_accumulated == pytest.approx(expected_total)

    def test_backtest_doesnt_crash_with_funding(self, cfg):
        """Smoke test: backtest runs without error when funding is enabled."""
        n = 600
        base = pd.Timestamp("2024-01-01", tz="UTC")
        np.random.seed(42)
        prices = 50000 + np.linspace(0, 3000, n) + np.random.normal(0, 50, n)
        volume = np.random.exponential(1000, n)
        volume[200:250] *= 5
        oi = 1e9 + np.linspace(0, 3e7, n) + np.random.normal(0, 1e6, n)
        funding = np.random.normal(-0.0002, 0.0003, n)

        df = pd.DataFrame({
            "timestamp": [base + pd.Timedelta(minutes=5 * i) for i in range(n)],
            "open": prices * 0.999, "high": prices * 1.004,
            "low": prices * 0.996, "close": prices,
            "volume": volume, "oi": oi, "funding_rate": funding,
        })
        result = backtest(df, cfg, initial_equity=10000.0)
        assert result.trades > 0
        assert result.equity_curve is not None  # equity curve was generated

    def test_funding_pnl_in_trade_net_pnl(self, cfg):
        """Verify that funding appears in individual trade legs."""
        df = _make_funding_dominant_df()
        # Use extended holding config so trades survive long enough for funding events
        long_cfg = StrategyConfig(
            fomo_entry=1.0,
            roc_long=0.0005,
            roc_short=-0.0005,
            oi_price_alignment_thresh=-0.1,
            oi_alignment_window=72,
            noise_atr_pct=0.05,
            fomo_exit=-1.0,      # never exit via fomo decay
            max_bars=500,         # hold long enough for funding
            sl_atr_mult=10.0,     # wide SL so trades aren't stopped
        )
        result = backtest(df, long_cfg, initial_equity=10000.0)
        if result.closed_legs > 0:
            # At least some trades should have non-zero funding
            funding_sum = result.trades_df["funding_pnl"].abs().sum()
            assert funding_sum > 0, (
                f"Expected non-zero funding in trades, got {funding_sum}. "
                f"Trades: {len(result.trades_df)}"
            )


def _make_funding_dominant_df() -> pd.DataFrame:
    """DataFrame where funding events are prominent (large funding rates)."""
    n = 600
    base = pd.Timestamp("2024-01-01", tz="UTC")
    np.random.seed(42)
    prices = 50000 + np.linspace(0, 2000, n) + np.random.normal(0, 50, n)
    volume = np.random.exponential(1000, n)
    volume[200:250] *= 5
    oi = 1e9 + np.linspace(0, 2e7, n) + np.random.normal(0, 1e6, n)

    # Large negative funding (favorable for longs) to trigger entries + funding cost
    funding = np.random.normal(-0.0008, 0.0002, n)

    df = pd.DataFrame({
        "timestamp": [base + pd.Timedelta(minutes=5 * i) for i in range(n)],
        "open": prices * 0.999, "high": prices * 1.004,
        "low": prices * 0.996, "close": prices,
        "volume": volume, "oi": oi, "funding_rate": funding,
    })
    return df
