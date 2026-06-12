"""Typed rejection-reason catalogue for the proposal scoring policy.

This module is the single source of truth for human-readable descriptions
of every ``ProposalRejectionReason`` member. The catalogue is used by
issue #63's Markdown report renderer and by the issue #64 episode report.
"""

from __future__ import annotations

from si_v2.propose.proposal_scoring.models import ProposalRejectionReason

REJECTION_REASON_CATALOGUE: dict[ProposalRejectionReason, str] = {
    ProposalRejectionReason.INSUFFICIENT_EVIDENCE_SAMPLE: (
        "The evidence sample count is below the policy minimum; the "
        "proposal is rejected or deferred until more data exists."
    ),
    ProposalRejectionReason.STALE_EVIDENCE: (
        "The evidence is older than the policy maximum age and is "
        "rejected as stale."
    ),
    ProposalRejectionReason.CONFLICTING_EVIDENCE: (
        "Conflicting evidence was detected for this (source, regime) "
        "pair; the proposal is rejected until the conflict is resolved."
    ),
    ProposalRejectionReason.UNSUPPORTED_EVIDENCE_SCHEMA: (
        "The evidence_schema_version is not in the policy's accepted set; "
        "the proposal is rejected to prevent silent schema drift."
    ),
    ProposalRejectionReason.UNSUPPORTED_POLICY_SCHEMA: (
        "The policy_version is unknown; the proposal is rejected to "
        "prevent silent policy drift."
    ),
    ProposalRejectionReason.INVALID_NUMERICS: (
        "One or more numeric inputs were NaN, ±Infinity, malformed, or "
        "out of supported precision; the proposal is rejected."
    ),
    ProposalRejectionReason.NEGATIVE_EXPECTANCY_FOR_INCREASE: (
        "The proposal asks for a weight increase but the evidence "
        "expectancy is negative; the proposal is rejected."
    ),
    ProposalRejectionReason.DRAWDOWN_ABOVE_POLICY_MAX: (
        "The evidence drawdown_proxy exceeds the policy maximum; the "
        "proposal is rejected."
    ),
    ProposalRejectionReason.MISSING_MANDATORY_BACKTEST: (
        "Backtest evidence is required by the policy but is missing; "
        "the proposal is rejected with promotion stage BACKTEST_REQUIRED."
    ),
    ProposalRejectionReason.MISSING_MANDATORY_WALK_FORWARD: (
        "Walk-forward evidence is required by the policy but is missing; "
        "the proposal is rejected with promotion stage WALK_FORWARD_REQUIRED."
    ),
    ProposalRejectionReason.MISSING_DATA_QUALITY_VERDICT: (
        "The upstream evidence pipeline did not mark the evidence as "
        "accepted; the proposal is rejected."
    ),
    ProposalRejectionReason.HUMAN_APPROVAL_UNAVAILABLE: (
        "Human approval is not available for this proposal; the proposal "
        "is rejected. This gate is non-bypassable."
    ),
    ProposalRejectionReason.INVALID_WEIGHTS_DO_NOT_SUM_TO_ONE: (
        "The component weights do not sum to 1.0; the policy is invalid."
    ),
    ProposalRejectionReason.POLICY_VERSION_MISMATCH: (
        "The policy_version does not match the engine's supported "
        "version; the proposal is rejected."
    ),
}


def format_rejection_reason(reason: ProposalRejectionReason) -> str:
    """Return a human-readable description for a rejection reason."""
    return REJECTION_REASON_CATALOGUE[reason]
