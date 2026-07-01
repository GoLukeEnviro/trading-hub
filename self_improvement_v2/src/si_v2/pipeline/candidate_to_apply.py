r"""SI-v2 Candidate-to-Apply Pipeline Orchestrator — Phase 6A.

This module implements the **missing orchestration layer** that connects
ShadowProposal candidates to the existing Apply/Restart/Measurement/Rollback
modules. It is the P1 gap from the original audit.

Architecture
------------
::

    CandidateApplyInput
        ↓
    candidate_to_apply_pipeline()
        │
        ├─ 1. Validate target bot (canary-only)
        ├─ 2. Validate parameter (safe, not forbidden)
        ├─ 3. Check dry_run
        ├─ 4. Check autonomy policy (replaces human gate in dry-run)
        ├─ 5. Check active measurement window
        ├─ 6. Check readiness (optional, read-only)
        ├─ 7. Check rollback availability
        └─ 8. Return CandidatePipelineDecision

    Status values:
        READY_FOR_AUTONOMOUS_DRY_RUN_APPLY  — all policy gates pass, ready for apply
        AUTO_DRY_RUN_APPROVED               — policy gates pass, execution not wired yet
        AUTO_DRY_RUN_BLOCKED                — policy gate violation
        AUTO_DRY_RUN_DEFERRED               — measurement window active
        READY_FOR_HUMAN_APPROVAL            — legacy: candidate needs human gate
        READY_FOR_CANARY_APPLY              — legacy: all gates pass, canary-ready
        BLOCKED                             — safety gate violation
        DEFERRED                            — measurement window active
        NOT_IMPLEMENTED_EXECUTION           — execute=True in Phase 6A

Safety invariants
-----------------
- ``execute=False`` is the default — no accidental execution.
- ``allow_non_canary`` is ``False`` by default — only canary accepted.
- Active measurement window defers new candidates.
- No subprocess, no Docker, no runtime mutation.
- No call to ``execute_apply()``, ``run_canary_restart_with_overlay()``,
  or ``execute_canary_rollback()``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final, Literal

from si_v2.apply_actuator.controlled_apply_actuator import ApplyMode
from si_v2.apply_actuator.restart_with_overlay import CANARY_BOT_ID
from si_v2.apply_actuator.runtime_binding import resolve_binding
from si_v2.autonomy import (
    AutonomyPolicyInput,
    evaluate_autonomy_policy,
)
from si_v2.propose.safe_parameters import FORBIDDEN_KEYS, SAFE_PARAMETERS

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

NOT_IMPLEMENTED_EXECUTION_MSG: Final[str] = (
    "execution_not_allowed_in_phase_6a: execute=True is not implemented. "
    "Requires separate Phase 6B runtime executor integration."
)

# ---------------------------------------------------------------------------
# Forbidden parameter keys (must never be in candidate parameters)
# ---------------------------------------------------------------------------

PIPELINE_FORBIDDEN_KEYS: frozenset[str] = FORBIDDEN_KEYS | frozenset({
    "strategy",
    "pair_whitelist",
    "pair_blacklist",
    "telegram",
})

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CandidateApplyInput:
    """A candidate ready for pipeline evaluation.

    Represents a single parameter change proposal from a ShadowProposal
    or manual source.
    """

    candidate_id: str
    """Unique identifier (e.g. ``max_open_trades_3_to_2``)."""

    source: str
    """Origin of the candidate (e.g. ``shadow_proposal``, ``manual``)."""

    target_bot: str
    """Target bot ID (must be ``freqtrade-freqforge-canary`` in Phase 6A)."""

    parameter: str
    """Parameter name to change (e.g. ``max_open_trades``)."""

    current_value: object
    """Current value of the parameter (e.g. ``3``)."""

    proposed_value: object
    """Proposed new value (e.g. ``2``)."""

    confidence: float | None = None
    """Optional confidence score (0.0-1.0)."""

    evidence_refs: tuple[str, ...] = ()
    """References to evidence artifacts (reports, cycle IDs)."""

    requires_human_approval: bool = True
    """Whether human approval is required before apply.

    In AUTONOMOUS_DRY_RUN mode, this is replaced by the autonomy policy.
    Retained for legacy compatibility.
    """

    autonomy_mode: Literal["OFF", "DRY_RUN", "LIVE_READY"] = "DRY_RUN"
    """Autonomy mode for this candidate evaluation.

    - ``OFF``: legacy human-gated behavior.
    - ``DRY_RUN``: use autonomy policy for dry-run decisions (default).
    - ``LIVE_READY``: future live-capable mode (not implemented).
    """

    def to_dict(self) -> dict[str, object]:
        return {
            "candidate_id": self.candidate_id,
            "source": self.source,
            "target_bot": self.target_bot,
            "parameter": self.parameter,
            "current_value": self.current_value,
            "proposed_value": self.proposed_value,
            "confidence": self.confidence,
            "evidence_refs": list(self.evidence_refs),
            "requires_human_approval": self.requires_human_approval,
            "autonomy_mode": self.autonomy_mode,
        }


@dataclass(frozen=True)
class CandidatePipelineDecision:
    """Structured decision from the candidate-to-apply pipeline."""

    status: Literal[
        "READY_FOR_HUMAN_APPROVAL",
        "READY_FOR_CANARY_APPLY",
        "READY_FOR_AUTONOMOUS_DRY_RUN_APPLY",
        "AUTO_DRY_RUN_APPROVED",
        "AUTO_DRY_RUN_BLOCKED",
        "AUTO_DRY_RUN_DEFERRED",
        "BLOCKED",
        "DEFERRED",
        "NOT_IMPLEMENTED_EXECUTION",
    ]
    candidate_id: str
    target_bot: str
    canary_only: bool
    readiness_ready: bool
    restart_required: bool
    measurement_required: bool
    rollback_available: bool
    blocked_reasons: tuple[str, ...]
    next_step: str
    created_at_utc: str

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "candidate_id": self.candidate_id,
            "target_bot": self.target_bot,
            "canary_only": self.canary_only,
            "readiness_ready": self.readiness_ready,
            "restart_required": self.restart_required,
            "measurement_required": self.measurement_required,
            "rollback_available": self.rollback_available,
            "blocked_reasons": list(self.blocked_reasons),
            "next_step": self.next_step,
            "created_at_utc": self.created_at_utc,
        }


@dataclass(frozen=True)
class CandidatePipelineResult:
    """Complete result including decision and context flags."""

    decision: CandidatePipelineDecision
    readiness_report: object | None
    restart_plan_required: bool
    measurement_plan_required: bool
    rollback_plan_required: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "decision": self.decision.to_dict(),
            "readiness_report": (
                str(self.readiness_report) if self.readiness_report is not None else None
            ),
            "restart_plan_required": self.restart_plan_required,
            "measurement_plan_required": self.measurement_plan_required,
            "rollback_plan_required": self.rollback_plan_required,
        }


# ---------------------------------------------------------------------------
# Pipeline validators
# ---------------------------------------------------------------------------


def _check_target_bot(
    target_bot: str,
    allow_non_canary: bool,
) -> tuple[bool, str]:
    """Block non-canary targets unless explicitly allowed."""
    if target_bot == CANARY_BOT_ID:
        return True, ""
    if not allow_non_canary:
        return False, f"non_canary_target: {target_bot!r} is not {CANARY_BOT_ID!r}"
    return True, ""


def _check_known_bot(target_bot: str) -> tuple[bool, str]:
    """Block unknown bots (no runtime binding)."""
    binding = resolve_binding(target_bot)
    if binding is not None:
        return True, ""
    return False, f"unknown_bot: no runtime binding for {target_bot!r}"


def _check_parameter_safe(
    parameter: str,
) -> tuple[bool, str]:
    """Block forbidden or unknown parameters."""
    if parameter in PIPELINE_FORBIDDEN_KEYS:
        return False, f"forbidden_parameter: {parameter!r}"
    if parameter not in SAFE_PARAMETERS:
        return False, f"unsafe_parameter: {parameter!r} not in SAFE_PARAMETERS"
    return True, ""


def _check_dry_run(pre_apply_config: Mapping[str, object]) -> tuple[bool, str]:
    val = pre_apply_config.get("dry_run")
    if val is True:
        return True, ""
    if val is None:
        return False, "dry_run_not_found: key 'dry_run' missing from pre_apply_config"
    return False, f"dry_run_not_true: dry_run={val!r}"


def _check_human_approval(
    requires_human_approval: bool,
) -> tuple[bool, str]:
    if requires_human_approval:
        return True, ""
    return False, "human_approval_not_required: requires_human_approval=False"


def _check_measurement_window(
    candidate_id: str,
    active_measurement_candidate_id: str | None,
) -> tuple[bool, str, Literal["BLOCKED", "DEFERRED", "PASS"]]:
    """Check if a measurement window is actively running for another candidate."""
    if active_measurement_candidate_id is None:
        return True, "", "PASS"
    if candidate_id == active_measurement_candidate_id:
        return True, "already_measuring: this candidate is already in measurement", "PASS"
    return (
        False,
        f"measurement_active_for: {active_measurement_candidate_id!r} — "
        f"defer new candidate {candidate_id!r} until measurement completes",
        "DEFERRED",
    )


def _check_readiness_available() -> bool:
    """Check if the controlled_apply_actuator module is importable."""
    try:
        import si_v2.apply_actuator.controlled_apply_actuator  # noqa: F401
        return True
    except ImportError:
        return False


def _check_rollback_available() -> bool:
    """Check if the rollback module is importable."""
    try:
        import si_v2.apply_actuator.rollback_rehearsal  # noqa: F401
        return True
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# Autonomy policy integration
# ---------------------------------------------------------------------------


def _evaluate_autonomy_for_candidate(
    candidate: CandidateApplyInput,
    pre_apply_config: Mapping[str, object],
    active_measurement_candidate_id: str | None,
    *,
    kill_switch_mode: str | None = None,
    riskguard_status: str | None = None,
    allowlist_compatible: bool | None = None,
) -> AutonomyPolicyInput | None:
    """Build an AutonomyPolicyInput from candidate data.

    Returns None if the candidate cannot be evaluated (e.g. missing data).

    Args:
        kill_switch_mode: Real kill switch mode from runtime evidence.
            Must not be None for autonomous dry-run evaluation.
        riskguard_status: Real RiskGuard status from runtime evidence.
            Must not be None for autonomous dry-run evaluation.
        allowlist_compatible: Real allowlist compatibility from evidence.
            Must not be None for autonomous dry-run evaluation.
    """
    # Fail-closed: missing evidence values block evaluation
    if kill_switch_mode is None:
        return None
    if riskguard_status is None:
        return None
    if allowlist_compatible is None:
        return None

    # Determine dry_run_all_true from config
    dry_run_val = pre_apply_config.get("dry_run")
    dry_run_all_true = dry_run_val is True

    # Build parameter overlay
    overlay: dict[str, int | float] = {}
    if candidate.parameter and candidate.proposed_value is not None:
        val = candidate.proposed_value
        if isinstance(val, (int, float)):
            overlay[candidate.parameter] = val

    return AutonomyPolicyInput(
        candidate_id=candidate.candidate_id,
        candidate_sha=candidate.candidate_id,  # candidate_id serves as SHA in Phase 6A
        target_bot=candidate.target_bot,
        hypothesis=candidate.source,
        parameter_overlay=overlay,
        source_cycle=candidate.source,
        confidence=candidate.confidence,
        dry_run_all_true=dry_run_all_true,
        kill_switch_mode=kill_switch_mode,
        riskguard_status=riskguard_status,
        active_measurement_candidate_id=active_measurement_candidate_id,
        rollback_available=_check_rollback_available(),
        allowlist_compatible=allowlist_compatible,
        canary_first=(candidate.target_bot == CANARY_BOT_ID),
        open_trades_on_target=None,
    )


# ---------------------------------------------------------------------------
# Main pipeline function
# ---------------------------------------------------------------------------


def candidate_to_apply_pipeline(
    *,
    candidate: CandidateApplyInput,
    pre_apply_config: Mapping[str, object],
    execute: bool = False,
    allow_non_canary: bool = False,
    active_measurement_candidate_id: str | None = "max_open_trades_3_to_2",
    kill_switch_mode: str | None = None,
    riskguard_status: str | None = None,
    allowlist_compatible: bool | None = None,
) -> CandidatePipelineResult:
    """Evaluate a candidate through the full SI-v2 apply pipeline.

    This is the **Phase 6A orchestrator**. It does NOT execute any
    runtime changes. It evaluates gates and returns a structured decision.

    Args:
        candidate: The candidate to evaluate.
        pre_apply_config: Pre-apply config dict (must contain ``dry_run``).
        execute: **Defaults to False.** Set True to test the execution gate
            (will return ``NOT_IMPLEMENTED_EXECUTION``).
        allow_non_canary: Allow non-canary targets (default: False).
        active_measurement_candidate_id: Currently active measurement
            candidate ID (default: ``max_open_trades_3_to_2``).
        kill_switch_mode: Real kill switch mode from runtime evidence.
            Required for autonomous dry-run evaluation. None -> BLOCKED.
        riskguard_status: Real RiskGuard status from runtime evidence.
            Required for autonomous dry-run evaluation. None -> BLOCKED.
        allowlist_compatible: Real allowlist compatibility from evidence.
            Required for autonomous dry-run evaluation. None -> BLOCKED.

    Returns:
        ``CandidatePipelineResult`` with decision and context flags.
    """
    now = datetime.now(UTC).isoformat()
    blocked: list[str] = []
    readiness_ready = False
    readiness_report: object = None

    # 1. Execute gate — always blocks in Phase 6A
    if execute:
        return CandidatePipelineResult(
            decision=CandidatePipelineDecision(
                status="NOT_IMPLEMENTED_EXECUTION",
                candidate_id=candidate.candidate_id,
                target_bot=candidate.target_bot,
                canary_only=not allow_non_canary,
                readiness_ready=False,
                restart_required=True,
                measurement_required=True,
                rollback_available=_check_rollback_available(),
                blocked_reasons=(NOT_IMPLEMENTED_EXECUTION_MSG,),
                next_step="Wait for Phase 6B runtime executor integration.",
                created_at_utc=now,
            ),
            readiness_report=None,
            restart_plan_required=True,
            measurement_plan_required=True,
            rollback_plan_required=True,
        )

    # 2. Target bot check
    target_ok, target_reason = _check_target_bot(candidate.target_bot, allow_non_canary)
    if not target_ok:
        blocked.append(target_reason)

    # 3. Known bot check
    known_ok, known_reason = _check_known_bot(candidate.target_bot)
    if not known_ok:
        blocked.append(known_reason)

    # 4. Parameter safety
    param_ok, param_reason = _check_parameter_safe(candidate.parameter)
    if not param_ok:
        blocked.append(param_reason)

    # 5. Dry run
    dry_ok, dry_reason = _check_dry_run(pre_apply_config)
    if not dry_ok:
        blocked.append(dry_reason)

    # 6. Measurement window check
    measure_ok, measure_reason, measure_action = _check_measurement_window(
        candidate.candidate_id, active_measurement_candidate_id,
    )
    if measure_action == "DEFERRED":
        return CandidatePipelineResult(
            decision=CandidatePipelineDecision(
                status="DEFERRED",
                candidate_id=candidate.candidate_id,
                target_bot=candidate.target_bot,
                canary_only=not allow_non_canary,
                readiness_ready=False,
                restart_required=True,
                measurement_required=False,
                rollback_available=_check_rollback_available(),
                blocked_reasons=(measure_reason,),
                next_step=f"Wait for measurement completion of {active_measurement_candidate_id!r}.",
                created_at_utc=now,
            ),
            readiness_report=None,
            restart_plan_required=True,
            measurement_plan_required=False,
            rollback_plan_required=True,
        )
    if not measure_ok:
        blocked.append(measure_reason)

    # 7. Check blocked list before autonomy policy
    if blocked:
        rollback_avail = _check_rollback_available()
        return CandidatePipelineResult(
            decision=CandidatePipelineDecision(
                status="BLOCKED",
                candidate_id=candidate.candidate_id,
                target_bot=candidate.target_bot,
                canary_only=not allow_non_canary,
                readiness_ready=False,
                restart_required=True,
                measurement_required=True,
                rollback_available=rollback_avail,
                blocked_reasons=tuple(blocked),
                next_step="Review blocked reasons, fix before retrying pipeline.",
                created_at_utc=now,
            ),
            readiness_report=None,
            restart_plan_required=True,
            measurement_plan_required=True,
            rollback_plan_required=rollback_avail,
        )

    # 8. Autonomy policy check (replaces human gate in DRY_RUN mode)
    if candidate.autonomy_mode == "DRY_RUN":
        policy_input = _evaluate_autonomy_for_candidate(
            candidate, pre_apply_config, active_measurement_candidate_id,
            kill_switch_mode=kill_switch_mode,
            riskguard_status=riskguard_status,
            allowlist_compatible=allowlist_compatible,
        )
        if policy_input is not None:
            policy_decision = evaluate_autonomy_policy(policy_input)

            if policy_decision.status == "AUTO_DRY_RUN_BLOCKED":
                return CandidatePipelineResult(
                    decision=CandidatePipelineDecision(
                        status="AUTO_DRY_RUN_BLOCKED",
                        candidate_id=candidate.candidate_id,
                        target_bot=candidate.target_bot,
                        canary_only=not allow_non_canary,
                        readiness_ready=False,
                        restart_required=True,
                        measurement_required=True,
                        rollback_available=_check_rollback_available(),
                        blocked_reasons=policy_decision.reasons,
                        next_step=policy_decision.required_next_step,
                        created_at_utc=now,
                    ),
                    readiness_report=None,
                    restart_plan_required=True,
                    measurement_plan_required=True,
                    rollback_plan_required=True,
                )

            if policy_decision.status == "AUTO_DRY_RUN_DEFERRED":
                return CandidatePipelineResult(
                    decision=CandidatePipelineDecision(
                        status="AUTO_DRY_RUN_DEFERRED",
                        candidate_id=candidate.candidate_id,
                        target_bot=candidate.target_bot,
                        canary_only=not allow_non_canary,
                        readiness_ready=False,
                        restart_required=True,
                        measurement_required=False,
                        rollback_available=_check_rollback_available(),
                        blocked_reasons=policy_decision.reasons,
                        next_step=policy_decision.required_next_step,
                        created_at_utc=now,
                    ),
                    readiness_report=None,
                    restart_plan_required=True,
                    measurement_plan_required=False,
                    rollback_plan_required=True,
                )

            # AUTO_DRY_RUN_APPROVED — continue to readiness check
            # (policy gates pass, but execution is not wired yet in Phase 6A)
        else:
            blocked.append("autonomy_policy_input_failed: could not build policy input")

        # Check blocked list after autonomy policy evaluation
        if blocked:
            rollback_avail = _check_rollback_available()
            return CandidatePipelineResult(
                decision=CandidatePipelineDecision(
                    status="BLOCKED",
                    candidate_id=candidate.candidate_id,
                    target_bot=candidate.target_bot,
                    canary_only=not allow_non_canary,
                    readiness_ready=False,
                    restart_required=True,
                    measurement_required=True,
                    rollback_available=rollback_avail,
                    blocked_reasons=tuple(blocked),
                    next_step="Review blocked reasons, fix before retrying pipeline.",
                    created_at_utc=now,
                ),
                readiness_report=None,
                restart_plan_required=True,
                measurement_plan_required=True,
                rollback_plan_required=rollback_avail,
            )
    else:
        # Legacy human approval check (OFF mode)
        if not candidate.requires_human_approval:
            return CandidatePipelineResult(
                decision=CandidatePipelineDecision(
                    status="DEFERRED",
                    candidate_id=candidate.candidate_id,
                    target_bot=candidate.target_bot,
                    canary_only=not allow_non_canary,
                    readiness_ready=False,
                    restart_required=True,
                    measurement_required=True,
                    rollback_available=_check_rollback_available(),
                    blocked_reasons=("requires_human_approval is False",),
                    next_step="Set requires_human_approval=True or obtain explicit human approval.",
                    created_at_utc=now,
                ),
                readiness_report=None,
                restart_plan_required=True,
                measurement_plan_required=True,
                rollback_plan_required=True,
            )

    # 8. Readiness check (optional, read-only)
    if _check_readiness_available() and not blocked:
        try:
            from si_v2.apply_actuator.controlled_apply_actuator import check_readiness
            overlay_val = candidate.proposed_value
            overlay_dict: dict[str, int | float] = {candidate.parameter: overlay_val}  # type: ignore[assignment]
            # Use real evidence values; None means the check will fail-closed
            rr = check_readiness(
                candidate_sha=candidate.candidate_id,
                bot_id=candidate.target_bot,
                parameter_overlay=overlay_dict,
                requires_human_approval=(candidate.autonomy_mode != "DRY_RUN"),
                pre_apply_config=dict(pre_apply_config),
                riskguard_status=riskguard_status,
                apply_mode=(
                    ApplyMode.AUTONOMOUS_DRY_RUN
                    if candidate.autonomy_mode == "DRY_RUN"
                    else ApplyMode.MANUAL_L3
                ),
            )
            readiness_ready = rr.ready
            readiness_report = rr
        except Exception:
            readiness_ready = False
            readiness_report = "readiness_check_failed"

    # Determine status
    rollback_avail = _check_rollback_available()

    if candidate.autonomy_mode == "DRY_RUN":
        # In DRY_RUN mode, policy gates passed — return approved status
        if readiness_ready:
            return CandidatePipelineResult(
                decision=CandidatePipelineDecision(
                    status="READY_FOR_AUTONOMOUS_DRY_RUN_APPLY",
                    candidate_id=candidate.candidate_id,
                    target_bot=candidate.target_bot,
                    canary_only=not allow_non_canary,
                    readiness_ready=True,
                    restart_required=True,
                    measurement_required=True,
                    rollback_available=rollback_avail,
                    blocked_reasons=(),
                    next_step=(
                        "All policy gates pass. Candidate is ready for autonomous "
                        "dry-run apply. Wire autonomous dry-run executor in Phase 6B."
                    ),
                    created_at_utc=now,
                ),
                readiness_report=readiness_report,
                restart_plan_required=True,
                measurement_plan_required=True,
                rollback_plan_required=rollback_avail,
            )

        return CandidatePipelineResult(
            decision=CandidatePipelineDecision(
                status="AUTO_DRY_RUN_APPROVED",
                candidate_id=candidate.candidate_id,
                target_bot=candidate.target_bot,
                canary_only=not allow_non_canary,
                readiness_ready=readiness_ready,
                restart_required=True,
                measurement_required=True,
                rollback_available=rollback_avail,
                blocked_reasons=(),
                next_step=(
                    "All policy gates pass. Candidate is approved for autonomous "
                    "dry-run apply. Wire autonomous dry-run executor in Phase 6B."
                ),
                created_at_utc=now,
            ),
            readiness_report=readiness_report,
            restart_plan_required=True,
            measurement_plan_required=True,
            rollback_plan_required=rollback_avail,
        )

    # Legacy mode (autonomy_mode == "OFF")
    if readiness_ready:
        return CandidatePipelineResult(
            decision=CandidatePipelineDecision(
                status="READY_FOR_CANARY_APPLY",
                candidate_id=candidate.candidate_id,
                target_bot=candidate.target_bot,
                canary_only=not allow_non_canary,
                readiness_ready=True,
                restart_required=True,
                measurement_required=True,
                rollback_available=rollback_avail,
                blocked_reasons=(),
                next_step=(
                    "All gates pass. Candidate is ready for canary apply. "
                    "Next: L3 gate → execute_apply() → RestartPlan → RestartGate → "
                    "RuntimeExecutor → RuntimeEffectProof → Measurement."
                ),
                created_at_utc=now,
            ),
            readiness_report=readiness_report,
            restart_plan_required=True,
            measurement_plan_required=True,
            rollback_plan_required=rollback_avail,
        )

    return CandidatePipelineResult(
        decision=CandidatePipelineDecision(
            status="READY_FOR_HUMAN_APPROVAL",
            candidate_id=candidate.candidate_id,
            target_bot=candidate.target_bot,
            canary_only=not allow_non_canary,
            readiness_ready=readiness_ready,
            restart_required=True,
            measurement_required=True,
            rollback_available=rollback_avail,
            blocked_reasons=(),
            next_step=(
                "Candidate passes basic validation but requires human approval. "
                "Run check_readiness() to verify all gates."
            ),
            created_at_utc=now,
        ),
        readiness_report=readiness_report,
        restart_plan_required=True,
        measurement_plan_required=True,
        rollback_plan_required=rollback_avail,
    )
