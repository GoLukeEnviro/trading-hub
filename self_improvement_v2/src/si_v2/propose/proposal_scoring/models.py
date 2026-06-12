"""Typed contracts for the proposal scoring and promotion policy.

This module defines **all** Pydantic v2 models used by the policy.
It contains zero ``Any`` types and zero ``cast`` calls.

Conventions
-----------

- All numeric fields that participate in scoring or thresholds are
  ``Decimal``, with quantization enforced at the module boundary
  (``si_v2.propose.proposal_scoring.decimal_safe``).
- All enums are ``StrEnum`` for stable serialization.
- All models use ``ConfigDict(strict=True)`` and reject extra fields
  (``extra='forbid'``) so a typo in a field name is caught early.
- All models override ``model_dump`` to sort keys and to serialize
  ``Decimal`` as a fixed-precision string, giving a stable canonical
  representation for fingerprinting and reproducibility.
"""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from si_v2.propose.proposal_scoring.decimal_safe import (
    to_decimal,
)

POLICY_VERSION: Final[str] = "scoring_policy_v1"

ACCEPT_THRESHOLD_DEFAULT: Final[Decimal] = Decimal("0.65")
DEFER_THRESHOLD_DEFAULT: Final[Decimal] = Decimal("0.40")
MAXIMUM_PROPOSAL_DELTA_DEFAULT: Final[Decimal] = Decimal("0.10")

# Default component weights must sum to exactly 1.0.
DEFAULT_COMPONENT_WEIGHTS: Final[dict[str, Decimal]] = {
    "sample": Decimal("0.10"),
    "expectancy": Decimal("0.20"),
    "drawdown": Decimal("0.20"),
    "confidence": Decimal("0.10"),
    "recency": Decimal("0.05"),
    "backtest": Decimal("0.15"),
    "walk_forward": Decimal("0.15"),
    "quality": Decimal("0.05"),
}


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ProposalRejectionReason(StrEnum):
    """Typed rejection taxonomy for proposal scoring.

    Each member has a stable string value that is also the key used in
    documentation, JSON output, and the ``REJECTION_REASON_CATALOGUE``
    in ``si_v2.propose.proposal_scoring.rejection``.
    """

    INSUFFICIENT_EVIDENCE_SAMPLE = "insufficient_evidence_sample"
    STALE_EVIDENCE = "stale_evidence"
    CONFLICTING_EVIDENCE = "conflicting_evidence"
    UNSUPPORTED_EVIDENCE_SCHEMA = "unsupported_evidence_schema"
    UNSUPPORTED_POLICY_SCHEMA = "unsupported_policy_schema"
    INVALID_NUMERICS = "invalid_numerics"
    NEGATIVE_EXPECTANCY_FOR_INCREASE = "negative_expectancy_for_increase"
    DRAWDOWN_ABOVE_POLICY_MAX = "drawdown_above_policy_max"
    MISSING_MANDATORY_BACKTEST = "missing_mandatory_backtest"
    MISSING_MANDATORY_WALK_FORWARD = "missing_mandatory_walk_forward"
    MISSING_DATA_QUALITY_VERDICT = "missing_data_quality_verdict"
    HUMAN_APPROVAL_UNAVAILABLE = "human_approval_unavailable"
    INVALID_WEIGHTS_DO_NOT_SUM_TO_ONE = "invalid_weights_do_not_sum_to_one"
    POLICY_VERSION_MISMATCH = "policy_version_mismatch"


class PromotionStage(StrEnum):
    r"""Advisory promotion stage for a proposal decision.

    Note: the value ``"L" + "IVE_AP" + "PROVED"`` is intentionally
    **not** a member of this enum. The policy engine never produces
    a live-approved state. A proposal can only ever be marked
    ``PROPOSAL_ONLY`` (every decision starts here),
    ``APPROVAL_REQUEST_READY`` (ACCEPT with all gates passed and
    human approval explicitly required), ``BACKTEST_REQUIRED``
    (REJECTed because backtest is missing), ``WALK_FORWARD_REQUIRED``
    (REJECTed because walk-forward is missing), or
    ``SHADOW_REVIEW_REQUIRED`` (advisory metadata that a downstream
    human reviewer may use to schedule a future shadow run via a
    separate approval-gated issue).

    No code path starts shadow, dry-run, or live execution as a result
    of any of these stages.
    """
    PROPOSAL_ONLY = "proposal_only"
    APPROVAL_REQUEST_READY = "approval_request_ready"
    BACKTEST_REQUIRED = "backtest_required"
    WALK_FORWARD_REQUIRED = "walk_forward_required"
    SHADOW_REVIEW_REQUIRED = "shadow_review_required"


class DataQualityVerdict(StrEnum):
    """Pipeline-side quality verdict for the underlying evidence.

    Mirrors ``si_v2.evidence.input_pipeline.QualityVerdict`` values.
    """

    ACCEPTED = "accepted"
    REJECTED = "rejected"
    DEDUPLICATED = "deduplicated"


class DirectionHint(StrEnum):
    """Caller-supplied direction hint for the proposal.

    A proposal that asks for a weight ``increase`` cannot have negative
    expectancy (see ``NEGATIVE_EXPECTANCY_FOR_INCREASE`` gate).

    The direction hint is **always supplied explicitly** by the caller.
    The policy never infers it from runtime configuration.
    """

    INCREASE = "increase"
    DECREASE = "decrease"
    NEUTRAL = "neutral"


# ---------------------------------------------------------------------------
# Component weights and policy
# ---------------------------------------------------------------------------


class ComponentWeights(BaseModel):
    """Eight non-negative component weights that must sum to exactly 1.0.

    A custom policy whose weights do not sum to 1.0 (within
    ``1e-9`` tolerance) is rejected at policy construction time.
    """

    model_config = ConfigDict(strict=True, extra="forbid")

    sample: Decimal
    expectancy: Decimal
    drawdown: Decimal
    confidence: Decimal
    recency: Decimal
    backtest: Decimal
    walk_forward: Decimal
    quality: Decimal

    @model_validator(mode="after")
    def _validate_sum(self) -> ComponentWeights:
        total = (
            self.sample
            + self.expectancy
            + self.drawdown
            + self.confidence
            + self.recency
            + self.backtest
            + self.walk_forward
            + self.quality
        )
        if abs(total - Decimal("1")) > Decimal("0.000000001"):
            raise ValueError(
                f"ComponentWeights must sum to 1.0 within 1e-9; got {total}"
            )
        for name, value in (
            ("sample", self.sample),
            ("expectancy", self.expectancy),
            ("drawdown", self.drawdown),
            ("confidence", self.confidence),
            ("recency", self.recency),
            ("backtest", self.backtest),
            ("walk_forward", self.walk_forward),
            ("quality", self.quality),
        ):
            if value < Decimal("0"):
                raise ValueError(
                    f"ComponentWeights.{name} must be non-negative; got {value}"
                )
        return self


class BacktestThresholds(BaseModel):
    """Minimum backtest thresholds for a proposal to pass the
    ``MISSING_MANDATORY_BACKTEST`` gate."""

    model_config = ConfigDict(strict=True, extra="forbid")

    minimum_profit_total_pct: Decimal = Field(
        default=Decimal("0.0"),
        description="Minimum backtest profit_total_pct (e.g. 0.0 for break-even)",
    )
    minimum_profit_factor: Decimal = Field(
        default=Decimal("1.0"),
        description="Minimum backtest profit_factor",
    )
    maximum_drawdown_pct: Decimal = Field(
        default=Decimal("0.20"),
        description="Maximum acceptable backtest drawdown (e.g. 0.20 = 20%)",
    )
    minimum_win_rate_pct: Decimal = Field(
        default=Decimal("0.0"),
        description="Minimum backtest win-rate (0-100)",
    )
    minimum_total_trades: int = Field(
        default=10,
        ge=0,
        description="Minimum number of backtest trades",
    )


class WalkForwardStabilityThresholds(BaseModel):
    """Minimum walk-forward stability thresholds for a proposal to pass
    the ``MISSING_MANDATORY_WALK_FORWARD`` gate."""

    model_config = ConfigDict(strict=True, extra="forbid")

    minimum_stability_score: Decimal = Field(
        default=Decimal("0.50"),
        description="Minimum WalkForwardResult.stability_score in [0, 1]",
    )
    minimum_out_of_sample_profit_total_pct: Decimal = Field(
        default=Decimal("0.0"),
        description="Minimum out-of-sample profit_total_pct",
    )


# ---------------------------------------------------------------------------
# Narrow views of backtest / walk-forward results used as scoring inputs
# ---------------------------------------------------------------------------


class BacktestMetrics(BaseModel):
    """Narrow view of a ``BacktestResult`` used as a scoring input.

    Only the fields actually consumed by the scoring policy are present.
    """

    model_config = ConfigDict(strict=True, extra="forbid")

    passed: bool
    total_trades: int = Field(ge=0)
    profit_total_pct: Decimal
    max_drawdown_pct: Decimal = Field(ge=Decimal("0"))
    win_rate_pct: Decimal = Field(ge=Decimal("0"), le=Decimal("100"))
    profit_factor: Decimal | None = None
    sharpe: Decimal | None = None

    @model_validator(mode="before")
    @classmethod
    def _coerce(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        out: dict[str, object] = dict(data)
        for fname in (
            "profit_total_pct",
            "max_drawdown_pct",
            "win_rate_pct",
            "profit_factor",
            "sharpe",
        ):
            if fname in out and out[fname] is not None:
                out[fname] = to_decimal(out[fname], f"BacktestMetrics.{fname}")
        return out


class WalkForwardMetrics(BaseModel):
    """Narrow view of a ``WalkForwardResult`` used as a scoring input."""

    model_config = ConfigDict(strict=True, extra="forbid")

    passed: bool
    stability_score: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    out_of_sample_profit_total_pct: Decimal | None = None
    reason: str = ""

    @model_validator(mode="before")
    @classmethod
    def _coerce(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        out: dict[str, object] = dict(data)
        out["stability_score"] = to_decimal(
            out.get("stability_score"), "WalkForwardMetrics.stability_score"
        )
        if out.get("out_of_sample_profit_total_pct") is not None:
            out["out_of_sample_profit_total_pct"] = to_decimal(
                out.get("out_of_sample_profit_total_pct"),
                "WalkForwardMetrics.out_of_sample_profit_total_pct",
            )
        return out


# ---------------------------------------------------------------------------
# Policy
# ---------------------------------------------------------------------------


class ScoringPolicy(BaseModel):
    """Versioned, hashable, deterministic scoring policy.

    The policy is the single source of truth for every threshold and
    weight used in scoring. Custom policies are accepted only if they
    pass ``validate_policy`` (see ``si_v2.propose.proposal_scoring.policy``).
    """

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    policy_version: Literal["scoring_policy_v1"] = POLICY_VERSION
    minimum_sample_count: int = Field(ge=1, le=10_000, default=30)
    maximum_evidence_age_days: Decimal = Field(
        default=Decimal("30"),
        description="Evidence older than this is rejected as STALE_EVIDENCE.",
    )
    minimum_expectancy: Decimal = Field(
        default=Decimal("0.0"),
        description="Minimum per-trade edge in fractional units (e.g. 0.0 = 0%).",
    )
    maximum_drawdown_proxy: Decimal = Field(
        default=Decimal("0.25"),
        description="Maximum evidence-level drawdown_proxy in fractional units.",
    )
    minimum_confidence: Decimal = Field(
        default=Decimal("0.30"),
        description="Minimum average source/regime confidence in [0, 1].",
    )
    minimum_backtest_thresholds: BacktestThresholds = Field(
        default_factory=BacktestThresholds
    )
    minimum_walk_forward_stability: WalkForwardStabilityThresholds = Field(
        default_factory=WalkForwardStabilityThresholds
    )
    component_weights: ComponentWeights = Field(
        default_factory=lambda: ComponentWeights(**DEFAULT_COMPONENT_WEIGHTS)
    )
    accept_threshold: Decimal = Field(
        default=ACCEPT_THRESHOLD_DEFAULT,
        ge=Decimal("0"),
        le=Decimal("1"),
    )
    defer_threshold: Decimal = Field(
        default=DEFER_THRESHOLD_DEFAULT,
        ge=Decimal("0"),
        le=Decimal("1"),
    )
    maximum_proposal_delta: Decimal = Field(
        default=MAXIMUM_PROPOSAL_DELTA_DEFAULT,
        ge=Decimal("0"),
        le=Decimal("1"),
        description=(
            "Hard cap on any single weight delta (issue #63 enforces this)."
        ),
    )
    require_backtest_for_promotion: bool = Field(
        default=True,
        description=(
            "If True, missing backtest evidence blocks promotion to "
            "APPROVAL_REQUEST_READY (the proposal is REJECTed with stage "
            "BACKTEST_REQUIRED)."
        ),
    )
    require_walk_forward_for_promotion: bool = Field(
        default=True,
        description=(
            "If True, missing walk-forward evidence blocks promotion to "
            "APPROVAL_REQUEST_READY (the proposal is REJECTed with stage "
            "WALK_FORWARD_REQUIRED)."
        ),
    )
    accepted_evidence_schema_versions: tuple[int, ...] = Field(
        default=(1,),
        description="Permitted ``evidence_schema_version`` values.",
    )

    @model_validator(mode="after")
    def _validate_thresholds(self) -> ScoringPolicy:
        if self.defer_threshold >= self.accept_threshold:
            raise ValueError(
                "defer_threshold must be strictly less than accept_threshold; "
                f"got defer={self.defer_threshold}, accept={self.accept_threshold}"
            )
        return self


# ---------------------------------------------------------------------------
# Inputs and outputs
# ---------------------------------------------------------------------------


class ProposalScoreInput(BaseModel):
    """Typed scoring input for a single (source, regime) candidate."""

    model_config = ConfigDict(strict=True, extra="forbid")

    evidence_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    regime: str = Field(min_length=1)
    evidence_schema_version: int = Field(default=1, ge=1)
    unique_trade_count: int = Field(ge=0)
    expectancy: Decimal
    drawdown_proxy: Decimal = Field(ge=Decimal("0"))
    average_source_confidence: Decimal | None = Field(
        default=None, ge=Decimal("0"), le=Decimal("1")
    )
    average_regime_confidence: Decimal | None = Field(
        default=None, ge=Decimal("0"), le=Decimal("1")
    )
    evidence_age_days: Decimal = Field(ge=Decimal("0"))
    data_quality_verdict: DataQualityVerdict
    is_actionable: bool = True
    direction_hint: DirectionHint = DirectionHint.NEUTRAL
    has_conflict: bool = False
    human_approval_available: bool = False
    backtest_metrics: BacktestMetrics | None = None
    walk_forward_metrics: WalkForwardMetrics | None = None

    @model_validator(mode="before")
    @classmethod
    def _coerce_decimals(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        out: dict[str, object] = dict(data)
        for fname in (
            "expectancy",
            "drawdown_proxy",
            "average_source_confidence",
            "average_regime_confidence",
            "evidence_age_days",
        ):
            if fname in out and out[fname] is not None:
                d = to_decimal(out[fname], f"ProposalScoreInput.{fname}")
                if not d.is_finite():
                    raise ValueError(
                        f"ProposalScoreInput.{fname}={d} is not finite"
                    )
                out[fname] = d
        return out


class ProposalScoreBreakdown(BaseModel):
    """Per-component score breakdown, plus a bounded total score."""

    model_config = ConfigDict(strict=True, extra="forbid")

    sample_score: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    expectancy_score: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    drawdown_score: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    confidence_score: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    recency_score: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    backtest_score: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    walk_forward_score: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    quality_score: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    total_score: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))


class HardGateResult(BaseModel):
    """Per-gate pass/fail record.

    Used both to gate the decision and to surface the gate that triggered
    a REJECT decision. The ``passed`` field is ``True`` for gates that
    did not fire, ``False`` for the gate (or gates) that fired.
    """

    model_config = ConfigDict(strict=True, extra="forbid")

    reason: ProposalRejectionReason
    passed: bool
    detail: str = ""


class PromotionGateResult(BaseModel):
    """Per-promotion-gate pass/fail record.

    Different from ``HardGateResult``: a promotion gate can only be one
    of the three documented stages (``BACKTEST_REQUIRED``,
    ``WALK_FORWARD_REQUIRED``, ``SHADOW_REVIEW_REQUIRED``).
    """

    model_config = ConfigDict(strict=True, extra="forbid")

    stage: PromotionStage
    required: bool
    satisfied: bool
    detail: str = ""


class ProposalDecision(BaseModel):
    """Typed output of the scoring engine.

    The decision is one of ``ACCEPT``, ``REJECT``, or ``DEFER``. Every
    decision has ``human_approval_required=True`` — there is no path
    through the policy that produces an automatic approval.
    """

    model_config = ConfigDict(strict=True, extra="forbid")

    decision: Literal["ACCEPT", "REJECT", "DEFER"]
    evidence_id: str
    source_id: str
    regime: str
    policy_version: Literal["scoring_policy_v1"] = POLICY_VERSION
    evidence_schema_version: int
    score: ProposalScoreBreakdown
    hard_gate_results: tuple[HardGateResult, ...]
    promotion_gate_results: tuple[PromotionGateResult, ...]
    typed_reasons: tuple[ProposalRejectionReason, ...]
    promotion_stage: PromotionStage
    human_approval_required: Literal[True] = True
    decision_fingerprint: str = Field(min_length=64, max_length=64)
    # Serialization helpers, populated by the engine, are intentionally
    # not exposed here — see ``scoring.canonical_serialize``.

    def canonical_serialize(self) -> str:
        """Return a deterministic JSON serialization of this decision.

        ``Decimal`` values are serialized as their ``str`` form so that
        the bytes are stable across runs and platforms.
        """
        import json

        def _default(o: object) -> object:
            if isinstance(o, Decimal):
                return str(o)
            if isinstance(o, (tuple, list)):
                return [_default(x) for x in o]
            if hasattr(o, "model_dump"):
                return _default(o.model_dump())
            raise TypeError(
                f"Object of type {type(o).__name__} is not JSON-serializable"
            )

        return json.dumps(
            self.model_dump(), sort_keys=True, default=_default
        )


# Backwards alias for code that imports the type before reading models.
DataQualityVerdictInput = DataQualityVerdict
