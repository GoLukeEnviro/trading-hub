"""Gate registry and evaluators for the Validation Gate Matrix (issue #65).

Each gate is a function that takes ``ValidationMatrixRequest`` and returns
a ``ValidationGateResult`` with a ``PASS``, ``FAIL``, ``DEFER``, or
``NOT_APPLICABLE`` status.

Gates are evaluated in stable registry order. The first HARD FAIL
short-circuits further gate evaluation (overall verdict becomes FAIL).
"""

from __future__ import annotations

from si_v2.validation.models import (
    ValidationGateDefinition,
    ValidationGateEvidence,
    ValidationGateResult,
    ValidationGateSeverity,
    ValidationGateStatus,
    ValidationMatrixRequest,
)

# ---------------------------------------------------------------------------
# Gate registry — stable ordered list
# ---------------------------------------------------------------------------

GATE_REGISTRY: tuple[ValidationGateDefinition, ...] = (
    ValidationGateDefinition(
        gate_id="schema_policy_compatibility",
        domain="schema and policy compatibility",
        description="Verify episode schema, policy, and matrix versions are supported.",
        severity=ValidationGateSeverity.HARD,
    ),
    ValidationGateDefinition(
        gate_id="evidence_source_provenance",
        domain="evidence source provenance and integrity",
        description="Validate evidence fingerprints, source manifest, and cache integrity.",
        severity=ValidationGateSeverity.HARD,
    ),
    ValidationGateDefinition(
        gate_id="evidence_sample_recency",
        domain="sample size and recency",
        description="Minimum sample count and maximum evidence age.",
        severity=ValidationGateSeverity.HARD,
    ),
    ValidationGateDefinition(
        gate_id="proposal_decision_delta",
        domain="proposal decision and delta bounds",
        description="Proposal decision (ACCEPT/REJECT/DEFER) and weight delta within bounds.",
        severity=ValidationGateSeverity.HARD,
    ),
    ValidationGateDefinition(
        gate_id="backtest_evidence",
        domain="backtest evidence and thresholds",
        description="Mandatory backtest presence and pass/fail status.",
        severity=ValidationGateSeverity.HARD,
    ),
    ValidationGateDefinition(
        gate_id="walk_forward_evidence",
        domain="walk-forward evidence and stability",
        description="Mandatory walk-forward presence and stability.",
        severity=ValidationGateSeverity.HARD,
    ),
    ValidationGateDefinition(
        gate_id="episode_report_integrity",
        domain="episode report integrity and manifest consistency",
        description="Episode fingerprint, artifact hashes, and manifest cross-consistency.",
        severity=ValidationGateSeverity.HARD,
    ),
    ValidationGateDefinition(
        gate_id="human_review_status",
        domain="human-review status",
        description="Pending, accepted, deferred, or rejected human review.",
        severity=ValidationGateSeverity.SOFT,
    ),
    ValidationGateDefinition(
        gate_id="shadow_readiness",
        domain="shadow-observation readiness metadata",
        description="Advisory metadata check for shadow observation readiness.",
        severity=ValidationGateSeverity.SOFT,
    ),
    ValidationGateDefinition(
        gate_id="dry_run_readiness",
        domain="dry-run-observation readiness metadata",
        description="Advisory metadata check for dry-run observation readiness.",
        severity=ValidationGateSeverity.SOFT,
    ),
    ValidationGateDefinition(
        gate_id="safety_invariants",
        domain="global safety invariants",
        description="Safety policy compliance, no live paths, no approval bypass.",
        severity=ValidationGateSeverity.HARD,
    ),
)

# ---------------------------------------------------------------------------
# Individual gate evaluators
# ---------------------------------------------------------------------------


def evaluate_schema_policy_compatibility(
    request: ValidationMatrixRequest,
) -> ValidationGateResult:
    """Gate 1: Schema and policy compatibility."""
    evidence: list[ValidationGateEvidence] = [
        ValidationGateEvidence(
            key="episode_schema_version",
            value=request.episode_schema_version,
            detail="Episode report schema version",
        ),
        ValidationGateEvidence(
            key="policy_version",
            value=request.policy_version,
            detail="Scoring policy version",
        ),
        ValidationGateEvidence(
            key="matrix_version",
            value=request.matrix_version,
            detail="Validation matrix version",
        ),
    ]
    if not request.episode_schema_version:
        return ValidationGateResult(
            gate_id="schema_policy_compatibility",
            status=ValidationGateStatus.FAIL,
            severity=ValidationGateSeverity.HARD,
            reason="Episode schema version is missing",
            evidence=tuple(evidence),
        )
    if not request.policy_compliant:
        return ValidationGateResult(
            gate_id="schema_policy_compatibility",
            status=ValidationGateStatus.FAIL,
            severity=ValidationGateSeverity.HARD,
            reason="Policy compliance check failed",
            evidence=tuple(evidence),
        )
    return ValidationGateResult(
        gate_id="schema_policy_compatibility",
        status=ValidationGateStatus.PASS,
        severity=ValidationGateSeverity.HARD,
        reason="Schema and policy versions are compatible",
        evidence=tuple(evidence),
    )


def evaluate_evidence_source_provenance(
    request: ValidationMatrixRequest,
) -> ValidationGateResult:
    """Gate 2: Evidence source provenance and integrity."""
    if not request.evidence_fingerprints_valid:
        return ValidationGateResult(
            gate_id="evidence_source_provenance",
            status=ValidationGateStatus.FAIL,
            severity=ValidationGateSeverity.HARD,
            reason="Evidence fingerprints are invalid or missing",
        )
    return ValidationGateResult(
        gate_id="evidence_source_provenance",
        status=ValidationGateStatus.PASS,
        severity=ValidationGateSeverity.HARD,
        reason="Evidence provenance and fingerprints are valid",
    )


def evaluate_evidence_sample_recency(
    request: ValidationMatrixRequest,
) -> ValidationGateResult:
    """Gate 3: Sample size and recency."""
    evidence: list[ValidationGateEvidence] = []
    if not request.evidence_sufficient_sample:
        evidence.append(
            ValidationGateEvidence(
                key="sufficient_sample",
                value="false",
                detail="Evidence sample count below minimum threshold",
            )
        )
        return ValidationGateResult(
            gate_id="evidence_sample_recency",
            status=ValidationGateStatus.FAIL,
            severity=ValidationGateSeverity.HARD,
            reason="Insufficient evidence sample size",
            evidence=tuple(evidence),
        )
    if not request.evidence_not_stale:
        evidence.append(
            ValidationGateEvidence(
                key="stale_evidence",
                value="true",
                detail="Evidence age exceeds maximum allowed",
            )
        )
        return ValidationGateResult(
            gate_id="evidence_sample_recency",
            status=ValidationGateStatus.FAIL,
            severity=ValidationGateSeverity.HARD,
            reason="Evidence is stale",
            evidence=tuple(evidence),
        )
    return ValidationGateResult(
        gate_id="evidence_sample_recency",
        status=ValidationGateStatus.PASS,
        severity=ValidationGateSeverity.HARD,
        reason="Evidence sample size and recency are acceptable",
    )


def evaluate_proposal_decision_delta(
    request: ValidationMatrixRequest,
) -> ValidationGateResult:
    """Gate 4: Proposal decision and delta bounds."""
    if request.has_proposal_reject:
        return ValidationGateResult(
            gate_id="proposal_decision_delta",
            status=ValidationGateStatus.FAIL,
            severity=ValidationGateSeverity.HARD,
            reason="At least one proposal is rejected",
        )
    if request.has_proposal_defer and not request.has_proposal_accept:
        return ValidationGateResult(
            gate_id="proposal_decision_delta",
            status=ValidationGateStatus.DEFER,
            severity=ValidationGateSeverity.HARD,
            reason="All proposals are deferred; no ACCEPT decision",
        )
    if request.evidence_expectancy_not_negative_for_increase is False:
        return ValidationGateResult(
            gate_id="proposal_decision_delta",
            status=ValidationGateStatus.FAIL,
            severity=ValidationGateSeverity.HARD,
            reason="Negative expectancy cannot receive an increase",
        )
    return ValidationGateResult(
        gate_id="proposal_decision_delta",
        status=ValidationGateStatus.PASS,
        severity=ValidationGateSeverity.HARD,
        reason="Proposal decisions and deltas are within bounds",
    )


def evaluate_backtest_evidence(
    request: ValidationMatrixRequest,
) -> ValidationGateResult:
    """Gate 5: Backtest evidence and thresholds."""
    if not request.backtest_present_and_passed:
        return ValidationGateResult(
            gate_id="backtest_evidence",
            status=ValidationGateStatus.FAIL,
            severity=ValidationGateSeverity.HARD,
            reason="Mandatory backtest evidence missing or failed",
        )
    return ValidationGateResult(
        gate_id="backtest_evidence",
        status=ValidationGateStatus.PASS,
        severity=ValidationGateSeverity.HARD,
        reason="Backtest evidence present and passed",
    )


def evaluate_walk_forward_evidence(
    request: ValidationMatrixRequest,
) -> ValidationGateResult:
    """Gate 6: Walk-forward evidence and stability."""
    if not request.walk_forward_present_and_passed:
        return ValidationGateResult(
            gate_id="walk_forward_evidence",
            status=ValidationGateStatus.FAIL,
            severity=ValidationGateSeverity.HARD,
            reason="Mandatory walk-forward evidence missing or failed",
        )
    return ValidationGateResult(
        gate_id="walk_forward_evidence",
        status=ValidationGateStatus.PASS,
        severity=ValidationGateSeverity.HARD,
        reason="Walk-forward evidence present and passed",
    )


def evaluate_episode_report_integrity(
    request: ValidationMatrixRequest,
) -> ValidationGateResult:
    """Gate 7: Episode report integrity and manifest consistency."""
    if not request.episode_verdict_is_hardened:
        return ValidationGateResult(
            gate_id="episode_report_integrity",
            status=ValidationGateStatus.FAIL,
            severity=ValidationGateSeverity.HARD,
            reason="Episode report did not use hardened verdict computation",
        )
    if not request.episode_fingerprint_manifest_consistent:
        return ValidationGateResult(
            gate_id="episode_report_integrity",
            status=ValidationGateStatus.FAIL,
            severity=ValidationGateSeverity.HARD,
            reason="Episode fingerprint manifest is inconsistent",
        )
    return ValidationGateResult(
        gate_id="episode_report_integrity",
        status=ValidationGateStatus.PASS,
        severity=ValidationGateSeverity.HARD,
        reason="Episode report integrity verified",
    )


def evaluate_human_review_status(
    request: ValidationMatrixRequest,
) -> ValidationGateResult:
    """Gate 8: Human-review status."""
    if request.human_review_rejected:
        return ValidationGateResult(
            gate_id="human_review_status",
            status=ValidationGateStatus.FAIL,
            severity=ValidationGateSeverity.SOFT,
            reason="Human has rejected the proposal(s)",
        )
    if request.human_review_pending:
        return ValidationGateResult(
            gate_id="human_review_status",
            status=ValidationGateStatus.DEFER,
            severity=ValidationGateSeverity.SOFT,
            reason="Human review is still pending",
        )
    if request.human_review_deferred:
        return ValidationGateResult(
            gate_id="human_review_status",
            status=ValidationGateStatus.DEFER,
            severity=ValidationGateSeverity.SOFT,
            reason="Human review has been deferred",
        )
    if request.human_review_accepted:
        return ValidationGateResult(
            gate_id="human_review_status",
            status=ValidationGateStatus.PASS,
            severity=ValidationGateSeverity.SOFT,
            reason="Human review accepted (review-only, not execution authority)",
        )
    return ValidationGateResult(
        gate_id="human_review_status",
        status=ValidationGateStatus.DEFER,
        severity=ValidationGateSeverity.SOFT,
        reason="Human review status is unknown",
    )


def evaluate_shadow_readiness(
    request: ValidationMatrixRequest,
) -> ValidationGateResult:
    """Gate 9: Shadow-observation readiness metadata."""
    if not request.shadow_readiness_metadata_ok:
        return ValidationGateResult(
            gate_id="shadow_readiness",
            status=ValidationGateStatus.DEFER,
            severity=ValidationGateSeverity.SOFT,
            reason="Shadow observation readiness metadata incomplete",
        )
    return ValidationGateResult(
        gate_id="shadow_readiness",
        status=ValidationGateStatus.PASS,
        severity=ValidationGateSeverity.SOFT,
        reason="Shadow observation readiness metadata verified",
    )


def evaluate_dry_run_readiness(
    request: ValidationMatrixRequest,
) -> ValidationGateResult:
    """Gate 10: Dry-run observation readiness metadata."""
    if not request.dry_run_readiness_metadata_ok:
        return ValidationGateResult(
            gate_id="dry_run_readiness",
            status=ValidationGateStatus.DEFER,
            severity=ValidationGateSeverity.SOFT,
            reason="Dry-run observation readiness metadata incomplete",
        )
    return ValidationGateResult(
        gate_id="dry_run_readiness",
        status=ValidationGateStatus.PASS,
        severity=ValidationGateSeverity.SOFT,
        reason="Dry-run observation readiness metadata verified",
    )


def evaluate_safety_invariants(
    request: ValidationMatrixRequest,
) -> ValidationGateResult:
    """Gate 11: Global safety invariants."""
    if not request.policy_compliant:
        return ValidationGateResult(
            gate_id="safety_invariants",
            status=ValidationGateStatus.FAIL,
            severity=ValidationGateSeverity.HARD,
            reason="Policy compliance check failed — safety invariant violated",
        )
    return ValidationGateResult(
        gate_id="safety_invariants",
        status=ValidationGateStatus.PASS,
        severity=ValidationGateSeverity.HARD,
        reason="All safety invariants satisfied",
    )


# ---------------------------------------------------------------------------
# Evaluator lookup
# ---------------------------------------------------------------------------

_GATE_EVALUATORS: dict[str, callable] = {
    "schema_policy_compatibility": evaluate_schema_policy_compatibility,
    "evidence_source_provenance": evaluate_evidence_source_provenance,
    "evidence_sample_recency": evaluate_evidence_sample_recency,
    "proposal_decision_delta": evaluate_proposal_decision_delta,
    "backtest_evidence": evaluate_backtest_evidence,
    "walk_forward_evidence": evaluate_walk_forward_evidence,
    "episode_report_integrity": evaluate_episode_report_integrity,
    "human_review_status": evaluate_human_review_status,
    "shadow_readiness": evaluate_shadow_readiness,
    "dry_run_readiness": evaluate_dry_run_readiness,
    "safety_invariants": evaluate_safety_invariants,
}


def get_evaluator(gate_id: str) -> callable:
    """Return the evaluator function for a gate ID."""
    evaluator = _GATE_EVALUATORS.get(gate_id)
    if evaluator is None:
        raise KeyError(f"No evaluator registered for gate_id={gate_id!r}")
    return evaluator


__all__ = [
    "GATE_REGISTRY",
    "evaluate_backtest_evidence",
    "evaluate_dry_run_readiness",
    "evaluate_episode_report_integrity",
    "evaluate_evidence_sample_recency",
    "evaluate_evidence_source_provenance",
    "evaluate_human_review_status",
    "evaluate_proposal_decision_delta",
    "evaluate_safety_invariants",
    "evaluate_schema_policy_compatibility",
    "evaluate_shadow_readiness",
    "evaluate_walk_forward_evidence",
    "get_evaluator",
]
