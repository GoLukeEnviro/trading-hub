"""SI-v2 Phase 6C — Autonomous Dry-Run Runtime Ceremony Runner.

Connects Phase 6B prepared artifacts to controlled canary dry-run
runtime action.

Flow
----
::

    EXECUTOR_DRY_RUN_APPLY_PREPARED
      → artifact verification
      → restart plan (plan_canary_restart_with_overlay)
      → restart gate check + canary recreate plan
      → autonomous dry-run runtime action
      → RuntimeEffectProof
      → T0 measurement activation record

Safety invariants
-----------------
- Canary-only: target_bot must be ``freqtrade-freqforge-canary``.
- dry_run=true required.
- Kill Switch NORMAL required.
- RiskGuard PASS required.
- Overlay hash must match file content.
- Rollback plan, audit, measurement plan must all exist.
- No per-apply human/L3 token in AUTONOMOUS_DRY_RUN mode.
- execute_runtime=False is the default — no accidental execution.
- Tests mock all runtime calls — no real Docker/Compose in tests.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Literal

from si_v2.apply_actuator.restart_gate import (
    build_canary_recreate_plan,
    check_restart_gate,
)
from si_v2.apply_actuator.restart_with_overlay import (
    CANARY_BOT_ID,
    RestartPlanResult,
    plan_canary_restart_with_overlay,
)
from si_v2.apply_actuator.runtime_executor import (
    CanaryRecreatePlan,
    RuntimeExecutionResult,
    run_canary_restart_with_overlay,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_STATE_DIR: Final[Path] = Path(
    "/opt/data/profiles/orchestrator/state/si_v2_controlled_apply"
)

AUTONOMOUS_MODE: Final[str] = "AUTONOMOUS_DRY_RUN"
MANUAL_MODE: Final[str] = "MANUAL_L3"
LIVE_MODE: Final[str] = "LIVE_CAPITAL_MODE"

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RuntimeCeremonyInput:
    """All inputs for the runtime ceremony runner.

    Every field must come from real Phase 6B executor output or
    runtime evidence — no mocked, simulated, or hardcoded values.
    """

    change_id: str
    """Unique change identifier from the executor."""

    candidate_id: str
    """Candidate identifier."""

    target_bot: str
    """Target bot ID (must be ``freqtrade-freqforge-canary``)."""

    overlay_path: str
    """Path to the overlay JSON file."""

    overlay_sha256: str
    """Expected SHA-256 of the overlay file."""

    rollback_plan_path: str
    """Path to the rollback plan JSON file."""

    audit_path: str
    """Path to the audit JSONL file."""

    measurement_start_plan_path: str
    """Path to the measurement start plan JSON file."""

    pre_apply_config: dict[str, object]
    """Pre-apply config dict (must contain ``dry_run``)."""

    current_command: tuple[str, ...]
    """Current Freqtrade process command (for restart plan)."""

    expected_parameter: str
    """The parameter being changed (e.g. ``max_open_trades``)."""

    expected_value: int | float
    """The expected value after restart (e.g. ``2``)."""

    kill_switch_mode: str
    """Real kill switch mode from runtime evidence."""

    riskguard_status: str
    """Real RiskGuard status from runtime evidence."""

    apply_mode: str = AUTONOMOUS_MODE
    """Operating mode: AUTONOMOUS_DRY_RUN (default), MANUAL_L3, or LIVE_CAPITAL_MODE."""


@dataclass(frozen=True)
class RuntimeCeremonyResult:
    """Structured result from the runtime ceremony runner."""

    status: Literal[
        "CEREMONY_READY",
        "CEREMONY_BLOCKED",
        "CEREMONY_EXECUTED_GREEN",
        "CEREMONY_EXECUTED_YELLOW",
        "CEREMONY_EXECUTED_RED",
        "CEREMONY_RUNTIME_NOT_EXECUTED",
    ]
    change_id: str
    candidate_id: str
    target_bot: str
    restart_plan_ready: bool
    runtime_status: str
    runtime_proof_status: str
    t0_measurement_active: bool
    blocked_reasons: tuple[str, ...]
    restart_plan: dict[str, object] | None
    runtime_result: dict[str, object] | None
    next_step: str

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "change_id": self.change_id,
            "candidate_id": self.candidate_id,
            "target_bot": self.target_bot,
            "restart_plan_ready": self.restart_plan_ready,
            "runtime_status": self.runtime_status,
            "runtime_proof_status": self.runtime_proof_status,
            "t0_measurement_active": self.t0_measurement_active,
            "blocked_reasons": list(self.blocked_reasons),
            "restart_plan": self.restart_plan,
            "runtime_result": self.runtime_result,
            "next_step": self.next_step,
        }


# ---------------------------------------------------------------------------
# Artifact verification
# ---------------------------------------------------------------------------


def _verify_file_exists(path_str: str, label: str) -> tuple[bool, str]:
    if not path_str:
        return False, f"{label}_path_empty: {label} path is empty"
    path = Path(path_str)
    if not path.exists():
        return False, f"{label}_missing: {label} file not found at {path}"
    return True, ""


def _verify_overlay_hash(overlay_path: str, expected_sha256: str) -> tuple[bool, str]:
    if not expected_sha256:
        return False, "overlay_sha_empty: expected overlay SHA-256 is empty"
    try:
        actual = hashlib.sha256(Path(overlay_path).read_bytes()).hexdigest()
    except OSError as e:
        return False, f"overlay_hash_read_error: {e}"
    if actual != expected_sha256:
        return False, (
            f"overlay_hash_mismatch: expected {expected_sha256}, "
            f"actual {actual}"
        )
    return True, ""


def _verify_dry_run(pre_apply_config: dict[str, object]) -> tuple[bool, str]:
    val = pre_apply_config.get("dry_run")
    if val is True:
        return True, ""
    if val is None:
        return False, "dry_run_not_found: key 'dry_run' missing from pre_apply_config"
    return False, f"dry_run_not_true: dry_run={val!r}"


def _verify_kill_switch(kill_switch_mode: str) -> tuple[bool, str]:
    if kill_switch_mode == "NORMAL":
        return True, ""
    return False, (
        f"kill_switch_not_normal: kill_switch_mode={kill_switch_mode!r}. "
        f"AUTONOMOUS_DRY_RUN requires NORMAL."
    )


def _verify_riskguard(riskguard_status: str) -> tuple[bool, str]:
    if riskguard_status == "PASS":
        return True, ""
    return False, (
        f"riskguard_not_pass: riskguard_status={riskguard_status!r}. "
        f"AUTONOMOUS_DRY_RUN requires PASS."
    )


def _verify_apply_mode(apply_mode: str) -> tuple[bool, str]:
    if apply_mode == AUTONOMOUS_MODE:
        return True, ""
    if apply_mode == MANUAL_MODE:
        return True, ""  # MANUAL_L3 is valid but handled separately
    if apply_mode == LIVE_MODE:
        return False, "live_capital_mode_not_implemented: LIVE_CAPITAL_MODE is not implemented"
    return False, f"unknown_apply_mode: {apply_mode!r}"


# ---------------------------------------------------------------------------
# T0 activation record writer
# ---------------------------------------------------------------------------


def _write_t0_activation_record(
    change_id: str,
    candidate_id: str,
    target_bot: str,
    runtime_status: str,
    runtime_proof_status: str,
    t0_dir: Path,
) -> str:
    """Write a T0 activation record.

    Returns the path to the record file.
    Does NOT enable any scheduler or watcher.
    """
    t0_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "event": "runtime_ceremony_t0_active",
        "change_id": change_id,
        "candidate_id": candidate_id,
        "target_bot": target_bot,
        "runtime_status": runtime_status,
        "runtime_proof_status": runtime_proof_status,
        "t0_timestamp_utc": datetime.now(UTC).isoformat(),
        "next_required_component": "autonomous_measurement_watcher",
    }
    filename = f"t0_active_{change_id[:16]}.json"
    path = t0_dir / filename
    tmp = path.with_suffix(f".json.tmp.{id(record)}")
    tmp.write_text(json.dumps(record, indent=2))
    tmp.replace(path)
    return str(path)


# ---------------------------------------------------------------------------
# Main ceremony function
# ---------------------------------------------------------------------------


def run_runtime_ceremony(
    input_: RuntimeCeremonyInput,
    *,
    execute_runtime: bool = False,
    canary_user_data: Path | None = None,
    compose_output_dir: Path | None = None,
    docker_available: bool = True,
    subprocess_runner: object | None = None,
    t0_dir: Path | None = None,
) -> RuntimeCeremonyResult:
    """Run the runtime ceremony for an autonomous dry-run apply.

    With ``execute_runtime=False`` (default):
    - Validates all Phase-6B artifacts.
    - Builds a restart plan.
    - Does NOT execute any runtime action.
    - Returns ``CEREMONY_READY`` or ``CEREMONY_BLOCKED``.

    With ``execute_runtime=True``:
    - Only allowed in ``AUTONOMOUS_DRY_RUN`` mode.
    - No L3 token required.
    - All safety gates must pass.
    - Runtime execution is mocked in tests via ``subprocess_runner``.
    - Returns ``CEREMONY_EXECUTED_GREEN`` / ``_YELLOW`` / ``_RED`` based on
      ``RuntimeEffectProof`` outcome.

    Args:
        input_: All inputs for the ceremony.
        execute_runtime: If True, execute the runtime action.
        canary_user_data: Override for canary user_data path.
        compose_output_dir: Override for compose output directory.
        docker_available: If False, skips real Docker calls.
        subprocess_runner: Override for subprocess runner (testing).
        t0_dir: Override for T0 activation record directory.

    Returns:
        ``RuntimeCeremonyResult`` with ceremony status and evidence.
    """
    resolved_state_dir = DEFAULT_STATE_DIR
    resolved_t0_dir = t0_dir or (resolved_state_dir / "t0_records")

    blocked: list[str] = []

    # --- Input validation ---

    if not input_.change_id:
        blocked.append("change_id_required: change_id must not be empty")
    if not input_.candidate_id:
        blocked.append("candidate_id_required: candidate_id must not be empty")

    # --- Apply mode check ---

    mode_ok, mode_reason = _verify_apply_mode(input_.apply_mode)
    if not mode_ok:
        blocked.append(mode_reason)

    # LIVE_CAPITAL_MODE blocks early
    if input_.apply_mode == LIVE_MODE:
        return RuntimeCeremonyResult(
            status="CEREMONY_BLOCKED",
            change_id=input_.change_id,
            candidate_id=input_.candidate_id,
            target_bot=input_.target_bot,
            restart_plan_ready=False,
            runtime_status="BLOCKED",
            runtime_proof_status="NOT_RUN",
            t0_measurement_active=False,
            blocked_reasons=tuple(blocked),
            restart_plan=None,
            runtime_result=None,
            next_step="LIVE_CAPITAL_MODE is not implemented.",
        )

    # --- Target bot check ---

    if input_.target_bot != CANARY_BOT_ID:
        blocked.append(
            f"non_canary_target: {input_.target_bot!r} is not "
            f"{CANARY_BOT_ID!r}"
        )

    # --- Artifact verification ---

    for path_str, label in [
        (input_.overlay_path, "overlay"),
        (input_.rollback_plan_path, "rollback_plan"),
        (input_.audit_path, "audit"),
        (input_.measurement_start_plan_path, "measurement_start_plan"),
    ]:
        ok, reason = _verify_file_exists(path_str, label)
        if not ok:
            blocked.append(reason)

    # --- Overlay hash check ---

    if input_.overlay_path and input_.overlay_sha256:
        hash_ok, hash_reason = _verify_overlay_hash(
            input_.overlay_path, input_.overlay_sha256,
        )
        if not hash_ok:
            blocked.append(hash_reason)
    elif not input_.overlay_sha256:
        blocked.append("overlay_sha_empty: overlay SHA-256 is empty")

    # --- Safety gates ---

    dry_ok, dry_reason = _verify_dry_run(input_.pre_apply_config)
    if not dry_ok:
        blocked.append(dry_reason)

    ks_ok, ks_reason = _verify_kill_switch(input_.kill_switch_mode)
    if not ks_ok:
        blocked.append(ks_reason)

    rg_ok, rg_reason = _verify_riskguard(input_.riskguard_status)
    if not rg_ok:
        blocked.append(rg_reason)

    # --- Blocked check ---

    if blocked:
        return RuntimeCeremonyResult(
            status="CEREMONY_BLOCKED",
            change_id=input_.change_id,
            candidate_id=input_.candidate_id,
            target_bot=input_.target_bot,
            restart_plan_ready=False,
            runtime_status="BLOCKED",
            runtime_proof_status="NOT_RUN",
            t0_measurement_active=False,
            blocked_reasons=tuple(blocked),
            restart_plan=None,
            runtime_result=None,
            next_step="Review blocked reasons, fix before retrying ceremony.",
        )

    # --- Build restart plan ---

    overlay_path_obj = Path(input_.overlay_path)
    restart_result: RestartPlanResult = plan_canary_restart_with_overlay(
        bot_id=input_.target_bot,
        overlay_path=overlay_path_obj,
        current_command=input_.current_command,
        expected_parameter=input_.expected_parameter,
        expected_value=input_.expected_value,
        pre_apply_config=input_.pre_apply_config,
        canary_user_data=canary_user_data,
    )

    restart_plan_dict: dict[str, object] | None = None
    if restart_result.ready and restart_result.plan is not None:
        restart_plan_dict = restart_result.plan.to_dict()

    if not restart_result.ready:
        return RuntimeCeremonyResult(
            status="CEREMONY_BLOCKED",
            change_id=input_.change_id,
            candidate_id=input_.candidate_id,
            target_bot=input_.target_bot,
            restart_plan_ready=False,
            runtime_status="BLOCKED",
            runtime_proof_status="NOT_RUN",
            t0_measurement_active=False,
            blocked_reasons=restart_result.blocked_reasons,
            restart_plan=None,
            runtime_result=None,
            next_step=(
                "Restart plan failed. Review blocked reasons from "
                "plan_canary_restart_with_overlay."
            ),
        )

    # --- Without runtime execution ---

    if not execute_runtime:
        return RuntimeCeremonyResult(
            status="CEREMONY_READY",
            change_id=input_.change_id,
            candidate_id=input_.candidate_id,
            target_bot=input_.target_bot,
            restart_plan_ready=True,
            runtime_status="NOT_EXECUTED",
            runtime_proof_status="NOT_RUN",
            t0_measurement_active=False,
            blocked_reasons=(),
            restart_plan=restart_plan_dict,
            runtime_result=None,
            next_step=(
                "All artifacts verified, restart plan ready. "
                "Set execute_runtime=True to execute the canary runtime action."
            ),
        )

    # --- Runtime execution (AUTONOMOUS_DRY_RUN only, no L3 token) ---

    # Build overlay payload from file
    overlay_payload: dict[str, object] = {}
    with contextlib.suppress(json.JSONDecodeError, OSError):
        overlay_payload = json.loads(overlay_path_obj.read_text())

    # Check restart gate
    gate_result = check_restart_gate(
        restart_result.plan,
        overlay_payload=overlay_payload,
        pre_apply_config=input_.pre_apply_config,
        execution_enabled=True,
        apply_mode=input_.apply_mode,
    )

    if not gate_result.ready:
        return RuntimeCeremonyResult(
            status="CEREMONY_BLOCKED",
            change_id=input_.change_id,
            candidate_id=input_.candidate_id,
            target_bot=input_.target_bot,
            restart_plan_ready=True,
            runtime_status="BLOCKED",
            runtime_proof_status="NOT_RUN",
            t0_measurement_active=False,
            blocked_reasons=gate_result.blocked_reasons,
            restart_plan=restart_plan_dict,
            runtime_result=None,
            next_step="Restart gate failed. Review blocked reasons.",
        )

    # Build recreate plan (restart_result.plan is guaranteed non-None when ready)
    assert restart_result.plan is not None, "plan must exist when ready"
    recreate_plan: CanaryRecreatePlan = build_canary_recreate_plan(
        restart_result.plan, gate_result,
    )

    # Run the canary restart via runtime executor
    # In AUTONOMOUS_DRY_RUN mode: execute=True, apply_mode bypasses token gate
    runtime_result: RuntimeExecutionResult = run_canary_restart_with_overlay(
        recreate_plan=recreate_plan,
        pre_apply_config=input_.pre_apply_config,
        overlay_payload=overlay_payload,
        execute=True,
        compose_output_dir=compose_output_dir,
        docker_available=docker_available,
        apply_mode=input_.apply_mode,
    )

    runtime_result_dict = runtime_result.to_dict()

    # Determine ceremony status from runtime result
    if runtime_result.status == "EXECUTED_GREEN":
        ceremony_status: str = "CEREMONY_EXECUTED_GREEN"
        runtime_proof_status = "GREEN"
    elif runtime_result.status == "EXECUTED_YELLOW":
        ceremony_status = "CEREMONY_EXECUTED_YELLOW"
        runtime_proof_status = "YELLOW"
    elif runtime_result.status == "EXECUTED_RED":
        ceremony_status = "CEREMONY_EXECUTED_RED"
        runtime_proof_status = "RED"
    else:
        ceremony_status = "CEREMONY_RUNTIME_NOT_EXECUTED"
        runtime_proof_status = "NOT_RUN"

    # Write T0 activation record only for GREEN proof
    t0_active = False
    if ceremony_status == "CEREMONY_EXECUTED_GREEN":
        _write_t0_activation_record(
            change_id=input_.change_id,
            candidate_id=input_.candidate_id,
            target_bot=input_.target_bot,
            runtime_status=ceremony_status,
            runtime_proof_status=runtime_proof_status,
            t0_dir=resolved_t0_dir,
        )
        t0_active = True

    return RuntimeCeremonyResult(
        status=ceremony_status,
        change_id=input_.change_id,
        candidate_id=input_.candidate_id,
        target_bot=input_.target_bot,
        restart_plan_ready=True,
        runtime_status=runtime_result.status,
        runtime_proof_status=runtime_proof_status,
        t0_measurement_active=t0_active,
        blocked_reasons=(),
        restart_plan=restart_plan_dict,
        runtime_result=runtime_result_dict,
        next_step=(
            f"Runtime ceremony {ceremony_status}. "
            f"Proof status: {runtime_proof_status}. "
            f"{'T0 measurement active.' if t0_active else 'No T0 activation.'}"
        ),
    )
