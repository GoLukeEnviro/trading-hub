"""Tests for promotion policy and gate behavior (issue #35)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from si_v2.propose.proposal_scoring import (
    DEFAULT_SCORING_POLICY_V1,
    BacktestMetrics,
    DataQualityVerdict,
    DirectionHint,
    PromotionStage,
    ProposalRejectionReason,
    ProposalScoreInput,
    ScoringPolicy,
    WalkForwardMetrics,
    score_proposal,
    validate_policy,
)
from si_v2.propose.proposal_scoring.models import ComponentWeights


def _make_input(
    *,
    backtest: BacktestMetrics | None = None,
    walk_forward: WalkForwardMetrics | None = None,
) -> ProposalScoreInput:
    return ProposalScoreInput(
        evidence_id="evi-1",
        source_id="rainbow:ta",
        regime="bullish",
        evidence_schema_version=1,
        unique_trade_count=80,
        expectancy=Decimal("0.012"),
        drawdown_proxy=Decimal("0.12"),
        average_source_confidence=Decimal("0.82"),
        average_regime_confidence=Decimal("0.75"),
        evidence_age_days=Decimal("3"),
        data_quality_verdict=DataQualityVerdict.ACCEPTED,
        is_actionable=True,
        direction_hint=DirectionHint.INCREASE,
        has_conflict=False,
        human_approval_available=True,
        backtest_metrics=backtest,
        walk_forward_metrics=walk_forward,
    )


def _strong_backtest() -> BacktestMetrics:
    return BacktestMetrics(
        passed=True,
        total_trades=120,
        profit_total_pct=Decimal("12.5"),
        max_drawdown_pct=Decimal("0.08"),
        win_rate_pct=Decimal("62.0"),
        profit_factor=Decimal("1.85"),
        sharpe=Decimal("1.4"),
    )


def _strong_walk_forward() -> WalkForwardMetrics:
    return WalkForwardMetrics(
        passed=True,
        stability_score=Decimal("0.78"),
        out_of_sample_profit_total_pct=Decimal("0.06"),
        reason="stable",
    )


class TestPromotionStageAcceptance:
    def test_accept_stage(self) -> None:
        d = score_proposal(
            _make_input(backtest=_strong_backtest(), walk_forward=_strong_walk_forward()),
            DEFAULT_SCORING_POLICY_V1,
        )
        assert d.decision == "ACCEPT"
        assert d.promotion_stage == PromotionStage.APPROVAL_REQUEST_READY


class TestPromotionStageBacktestRequired:
    def test_backtest_required_when_missing(self) -> None:
        d = score_proposal(
            _make_input(walk_forward=_strong_walk_forward()),
            DEFAULT_SCORING_POLICY_V1,
        )
        assert d.promotion_stage == PromotionStage.BACKTEST_REQUIRED
        assert d.decision == "REJECT"
        assert ProposalRejectionReason.MISSING_MANDATORY_BACKTEST in d.typed_reasons


class TestPromotionStageWalkForwardRequired:
    def test_walk_forward_required_when_missing(self) -> None:
        d = score_proposal(
            _make_input(backtest=_strong_backtest()),
            DEFAULT_SCORING_POLICY_V1,
        )
        assert d.promotion_stage == PromotionStage.WALK_FORWARD_REQUIRED
        assert d.decision == "REJECT"
        assert (
            ProposalRejectionReason.MISSING_MANDATORY_WALK_FORWARD
            in d.typed_reasons
        )


class TestPromotionStageProposalOnly:
    def test_proposal_only_on_low_score(self) -> None:
        # All gates pass but score is low (no backtest/wf to bump it up)
        policy = DEFAULT_SCORING_POLICY_V1.model_copy(
            update={
                "require_backtest_for_promotion": False,
                "require_walk_forward_for_promotion": False,
            }
        )
        # With all-zero components except sample/expectancy, the score is
        # very low → REJECT with stage PROPOSAL_ONLY.
        inp = ProposalScoreInput(
            evidence_id="evi-2",
            source_id="rainbow:ta",
            regime="bullish",
            evidence_schema_version=1,
            unique_trade_count=80,
            expectancy=Decimal("0.001"),
            drawdown_proxy=Decimal("0.20"),
            average_source_confidence=Decimal("0.30"),
            average_regime_confidence=Decimal("0.30"),
            evidence_age_days=Decimal("29"),
            data_quality_verdict=DataQualityVerdict.ACCEPTED,
            is_actionable=True,
            direction_hint=DirectionHint.NEUTRAL,
            has_conflict=False,
            human_approval_available=True,
        )
        d = score_proposal(inp, policy)
        # All hard gates pass, score < defer threshold → REJECT
        assert d.decision == "REJECT"
        assert d.promotion_stage == PromotionStage.PROPOSAL_ONLY


class TestMaximumProposalDelta:
    def test_default_maximum_proposal_delta(self) -> None:
        assert (
            DEFAULT_SCORING_POLICY_V1.maximum_proposal_delta == Decimal("0.10")
        )

    def test_custom_maximum_delta_quantized(self) -> None:
        policy = DEFAULT_SCORING_POLICY_V1.model_copy(
            update={"maximum_proposal_delta": Decimal("0.050000")}
        )
        assert policy.maximum_proposal_delta == Decimal("0.050000")


class TestPolicyValidation:
    def test_default_policy_validates(self) -> None:
        validate_policy(DEFAULT_SCORING_POLICY_V1)

    def test_inverted_thresholds_rejected(self) -> None:
        with pytest.raises((ValueError, ValidationError)):
            ScoringPolicy(
                defer_threshold=Decimal("0.80"),
                accept_threshold=Decimal("0.50"),
            )

    def test_defer_equals_accept_rejected(self) -> None:
        with pytest.raises((ValueError, ValidationError)):
            ScoringPolicy(
                defer_threshold=Decimal("0.50"),
                accept_threshold=Decimal("0.50"),
            )


class TestComponentWeightsValidation:
    def test_default_weights_sum_to_one(self) -> None:
        w = DEFAULT_SCORING_POLICY_V1.component_weights
        total = (
            w.sample
            + w.expectancy
            + w.drawdown
            + w.confidence
            + w.recency
            + w.backtest
            + w.walk_forward
            + w.quality
        )
        assert abs(total - Decimal("1")) <= Decimal("1e-9")

    def test_weights_exactly_one_accepted(self) -> None:
        # Slightly less than one to avoid float drift
        cw = ComponentWeights(
            sample=Decimal("0.10"),
            expectancy=Decimal("0.20"),
            drawdown=Decimal("0.20"),
            confidence=Decimal("0.10"),
            recency=Decimal("0.05"),
            backtest=Decimal("0.15"),
            walk_forward=Decimal("0.15"),
            quality=Decimal("0.050000"),
        )
        assert cw is not None

    def test_weights_drift_rejected(self) -> None:
        with pytest.raises((ValueError, ValidationError)):
            ComponentWeights(
                sample=Decimal("0.10"),
                expectancy=Decimal("0.20"),
                drawdown=Decimal("0.20"),
                confidence=Decimal("0.10"),
                recency=Decimal("0.05"),
                backtest=Decimal("0.15"),
                walk_forward=Decimal("0.15"),
                quality=Decimal("0.050001"),  # total 1.000001 → reject
            )


class TestAcceptDeferThresholdsQuantized:
    def test_thresholds_quantized(self) -> None:
        # The default thresholds must be quantized to SCORING_QUANTUM
        from si_v2.propose.proposal_scoring.decimal_safe import SCORING_QUANTUM

        assert (
            DEFAULT_SCORING_POLICY_V1.accept_threshold.quantize(SCORING_QUANTUM)
            == DEFAULT_SCORING_POLICY_V1.accept_threshold
        )
        assert (
            DEFAULT_SCORING_POLICY_V1.defer_threshold.quantize(SCORING_QUANTUM)
            == DEFAULT_SCORING_POLICY_V1.defer_threshold
        )
