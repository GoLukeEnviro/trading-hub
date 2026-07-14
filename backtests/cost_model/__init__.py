"""Deterministic backtest cost model and walk-forward evaluator.

This module provides realistic cost calculations (fees, slippage, funding)
and a walk-forward evaluation scaffold.  It is **not** a live trading or
strategy promotion tool — it improves the quality of strategy evaluation
by ensuring that costs are not ignored.

All functions are pure, deterministic, and operate on plain dataclasses.
No exchange, Docker, or runtime dependency required.
"""

from __future__ import annotations

from .cost_calculator import (
    calc_all_costs,
    calc_enter_fee,
    calc_exit_fee,
    calc_funding_cost,
    calc_gross_pnl,
    calc_gross_return_pct,
    calc_mark_to_market_pnl,
    calc_net_pnl,
    calc_net_return_pct,
    calc_slippage_cost,
    compute_aggregate_metrics,
    compute_trade_result,
)
from .models import (
    DEFAULT_COST_CONFIG,
    AggregateMetrics,
    CostBreakdown,
    CostConfig,
    TradeInput,
    TradeResult,
    WalkForwardWindow,
    WindowMetrics,
)
from .walk_forward import (
    compute_window_metrics,
    evaluate_walk_forward,
    split_windows,
)

__all__ = [
    "DEFAULT_COST_CONFIG",
    # Models
    "AggregateMetrics",
    "CostBreakdown",
    "CostConfig",
    "TradeInput",
    "TradeResult",
    "WalkForwardWindow",
    "WindowMetrics",
    # Per-trade
    "calc_all_costs",
    "calc_enter_fee",
    "calc_exit_fee",
    "calc_funding_cost",
    "calc_gross_pnl",
    "calc_gross_return_pct",
    "calc_mark_to_market_pnl",
    "calc_net_pnl",
    "calc_net_return_pct",
    "calc_slippage_cost",
    "compute_aggregate_metrics",
    "compute_trade_result",
    # Walk-forward
    "compute_window_metrics",
    "evaluate_walk_forward",
    "split_windows",
]
