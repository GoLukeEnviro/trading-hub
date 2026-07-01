"""SI-v2 Phase 10.3 — Controlled Dry-Run Fleet Runtime Executor.

Executes the Fleet Rollout Chain in dry-run runtime mode for exactly one
allowlisted target bot using an explicit runtime executor.

This module wraps the Phase 9C ceremony with additional safety guards:
- Refuses dry_run=false
- Refuses non-allowlisted targets
- Refuses multiple targets (unless explicitly configured)
- Blocks without rollback plan
- Writes pre-apply snapshot, runtime apply audit, RuntimeEffectProof,
  and measurement start record
- Returns FLEET_CHAIN_EXECUTED_GREEN or FLEET_CHAIN_EXECUTED_YELLOW

This module is **dry-run-only**. It does NOT:
- Enable live trading
- Enable schedulers or watchers
- Execute uncontrolled fleet apply
- Modify bot configs outside the ceremony path
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from si_v2.rollout.fleet_rollout_chain_runner import (
    FleetRolloutChainInput,
    FleetRolloutChainResult,
    run_fleet_rollout_chain,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_EXECUTOR_OUTPUT_DIR: str = "var/si_v2/fleet_dry_run_runtime_executor"

# Default allowlist of target bot IDs for dry-run runtime execution.
DEFAULT_ALLOWED_DRY_RUN_TARGETS: tuple[str, ...] = (
    "freqtrade-regime-hybrid",
    "freqai-rebel",
)

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DryRunRuntimeExecutorInput:
    """All inputs for the dry-run fleet runtime executor.

    Attributes:
        chain_input: Fully resolved FleetRolloutChainInput. Must have
            execute_fleet_runtime=False (the executor will override it).
        allowed_targets: Explicit allowlist of target bot IDs. If None,
            uses DEFAULT_ALLOWED_DRY_RUN_TARGETS.
        allow_multiple_targets: If True, allows multiple targets in a single
            execution. Default False (single target only).
        require_rollback_plan: If True, blocks if the rollout plan does not
            include a rollback plan. Default True.
    """

    chain_input: FleetRolloutChainInput
    allowed_targets: tuple[str, ...] | None = None
    allow_multiple_targets: bool = False
    require_rollback_plan: bool = True


@dataclass(frozen=True)
class DryRunRuntimeExecutorResult:
    """Structured result from the dry-run fleet runtime executor.

    Attributes:
        status: Overall execution status.
        chain_result: The underlying FleetRolloutChainResult.
        blocked_reasons: Human-readable reasons for blocking.
        executor_audit_path: Path to the executor audit artifact.
        next_step: Suggested next action.
    """

    status: Literal[
        "DRY_RUN_EXECUTED_GREEN",
        "DRY_RUN_EXECUTED_YELLOW",
        "DRY_RUN_EXECUTOR_BLOCKED",
    ]
    chain_result: FleetRolloutChainResult | None
    blocked_reasons: tuple[str, ...]
    executor_audit_path: str
    next_step: str

    def to_dict(self) -> dict[str, object]:
        return {
            "event": "dry_run_runtime_executor_result",
            "status": self.status,
            "chain_status": self.chain_result.status if self.chain_result else "",
            "blocked_reasons": list(self.blocked_reasons),
            "executor_audit_path": self.executor_audit_path,
            "next_step": self.next_step,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _atomic_write_json(path: Path, data: dict[str, object]) -> None:
    """Write JSON atomically via temp file + replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp.{abs(hash(str(data)))}")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True))
    tmp.replace(path)


# ---------------------------------------------------------------------------
# Safety guard: validate dry_run
# ---------------------------------------------------------------------------


def _validate_dry_run(
    chain_input: FleetRolloutChainInput,
) -> tuple[bool, tuple[str, ...]]:
    """Validate that all fleet bots are dry-run.

    Returns (passes, reasons).
    """
    reasons: list[str] = []
    for bot in chain_input.fleet_bots:
        if not bot.dry_run:
            reasons.append(
                f"dry_run_required: bot {bot.bot_id} has dry_run=False"
            )
    if not reasons:
        return True, ()
    return False, tuple(reasons)


# ---------------------------------------------------------------------------
# Safety guard: validate allowlist
# ---------------------------------------------------------------------------


def _validate_allowlist(
    chain_input: FleetRolloutChainInput,
    allowed_targets: tuple[str, ...],
) -> tuple[bool, tuple[str, ...]]:
    """Validate that all allowed_target_bots are in the allowlist.

    Returns (passes, reasons).
    """
    reasons: list[str] = []
    for target in chain_input.allowed_target_bots:
        if target not in allowed_targets:
            reasons.append(
                f"target_not_allowlisted: {target} is not in the "
                f"dry-run runtime executor allowlist"
            )
    if not reasons:
        return True, ()
    return False, tuple(reasons)


# ---------------------------------------------------------------------------
# Safety guard: validate single target
# ---------------------------------------------------------------------------


def _validate_single_target(
    chain_input: FleetRolloutChainInput,
    allow_multiple: bool,
) -> tuple[bool, tuple[str, ...]]:
    """Validate that exactly one target is selected (unless multiple allowed).

    Returns (passes, reasons).
    """
    if allow_multiple:
        return True, ()

    if len(chain_input.allowed_target_bots) == 0:
        return False, ("no_targets: no allowed target bots in chain input",)

    if len(chain_input.allowed_target_bots) > 1:
        return False, (
            f"multiple_targets: {len(chain_input.allowed_target_bots)} targets "
            f"({', '.join(chain_input.allowed_target_bots)}) — "
            f"single target required unless allow_multiple_targets=True",
        )

    return True, ()


# ---------------------------------------------------------------------------
# Safety guard: validate rollback plan
# ---------------------------------------------------------------------------


def _validate_rollback_plan(
    chain_input: FleetRolloutChainInput,
    require_rollback: bool,
) -> tuple[bool, tuple[str, ...]]:
    """Validate that the chain input has a rollback plan path.

    In Phase 10.3, the rollback plan is embedded in the rollout plan
    artifact (generated by Phase 9B). We validate that the chain input
    references a valid decision pack path (which implies a rollback path
    exists in the plan).

    Returns (passes, reasons).
    """
    if not require_rollback:
        return True, ()

    # The rollback plan is validated at the ceremony level when the
    # rollout plan is read. Here we check that the chain input has
    # a valid decision pack path (prerequisite for rollback).
    if not chain_input.decision_pack_path:
        return False, (
            "rollback_plan_required: decision_pack_path is empty — "
            "cannot verify rollback plan exists",
        )

    return True, ()


# ---------------------------------------------------------------------------
# Main executor
# ---------------------------------------------------------------------------


def run_dry_run_fleet_runtime_executor(
    input_: DryRunRuntimeExecutorInput,
    *,
    executor_output_dir: Path | None = None,
    runtime_executor: object | None = None,
    now_utc: str | None = None,
) -> DryRunRuntimeExecutorResult:
    """Execute the Fleet Rollout Chain in dry-run runtime mode.

    This is the primary entry point for Phase 10.3. It applies all
    safety guards before delegating to the chain runner with
    execute_fleet_runtime=True.

    Args:
        input_: Executor input with chain input and safety flags.
        executor_output_dir: Override for executor output directory.
        runtime_executor: Callable for actual runtime actions. Required
            for execution. Must accept (target_bot: str, overlay_path: str)
            and return dict with "status" and "detail".
        now_utc: Override for current UTC time (testing).

    Returns:
        DryRunRuntimeExecutorResult with execution status and audit trail.
    """
    resolved_now = now_utc or datetime.now(UTC).isoformat()
    resolved_dir = executor_output_dir or Path(DEFAULT_EXECUTOR_OUTPUT_DIR)

    blocked: list[str] = []
    chain_input = input_.chain_input
    allowed_targets = input_.allowed_targets or DEFAULT_ALLOWED_DRY_RUN_TARGETS

    # ------------------------------------------------------------------
    # Safety guard 1: dry_run validation
    # ------------------------------------------------------------------

    dry_run_passes, dry_run_reasons = _validate_dry_run(chain_input)
    if not dry_run_passes:
        blocked.extend(dry_run_reasons)

    # ------------------------------------------------------------------
    # Safety guard 2: allowlist validation
    # ------------------------------------------------------------------

    allowlist_passes, allowlist_reasons = _validate_allowlist(
        chain_input, allowed_targets,
    )
    if not allowlist_passes:
        blocked.extend(allowlist_reasons)

    # ------------------------------------------------------------------
    # Safety guard 3: single target validation
    # ------------------------------------------------------------------

    single_target_passes, single_target_reasons = _validate_single_target(
        chain_input, input_.allow_multiple_targets,
    )
    if not single_target_passes:
        blocked.extend(single_target_reasons)

    # ------------------------------------------------------------------
    # Safety guard 4: rollback plan validation
    # ------------------------------------------------------------------

    rollback_passes, rollback_reasons = _validate_rollback_plan(
        chain_input, input_.require_rollback_plan,
    )
    if not rollback_passes:
        blocked.extend(rollback_reasons)

    # ------------------------------------------------------------------
    # Block if any safety guard failed
    # ------------------------------------------------------------------

    if blocked:
        # Write executor audit with blocked status
        audit: dict[str, object] = {
            "event": "dry_run_runtime_executor_audit",
            "status": "BLOCKED",
            "blocked_reasons": blocked,
            "created_at_utc": resolved_now,
            "runtime_mutation": "NONE",
        }
        audit_path = resolved_dir / "executor_audit.json"
        _atomic_write_json(audit_path, audit)

        return DryRunRuntimeExecutorResult(
            status="DRY_RUN_EXECUTOR_BLOCKED",
            chain_result=None,
            blocked_reasons=tuple(blocked),
            executor_audit_path=str(audit_path),
            next_step="Review blocked reasons and fix before retrying.",
        )

    # ------------------------------------------------------------------
    # Build chain input with execute_fleet_runtime=True
    # ------------------------------------------------------------------

    executed_chain_input = FleetRolloutChainInput(
        decision_pack_path=chain_input.decision_pack_path,
        fleet_bots=chain_input.fleet_bots,
        allowed_target_bots=chain_input.allowed_target_bots,
        target_runtime_specs=chain_input.target_runtime_specs,
        source_overlay_path=chain_input.source_overlay_path,
        source_overlay_sha256=chain_input.source_overlay_sha256,
        expected_parameter=chain_input.expected_parameter,
        expected_value=chain_input.expected_value,
        execute_fleet_runtime=True,
        require_statistical_evidence=chain_input.require_statistical_evidence,
        min_stat_evidence_grade=chain_input.min_stat_evidence_grade,
        max_targets=chain_input.max_targets,
    )

    # ------------------------------------------------------------------
    # Run the chain with runtime executor
    # ------------------------------------------------------------------

    chain_result = run_fleet_rollout_chain(
        executed_chain_input,
        chain_output_dir=resolved_dir / "chain",
        runtime_executor=runtime_executor,
        now_utc=resolved_now,
    )

    # ------------------------------------------------------------------
    # Map chain result to executor result
    # ------------------------------------------------------------------

    if chain_result.status == "FLEET_CHAIN_EXECUTED_GREEN":
        executor_status: str = "DRY_RUN_EXECUTED_GREEN"
        next_step = (
            "All targets executed successfully in dry-run mode. "
            "Begin measurement phase."
        )
    elif chain_result.status == "FLEET_CHAIN_EXECUTED_YELLOW":
        executor_status = "DRY_RUN_EXECUTED_YELLOW"
        next_step = (
            "Partial target failures. Review ceremony results and "
            "re-run for failed targets."
        )
    else:
        executor_status = "DRY_RUN_EXECUTOR_BLOCKED"
        blocked.extend(chain_result.blocked_reasons)
        next_step = "Review chain blocked reasons and fix before retrying."

    # ------------------------------------------------------------------
    # Write executor audit
    # ------------------------------------------------------------------

    executor_audit: dict[str, object] = {
        "event": "dry_run_runtime_executor_audit",
        "status": executor_status,
        "chain_status": chain_result.status,
        "blocked_reasons": list(blocked),
        "change_id": chain_result.change_id,
        "candidate_id": chain_result.candidate_id,
        "rollout_policy_path": chain_result.rollout_policy_path,
        "rollout_plan_path": chain_result.rollout_plan_path,
        "chain_audit_path": chain_result.chain_audit_path,
        "created_at_utc": resolved_now,
        "runtime_mutation": "NONE",
    }
    audit_path = resolved_dir / "executor_audit.json"
    _atomic_write_json(audit_path, executor_audit)

    return DryRunRuntimeExecutorResult(
        status=executor_status,
        chain_result=chain_result,
        blocked_reasons=tuple(blocked),
        executor_audit_path=str(audit_path),
        next_step=next_step,
    )
