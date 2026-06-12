"""Proposal scoring and promotion policy (issue #35).

This subpackage defines the typed, deterministic, versioned scoring and
promotion policy that the Weight Proposal Engine (issue #63) consumes.

It is **advisory only**:

- Never reads or writes live strategy / Freqtrade configuration.
- Never starts shadow, dry-run, or live execution.
- Never marks a proposal as approved.
- Never infers runtime state from anywhere except the typed input it
  receives in the same function call.

Public surface (re-exported here):

    ScoringPolicy              — versioned, hashable policy object.
    DEFAULT_SCORING_POLICY_V1  — immutable, frozen default policy.
    ProposalScoreInput         — typed scoring input.
    ProposalDecision           — typed scoring output.
    ProposalRejectionReason    — typed rejection taxonomy.
    PromotionStage             — typed promotion stage enum.
    PromotionGateResult        — per-gate pass/fail record.
    ComponentWeights           — component-weight map (must sum to 1).
    BacktestMetrics            — narrow view of BacktestResult.
    WalkForwardMetrics         — narrow view of WalkForwardResult.
    score_proposal             — pure function, deterministic.
    validate_policy            — full policy validation.
    ACCEPT_THRESHOLD_DEFAULT   — 0.65
    DEFER_THRESHOLD_DEFAULT    — 0.40
    POLICY_VERSION             — "scoring_policy_v1"
    SCORING_QUANTUM            — Decimal("0.000001")  (6 decimals)
"""

from __future__ import annotations

from si_v2.propose.proposal_scoring.decimal_safe import (
    SCORING_QUANTUM,
    quantize_score,
)
from si_v2.propose.proposal_scoring.models import (
    ACCEPT_THRESHOLD_DEFAULT,
    DEFER_THRESHOLD_DEFAULT,
    MAXIMUM_PROPOSAL_DELTA_DEFAULT,
    POLICY_VERSION,
    BacktestMetrics,
    ComponentWeights,
    DataQualityVerdict,
    DirectionHint,
    HardGateResult,
    PromotionGateResult,
    PromotionStage,
    ProposalDecision,
    ProposalRejectionReason,
    ProposalScoreBreakdown,
    ProposalScoreInput,
    ScoringPolicy,
    WalkForwardMetrics,
    WalkForwardStabilityThresholds,
)
from si_v2.propose.proposal_scoring.policy import (
    DEFAULT_SCORING_POLICY_V1,
    validate_policy,
)
from si_v2.propose.proposal_scoring.rejection import (
    REJECTION_REASON_CATALOGUE,
    format_rejection_reason,
)
from si_v2.propose.proposal_scoring.scoring import score_proposal

__all__ = [
    "ACCEPT_THRESHOLD_DEFAULT",
    "DEFAULT_SCORING_POLICY_V1",
    "DEFER_THRESHOLD_DEFAULT",
    "MAXIMUM_PROPOSAL_DELTA_DEFAULT",
    "POLICY_VERSION",
    "REJECTION_REASON_CATALOGUE",
    "SCORING_QUANTUM",
    "BacktestMetrics",
    "ComponentWeights",
    "DataQualityVerdict",
    "DirectionHint",
    "HardGateResult",
    "PromotionGateResult",
    "PromotionStage",
    "ProposalDecision",
    "ProposalRejectionReason",
    "ProposalScoreBreakdown",
    "ProposalScoreInput",
    "ScoringPolicy",
    "WalkForwardMetrics",
    "WalkForwardStabilityThresholds",
    "format_rejection_reason",
    "quantize_score",
    "score_proposal",
    "validate_policy",
]
