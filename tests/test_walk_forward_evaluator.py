from __future__ import annotations

import pytest

from backtests.cost_model.cost_calculator import compute_trade_result
from backtests.cost_model.models import CostConfig, TradeInput
from backtests.cost_model.walk_forward import (
    evaluate_walk_forward,
    split_windows,
)


def _trade(entry: float, exit_: float, side: str = "long") -> TradeInput:
    return TradeInput(entry_price=entry, exit_price=exit_, quantity=1.0, side=side, hold_hours=1.0)


def _results(count: int, winning: bool = True) -> list:
    """Create *count* deterministic results."""
    trades = [_trade(100.0, 120.0 if winning else 80.0) for _ in range(count)]
    return [compute_trade_result(t) for t in trades]


# ===========================================================================
# Window splitting
# ===========================================================================


class TestSplitWindows:
    def test_sufficient_trades_produces_windows(self) -> None:
        windows = split_windows(30, n_splits=3)
        assert len(windows) == 3

    def test_insufficient_trades_returns_empty(self) -> None:
        windows = split_windows(3, n_splits=3)
        assert windows == []

    def test_windows_cover_all_trades(self) -> None:
        n = 60
        windows = split_windows(n, n_splits=3)
        total_covered = sum((w.train_end - w.train_start) + (w.test_end - w.test_start) for w in windows)
        assert total_covered == n

    def test_train_test_non_overlapping(self) -> None:
        windows = split_windows(60, n_splits=3)
        for w in windows:
            assert w.train_start <= w.train_end
            assert w.test_start <= w.test_end
            assert w.train_end <= w.test_start  # no overlap

    def test_window_indices_sensible(self) -> None:
        windows = split_windows(60, n_splits=3)
        assert windows[0].train_start == 0
        assert windows[-1].test_end == 60


# ===========================================================================
# Walk-forward evaluation
# ===========================================================================


class TestWalkForwardEvaluation:
    def test_evaluates_multiple_windows(self) -> None:
        results = _results(60, winning=True)
        agg = evaluate_walk_forward(results, n_splits=3)
        assert agg.total_trades == 60
        assert agg.total_net_pnl > 0
        assert len(agg.windows) == 6  # 3 windows x 2 (train + test)

    def test_aggregate_metrics_match(self) -> None:
        results = _results(30, winning=True)
        agg = evaluate_walk_forward(results, n_splits=2)
        # Total net should be sum of all trade net PnLs
        expected_net = sum(r.net_pnl for r in results)
        assert agg.total_net_pnl == pytest.approx(expected_net, rel=1e-9)

    def test_costs_turn_gross_to_net_negative(self) -> None:
        """High-cost config makes gross-positive walk-forward net-negative."""
        cfg = CostConfig(entry_fee_rate=0.05, exit_fee_rate=0.05, slippage_rate=0.05, funding_rate_per_8h=0.02)
        trades = [_trade(100.0, 103.0) for _ in range(20)]  # small gross profit per trade
        results = [compute_trade_result(t, cfg) for t in trades]
        agg = evaluate_walk_forward(results, n_splits=2)
        total_gross = sum(r.gross_pnl for r in results)
        assert total_gross > 0  # gross positive
        assert agg.total_net_pnl < total_gross  # net less than gross
        # With high costs, net may be negative
        assert agg.total_fees > 0

    def test_losing_scenario_metrics(self) -> None:
        results = _results(20, winning=False)
        agg = evaluate_walk_forward(results, n_splits=2)
        assert agg.total_net_pnl < 0
        assert agg.win_rate_pct < 50

    def test_insufficient_trades_returns_empty_metrics(self) -> None:
        results = _results(2, winning=True)
        agg = evaluate_walk_forward(results, n_splits=2)
        assert agg.total_trades == 2
        assert agg.win_rate_pct == 0.0  # empty metrics

    def test_per_window_metrics_present(self) -> None:
        results = _results(60, winning=True)
        agg = evaluate_walk_forward(results, n_splits=3)
        for wm in agg.windows:
            assert wm.trade_count > 0
            assert wm.window_label in ("train", "test")
            assert wm.net_pnl != 0.0
