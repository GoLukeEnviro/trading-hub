"""Aggregate Metrics Adapter — convert signal snapshot data to WalkForward metrics.

This module provides the bridge between the SI v2 signal collection pipeline
(BotSignalSnapshot) and the walk-forward net metrics evaluation
(``evaluate_from_aggregate_metrics``).

The adapter is a pure function: no I/O, no side effects, no external state.

Design:
  - Accepts a BotSignalSnapshot (or None/duck-typed object with the same fields).
  - Maps available fields to the AggregateMetrics-like dict expected by
    ``evaluate_from_aggregate_metrics()``.
  - Reports a ``metrics_source`` tag for transparency in the cycle metadata.
  - Missing, malformed, or insufficient data safely falls back to None so
    the caller can keep INSUFFICIENT_EVIDENCE.

Mapping:
  - ``num_trades`` (from /api/v1/profit) → ``total_trades`` (lifetime closed trades)
  - ``profit_closed_coin`` → ``total_net_pnl``
  - ``profit_factor`` → ``profit_factor``
  - ``max_drawdown_pct`` → not mapped (not available from current signal
    endpoints; evaluator will detect absence and block with
    ``REASON_CODE_MISSING_DRAWDOWN``)
  - ``win_rate_pct`` → 0.0 (not available from current signal endpoints)
"""

from __future__ import annotations


# ------------------------------------------------------------------
# Source tags
# ------------------------------------------------------------------
METRICS_SOURCE_REAL: str = "real"
"""Metrics derived from available signal snapshot data."""

METRICS_SOURCE_MISSING: str = "missing"
"""No signal snapshot or snapshot had zero trade data."""

METRICS_SOURCE_INSUFFICIENT: str = "insufficient"
"""Snapshot exists but has too few trades for meaningful evaluation."""

METRICS_SOURCE_NOT_APPLICABLE: str = "not_applicable"
"""Called for NO_PROPOSAL decisions — no metrics to evaluate."""


# ------------------------------------------------------------------
# Adapter function
# ------------------------------------------------------------------


def derive_aggregate_metrics(
    signal_snapshot: object | None,
) -> tuple[dict[str, object] | None, str]:
    """Derive aggregate metrics from a BotSignalSnapshot.

    Args:
        signal_snapshot: A BotSignalSnapshot-like object with
            ``num_trades``, ``profit_closed_coin``, ``profit_factor``,
            ``daily_trade_count_total``, ``profit_all_coin`` attributes,
            or None.

    Returns:
        A tuple of (metrics_dict, source_tag):
            metrics_dict: dict suitable for ``evaluate_from_aggregate_metrics()``
                with keys ``total_trades``, ``total_net_pnl``, ``total_fees``,
                ``total_slippage``, ``total_funding``,
                ``profit_factor``, ``win_rate_pct``. Returns None when no
                usable data exists.
            source_tag: One of ``METRICS_SOURCE_*`` constants.
    """
    if signal_snapshot is None:
        return None, METRICS_SOURCE_MISSING

    # Extract fields safely (duck-type to handle test doubles)
    num_trades = _safe_int(signal_snapshot, "num_trades", 0)
    profit_closed_coin = _safe_float(signal_snapshot, "profit_closed_coin", 0.0)
    profit_factor = _safe_float(signal_snapshot, "profit_factor", 0.0)
    daily_trade_count_total = _safe_int(
        signal_snapshot, "daily_trade_count_total", 0
    )
    profit_all_coin = _safe_float(signal_snapshot, "profit_all_coin", 0.0)

    # Use the best available source for total_trades.
    # num_trades (lifetime) is preferred; fall back to daily.
    total_trades = num_trades if num_trades > 0 else daily_trade_count_total

    # Use profit_closed_coin (closed trades only) as the best proxy for
    # net PnL. Fall back to profit_all_coin (includes open positions).
    total_net_pnl = profit_closed_coin if profit_closed_coin != 0.0 else profit_all_coin

    # If there's no evidence of any trade activity, report as missing
    if total_trades == 0 and total_net_pnl == 0.0 and profit_factor == 0.0:
        return None, METRICS_SOURCE_MISSING

    # If trades exist but too few for meaningful evaluation,
    # still return the metrics so the evaluator can produce
    # INSUFFICIENT_EVIDENCE with accurate trade count metadata.
    source_tag = METRICS_SOURCE_REAL if total_trades > 0 else METRICS_SOURCE_INSUFFICIENT

    metrics: dict[str, object] = {
        "total_trades": total_trades,
        "total_net_pnl": total_net_pnl,
        "total_fees": 0,
        "total_slippage": 0,
        "total_funding": 0,
        "profit_factor": profit_factor,
        "win_rate_pct": 0.0,
    }

    return metrics, source_tag


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------


def _safe_int(obj: object, attr: str, default: int) -> int:
    """Safely extract an int attribute from a duck-typed object."""
    val = getattr(obj, attr, None)
    if isinstance(val, int):
        return val
    if isinstance(val, float):
        return int(val)
    return default


def _safe_float(obj: object, attr: str, default: float) -> float:
    """Safely extract a float attribute from a duck-typed object."""
    val = getattr(obj, attr, None)
    if isinstance(val, (int, float)):
        return float(val)
    return default
