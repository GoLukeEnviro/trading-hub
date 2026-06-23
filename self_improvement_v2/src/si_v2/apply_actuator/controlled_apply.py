"""SI-v2 Controlled Apply Runner — wires Apply Actuator into the apply flow (#335).

This is the integration layer that connects:
  1. Approved ShadowProposal (from evidence bundle / per_bot_decisions)
  2. → OverlayProposal (actuator format)
  3. → Apply Actuator (binding → validation → draft → proof → verdict)
  4. → Token Gate (L3 activation)

Without the L3 activation token, the runner operates in AUDIT_ONLY mode:
  - Runs compute_apply_result() in audit mode (docker_available=False)
  - Produces a structured report
  - Does NOT write to runtime bot mounts
  - Does NOT mutate configs
  - Does NOT restart bots
  - Mutation counter stays at 0
  - Measurement stays BLOCKED

With the L3 activation token (future, not consumed in this PR):
  - Runs compute_apply_result() with docker_available=True
  - The actuator's fail-closed policy still applies
  - Mutation counter increments ONLY if proof_status == GREEN
  - Measurement starts ONLY if status == APPLIED_WITH_RUNTIME_PROOF

Token gate:
  env var: APPROVE_SI_V2_RUNTIME_ACTUATOR_ACTIVATION
  value:   APPROVE

Safety invariants (enforced regardless of token):
  - Never writes to runtime bot mount paths
  - Never restarts bots
  - Never sets dry_run=false
  - Never enables live trading
  - Never changes strategies
  - Never mutates Docker/Compose/cron
  - Fail-closed: any uncertainty → BLOCKED

Reference candidate: 65502d13a99bfadd (freqtrade-freqforge, safe_parameter_overlay_only)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Final

from si_v2.apply_actuator.models import (
    ApplyActuatorResult,
    ApplyStatus,
    OverlayProposal,
)
from si_v2.apply_actuator.policy import (
    compute_apply_result,
    compute_measurement_rule,
    compute_mutation_counter_rule,
)
from si_v2.apply_actuator.runtime_binding import resolve_binding

# ---------------------------------------------------------------------------
# Token gate constants
# ---------------------------------------------------------------------------

ACTIVATION_TOKEN_ENV: Final[str] = "APPROVE_SI_V2_RUNTIME_ACTUATOR_ACTIVATION"
ACTIVATION_TOKEN_VALUE: Final[str] = "APPROVE"

# ---------------------------------------------------------------------------
# Controlled apply status — describes the runner's own mode
# ---------------------------------------------------------------------------


class ControlledApplyMode(StrEnum):
    """The mode the controlled apply runner is operating in."""

    AUDIT_ONLY = "AUDIT_ONLY"
    """No L3 token provided. Draft/audit only, no runtime effects."""

    TOKEN_GATED_BLOCKED = "TOKEN_GATED_BLOCKED"
    """Token present but actuator blocked the apply (fail-closed)."""

    ACTUATOR_VERIFIED = "ACTUATOR_VERIFIED"
    """Token present and actuator returned APPLIED_WITH_RUNTIME_PROOF."""


# ---------------------------------------------------------------------------
# Controlled apply result — the unified output
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ControlledApplyResult:
    """Complete result of a controlled apply attempt.

    This wraps the actuator result with the runner's own metadata:
    token state, mode, eligibility, and safety verdict.
    """

    mode: ControlledApplyMode = ControlledApplyMode.AUDIT_ONLY
    proposal_id: str = ""
    bot_id: str = ""
    eligible: bool = False
    eligibility_reasons: tuple[str, ...] = field(default_factory=tuple)
    token_provided: bool = False
    actuator_result: ApplyActuatorResult = field(default_factory=ApplyActuatorResult)
    errors: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def mutation_counter_should_increment(self) -> bool:
        """Whether the mutation counter may increment.

        Only true if token is provided AND actuator proof is GREEN.
        """
        return (
            self.token_provided
            and self.actuator_result.mutation_counter_should_increment
        )

    @property
    def measurement_allowed(self) -> bool:
        """Whether measurement is allowed.

        Only true if token is provided AND actuator allows it.
        """
        return (
            self.token_provided
            and self.actuator_result.measurement_allowed
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "mode": self.mode.value,
            "proposal_id": self.proposal_id,
            "bot_id": self.bot_id,
            "eligible": self.eligible,
            "eligibility_reasons": list(self.eligibility_reasons),
            "token_provided": self.token_provided,
            "mutation_counter_should_increment": self.mutation_counter_should_increment,
            "measurement_allowed": self.measurement_allowed,
            "actuator_result": self.actuator_result.to_dict(),
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


# ---------------------------------------------------------------------------
# Token gate
# ---------------------------------------------------------------------------


def check_activation_token() -> tuple[bool, str]:
    """Check whether the L3 activation token is present.

    Returns:
        Tuple of (token_provided: bool, detail: str).
    """
    value = os.environ.get(ACTIVATION_TOKEN_ENV, "")
    if value == ACTIVATION_TOKEN_VALUE:
        return (True, f"Token '{ACTIVATION_TOKEN_ENV}' is set to APPROVE")
    return (False, f"Token '{ACTIVATION_TOKEN_ENV}' not set or incorrect")


# ---------------------------------------------------------------------------
# Proposal conversion: evidence bundle dict → OverlayProposal
# ---------------------------------------------------------------------------


def proposal_to_overlay(
    proposal: dict[str, object],
) -> OverlayProposal:
    """Convert an approved proposal dict to an OverlayProposal.

    Args:
        proposal: Per-bot decision dict from an evidence bundle.
            Expected keys: bot_id, candidate_sha256 (used as proposal_id),
            mutation_policy, parameter_overlay.

    Returns:
        OverlayProposal suitable for the actuator pipeline.
    """
    proposal_id = str(proposal.get("candidate_sha256", ""))[:16]
    if not proposal_id:
        proposal_id = str(proposal.get("proposal_id", "unknown"))

    bot_id_raw = str(proposal.get("bot_id", ""))
    bot_id = _normalize_bot_id(bot_id_raw)

    policy = str(proposal.get("mutation_policy", "safe_parameter_overlay_only"))
    parameters = proposal.get("parameter_overlay", {})
    if not isinstance(parameters, dict):
        parameters = {}

    return OverlayProposal(
        proposal_id=proposal_id,
        bot_id=bot_id,
        policy=policy,
        parameters=dict(parameters),
        source_cycle_id=str(proposal.get("cycle_id", "")),
    )


def _normalize_bot_id(bot_id: str) -> str:
    """Normalize a bot_id to the canonical form used in runtime bindings.

    Handles common variations:
      - 'freqforge' → 'freqtrade-freqforge'
      - 'freqforge-canary' → 'freqtrade-freqforge-canary'
      - 'regime-hybrid' → 'freqtrade-regime-hybrid'
      - 'freqai-rebel' → 'freqtrade-freqai-rebel' (already canonical)
    """
    if not bot_id:
        return bot_id

    # Already canonical
    if bot_id.startswith("freqtrade-"):
        return bot_id

    # Handle freqai-rebel which has a different prefix pattern
    if bot_id == "freqai-rebel":
        return "freqai-rebel"

    # Assume freqtrade- prefix
    return f"freqtrade-{bot_id}"


# ---------------------------------------------------------------------------
# Main entry point: run_controlled_apply
# ---------------------------------------------------------------------------


def run_controlled_apply(
    proposal: dict[str, object],
    *,
    docker_available: bool | None = None,
) -> ControlledApplyResult:
    """Run a controlled apply through the Apply Actuator.

    This is the main wiring function. It:
      1. Checks eligibility
      2. Converts proposal to OverlayProposal
      3. Checks the token gate
      4. Runs the actuator in the appropriate mode
      5. Returns a unified result

    Args:
        proposal: Per-bot decision dict from an evidence bundle.
        docker_available: Override for Docker availability.
            If None, uses True if token provided, False otherwise.

    Returns:
        ControlledApplyResult with all gates and safety verdicts.

    Safety:
        - Without token: AUDIT_ONLY, no runtime effects
        - With token: actuator fail-closed policy still applies
        - Either way: no runtime file writes, no bot restart
    """
    from si_v2.apply.dry_run_apply_path import check_apply_eligibility

    errors: list[str] = []
    warnings: list[str] = []

    # Step 1: Eligibility check
    eligible, eligibility_reasons = check_apply_eligibility(proposal)
    if not eligible:
        return ControlledApplyResult(
            mode=ControlledApplyMode.TOKEN_GATED_BLOCKED,
            proposal_id=str(proposal.get("candidate_sha256", ""))[:16],
            bot_id=str(proposal.get("bot_id", "")),
            eligible=False,
            eligibility_reasons=tuple(eligibility_reasons),
            token_provided=False,
            actuator_result=ApplyActuatorResult(
                status=ApplyStatus.BLOCKED,
                proposal_id=str(proposal.get("candidate_sha256", ""))[:16],
                bot_id=str(proposal.get("bot_id", "")),
                errors=("Eligibility check failed",),
            ),
            errors=tuple(eligibility_reasons),
        )

    # Step 2: Convert to OverlayProposal
    overlay = proposal_to_overlay(proposal)

    # Step 3: Check token gate
    token_provided, token_detail = check_activation_token()
    if not token_provided:
        warnings.append(token_detail)

    # Step 4: Determine Docker availability
    if docker_available is None:
        docker_available = token_provided

    # Step 5: Run actuator
    actuator_result = compute_apply_result(
        overlay,
        docker_available=docker_available,
    )

    # Step 6: Determine mode
    if not token_provided:
        mode = ControlledApplyMode.AUDIT_ONLY
        warnings.append(
            "AUDIT_ONLY: no runtime file writes, no bot restart, "
            "mutation counter stays 0, measurement blocked"
        )
    elif actuator_result.status == ApplyStatus.APPLIED_WITH_RUNTIME_PROOF:
        mode = ControlledApplyMode.ACTUATOR_VERIFIED
    else:
        mode = ControlledApplyMode.TOKEN_GATED_BLOCKED
        warnings.append(
            f"Token provided but actuator status={actuator_result.status.value} "
            f"(fail-closed: no mutation, no measurement)"
        )

    # Step 7: Build unified result
    result = ControlledApplyResult(
        mode=mode,
        proposal_id=overlay.proposal_id,
        bot_id=overlay.bot_id,
        eligible=True,
        eligibility_reasons=tuple(eligibility_reasons),
        token_provided=token_provided,
        actuator_result=actuator_result,
        errors=tuple(errors),
        warnings=tuple(warnings),
    )

    return result


# ---------------------------------------------------------------------------
# Batch helper: run controlled apply for all approved proposals in a cycle
# ---------------------------------------------------------------------------


def run_controlled_apply_batch(
    per_bot_decisions: list[dict[str, object]],
) -> list[ControlledApplyResult]:
    """Run controlled apply for all approved proposals in an evidence cycle.

    Args:
        per_bot_decisions: List of per-bot decision dicts.

    Returns:
        List of ControlledApplyResult, one per approved SHADOW_PROPOSAL.
        Non-proposal or non-approved decisions are skipped.
    """
    results: list[ControlledApplyResult] = []

    for decision in per_bot_decisions:
        dt = str(decision.get("decision_type", ""))
        status = str(decision.get("approval_status", ""))

        if dt != "SHADOW_PROPOSAL":
            continue
        if status != "APPROVED":
            continue

        result = run_controlled_apply(decision)
        results.append(result)

    return results


# ---------------------------------------------------------------------------
# Reporting helper: summarize results for human review
# ---------------------------------------------------------------------------


def summarize_results(
    results: list[ControlledApplyResult],
) -> dict[str, object]:
    """Produce a summary dict of controlled apply results.

    Useful for logging to the measurement ledger or shadow decision log.
    """
    total = len(results)
    audit_only = sum(1 for r in results if r.mode == ControlledApplyMode.AUDIT_ONLY)
    blocked = sum(1 for r in results if r.mode == ControlledApplyMode.TOKEN_GATED_BLOCKED)
    verified = sum(1 for r in results if r.mode == ControlledApplyMode.ACTUATOR_VERIFIED)

    return {
        "total_proposals": total,
        "audit_only": audit_only,
        "token_gated_blocked": blocked,
        "actuator_verified": verified,
        "mutation_counters_incremented": sum(
            1 for r in results if r.mutation_counter_should_increment
        ),
        "measurement_allowed": sum(
            1 for r in results if r.measurement_allowed
        ),
        "all_mutations_zero": not any(
            r.mutation_counter_should_increment for r in results
        ),
    }
