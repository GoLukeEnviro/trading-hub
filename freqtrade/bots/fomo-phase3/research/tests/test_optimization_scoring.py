"""Tests for optimization scoring function."""
import math

import pandas as pd
import pytest

from fomo_phase3.config import StrategyConfig
from fomo_phase3.metrics import BacktestResult
from fomo_phase3.optimization import score_result_for_optimization


def _make_result(trades: int, max_dd_pct: float, pf: float, sharpe: float,
                 ret_pct: float, trades_df: pd.DataFrame | None = None) -> BacktestResult:
    if trades_df is None:
        position_ids = list(range(1, max(trades + 1, 2)))
        net_pnls = [100.0 if i % 2 == 0 else -50.0 for i in position_ids]
        trades_df = pd.DataFrame({
            "position_id": position_ids,
            "net_pnl": net_pnls,
            "exit_reason": ["TP1_HIT"] * len(position_ids),
        })
    return BacktestResult(
        initial_equity=10000.0,
        final_equity=10000.0 * (1 + ret_pct / 100),
        total_return_pct=ret_pct,
        max_drawdown_pct=max_dd_pct,
        sharpe=sharpe,
        profit_factor=pf,
        win_rate=50.0,
        trades=trades,
        closed_legs=len(trades_df),
        funding_pnl=0.0,
        trades_df=trades_df,
        equity_curve=pd.DataFrame({"equity": [10000, 10100, 10050]}),
    )


class TestScoreResultForOptimization:

    def test_penalizes_few_trades(self):
        cfg = StrategyConfig(min_trades_per_test=10)
        result = _make_result(trades=3, max_dd_pct=2.0, pf=2.0, sharpe=1.5, ret_pct=5.0)
        score = score_result_for_optimization(result, cfg)
        assert score == -999.0, "Should penalize below min_trades_per_test"

    def test_penalizes_high_drawdown(self):
        cfg = StrategyConfig(max_drawdown_constraint=0.12)
        result = _make_result(trades=15, max_dd_pct=15.0, pf=1.5, sharpe=1.2, ret_pct=8.0)
        score = score_result_for_optimization(result, cfg)
        assert score < -900.0, "Should heavily penalize drawdown above constraint"

    def test_positive_score_for_good_results(self):
        cfg = StrategyConfig(min_trades_per_test=10, max_drawdown_constraint=0.12)
        result = _make_result(trades=20, max_dd_pct=5.0, pf=2.0, sharpe=1.5, ret_pct=10.0)
        score = score_result_for_optimization(result, cfg)
        assert score > 0, "Good results should produce positive score"

    def test_infinite_pf_handled_gracefully(self):
        cfg = StrategyConfig(min_trades_per_test=10, max_drawdown_constraint=0.12)
        trades_df = pd.DataFrame({
            "position_id": list(range(1, 13)),
            "net_pnl": [100.0, 50.0, 75.0] * 4,
            "exit_reason": ["TP1_HIT"] * 12,
        })
        result = _make_result(trades=12, max_dd_pct=3.0, pf=float("inf"),
                              sharpe=2.0, ret_pct=5.0, trades_df=trades_df)
        score = score_result_for_optimization(result, cfg)
        assert score > -800, "Infinite PF should not crash"

    def test_better_sharpe_increases_score(self):
        cfg = StrategyConfig(min_trades_per_test=10, max_drawdown_constraint=0.12)
        r1 = _make_result(trades=20, max_dd_pct=5.0, pf=1.5, sharpe=1.0, ret_pct=5.0)
        r2 = _make_result(trades=20, max_dd_pct=5.0, pf=1.5, sharpe=2.0, ret_pct=5.0)
        s1 = score_result_for_optimization(r1, cfg)
        s2 = score_result_for_optimization(r2, cfg)
        assert s2 > s1, "Higher Sharpe should score better"
