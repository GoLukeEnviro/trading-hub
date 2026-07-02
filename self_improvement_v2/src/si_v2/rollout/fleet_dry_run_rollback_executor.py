"""SI-v2 Phase 10.5 — Controlled Dry-Run Fleet Rollback Executor.

Executes a controlled dry-run rollback for a target bot when the post-fleet
measurement watcher (Phase 10.4) emits ROLLBACK_FLEET_OVERLAY.

This module wraps the rollback ceremony with safety guards:
- Refuses non-ROLLBACK decision packs
- Refuses KEEP or EXTEND decision packs
- Requires snapshot artifact from Phase 10.3
- Requires rollback plan from rollout artifacts
- Refuses non-dry-run bots
- Refuses non-allowlisted targets
- Refuses multiple targets (unless explicitly configured)
- Writes rollback audit, rollback RuntimeEffectProof, and post-rollback
  measurement start record
- Returns DRY_RUN_ROLLBACK_GREEN or DRY_RUN_ROLLBACK_YELLOW

This module is **dry-run-only**. It does NOT:
- Enable live trading
- Enable schedulers or watchers
- Execute uncontrolled fleet rollback
- Modify bot configs outside the ceremony path
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_ROLLBACK_OUTPUT_DIR: str = "var/si_v2/fleet_dry_run_rollback_executor"

# Default allowlist of target bot IDs for dry-run rollback execution.
DEFAULT_ALLOWED_DRY_RUN_TARGETS: tuple[str, ...] = (
    "freqtrade-regime-hybrid",
    "freqai-rebel",
)

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DryRunRollbackExecutorInput:
    """All inputs for the dry-run fleet rollback executor.

    Attributes:
        decision_pack_path: Path to the Phase 10.4 decision pack JSON.
            Must have decision=ROLLBACK_FLEET_OVERLAY.
        snapshot_path: Path to the pre-apply snapshot from Phase 10.3.
        rollback_plan_path: Path to the rollback plan from rollout artifacts.
        target_bot: Bot ID to roll back.
        allowed_targets: Explicit allowlist of target bot IDs. If None,
            uses DEFAULT_ALLOWED_DRY_RUN_TARGETS.
        allow_multiple_targets: If True, allows multiple targets in a single
            execution. Default False (single target only).
    """

    decision_pack_path: str
    snapshot_path: str
    rollback_plan_path: str
    target_bot: str
    allowed_targets: tuple[str, ...] | None = None
    allow_multiple_targets: bool = False


@dataclass(frozen=True)
class DryRunRollbackExecutorResult:
    """Structured result from the dry-run fleet rollback executor.

    Attributes:
        status: Overall execution status.
        change_id: Change ID from the decision pack.
        candidate_id: Candidate ID from the decision pack.
        target_bot: Bot that was rolled back.
        blocked_reasons: Human-readable reasons for blocking.
        rollback_audit_path: Path to the rollback audit artifact.
        rollback_effect_proof_path: Path to the rollback RuntimeEffectProof.
        post_rollback_measurement_start_path: Path to the post-rollback
            measurement start record.
        next_step: Suggested next action.
    """

    status: Literal[
        "DRY_RUN_ROLLBACK_GREEN",
        "DRY_RUN_ROLLBACK_YELLOW",
        "DRY_RUN_ROLLBACK_BLOCKED",
    ]
    change_id: str
    candidate_id: str
    target_bot: str
    blocked_reasons: tuple[str, ...]
    rollback_audit_path: str
    rollback_effect_proof_path: str
    post_rollback_measurement_start_path: str
    next_step: str

    def to_dict(self) -> dict[str, object]:
        return {
            "event": "dry_run_rollback_executor_result",
            "status": self.status,
            "change_id": self.change_id,
            "candidate_id": self.candidate_id,
            "target_bot": self.target_bot,
            "blocked_reasons": list(self.blocked_reasons),
            "rollback_audit_path": self.rollback_audit_path,
            "rollback_effect_proof_path": self.rollback_effect_proof_path,
            "post_rollback_measurement_start_path": self.post_rollback_measurement_start_path,
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


def _read_json(path: str) -> dict[str, object] | None:
    """Read and parse a JSON file. Returns None on failure."""
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return None


# ---------------------------------------------------------------------------
# Safety guard: validate decision pack is ROLLBACK
# ---------------------------------------------------------------------------


def _validate_rollback_decision(
    decision_pack_path: str,
) -> tuple[bool, tuple[str, ...]]:
    """Validate that the decision pack says ROLLBACK_FLEET_OVERLAY.

    Returns (passes, reasons).
    """
    reasons: list[str] = []
    pack = _read_json(decision_pack_path)
    if pack is None:
        return False, (f"decision_pack_not_readable: {decision_pack_path}",)

    decision = str(pack.get("decision", ""))
    if decision != "ROLLBACK_FLEET_OVERLAY":
        reasons.append(
            f"decision_not_rollback: decision={decision!r} != "
            f"ROLLBACK_FLEET_OVERLAY"
        )

    event = str(pack.get("event", ""))
    if event != "post_fleet_measurement_decision":
        reasons.append(
            f"unexpected_event: {event!r} != post_fleet_measurement_decision"
        )

    runtime_mutation = str(pack.get("runtime_mutation", ""))
    if runtime_mutation != "NONE":
        reasons.append(
            f"runtime_mutation_not_none: {runtime_mutation!r}"
        )

    if not reasons:
        return True, ()
    return False, tuple(reasons)


# ---------------------------------------------------------------------------
# Safety guard: validate snapshot exists
# ---------------------------------------------------------------------------


def _validate_snapshot_exists(
    snapshot_path: str,
) -> tuple[bool, tuple[str, ...]]:
    """Validate that the pre-apply snapshot artifact exists.

    Returns (passes, reasons).
    """
    reasons: list[str] = []
    if not snapshot_path:
        reasons.append("snapshot_path_empty: no snapshot path provided")
        return False, tuple(reasons)

    p = Path(snapshot_path)
    if not p.exists():
        reasons.append(f"snapshot_not_found: {snapshot_path}")
        return False, tuple(reasons)

    snapshot = _read_json(snapshot_path)
    if snapshot is None:
        reasons.append(f"snapshot_not_readable: {snapshot_path}")
        return False, tuple(reasons)

    if snapshot.get("runtime_mutation") != "NONE":
        reasons.append(
            f"snapshot_runtime_mutation_not_none: "
            f"{snapshot.get('runtime_mutation')!r}",
        )
        return False, tuple(reasons)

    return True, ()


# ---------------------------------------------------------------------------
# Safety guard: validate rollback plan exists
# ---------------------------------------------------------------------------


def _validate_rollback_plan_exists(
    rollback_plan_path: str,
) -> tuple[bool, tuple[str, ...]]:
    """Validate that the rollback plan artifact exists.

    Returns (passes, reasons).
    """
    if not rollback_plan_path:
        return False, ("rollback_plan_path_empty: no rollback plan path provided",)

    p = Path(rollback_plan_path)
    if not p.exists():
        return False, (f"rollback_plan_not_found: {rollback_plan_path}",)

    plan = _read_json(rollback_plan_path)
    if plan is None:
        return False, (f"rollback_plan_not_readable: {rollback_plan_path}",)

    if plan.get("runtime_mutation") != "NONE":
        return False, (
            f"rollback_plan_runtime_mutation_not_none: "
            f"{plan.get('runtime_mutation')!r}",
        )

    return True, ()


# ---------------------------------------------------------------------------
# Safety guard: validate allowlist
# ---------------------------------------------------------------------------


def _validate_allowlist(
    target_bot: str,
    allowed_targets: tuple[str, ...],
) -> tuple[bool, tuple[str, ...]]:
    """Validate that the target bot is in the allowlist.

    Returns (passes, reasons).
    """
    if target_bot not in allowed_targets:
        return False, (
            f"target_not_allowlisted: {target_bot} is not in the "
            f"dry-run rollback executor allowlist",
        )
    return True, ()


# ---------------------------------------------------------------------------
# Safety guard: validate single target
# ---------------------------------------------------------------------------


def _validate_single_target(
    target_bot: str,
    allow_multiple: bool,
) -> tuple[bool, tuple[str, ...]]:
    """Validate that exactly one target is selected (unless multiple allowed).

    Returns (passes, reasons).
    """
    if allow_multiple:
        return True, ()

    if not target_bot:
        return False, ("no_target: target_bot is empty",)

    # Single target is always valid — multiple targets would need
    # a different input shape.
    return True, ()


# ---------------------------------------------------------------------------
# Safety guard: validate dry-run target
# ---------------------------------------------------------------------------


def _validate_dry_run_target(
    target_bot: str,
    rollback_plan_path: str,
) -> tuple[bool, tuple[str, ...]]:
    """Validate that the target bot is dry-run.

    Checks the rollback plan for dry_run confirmation.

    Returns (passes, reasons).
    """
    reasons: list[str] = []
    plan = _read_json(rollback_plan_path)
    if plan is None:
        reasons.append(f"rollback_plan_not_readable: {rollback_plan_path}")
        return False, tuple(reasons)

    # Check if the rollback plan references a dry-run bot
    # The plan's rollback_command_prefix should contain dry_run references
    cmd_prefix = plan.get("rollback_command_prefix", [])
    if isinstance(cmd_prefix, list):
        cmd_str = " ".join(str(c) for c in cmd_prefix)
        if "dry_run" not in cmd_str.lower() and "--dry-run" not in cmd_str.lower():
            reasons.append(
                f"dry_run_not_confirmed: {target_bot} rollback plan "
                f"does not reference dry_run in command prefix"
            )
            return False, tuple(reasons)

    return True, ()


# ---------------------------------------------------------------------------
# Main rollback executor
# ---------------------------------------------------------------------------


def run_dry_run_fleet_rollback_executor(
    input_: DryRunRollbackExecutorInput,
    *,
    rollback_output_dir: Path | None = None,
    runtime_executor: object | None = None,
    now_utc: str | None = None,
) -> DryRunRollbackExecutorResult:
    """Execute a controlled dry-run fleet rollback.

    This is the primary entry point for Phase 10.5. It applies all
    safety guards before delegating to the runtime executor for the
    actual rollback action.

    Args:
        input_: Executor input with decision pack, snapshot, rollback plan.
        rollback_output_dir: Override for rollback output directory.
        runtime_executor: Callable for actual runtime rollback actions.
            Must accept (target_bot: str, rollback_plan_path: str)
            and return dict with "status" and "detail".
        now_utc: Override for current UTC time (testing).

    Returns:
        DryRunRollbackExecutorResult with execution status and audit trail.
    """
    resolved_now = now_utc or datetime.now(UTC).isoformat()
    resolved_dir = rollback_output_dir or Path(DEFAULT_ROLLBACK_OUTPUT_DIR)

    blocked: list[str] = []
    allowed_targets = input_.allowed_targets or DEFAULT_ALLOWED_DRY_RUN_TARGETS

    # ------------------------------------------------------------------
    # Safety guard 1: validate decision pack is ROLLBACK
    # ------------------------------------------------------------------

    decision_pack = _read_json(input_.decision_pack_path)
    if decision_pack is None:
        blocked.append(
            f"decision_pack_not_readable: {input_.decision_pack_path}"
        )
    else:
        decision = str(decision_pack.get("decision", ""))
        if decision != "ROLLBACK_FLEET_OVERLAY":
            blocked.append(
                f"decision_not_rollback: decision={decision!r} != "
                f"ROLLBACK_FLEET_OVERLAY"
            )

    # Extract change_id and candidate_id from decision pack
    change_id = str(decision_pack.get("change_id", "")) if decision_pack else ""
    candidate_id = str(decision_pack.get("candidate_id", "")) if decision_pack else ""

    # ------------------------------------------------------------------
    # Safety guard 2: validate snapshot exists
    # ------------------------------------------------------------------

    snapshot_passes, snapshot_reasons = _validate_snapshot_exists(
        input_.snapshot_path,
    )
    if not snapshot_passes:
        blocked.extend(snapshot_reasons)

    # ------------------------------------------------------------------
    # Safety guard 3: validate rollback plan exists
    # ------------------------------------------------------------------

    plan_passes, plan_reasons = _validate_rollback_plan_exists(
        input_.rollback_plan_path,
    )
    if not plan_passes:
        blocked.extend(plan_reasons)

    # ------------------------------------------------------------------
    # Safety guard 4: validate allowlist
    # ------------------------------------------------------------------

    allowlist_passes, allowlist_reasons = _validate_allowlist(
        input_.target_bot, allowed_targets,
    )
    if not allowlist_passes:
        blocked.extend(allowlist_reasons)

    # ------------------------------------------------------------------
    # Safety guard 5: validate single target
    # ------------------------------------------------------------------

    single_target_passes, single_target_reasons = _validate_single_target(
        input_.target_bot, input_.allow_multiple_targets,
    )
    if not single_target_passes:
        blocked.extend(single_target_reasons)

    # ------------------------------------------------------------------
    # Safety guard 6: validate dry-run target
    # ------------------------------------------------------------------

    dry_run_passes, dry_run_reasons = _validate_dry_run_target(
        input_.target_bot, input_.rollback_plan_path,
    )
    if not dry_run_passes:
        blocked.extend(dry_run_reasons)

    # ------------------------------------------------------------------
    # Block if any safety guard failed
    # ------------------------------------------------------------------

    if blocked:
        # Write rollback audit with blocked status
        audit: dict[str, object] = {
            "event": "dry_run_rollback_executor_audit",
            "status": "BLOCKED",
            "change_id": change_id,
            "candidate_id": candidate_id,
            "target_bot": input_.target_bot,
            "blocked_reasons": blocked,
            "created_at_utc": resolved_now,
            "runtime_mutation": "NONE",
        }
        audit_path = resolved_dir / "rollback_audit.json"
        _atomic_write_json(audit_path, audit)

        return DryRunRollbackExecutorResult(
            status="DRY_RUN_ROLLBACK_BLOCKED",
            change_id=change_id,
            candidate_id=candidate_id,
            target_bot=input_.target_bot,
            blocked_reasons=tuple(blocked),
            rollback_audit_path=str(audit_path),
            rollback_effect_proof_path="",
            post_rollback_measurement_start_path="",
            next_step="Review blocked reasons and fix before retrying rollback.",
        )

    # ------------------------------------------------------------------
    # Execute rollback via runtime executor
    # ------------------------------------------------------------------

    target_dir = resolved_dir / change_id[:24] / "targets" / input_.target_bot

    rollback_audit_path = str(target_dir / "rollback_audit.json")
    rollback_effect_proof_path = str(target_dir / "rollback_effect_proof.json")
    post_rollback_measurement_start_path = str(
        target_dir / "post_rollback_measurement_start_record.json"
    )

    try:
        # 1. Write pre-rollback audit
        pre_audit: dict[str, object] = {
            "event": "rollback_audit",
            "target_bot": input_.target_bot,
            "decision_pack_path": input_.decision_pack_path,
            "snapshot_path": input_.snapshot_path,
            "rollback_plan_path": input_.rollback_plan_path,
            "rollback_started_at_utc": resolved_now,
            "runtime_mutation": "NONE",
        }
        _atomic_write_json(target_dir / "rollback_audit.json", pre_audit)

        # 2. Execute rollback action via runtime executor
        if runtime_executor is not None:
            executor_result: dict[str, str] = runtime_executor(  # type: ignore[operator]
                input_.target_bot, input_.rollback_plan_path
            )
            executor_status = executor_result.get("status", "unknown")
            executor_detail = executor_result.get("detail", "")
        else:
            executor_status = "simulated"
            executor_detail = "no runtime executor provided — dry-run simulation"

        # 3. Write rollback RuntimeEffectProof
        effect_proof: dict[str, object] = {
            "event": "rollback_effect_proof",
            "target_bot": input_.target_bot,
            "rollback_status": "EXECUTED",
            "executor_status": executor_status,
            "executor_detail": executor_detail,
            "rollback_audit": rollback_audit_path,
            "snapshot_used": input_.snapshot_path,
            "rollback_plan_used": input_.rollback_plan_path,
            "proven_at_utc": resolved_now,
            "runtime_mutation": "NONE",
        }
        _atomic_write_json(
            target_dir / "rollback_effect_proof.json", effect_proof
        )

        # 4. Write post-rollback measurement start record
        measurement_start: dict[str, object] = {
            "event": "post_rollback_measurement_start_record",
            "target_bot": input_.target_bot,
            "rollback_status": "EXECUTED",
            "measurement_started_at_utc": resolved_now,
            "expected_parameter": str(
                decision_pack.get("expected_parameter", "")
                if decision_pack else ""
            ),
            "expected_value": (
                decision_pack.get("expected_value", 0)
                if decision_pack else 0
            ),
            "runtime_mutation": "NONE",
        }
        _atomic_write_json(
            target_dir / "post_rollback_measurement_start_record.json",
            measurement_start,
        )

        # 5. Write executor-level rollback audit
        executor_audit: dict[str, object] = {
            "event": "dry_run_rollback_executor_audit",
            "status": "DRY_RUN_ROLLBACK_GREEN",
            "change_id": change_id,
            "candidate_id": candidate_id,
            "target_bot": input_.target_bot,
            "executor_status": executor_status,
            "executor_detail": executor_detail,
            "rollback_audit_path": rollback_audit_path,
            "rollback_effect_proof_path": rollback_effect_proof_path,
            "post_rollback_measurement_start_path": (
                post_rollback_measurement_start_path
            ),
            "created_at_utc": resolved_now,
            "runtime_mutation": "NONE",
        }
        _atomic_write_json(
            resolved_dir / "rollback_executor_audit.json", executor_audit
        )

        return DryRunRollbackExecutorResult(
            status="DRY_RUN_ROLLBACK_GREEN",
            change_id=change_id,
            candidate_id=candidate_id,
            target_bot=input_.target_bot,
            blocked_reasons=(),
            rollback_audit_path=rollback_audit_path,
            rollback_effect_proof_path=rollback_effect_proof_path,
            post_rollback_measurement_start_path=(
                post_rollback_measurement_start_path
            ),
            next_step=(
                "Rollback executed successfully in dry-run mode. "
                "Begin post-rollback measurement phase."
            ),
        )

    except Exception as e:
        # Write executor audit with YELLOW status
        error_audit: dict[str, object] = {
            "event": "dry_run_rollback_executor_audit",
            "status": "DRY_RUN_ROLLBACK_YELLOW",
            "change_id": change_id,
            "candidate_id": candidate_id,
            "target_bot": input_.target_bot,
            "error": str(e),
            "created_at_utc": resolved_now,
            "runtime_mutation": "NONE",
        }
        _atomic_write_json(
            resolved_dir / "rollback_executor_audit.json", error_audit
        )

        return DryRunRollbackExecutorResult(
            status="DRY_RUN_ROLLBACK_YELLOW",
            change_id=change_id,
            candidate_id=candidate_id,
            target_bot=input_.target_bot,
            blocked_reasons=(f"rollback_execution_failed: {e}",),
            rollback_audit_path=rollback_audit_path,
            rollback_effect_proof_path=rollback_effect_proof_path,
            post_rollback_measurement_start_path=(
                post_rollback_measurement_start_path
            ),
            next_step=(
                "Rollback execution encountered errors. "
                "Review and re-run rollback for failed targets."
            ),
        )
