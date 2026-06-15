"""Walk-forward evaluator that applies the cost model across time windows.

Splits a sequence of ``TradeResult`` into train/test windows and computes
net metrics per window and in aggregate.
"""

from __future__ import annotations

from .cost_calculator import compute_aggregate_metrics
from .models import (
    AggregateMetrics,
    TradeResult,
    WalkForwardWindow,
    WindowMetrics,
)

# Minimum trades per window for meaningful analysis
_MIN_TRADES_PER_WINDOW = 5

# Default split ratio (train : test)
_DEFAULT_TRAIN_RATIO = 0.7


# ---------------------------------------------------------------------------
# Window splitting
# ---------------------------------------------------------------------------


def split_windows(
    n_trades: int,
    n_splits: int = 3,
    train_ratio: float = _DEFAULT_TRAIN_RATIO,
) -> list[WalkForwardWindow]:
    """Split *n_trades* into *n_splits* sequential train/test windows.

    Parameters
    ----------
    n_trades : int
        Total number of trades in the dataset.
    n_splits : int
        Number of walk-forward windows (default 3).
    train_ratio : float
        Fraction of each window used for training (default 0.7).

    Returns
    -------
    list[WalkForwardWindow]
        Non-overlapping windows covering all trades.
    """
    if n_trades < _MIN_TRADES_PER_WINDOW:
        return []

    trades_per_window = n_trades // n_splits
    windows: list[WalkForwardWindow] = []

    for i in range(n_splits):
        start = i * trades_per_window
        end = n_trades if i == n_splits - 1 else (i + 1) * trades_per_window
        window_size = end - start
        train_size = max(1, int(window_size * train_ratio))

        windows.append(
            WalkForwardWindow(
                train_start=start,
                train_end=start + train_size,
                test_start=start + train_size,
                test_end=end,
            )
        )

    return windows


# ---------------------------------------------------------------------------
# Window metrics
# ---------------------------------------------------------------------------


def compute_window_metrics(
    results: list[TradeResult],
    window: WalkForwardWindow,
    label: str,
) -> WindowMetrics:
    """Compute net metrics for a single window slice."""
    if label == "train":
        window_results = results[window.train_start : window.train_end]
    else:
        window_results = results[window.test_start : window.test_end]

    agg = compute_aggregate_metrics(window_results)

    return WindowMetrics(
        window_label=label,
        trade_count=agg.total_trades,
        gross_pnl=agg.total_gross_pnl,
        net_pnl=agg.total_net_pnl,
        total_fees=agg.total_fees,
        total_slippage=agg.total_slippage,
        total_funding=agg.total_funding,
        win_rate_pct=agg.win_rate_pct,
        max_drawdown_pct=agg.max_drawdown_pct,
        avg_net_pnl=agg.avg_net_pnl,
        avg_return_pct=agg.avg_return_pct,
        profit_factor=agg.profit_factor,
    )


# ---------------------------------------------------------------------------
# Full evaluation
# ---------------------------------------------------------------------------


def evaluate_walk_forward(
    results: list[TradeResult],
    n_splits: int = 3,
    train_ratio: float = _DEFAULT_TRAIN_RATIO,
) -> AggregateMetrics:
    """Run a full walk-forward evaluation on a list of trade results.

    Parameters
    ----------
    results : list[TradeResult]
        Ordered trade results (chronological).
    n_splits : int
        Number of walk-forward windows.
    train_ratio : float
        Fraction of each window used for training.

    Returns
    -------
    AggregateMetrics
        Aggregate metrics across all trades, with per-window breakdowns.

    Notes
    -----
    When trade count is very low, returns empty metrics with no windows
    rather than crashing.
    """
    if len(results) < _MIN_TRADES_PER_WINDOW:
        return AggregateMetrics(
            total_trades=len(results),
            total_gross_pnl=0.0,
            total_net_pnl=0.0,
            total_fees=0.0,
            total_slippage=0.0,
            total_funding=0.0,
            win_rate_pct=0.0,
            max_drawdown_pct=0.0,
            avg_net_pnl=0.0,
            avg_return_pct=0.0,
            profit_factor=0.0,
        )

    windows = split_windows(len(results), n_splits, train_ratio)
    window_list: list[WindowMetrics] = []

    for w in windows:
        train_metrics = compute_window_metrics(results, w, "train")
        test_metrics = compute_window_metrics(results, w, "test")
        window_list.append(train_metrics)
        window_list.append(test_metrics)

    return compute_aggregate_metrics(results, windows=window_list)
