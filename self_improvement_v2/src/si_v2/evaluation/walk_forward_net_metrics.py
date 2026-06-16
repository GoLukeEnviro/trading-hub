r"""Walk-Forward Net Metrics Evaluation — pure evaluation logic.

This module implements deterministic, read-only evaluation of net metrics
(walk-forward or backtest) for ShadowProposal decisions.

It answers: "given these net metrics, should this proposal be promotion-blocked?"

Key design decisions:
  - Pure function — no I/O, no external state, no side effects.
  - Accepts metrics as flat fields OR from an AggregateMetrics-like dict.
  - All thresholds are explicit parameters with safe defaults.
  - Output is a structured WalkForwardEvaluation dataclass that flows into
    the cycle's safety_results dict as metadata-only.

Integration:
  Called from active_cycle_runner.py Step 4 (safety path). For each
  SHADOW_PROPOSAL decision, the runner calls evaluate_net_metrics() with
  whatever trade-level evidence is available. Currently defaults to
  INSUFFICIENT_EVIDENCE since the cycle runner collects ping/status
  evidence, not trade histories. Future cycles can pass real AggregateMetrics.

Safety invariants:
  - Never modifies any external state.
  - Never enables live trading or sets dry_run mode to false.
  - Never changes config, strategy, or Docker state.
  - promotion_blocked defaults to True for anything other than PASS_REVIEW.
  - PASS_REVIEW still requires PENDING_HUMAN (never auto-approves).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

# ---------------------------------------------------------------------------
# Evaluation status constants
# ---------------------------------------------------------------------------
STATUS_PASS_REVIEW: Final[str] = "PASS_REVIEW"
"""Proposal passed net metrics review — ready for human evaluation."""

STATUS_NEGATIVE_NET_METRICS: Final[str] = "NEGATIVE_NET_METRICS"
"""Net metrics are clearly negative — proposal should be blocked."""

STATUS_INSUFFICIENT_EVIDENCE: Final[str] = "INSUFFICIENT_EVIDENCE"
"""Not enough trades or evidence to evaluate — proposal blocked."""

STATUS_NOT_APPLICABLE: Final[str] = "NOT_APPLICABLE"
"""No evaluation possible (NO_PROPOSAL, not a candidate)."""

# ---------------------------------------------------------------------------
# Reason code constants
# ---------------------------------------------------------------------------
REASON_CODE_INSUFFICIENT_EVIDENCE: Final[str] = "walk_forward_insufficient_evidence"
REASON_CODE_NEGATIVE_NET_METRICS: Final[str] = "walk_forward_net_metrics_negative"
REASON_CODE_HIGH_DRAWDOWN: Final[str] = "walk_forward_high_drawdown"

# ---------------------------------------------------------------------------
# Default thresholds (conservative)
# ---------------------------------------------------------------------------
_MIN_TRADES_FOR_EVALUATION: Final[int] = 5
"""Minimum trades required to produce a meaningful evaluation."""

_MAX_DRAWDOWN_THRESHOLD_PCT: Final[float] = 15.0
"""Max drawdown above this value always blocks promotion."""

_NEGATIVE_PNL_THRESHOLD: Final[float] = 0.0
"""Net PnL at or below this value blocks promotion."""

_PROFIT_FACTOR_MIN: Final[float] = 1.0
"""Profit factor below 1.0 means net-negative performance."""


# ---------------------------------------------------------------------------
# Evaluation result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WalkForwardEvaluation:
    """Structured result of a net-metrics evaluation.

    All fields are metadata-only and never used for automatic execution.
    ``promotion_blocked`` and ``reason_codes`` are the primary safety outputs.

    Attributes:
        total_trades: Number of trades evaluated.
        total_net_pnl: Sum of net PnL across all trades.
        total_fees: Sum of all fees (entry + exit).
        total_slippage: Sum of all slippage costs.
        total_funding: Sum of all funding costs.
        max_drawdown_pct: Maximum peak-to-trough drawdown (%).
        profit_factor: Gross profit / gross loss.
        win_rate_pct: Percentage of winning trades.
        evaluation_status: One of PASS_REVIEW, NEGATIVE_NET_METRICS,
            INSUFFICIENT_EVIDENCE, or NOT_APPLICABLE.
        promotion_blocked: True when the proposal should not be promotable.
        promotion_block_reason_codes: List of reason codes explaining why
            promotion is blocked (empty when not blocked).
    """

    total_trades: int = 0
    total_net_pnl: float = 0.0
    total_fees: float = 0.0
    total_slippage: float = 0.0
    total_funding: float = 0.0
    max_drawdown_pct: float = 0.0
    profit_factor: float = 0.0
    win_rate_pct: float = 0.0

    evaluation_status: str = STATUS_INSUFFICIENT_EVIDENCE
    promotion_blocked: bool = True
    promotion_block_reason_codes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        """JSON-safe dict for embedding in safety_results / evidence bundles."""
        return {
            "total_trades": self.total_trades,
            "total_net_pnl": self.total_net_pnl,
            "total_fees": self.total_fees,
            "total_slippage": self.total_slippage,
            "total_funding": self.total_funding,
            "max_drawdown_pct": self.max_drawdown_pct,
            "profit_factor": self.profit_factor,
            "win_rate_pct": self.win_rate_pct,
            "evaluation_status": self.evaluation_status,
            "promotion_blocked": self.promotion_blocked,
            "promotion_block_reason_codes": list(self.promotion_block_reason_codes),
        }


# ---------------------------------------------------------------------------
# Evaluation function
# ---------------------------------------------------------------------------


def evaluate_net_metrics(
    total_trades: int = 0,
    total_net_pnl: float = 0.0,
    total_fees: float = 0.0,
    total_slippage: float = 0.0,
    total_funding: float = 0.0,
    max_drawdown_pct: float = 0.0,
    profit_factor: float = 0.0,
    win_rate_pct: float = 0.0,
    *,
    min_trades: int = _MIN_TRADES_FOR_EVALUATION,
    max_drawdown_threshold_pct: float = _MAX_DRAWDOWN_THRESHOLD_PCT,
    negative_pnl_threshold: float = _NEGATIVE_PNL_THRESHOLD,
) -> WalkForwardEvaluation:
    """Evaluate net metrics and produce a promotion recommendation.

    This is a pure function — no I/O, no side effects, no external state.

    Args:
        total_trades: Total number of trades evaluated.
        total_net_pnl: Net PnL (total) across all trades in quote currency.
        total_fees: Total fees incurred (entry + exit).
        total_slippage: Total slippage cost.
        total_funding: Total funding cost.
        max_drawdown_pct: Maximum drawdown as percentage.
        profit_factor: Gross profit / gross loss ratio.
        win_rate_pct: Percentage of trades that were profitable.
        min_trades: Minimum trade count for a meaningful evaluation.
        max_drawdown_threshold_pct: Drawdown above this blocks promotion.
        negative_pnl_threshold: Net PnL at or below this blocks promotion.

    Returns:
        WalkForwardEvaluation with evaluation_status and safety fields.
    """
    reason_codes: list[str] = []

    # ── Insufficient evidence check ────────────────────────────────────
    if total_trades < min_trades:
        return WalkForwardEvaluation(
            total_trades=total_trades,
            total_net_pnl=total_net_pnl,
            total_fees=total_fees,
            total_slippage=total_slippage,
            total_funding=total_funding,
            max_drawdown_pct=max_drawdown_pct,
            profit_factor=profit_factor,
            win_rate_pct=win_rate_pct,
            evaluation_status=STATUS_INSUFFICIENT_EVIDENCE,
            promotion_blocked=True,
            promotion_block_reason_codes=[REASON_CODE_INSUFFICIENT_EVIDENCE],
        )

    # ── Negative net PnL ───────────────────────────────────────────────
    if total_net_pnl <= negative_pnl_threshold:
        reason_codes.append(REASON_CODE_NEGATIVE_NET_METRICS)

    # ── Excessive drawdown ─────────────────────────────────────────────
    if max_drawdown_pct >= max_drawdown_threshold_pct:
        reason_codes.append(REASON_CODE_HIGH_DRAWDOWN)

    # ── Determine status ───────────────────────────────────────────────
    if reason_codes:
        # Some metric thresholds were breached
        return WalkForwardEvaluation(
            total_trades=total_trades,
            total_net_pnl=total_net_pnl,
            total_fees=total_fees,
            total_slippage=total_slippage,
            total_funding=total_funding,
            max_drawdown_pct=max_drawdown_pct,
            profit_factor=profit_factor,
            win_rate_pct=win_rate_pct,
            evaluation_status=STATUS_NEGATIVE_NET_METRICS,
            promotion_blocked=True,
            promotion_block_reason_codes=reason_codes,
        )

    # ── Positive / neutral net metrics — pass review, but still needs human
    return WalkForwardEvaluation(
        total_trades=total_trades,
        total_net_pnl=total_net_pnl,
        total_fees=total_fees,
        total_slippage=total_slippage,
        total_funding=total_funding,
        max_drawdown_pct=max_drawdown_pct,
        profit_factor=profit_factor,
        win_rate_pct=win_rate_pct,
        evaluation_status=STATUS_PASS_REVIEW,
        promotion_blocked=False,
        promotion_block_reason_codes=[],
    )


def evaluate_from_aggregate_metrics(
    metrics_dict: dict[str, object],
    *,
    min_trades: int = _MIN_TRADES_FOR_EVALUATION,
    max_drawdown_threshold_pct: float = _MAX_DRAWDOWN_THRESHOLD_PCT,
) -> WalkForwardEvaluation:
    """Convenience wrapper that reads from an AggregateMetrics-like dict.

    Accepts any dict with the expected fields (including JSON-deserialized
    AggregateMetrics). Fields missing or non-numeric are treated as 0.

    Args:
        metrics_dict: Dict matching AggregateMetrics field names.
        min_trades: Minimum trades for evaluation.
        max_drawdown_threshold_pct: Max drawdown threshold.

    Returns:
        WalkForwardEvaluation result.
    """
    return evaluate_net_metrics(
        total_trades=_safe_int(metrics_dict, "total_trades"),
        total_net_pnl=_safe_float(metrics_dict, "total_net_pnl"),
        total_fees=_safe_float(metrics_dict, "total_fees"),
        total_slippage=_safe_float(metrics_dict, "total_slippage"),
        total_funding=_safe_float(metrics_dict, "total_funding"),
        max_drawdown_pct=_safe_float(metrics_dict, "max_drawdown_pct"),
        profit_factor=_safe_float(metrics_dict, "profit_factor"),
        win_rate_pct=_safe_float(metrics_dict, "win_rate_pct"),
        min_trades=min_trades,
        max_drawdown_threshold_pct=max_drawdown_threshold_pct,
    )


def default_no_proposal_evaluation() -> WalkForwardEvaluation:
    """Produce a NOT_APPLICABLE evaluation for NO_PROPOSAL decisions.

    Returns:
        WalkForwardEvaluation with evaluation_status=NOT_APPLICABLE
        and promotion_blocked=True.
    """
    return WalkForwardEvaluation(
        total_trades=0,
        total_net_pnl=0.0,
        total_fees=0.0,
        total_slippage=0.0,
        total_funding=0.0,
        max_drawdown_pct=0.0,
        profit_factor=0.0,
        win_rate_pct=0.0,
        evaluation_status=STATUS_NOT_APPLICABLE,
        promotion_blocked=True,
        promotion_block_reason_codes=["no_proposal"],
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _safe_float(d: dict[str, object], key: str) -> float:
    """Extract a float from a dict, returning 0.0 on missing/invalid values."""
    val = d.get(key)
    if isinstance(val, (int, float)):
        return float(val)
    return 0.0


def _safe_int(d: dict[str, object], key: str) -> int:
    """Extract an int from a dict, returning 0 on missing/invalid values."""
    val = d.get(key)
    if isinstance(val, int):
        return val
    if isinstance(val, float):
        return int(val)
    return 0
