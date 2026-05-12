"""Tests for metrics: drawdown, sharpe, profit factor (leg + position), expectancy, breakeven WR."""
import math

import numpy as np
import pandas as pd
import pytest

from fomo_phase3.config import StrategyConfig
from fomo_phase3.metrics import (
    BacktestResult,
    Trade,
    breakeven_win_rate,
    calc_drawdown,
    calc_sharpe,
    expectancy,
    leg_profit_factor,
    position_profit_factor,
    position_win_rate,
    result_summary,
)


@pytest.fixture
def simple_equity_curve() -> pd.Series:
    """Equity: 1000 -> 1050 -> 1020 -> 1100 -> 1080 -> 1150."""
    return pd.Series([1000.0, 1050.0, 1020.0, 1100.0, 1080.0, 1150.0])


@pytest.fixture
def flat_equity_curve() -> pd.Series:
    return pd.Series([1000.0] * 100)


@pytest.fixture
def trades_with_positions() -> pd.DataFrame:
    """Three positions with multiple legs."""
    return pd.DataFrame({
        "position_id": [1, 1, 2, 2, 3],
        "net_pnl":      [60.0, 40.0, -30.0, -20.0, 100.0],
        "exit_reason":  ["TP1_HIT", "TP2_HIT", "SL_HIT", "TP2_HIT", "TP1_HIT"],
        "direction":    ["LONG", "LONG", "SHORT", "SHORT", "LONG"],
        "qty":          [0.6, 0.4, 0.5, 0.5, 1.0],
    })


class TestCalcDrawdown:

    def test_simple_equity(self, simple_equity_curve):
        # Peak = 1050, trough = 1020, drawdown = (1020/1050 - 1) = -2.857%
        dd = calc_drawdown(simple_equity_curve)
        assert dd == pytest.approx(0.02857, abs=0.001)

    def test_flat_equity(self, flat_equity_curve):
        dd = calc_drawdown(flat_equity_curve)
        assert dd == 0.0

    def test_strictly_increasing(self):
        dd = calc_drawdown(pd.Series([100, 200, 300]))
        assert dd == 0.0


class TestCalcSharpe:

    def test_positive_returns(self):
        eq = pd.Series([1000, 1010, 1020, 1030, 1040])
        sr = calc_sharpe(eq, 252)
        assert sr > 0

    def test_flat_returns(self, flat_equity_curve):
        sr = calc_sharpe(flat_equity_curve, 252)
        assert sr == 0.0

    def test_too_few_points(self):
        sr = calc_sharpe(pd.Series([1000, 1001]), 252)
        assert sr == 0.0


class TestProfitFactor:

    def test_leg_pf_positive(self, trades_with_positions):
        pf = leg_profit_factor(trades_with_positions)
        # wins: 60 + 40 + 100 = 200, losses: -30 + -20 = -50
        assert pf == pytest.approx(200.0 / 50.0)

    def test_position_pf(self, trades_with_positions):
        pf = position_profit_factor(trades_with_positions)
        # position 1: 60+40=100, position 2: -50, position 3: 100
        # wins: 100+100=200, losses: 50
        assert pf == pytest.approx(200.0 / 50.0)

    def test_position_pf_differs_from_leg_pf_with_mixed_positions(self, trades_with_positions):
        leg_pf = leg_profit_factor(trades_with_positions)
        pos_pf = position_profit_factor(trades_with_positions)
        # They should be equal in this case because each position's legs are same sign
        # But in general they differ. Let's add a mixed case.
        df_both = pd.DataFrame({
            "position_id": [1, 1, 2],
            "net_pnl": [50.0, -10.0, 30.0],  # pos1 = total 40, pos2 = 30
        })
        pos_pf2 = position_profit_factor(df_both)
        leg_pf2 = leg_profit_factor(df_both)
        # leg_pf = (50+30) / 10 = 8.0
        # pos_pf = (40+30) / ...  # actually both positions are positive, so inf
        assert pos_pf2 == float("inf")  # no negative positions
        assert leg_pf2 < pos_pf2

    def test_empty_pf(self):
        assert leg_profit_factor(pd.DataFrame()) == 0.0


class TestPositionWinRate:

    def test_basic(self, trades_with_positions):
        wr = position_win_rate(trades_with_positions)
        # positions: 1=+100, 2=-50, 3=+100 => 2/3 = 66.7%
        assert wr == pytest.approx(66.6667, abs=0.1)

    def test_empty(self):
        assert position_win_rate(pd.DataFrame()) == 0.0


class TestExpectancy:

    def test_basic(self, trades_with_positions):
        exp = expectancy(trades_with_positions)
        # positions: 1=+100, 2=-50, 3=+100 => avg = 150/3 = 50
        assert exp == pytest.approx(50.0)

    def test_empty(self):
        assert expectancy(pd.DataFrame()) == 0.0


class TestBreakevenWinRate:

    def test_simple(self):
        df = pd.DataFrame({
            "position_id": [1, 2, 3],
            "net_pnl": [100.0, -50.0, 30.0],
        })
        # avg_win = (100+30)/2 = 65, avg_loss = 50, breakeven = 50/(65+50) = 0.4348
        be = breakeven_win_rate(df)
        assert be == pytest.approx(50.0 / (65.0 + 50.0))

    def test_all_wins(self):
        df = pd.DataFrame({"position_id": [1], "net_pnl": [100.0]})
        be = breakeven_win_rate(df)
        assert be == 0.0  # can't compute

    def test_empty(self):
        assert breakeven_win_rate(pd.DataFrame()) == 0.0


class TestResultSummary:

    def test_includes_required_keys(self):
        trades_df = pd.DataFrame({"net_pnl": [10, 20, -5], "position_id": [1, 1, 2]})
        result = BacktestResult(
            initial_equity=10000.0,
            final_equity=10050.0,
            total_return_pct=0.5,
            max_drawdown_pct=2.0,
            sharpe=1.2,
            profit_factor=1.8,
            win_rate=55.0,
            trades=2,
            closed_legs=3,
            funding_pnl=-5.0,
            trades_df=trades_df,
            equity_curve=pd.DataFrame({"equity": [10000, 10050]}),
        )
        s = result_summary(result)
        required_keys = [
            "initial_equity", "final_equity", "total_return_pct", "max_drawdown_pct",
            "sharpe", "profit_factor", "win_rate", "trades", "closed_legs", "funding_pnl",
        ]
        for key in required_keys:
            assert key in s, f"Missing key: {key}"
