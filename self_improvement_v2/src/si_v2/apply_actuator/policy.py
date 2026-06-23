r"""Apply Actuator policy — central decision logic for all gates.

This is the authoritative module that decides:
  1. Whether an apply is valid
  2. Whether the mutation counter should increment
  3. Whether measurement is allowed

All decisions are fail-closed: uncertainty → BLOCKED.
"""

from __future__ import annotations

from si_v2.apply_actuator.models import (
    ApplyActuatorResult,
    ApplyStatus,
    BotRuntimeBinding,
    EffectiveConfigDraft,
    OverlayProposal,
    ProofStatus,
    RuntimeEffectProof,
)
from si_v2.apply_actuator.runtime_binding import resolve_binding
from si_v2.apply_actuator.overlay_merge import (
    generate_effective_config,
    validate_overlay_safety,
)
from si_v2.apply_actuator.proof import verify_runtime_effect


# ---------------------------------------------------------------------------
# Mutation counter rule
# ---------------------------------------------------------------------------


def compute_mutation_counter_rule(proof: RuntimeEffectProof) -> tuple[bool, str]:
    """Decide whether the mutation counter should increment.

    Core invariant: Mutation counter increments ONLY if runtime proof is GREEN.

    Args:
        proof: Verified runtime effect proof.

    Returns:
        Tuple of (should_increment: bool, reason: str).
    """
    if proof.proof_status != ProofStatus.GREEN:
        return (
            False,
            f"Mutation counter blocked: proof_status={proof.proof_status.value} (requires GREEN)",
        )

    if not proof.file_visible_to_bot:
        return (False, "Mutation counter blocked: file not visible to bot")

    if not proof.effective_config_contains_expected_values:
        return (False, "Mutation counter blocked: effective config mismatch")

    if not proof.loaded_config_contains_expected_values:
        return (False, "Mutation counter blocked: loaded config mismatch")

    if not proof.dry_run_true:
        return (False, "Mutation counter blocked: dry_run is False")

    if not proof.live_trading_false:
        return (False, "Mutation counter blocked: live trading True")

    if not proof.strategy_unchanged:
        return (False, "Mutation counter blocked: strategy changed")

    return (True, "GREEN — runtime effect proven, mutation counter may increment")


# ---------------------------------------------------------------------------
# Measurement rule
# ---------------------------------------------------------------------------


def compute_measurement_rule(result: ApplyActuatorResult) -> tuple[bool, str]:
    """Decide whether measurement is allowed.

    Core invariant: Measurement starts ONLY if status is APPLIED_WITH_RUNTIME_PROOF.

    Args:
        result: Complete apply actuator result.

    Returns:
        Tuple of (allowed: bool, reason: str).
    """
    if result.status != ApplyStatus.APPLIED_WITH_RUNTIME_PROOF:
        return (
            False,
            f"Measurement blocked: apply_status={result.status.value} (requires APPLIED_WITH_RUNTIME_PROOF)",
        )

    if not result.mutation_counter_should_increment:
        return (
            False,
            "Measurement blocked: mutation counter not incremented (proof not GREEN)",
        )

    return (True, "Measurement allowed — runtime proof GREEN, mutation confirmed")


# ---------------------------------------------------------------------------
# Main apply result computation
# ---------------------------------------------------------------------------


def compute_apply_result(
    proposal: OverlayProposal,
    *,
    docker_available: bool = True,
) -> ApplyActuatorResult:
    """Compute the complete apply result with all safety gates.

    This is the main entry point for the Apply Actuator.
    It orchestrates: binding → validation → draft → proof → verdict.

    Args:
        proposal: The overlay proposal to evaluate.
        docker_available: Whether Docker is available for container checks.

    Returns:
        ApplyActuatorResult with status, proof, and gate decisions.
    """
    errors: list[str] = []
    warnings: list[str] = []

    # Step 1: Resolve runtime binding
    binding = resolve_binding(proposal.bot_id)
    if binding is None:
        return ApplyActuatorResult(
            status=ApplyStatus.BLOCKED,
            proposal_id=proposal.proposal_id,
            bot_id=proposal.bot_id,
            errors=(f"No runtime binding found for bot_id={proposal.bot_id!r}",),
        )

    if not binding.runtime_visible:
        errors.append(f"Bot {proposal.bot_id} runtime not visible")

    # Step 2: Validate overlay safety
    safe, safety_issues = validate_overlay_safety(proposal)
    if not safe:
        errors.extend(safety_issues)

    # Step 3: Generate effective config draft
    draft: EffectiveConfigDraft | None = None
    if not errors:
        draft, draft_errors = generate_effective_config(proposal, binding)
        if draft is None:
            errors.extend(draft_errors)
        else:
            warnings.extend(draft_errors)

    # Step 4: Verify runtime effect
    proof: RuntimeEffectProof
    if draft is not None:
        # Build expected container overlay path
        overlay_path = (
            f"{binding.container_user_data_path}/overlay_{proposal.proposal_id[:8]}.json"
        )
        proof = verify_runtime_effect(
            proposal, binding, draft,
            overlay_container_path=overlay_path,
            docker_available=docker_available,
        )
    else:
        proof = RuntimeEffectProof(
            proposal_id=proposal.proposal_id,
            bot_id=proposal.bot_id,
            proof_status=ProofStatus.RED,
            errors=tuple(errors),
        )

    # Step 5: Determine apply status
    status = _determine_apply_status(proposal, binding, proof, errors)

    # Step 6: Compute mutation counter rule
    mutation_ok, mutation_reason = compute_mutation_counter_rule(proof)
    if not mutation_ok:
        warnings.append(mutation_reason)

    # Step 7: Build result
    result = ApplyActuatorResult(
        status=status,
        proposal_id=proposal.proposal_id,
        bot_id=proposal.bot_id,
        proof=proof,
        mutation_counter_should_increment=mutation_ok,
        measurement_allowed=False,  # Set after status check below
        errors=tuple(errors),
        warnings=tuple(warnings),
    )

    # Step 8: Compute measurement rule
    measure_ok, measure_reason = compute_measurement_rule(result)
    if not measure_ok:
        warnings.append(measure_reason)

    # Return with measurement decision
    return ApplyActuatorResult(
        status=status,
        proposal_id=proposal.proposal_id,
        bot_id=proposal.bot_id,
        proof=proof,
        mutation_counter_should_increment=mutation_ok,
        measurement_allowed=measure_ok,
        errors=tuple(errors),
        warnings=tuple(warnings),
    )


def _determine_apply_status(
    proposal: OverlayProposal,
    binding: BotRuntimeBinding,
    proof: RuntimeEffectProof,
    errors: list[str],
) -> ApplyStatus:
    """Determine the apply status from evidence.

    Fail-closed: each detected error or uncertainty → BLOCKED or NO_RUNTIME_EFFECT.
    """
    # Hard blocks
    if errors:
        return ApplyStatus.BLOCKED

    if not proof.dry_run_true:
        return ApplyStatus.BLOCKED

    if not proof.live_trading_false:
        return ApplyStatus.BLOCKED

    if not proof.strategy_unchanged:
        return ApplyStatus.BLOCKED

    if binding is None or not binding.runtime_visible:
        return ApplyStatus.BLOCKED

    # Runtime proof inspection
    if proof.proof_status == ProofStatus.GREEN:
        return ApplyStatus.APPLIED_WITH_RUNTIME_PROOF

    if proof.proof_status == ProofStatus.RED:
        # File exists but wrong path or not loaded → NO_RUNTIME_EFFECT
        if not proof.file_visible_to_bot:
            return ApplyStatus.NO_RUNTIME_EFFECT
        return ApplyStatus.BLOCKED

    if proof.proof_status == ProofStatus.YELLOW:
        if proof.file_visible_to_bot and not proof.loaded_config_contains_expected_values:
            return ApplyStatus.RUNTIME_PROOF_REQUIRED
        return ApplyStatus.BLOCKED

    return ApplyStatus.DRAFTED_NOT_APPLIED
