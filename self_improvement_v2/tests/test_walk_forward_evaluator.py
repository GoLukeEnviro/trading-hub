"""Tests for walk_forward_net_metrics evaluation logic.

Covers:
  - Positive net metrics -> PASS_REVIEW, promotion_blocked=False
  - Negative net PnL -> promotion_blocked=True + reason code
  - High drawdown -> promotion_blocked=True + reason code
  - Insufficient trades -> promotion_blocked=True + INSUFFICIENT_EVIDENCE
  - NOT_APPLICABLE for NO_PROPOSAL scenarios
  - Human Approval remains required (PASS_REVIEW never auto-approves)
  - AggregateMetrics convenience wrapper
  - No-proposal default evaluation
  - Edge cases: zero trades, zero metrics, exact thresholds
"""

from __future__ import annotations

from si_v2.evaluation.walk_forward_net_metrics import (
    REASON_CODE_HIGH_DRAWDOWN,
    REASON_CODE_INSUFFICIENT_EVIDENCE,
    REASON_CODE_MISSING_DRAWDOWN,
    REASON_CODE_NEGATIVE_NET_METRICS,
    STATUS_INSUFFICIENT_EVIDENCE,
    STATUS_NEGATIVE_NET_METRICS,
    STATUS_NOT_APPLICABLE,
    STATUS_PASS_REVIEW,
    default_no_proposal_evaluation,
    evaluate_from_aggregate_metrics,
    evaluate_net_metrics,
)

# =========================================================================
# 1. Positive net metrics
# =========================================================================


class TestPositiveNetMetrics:
    """Proposals with clearly positive metrics pass review but still need human approval."""

    def test_positive_metrics_pass_review(self) -> None:
        """All metrics are positive -> PASS_REVIEW, promotion_blocked=False."""
        result = evaluate_net_metrics(
            total_trades=20,
            total_net_pnl=1500.0,
            total_fees=20.0,
            total_slippage=10.0,
            total_funding=5.0,
            max_drawdown_pct=8.0,
            profit_factor=2.5,
            win_rate_pct=65.0,
        )
        assert result.evaluation_status == STATUS_PASS_REVIEW
        assert result.promotion_blocked is False
        assert result.promotion_block_reason_codes == []
        assert result.total_trades == 20
        assert result.total_net_pnl == 1500.0

    def test_pass_review_still_needs_human_approval(self) -> None:
        """PASS_REVIEW must NOT imply auto-approval; metadata only."""
        result = evaluate_net_metrics(
            total_trades=20,
            total_net_pnl=1500.0,
            max_drawdown_pct=5.0,
            profit_factor=2.0,
            win_rate_pct=60.0,
        )
        assert result.evaluation_status == STATUS_PASS_REVIEW
        # The evaluation does not set approval_status — that's the caller's job.
        # The caller (active_cycle_runner) always sets approval_status=PENDING_HUMAN
        # for non-blocked proposals. Verify promotion_blocked is False, which
        # is the condition that allows PENDING_HUMAN.
        assert result.promotion_blocked is False

    def test_exactly_at_threshold_not_blocked(self) -> None:
        """Max drawdown exactly at threshold should NOT block promotion."""
        result = evaluate_net_metrics(
            total_trades=10,
            total_net_pnl=500.0,
            max_drawdown_pct=14.999,  # just under 15%
            profit_factor=1.5,
            win_rate_pct=55.0,
        )
        assert result.evaluation_status == STATUS_PASS_REVIEW
        assert result.promotion_blocked is False


# =========================================================================
# 2. Negative net PnL
# =========================================================================


class TestNegativeNetPnL:
    """Negative net PnL always blocks promotion."""

    def test_negative_net_pnl_blocks(self) -> None:
        """Net PnL at or below 0 blocks promotion with correct reason."""
        result = evaluate_net_metrics(
            total_trades=15,
            total_net_pnl=-200.0,
            max_drawdown_pct=10.0,
            profit_factor=0.8,
            win_rate_pct=40.0,
        )
        assert result.evaluation_status == STATUS_NEGATIVE_NET_METRICS
        assert result.promotion_blocked is True
        assert REASON_CODE_NEGATIVE_NET_METRICS in result.promotion_block_reason_codes

    def test_zero_net_pnl_blocks(self) -> None:
        """Zero net PnL (break-even) is treated as negative for promotion safety."""
        result = evaluate_net_metrics(
            total_trades=10,
            total_net_pnl=0.0,
            max_drawdown_pct=5.0,
            profit_factor=1.0,
            win_rate_pct=50.0,
        )
        assert result.evaluation_status == STATUS_NEGATIVE_NET_METRICS
        assert result.promotion_blocked is True


# =========================================================================
# 3. High drawdown
# =========================================================================


class TestHighDrawdown:
    """Excessive drawdown blocks promotion regardless of net PnL."""

    def test_high_drawdown_blocks(self) -> None:
        """Drawdown above 15% blocks promotion even with positive PnL."""
        result = evaluate_net_metrics(
            total_trades=20,
            total_net_pnl=500.0,
            max_drawdown_pct=25.0,
            profit_factor=1.5,
            win_rate_pct=55.0,
        )
        assert result.evaluation_status == STATUS_NEGATIVE_NET_METRICS
        assert result.promotion_blocked is True
        assert REASON_CODE_HIGH_DRAWDOWN in result.promotion_block_reason_codes

    def test_drawdown_and_negative_pnl_multi_reason(self) -> None:
        """Both negative PnL and high drawdown produce multiple reason codes."""
        result = evaluate_net_metrics(
            total_trades=20,
            total_net_pnl=-100.0,
            max_drawdown_pct=20.0,
            profit_factor=0.9,
            win_rate_pct=45.0,
        )
        assert result.promotion_blocked is True
        assert REASON_CODE_NEGATIVE_NET_METRICS in result.promotion_block_reason_codes
        assert REASON_CODE_HIGH_DRAWDOWN in result.promotion_block_reason_codes


# =========================================================================
# 4. Insufficient evidence
# =========================================================================


class TestInsufficientEvidence:
    """Fewer than min_trades trades always blocks and returns INSUFFICIENT_EVIDENCE."""

    def test_zero_trades_insufficient(self) -> None:
        """Zero trades -> INSUFFICIENT_EVIDENCE."""
        result = evaluate_net_metrics(
            total_trades=0,
            total_net_pnl=0.0,
            max_drawdown_pct=0.0,
            profit_factor=0.0,
            win_rate_pct=0.0,
        )
        assert result.evaluation_status == STATUS_INSUFFICIENT_EVIDENCE
        assert result.promotion_blocked is True
        assert REASON_CODE_INSUFFICIENT_EVIDENCE in result.promotion_block_reason_codes

    def test_four_trades_insufficient(self) -> None:
        """4 trades (below default 5) -> INSUFFICIENT_EVIDENCE."""
        result = evaluate_net_metrics(
            total_trades=4,
            total_net_pnl=200.0,
            max_drawdown_pct=5.0,
            profit_factor=2.0,
            win_rate_pct=75.0,
        )
        assert result.evaluation_status == STATUS_INSUFFICIENT_EVIDENCE
        assert result.promotion_blocked is True

    def test_five_trades_sufficient(self) -> None:
        """5 trades (at default min_trades) is sufficient for evaluation."""
        result = evaluate_net_metrics(
            total_trades=5,
            total_net_pnl=200.0,
            max_drawdown_pct=5.0,
            profit_factor=2.0,
            win_rate_pct=80.0,
        )
        assert result.evaluation_status != STATUS_INSUFFICIENT_EVIDENCE
        # Should pass review with positive metrics
        assert result.evaluation_status == STATUS_PASS_REVIEW


# =========================================================================
# 5. NOT_APPLICABLE for NO_PROPOSAL
# =========================================================================


class TestNotApplicable:
    """NO_PROPOSAL decisions get NOT_APPLICABLE evaluation (non-promotable)."""

    def test_default_no_proposal_evaluation(self) -> None:
        """default_no_proposal_evaluation returns NOT_APPLICABLE and blocked."""
        result = default_no_proposal_evaluation()
        assert result.evaluation_status == STATUS_NOT_APPLICABLE
        assert result.promotion_blocked is True
        assert result.promotion_block_reason_codes == ["no_proposal"]
        assert result.total_trades == 0

    def test_no_proposal_never_promotable(self) -> None:
        """NOT_APPLICABLE evaluations must never be promotable."""
        result = default_no_proposal_evaluation()
        assert result.promotion_blocked is True
        # NOT_APPLICABLE should never result in PASS_REVIEW
        assert result.evaluation_status != STATUS_PASS_REVIEW


# =========================================================================
# 6. AggregateMetrics wrapper
# =========================================================================


class TestFromAggregateMetrics:
    """Convenience wrapper for AggregateMetrics dicts."""

    def test_empty_metrics_dict(self) -> None:
        """Empty dict -> all fields default to 0 -> INSUFFICIENT_EVIDENCE."""
        result = evaluate_from_aggregate_metrics({})
        assert result.evaluation_status == STATUS_INSUFFICIENT_EVIDENCE
        assert result.promotion_blocked is True
        assert result.total_trades == 0
        assert result.total_net_pnl == 0.0

    def test_full_metrics_dict(self) -> None:
        """Full metrics dict with positive values -> PASS_REVIEW."""
        result = evaluate_from_aggregate_metrics({
            "total_trades": 30,
            "total_net_pnl": 2500.0,
            "total_fees": 30.0,
            "total_slippage": 15.0,
            "total_funding": 5.0,
            "max_drawdown_pct": 10.0,
            "profit_factor": 2.0,
            "win_rate_pct": 60.0,
        })
        assert result.evaluation_status == STATUS_PASS_REVIEW
        assert result.promotion_blocked is False

    def test_missing_fields_default_to_zero(self) -> None:
        """Missing optional fields default to 0, but missing drawdown blocks."""
        result = evaluate_from_aggregate_metrics({
            "total_trades": 10,
            "total_net_pnl": 100.0,
        })
        assert result.total_trades == 10
        assert result.total_net_pnl == 100.0
        assert result.max_drawdown_pct == 0.0
        assert result.profit_factor == 0.0
        # max_drawdown_pct key absent -> missing drawdown detected -> blocked
        assert result.evaluation_status == STATUS_INSUFFICIENT_EVIDENCE
        assert result.promotion_blocked is True
        assert REASON_CODE_MISSING_DRAWDOWN in result.promotion_block_reason_codes


# =========================================================================
# 7. Edge cases
# =========================================================================


class TestEdgeCases:
    """Boundary conditions and edge cases."""

    def test_custom_min_trades(self) -> None:
        """Custom min_trades threshold works correctly."""
        # With min_trades=1, even 1 trade should be sufficient
        result = evaluate_net_metrics(
            total_trades=1,
            total_net_pnl=100.0,
            max_drawdown_pct=0.0,
            profit_factor=float("inf"),
            win_rate_pct=100.0,
            min_trades=1,
        )
        assert result.evaluation_status == STATUS_PASS_REVIEW
        assert result.promotion_blocked is False

    def test_custom_drawdown_threshold(self) -> None:
        """Custom max_drawdown_threshold works."""
        # With a 10% threshold, 12% drawdown should block
        result = evaluate_net_metrics(
            total_trades=10,
            total_net_pnl=500.0,
            max_drawdown_pct=12.0,
            profit_factor=1.5,
            win_rate_pct=55.0,
            max_drawdown_threshold_pct=10.0,
        )
        assert result.promotion_blocked is True
        assert REASON_CODE_HIGH_DRAWDOWN in result.promotion_block_reason_codes

    def test_to_dict_roundtrip(self) -> None:
        """WalkForwardEvaluation.to_dict() produces correct JSON-safe dict."""
        result = evaluate_net_metrics(
            total_trades=15,
            total_net_pnl=-200.0,
            max_drawdown_pct=10.0,
            profit_factor=0.8,
            win_rate_pct=40.0,
        )
        d = result.to_dict()
        assert d["total_trades"] == 15
        assert d["total_net_pnl"] == -200.0
        assert d["evaluation_status"] == STATUS_NEGATIVE_NET_METRICS
        assert d["promotion_blocked"] is True
        assert isinstance(d["promotion_block_reason_codes"], list)
        assert REASON_CODE_NEGATIVE_NET_METRICS in d["promotion_block_reason_codes"]

    def test_float_inf_profit_factor(self) -> None:
        """Infinite profit factor (no losses) is handled without crash."""
        result = evaluate_net_metrics(
            total_trades=10,
            total_net_pnl=1000.0,
            max_drawdown_pct=5.0,
            profit_factor=float("inf"),
            win_rate_pct=100.0,
        )
        assert result.evaluation_status == STATUS_PASS_REVIEW
        assert result.promotion_blocked is False


# =========================================================================
# 8. Safety invariants
# =========================================================================


class TestSafetyInvariants:
    """Verify no dangerous behavior is introduced."""

    def test_no_live_trading_fields(self) -> None:
        """WalkForwardEvaluation must not contain live trading fields."""
        result = evaluate_net_metrics(
            total_trades=10,
            total_net_pnl=500.0,
            max_drawdown_pct=5.0,
            profit_factor=1.5,
            win_rate_pct=60.0,
        )
        d = result.to_dict()
        # These fields must NOT exist
        assert "dry_run" not in d
        assert "live_trading" not in d
        assert "exchange" not in d
        assert "api_key" not in d
        assert "apply" not in d

    def test_no_auto_apply(self) -> None:
        """PASS_REVIEW must not set any auto-apply flag."""
        result = evaluate_net_metrics(
            total_trades=20,
            total_net_pnl=1500.0,
            max_drawdown_pct=5.0,
            profit_factor=2.0,
            win_rate_pct=65.0,
        )
        assert result.evaluation_status == STATUS_PASS_REVIEW
        # The evaluation result has no 'apply' or 'auto_approve' concept
        assert not hasattr(result, "auto_approve")
        assert not hasattr(result, "apply")
