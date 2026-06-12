"""ScoringPolicy construction and validation helpers.

The default policy is exposed as a module-level constant so it can be
reused everywhere (notably by issue #63). Custom policies are accepted
only if they pass ``validate_policy``.
"""

from __future__ import annotations

from decimal import Decimal

from si_v2.propose.proposal_scoring.decimal_safe import SCORING_QUANTUM
from si_v2.propose.proposal_scoring.models import (
    ACCEPT_THRESHOLD_DEFAULT,
    DEFAULT_COMPONENT_WEIGHTS,
    DEFER_THRESHOLD_DEFAULT,
    MAXIMUM_PROPOSAL_DELTA_DEFAULT,
    POLICY_VERSION,
    BacktestThresholds,
    ComponentWeights,
    ScoringPolicy,
    WalkForwardStabilityThresholds,
)

DEFAULT_BACKTEST_THRESHOLDS: BacktestThresholds = BacktestThresholds()
DEFAULT_WALK_FORWARD_STABILITY: WalkForwardStabilityThresholds = (
    WalkForwardStabilityThresholds()
)

DEFAULT_SCORING_POLICY_V1: ScoringPolicy = ScoringPolicy(
    policy_version=POLICY_VERSION,
    minimum_sample_count=30,
    maximum_evidence_age_days=Decimal("30"),
    minimum_expectancy=Decimal("0.0"),
    maximum_drawdown_proxy=Decimal("0.25"),
    minimum_confidence=Decimal("0.30"),
    minimum_backtest_thresholds=DEFAULT_BACKTEST_THRESHOLDS,
    minimum_walk_forward_stability=DEFAULT_WALK_FORWARD_STABILITY,
    component_weights=ComponentWeights(**DEFAULT_COMPONENT_WEIGHTS),
    accept_threshold=ACCEPT_THRESHOLD_DEFAULT,
    defer_threshold=DEFER_THRESHOLD_DEFAULT,
    maximum_proposal_delta=MAXIMUM_PROPOSAL_DELTA_DEFAULT,
    require_backtest_for_promotion=True,
    require_walk_forward_for_promotion=True,
    accepted_evidence_schema_versions=(1,),
)


def validate_policy(policy: ScoringPolicy) -> None:
    """Validate a ``ScoringPolicy`` beyond the checks already enforced by
    Pydantic.

    This function is idempotent — it raises ``ValueError`` on the first
    violation, and returns ``None`` on success.

    Checks (in addition to those already in Pydantic):

    - Component weights sum to ``1.0`` within ``1e-9``.
    - All component weights are non-negative.
    - ``defer_threshold < accept_threshold``.
    - All Decimal thresholds are quantized to ``SCORING_QUANTUM``.
    """
    weights = policy.component_weights
    weight_values = (
        weights.sample,
        weights.expectancy,
        weights.drawdown,
        weights.confidence,
        weights.recency,
        weights.backtest,
        weights.walk_forward,
        weights.quality,
    )
    for name, value in zip(
        (
            "sample",
            "expectancy",
            "drawdown",
            "confidence",
            "recency",
            "backtest",
            "walk_forward",
            "quality",
        ),
        weight_values,
        strict=True,
    ):
        if value < Decimal("0"):
            raise ValueError(
                f"ComponentWeights.{name} must be non-negative; got {value}"
            )
    total = sum(weight_values, Decimal("0"))
    if abs(total - Decimal("1")) > Decimal("0.000000001"):
        raise ValueError(
            f"ComponentWeights must sum to 1.0 within 1e-9; got {total}"
        )

    if policy.defer_threshold >= policy.accept_threshold:
        raise ValueError(
            "defer_threshold must be strictly less than accept_threshold; "
            f"got defer={policy.defer_threshold}, accept={policy.accept_threshold}"
        )

    for fname, value in (
        ("accept_threshold", policy.accept_threshold),
        ("defer_threshold", policy.defer_threshold),
        ("maximum_proposal_delta", policy.maximum_proposal_delta),
        ("maximum_evidence_age_days", policy.maximum_evidence_age_days),
        ("maximum_drawdown_proxy", policy.maximum_drawdown_proxy),
        ("minimum_confidence", policy.minimum_confidence),
        ("minimum_expectancy", policy.minimum_expectancy),
    ):
        if value.quantize(SCORING_QUANTUM) != value:
            raise ValueError(
                f"ScoringPolicy.{fname}={value} is not quantized to "
                f"SCORING_QUANTUM={SCORING_QUANTUM}"
            )
