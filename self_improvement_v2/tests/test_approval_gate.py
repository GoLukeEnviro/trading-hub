"""Tests for the Human Approval Gate (#276).

Covers positive and negative approval-eligibility cases for all four bots,
matching the acceptance criteria from issue #276:

  - Approval-Gate accepts only ShadowProposals with complete real evidence
  - NO_PROPOSAL, INSUFFICIENT_EVIDENCE, NEGATIVE_NET_METRICS, missing_drawdown,
    high_drawdown and auth errors remain not approval-eligible
  - Approval status model: PENDING_HUMAN, APPROVED, REJECTED, EXPIRED, NOT_APPLICABLE
  - Per-bot approval, no cross-bot leakage
  - No secrets in approval artifacts
  - No auto-apply, no auto-promotion, human approval remains mandatory

Test data is derived from realistic scenarios observed in natural scheduled
SI v2 cycles (20260619T121720Z, 20260619T181720Z).
"""

from __future__ import annotations

from si_v2.approval.approval_gate import (
    REASON_HIGH_DRAWDOWN,
    REASON_INSUFFICIENT_EVIDENCE,
    REASON_INSUFFICIENT_TRADES,
    REASON_METRICS_NOT_REAL,
    REASON_METRICS_PARTIAL,
    REASON_MISSING_DRAWDOWN,
    REASON_MISSING_PNL,
    REASON_MISSING_PROFIT_FACTOR,
    REASON_NEGATIVE_NET_METRICS,
    REASON_NO_PROPOSAL,
    REASON_NOT_APPLICABLE_EVALUATION,
    REASON_PROMOTION_BLOCKED,
    ApprovalGateVerdict,
    ApprovalStatus,
    evaluate_approval_eligibility,
)

# ---------------------------------------------------------------------------
# Status model tests
# ---------------------------------------------------------------------------


class TestApprovalStatusModel:
    """Verify the approval status enum and verdict dataclass."""

    def test_status_values(self) -> None:
        assert ApprovalStatus.PENDING_HUMAN == "PENDING_HUMAN"
        assert ApprovalStatus.APPROVED == "APPROVED"
        assert ApprovalStatus.REJECTED == "REJECTED"
        assert ApprovalStatus.EXPIRED == "EXPIRED"
        assert ApprovalStatus.NOT_APPLICABLE == "NOT_APPLICABLE"

    def test_verdict_to_dict_has_no_secrets(self) -> None:
        verdict = ApprovalGateVerdict(
            bot_id="freqtrade-freqforge",
            approval_status=ApprovalStatus.PENDING_HUMAN,
            approval_eligible=True,
            reason_codes=[],
        )
        d = verdict.to_dict()
        assert "secret" not in str(d).lower()
        assert "password" not in str(d).lower()
        assert "token" not in str(d).lower()
        assert d["bot_id"] == "freqtrade-freqforge"
        assert d["approval_status"] == "PENDING_HUMAN"
        assert d["approval_eligible"] is True
        assert d["reason_codes"] == []

    def test_verdict_is_frozen(self) -> None:
        """Verdict dataclass must be immutable."""
        verdict = ApprovalGateVerdict(
            bot_id="test",
            approval_status=ApprovalStatus.NOT_APPLICABLE,
            approval_eligible=False,
        )
        try:
            verdict.bot_id = "other"  # type: ignore[misc]
            raise AssertionError("Should have raised FrozenInstanceError")
        except AttributeError:
            pass


# ---------------------------------------------------------------------------
# Positive case — eligible for approval
# ---------------------------------------------------------------------------


class TestApprovalEligiblePositive:
    """A ShadowProposal with complete real evidence and PASS_REVIEW is eligible."""

    def test_full_positive_case(self) -> None:
        verdict = evaluate_approval_eligibility(
            bot_id="freqtrade-freqforge",
            decision_type="SHADOW_PROPOSAL",
            evaluation_status="PASS_REVIEW",
            metrics_source="real",
            promotion_blocked=False,
            promotion_block_reason_codes=[],
            total_trades=15,
            total_net_pnl=42.5,
            profit_factor=1.8,
            max_drawdown_pct=5.2,
        )
        assert verdict.approval_status == ApprovalStatus.PENDING_HUMAN
        assert verdict.approval_eligible is True
        assert verdict.reason_codes == []

    def test_positive_with_min_trades_boundary(self) -> None:
        """Exactly min_trades (5) should still be eligible."""
        verdict = evaluate_approval_eligibility(
            bot_id="freqtrade-regime-hybrid",
            decision_type="SHADOW_PROPOSAL",
            evaluation_status="PASS_REVIEW",
            metrics_source="real",
            promotion_blocked=False,
            promotion_block_reason_codes=[],
            total_trades=5,
            total_net_pnl=10.0,
            profit_factor=1.2,
            max_drawdown_pct=3.0,
        )
        assert verdict.approval_eligible is True

    def test_positive_with_zero_pnl(self) -> None:
        """Zero PnL is a valid value (not None) — neutral metrics pass."""
        verdict = evaluate_approval_eligibility(
            bot_id="freqtrade-freqforge-canary",
            decision_type="SHADOW_PROPOSAL",
            evaluation_status="PASS_REVIEW",
            metrics_source="real",
            promotion_blocked=False,
            promotion_block_reason_codes=[],
            total_trades=10,
            total_net_pnl=0.0,
            profit_factor=1.0,
            max_drawdown_pct=2.0,
        )
        assert verdict.approval_eligible is True


# ---------------------------------------------------------------------------
# Negative cases — each blocking reason
# ---------------------------------------------------------------------------


class TestApprovalBlockedNoProposal:
    """NO_PROPOSAL decisions are never approval-applicable."""

    def test_no_proposal_returns_not_applicable(self) -> None:
        verdict = evaluate_approval_eligibility(
            bot_id="freqtrade-freqforge",
            decision_type="NO_PROPOSAL",
            evaluation_status="NOT_APPLICABLE",
            metrics_source="not_applicable",
            promotion_blocked=True,
            promotion_block_reason_codes=["no_proposal"],
        )
        assert verdict.approval_status == ApprovalStatus.NOT_APPLICABLE
        assert verdict.approval_eligible is False
        assert REASON_NO_PROPOSAL in verdict.reason_codes


class TestApprovalBlockedInsufficientEvidence:
    """INSUFFICIENT_EVIDENCE blocks approval eligibility."""

    def test_insufficient_evidence_blocks(self) -> None:
        verdict = evaluate_approval_eligibility(
            bot_id="freqai-rebel",
            decision_type="SHADOW_PROPOSAL",
            evaluation_status="INSUFFICIENT_EVIDENCE",
            metrics_source="real",
            promotion_blocked=True,
            promotion_block_reason_codes=["walk_forward_insufficient_evidence"],
            total_trades=2,
            total_net_pnl=5.0,
            profit_factor=1.1,
            max_drawdown_pct=1.0,
        )
        assert verdict.approval_status == ApprovalStatus.PENDING_HUMAN
        assert verdict.approval_eligible is False
        assert REASON_INSUFFICIENT_EVIDENCE in verdict.reason_codes
        assert REASON_INSUFFICIENT_TRADES in verdict.reason_codes


class TestApprovalBlockedNegativeMetrics:
    """NEGATIVE_NET_METRICS blocks approval eligibility."""

    def test_negative_net_metrics_blocks(self) -> None:
        verdict = evaluate_approval_eligibility(
            bot_id="freqtrade-regime-hybrid",
            decision_type="SHADOW_PROPOSAL",
            evaluation_status="NEGATIVE_NET_METRICS",
            metrics_source="real",
            promotion_blocked=True,
            promotion_block_reason_codes=["walk_forward_net_metrics_negative"],
            total_trades=10,
            total_net_pnl=-14.26,
            profit_factor=0.58,
            max_drawdown_pct=0.77,
        )
        assert verdict.approval_status == ApprovalStatus.PENDING_HUMAN
        assert verdict.approval_eligible is False
        assert REASON_NEGATIVE_NET_METRICS in verdict.reason_codes


class TestApprovalBlockedMissingDrawdown:
    """Missing drawdown blocks approval eligibility."""

    def test_missing_drawdown_blocks(self) -> None:
        verdict = evaluate_approval_eligibility(
            bot_id="freqtrade-freqforge",
            decision_type="SHADOW_PROPOSAL",
            evaluation_status="INSUFFICIENT_EVIDENCE",
            metrics_source="partial",
            promotion_blocked=True,
            promotion_block_reason_codes=["walk_forward_missing_drawdown"],
            total_trades=10,
            total_net_pnl=5.0,
            profit_factor=1.2,
        )
        assert verdict.approval_eligible is False
        assert REASON_MISSING_DRAWDOWN in verdict.reason_codes
        assert REASON_METRICS_PARTIAL in verdict.reason_codes


class TestApprovalBlockedHighDrawdown:
    """High drawdown blocks approval eligibility."""

    def test_high_drawdown_blocks(self) -> None:
        verdict = evaluate_approval_eligibility(
            bot_id="freqai-rebel",
            decision_type="SHADOW_PROPOSAL",
            evaluation_status="NEGATIVE_NET_METRICS",
            metrics_source="real",
            promotion_blocked=True,
            promotion_block_reason_codes=["walk_forward_high_drawdown"],
            total_trades=15,
            total_net_pnl=20.0,
            profit_factor=1.3,
            max_drawdown_pct=20.0,
        )
        assert verdict.approval_eligible is False
        assert REASON_HIGH_DRAWDOWN in verdict.reason_codes


class TestApprovalBlockedMetricsSource:
    """Non-real metrics source blocks approval eligibility."""

    def test_not_applicable_metrics_source_blocks(self) -> None:
        verdict = evaluate_approval_eligibility(
            bot_id="freqtrade-freqforge",
            decision_type="SHADOW_PROPOSAL",
            evaluation_status="PASS_REVIEW",
            metrics_source="not_applicable",
            promotion_blocked=False,
            promotion_block_reason_codes=[],
            total_trades=10,
            total_net_pnl=10.0,
            profit_factor=1.2,
            max_drawdown_pct=3.0,
        )
        assert verdict.approval_eligible is False
        assert REASON_METRICS_NOT_REAL in verdict.reason_codes

    def test_partial_metrics_source_blocks(self) -> None:
        verdict = evaluate_approval_eligibility(
            bot_id="freqtrade-freqforge-canary",
            decision_type="SHADOW_PROPOSAL",
            evaluation_status="PASS_REVIEW",
            metrics_source="partial",
            promotion_blocked=False,
            promotion_block_reason_codes=[],
            total_trades=10,
            total_net_pnl=10.0,
            profit_factor=1.2,
            max_drawdown_pct=3.0,
        )
        assert verdict.approval_eligible is False
        assert REASON_METRICS_PARTIAL in verdict.reason_codes


class TestApprovalBlockedNotApplicableEvaluation:
    """NOT_APPLICABLE evaluation status returns NOT_APPLICABLE approval."""

    def test_not_applicable_evaluation(self) -> None:
        verdict = evaluate_approval_eligibility(
            bot_id="freqtrade-freqforge",
            decision_type="SHADOW_PROPOSAL",
            evaluation_status="NOT_APPLICABLE",
            metrics_source="not_applicable",
            promotion_blocked=True,
            promotion_block_reason_codes=["no_proposal"],
        )
        assert verdict.approval_status == ApprovalStatus.NOT_APPLICABLE
        assert verdict.approval_eligible is False
        assert REASON_NOT_APPLICABLE_EVALUATION in verdict.reason_codes


class TestApprovalBlockedMissingFields:
    """Missing evidence fields block approval eligibility."""

    def test_missing_pnl_blocks(self) -> None:
        verdict = evaluate_approval_eligibility(
            bot_id="freqtrade-freqforge",
            decision_type="SHADOW_PROPOSAL",
            evaluation_status="PASS_REVIEW",
            metrics_source="real",
            promotion_blocked=False,
            promotion_block_reason_codes=[],
            total_trades=10,
            total_net_pnl=None,
            profit_factor=1.2,
            max_drawdown_pct=3.0,
        )
        assert verdict.approval_eligible is False
        assert REASON_MISSING_PNL in verdict.reason_codes

    def test_missing_profit_factor_blocks(self) -> None:
        verdict = evaluate_approval_eligibility(
            bot_id="freqtrade-regime-hybrid",
            decision_type="SHADOW_PROPOSAL",
            evaluation_status="PASS_REVIEW",
            metrics_source="real",
            promotion_blocked=False,
            promotion_block_reason_codes=[],
            total_trades=10,
            total_net_pnl=10.0,
            profit_factor=None,
            max_drawdown_pct=3.0,
        )
        assert verdict.approval_eligible is False
        assert REASON_MISSING_PROFIT_FACTOR in verdict.reason_codes

    def test_insufficient_trades_blocks(self) -> None:
        verdict = evaluate_approval_eligibility(
            bot_id="freqai-rebel",
            decision_type="SHADOW_PROPOSAL",
            evaluation_status="PASS_REVIEW",
            metrics_source="real",
            promotion_blocked=False,
            promotion_block_reason_codes=[],
            total_trades=3,
            total_net_pnl=10.0,
            profit_factor=1.2,
            max_drawdown_pct=3.0,
        )
        assert verdict.approval_eligible is False
        assert REASON_INSUFFICIENT_TRADES in verdict.reason_codes


# ---------------------------------------------------------------------------
# Four-bot realistic scenario from natural scheduled cycles
# ---------------------------------------------------------------------------


class TestFourBotRealisticScenarios:
    """Test approval gate against realistic four-bot fleet data.

    Scenarios mirror the actual cycle state from 20260619T181720Z:
      - freqforge:       NO_PROPOSAL (insufficient_signal_depth)
      - regime-hybrid:   SHADOW_PROPOSAL, real metrics, net-negative
      - freqforge-canary: NO_PROPOSAL (insufficient_signal_depth)
      - freqai-rebel:    SHADOW_PROPOSAL, real metrics, net-negative
    """

    def _evaluate_all_four(self) -> dict[str, ApprovalGateVerdict]:
        """Evaluate all four bots with realistic cycle data."""
        return {
            "freqtrade-freqforge": evaluate_approval_eligibility(
                bot_id="freqtrade-freqforge",
                decision_type="NO_PROPOSAL",
                evaluation_status="NOT_APPLICABLE",
                metrics_source="not_applicable",
                promotion_blocked=True,
                promotion_block_reason_codes=["no_proposal"],
            ),
            "freqtrade-regime-hybrid": evaluate_approval_eligibility(
                bot_id="freqtrade-regime-hybrid",
                decision_type="SHADOW_PROPOSAL",
                evaluation_status="NEGATIVE_NET_METRICS",
                metrics_source="real",
                promotion_blocked=True,
                promotion_block_reason_codes=[
                    "walk_forward_net_metrics_negative",
                ],
                total_trades=10,
                total_net_pnl=-14.26,
                profit_factor=0.58,
                max_drawdown_pct=0.77,
            ),
            "freqtrade-freqforge-canary": evaluate_approval_eligibility(
                bot_id="freqtrade-freqforge-canary",
                decision_type="NO_PROPOSAL",
                evaluation_status="NOT_APPLICABLE",
                metrics_source="not_applicable",
                promotion_blocked=True,
                promotion_block_reason_codes=["no_proposal"],
            ),
            "freqai-rebel": evaluate_approval_eligibility(
                bot_id="freqai-rebel",
                decision_type="SHADOW_PROPOSAL",
                evaluation_status="NEGATIVE_NET_METRICS",
                metrics_source="real",
                promotion_blocked=True,
                promotion_block_reason_codes=[
                    "walk_forward_net_metrics_negative",
                ],
                total_trades=20,
                total_net_pnl=-0.64,
                profit_factor=0.21,
                max_drawdown_pct=0.04,
            ),
        }

    def test_all_four_none_eligible_current_cycle(self) -> None:
        """In the current cycle, none of the four bots is approval-eligible."""
        verdicts = self._evaluate_all_four()
        for bot_id, verdict in verdicts.items():
            assert verdict.approval_eligible is False, (
                f"{bot_id} should not be eligible"
            )

    def test_freqforge_no_proposal_not_applicable(self) -> None:
        verdicts = self._evaluate_all_four()
        v = verdicts["freqtrade-freqforge"]
        assert v.approval_status == ApprovalStatus.NOT_APPLICABLE
        assert REASON_NO_PROPOSAL in v.reason_codes

    def test_regime_hybrid_negative_metrics(self) -> None:
        verdicts = self._evaluate_all_four()
        v = verdicts["freqtrade-regime-hybrid"]
        assert v.approval_status == ApprovalStatus.PENDING_HUMAN
        assert REASON_NEGATIVE_NET_METRICS in v.reason_codes
        assert v.approval_eligible is False

    def test_canary_no_proposal_not_applicable(self) -> None:
        verdicts = self._evaluate_all_four()
        v = verdicts["freqtrade-freqforge-canary"]
        assert v.approval_status == ApprovalStatus.NOT_APPLICABLE
        assert REASON_NO_PROPOSAL in v.reason_codes

    def test_rebel_negative_metrics(self) -> None:
        verdicts = self._evaluate_all_four()
        v = verdicts["freqai-rebel"]
        assert v.approval_status == ApprovalStatus.PENDING_HUMAN
        assert REASON_NEGATIVE_NET_METRICS in v.reason_codes
        assert v.approval_eligible is False

    def test_no_cross_bot_contamination(self) -> None:
        """Each bot's verdict must reference only its own bot_id."""
        verdicts = self._evaluate_all_four()
        for bot_id, verdict in verdicts.items():
            # bot_id field must match exactly
            assert verdict.bot_id == bot_id
            # Reason codes are generic identifiers, not bot-specific
            for rc in verdict.reason_codes:
                assert rc.startswith("approval_")

    def test_all_verdicts_safe_for_audit(self) -> None:
        """No secrets in any verdict serialization."""
        verdicts = self._evaluate_all_four()
        for _bot_id, verdict in verdicts.items():
            serialized = str(verdict.to_dict())
            assert "secret" not in serialized.lower()
            assert "password" not in serialized.lower()
            assert "token" not in serialized.lower()
            assert "api_key" not in serialized.lower()


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestApprovalEdgeCases:
    """Edge cases and boundary conditions."""

    def test_empty_decision_type_treated_as_no_proposal(self) -> None:
        """Unknown decision types fall through to NOT_APPLICABLE via NOT_APPLICABLE evaluation."""
        verdict = evaluate_approval_eligibility(
            bot_id="test-bot",
            decision_type="",
            evaluation_status="NOT_APPLICABLE",
            metrics_source="not_applicable",
            promotion_blocked=True,
            promotion_block_reason_codes=["unknown"],
        )
        # Empty decision_type is not "NO_PROPOSAL", so Gate 1 passes
        # Gate 2 catches NOT_APPLICABLE evaluation
        assert verdict.approval_status == ApprovalStatus.NOT_APPLICABLE
        assert verdict.approval_eligible is False

    def test_promotion_blocked_without_specific_reason(self) -> None:
        """If promotion_blocked=True but no specific reason, generic reason added."""
        verdict = evaluate_approval_eligibility(
            bot_id="test-bot",
            decision_type="SHADOW_PROPOSAL",
            evaluation_status="PASS_REVIEW",
            metrics_source="real",
            promotion_blocked=True,
            promotion_block_reason_codes=["some_other_block"],
            total_trades=10,
            total_net_pnl=5.0,
            profit_factor=1.2,
            max_drawdown_pct=3.0,
        )
        assert verdict.approval_eligible is False
        assert REASON_PROMOTION_BLOCKED in verdict.reason_codes

    def test_custom_min_trades_override(self) -> None:
        """Custom min_trades threshold is respected."""
        verdict = evaluate_approval_eligibility(
            bot_id="test-bot",
            decision_type="SHADOW_PROPOSAL",
            evaluation_status="PASS_REVIEW",
            metrics_source="real",
            promotion_blocked=False,
            promotion_block_reason_codes=[],
            total_trades=5,
            total_net_pnl=5.0,
            profit_factor=1.2,
            max_drawdown_pct=3.0,
            min_trades=10,
        )
        assert verdict.approval_eligible is False
        assert REASON_INSUFFICIENT_TRADES in verdict.reason_codes

    def test_multiple_blocking_reasons_accumulated(self) -> None:
        """Multiple blocking reasons are all accumulated in reason_codes."""
        verdict = evaluate_approval_eligibility(
            bot_id="test-bot",
            decision_type="SHADOW_PROPOSAL",
            evaluation_status="INSUFFICIENT_EVIDENCE",
            metrics_source="not_applicable",
            promotion_blocked=True,
            promotion_block_reason_codes=[
                "walk_forward_insufficient_evidence",
                "walk_forward_missing_drawdown",
            ],
            total_trades=2,
            total_net_pnl=None,
            profit_factor=None,
        )
        assert verdict.approval_eligible is False
        assert REASON_INSUFFICIENT_EVIDENCE in verdict.reason_codes
        assert REASON_METRICS_NOT_REAL in verdict.reason_codes
        assert REASON_MISSING_DRAWDOWN in verdict.reason_codes
        assert REASON_INSUFFICIENT_TRADES in verdict.reason_codes
        assert REASON_MISSING_PNL in verdict.reason_codes
        assert REASON_MISSING_PROFIT_FACTOR in verdict.reason_codes
