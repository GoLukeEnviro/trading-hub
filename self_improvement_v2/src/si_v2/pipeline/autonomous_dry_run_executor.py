"""SI-v2 Phase 6B — Autonomous Dry-Run Executor.

Connects AUTO_DRY_RUN_APPROVED policy decisions to controlled canary
dry-run apply artifacts: overlay, rollback plan, audit event, and
measurement start plan.

This module does NOT execute external runtime actions or scheduler changes.
It prepares the artifacts so a future runtime ceremony
can apply them.

Safety invariants
-----------------
- Canary-only: target_bot must be ``freqtrade-freqforge-canary``.
- dry_run=true required.
- RiskGuard PASS required.
- Kill Switch NORMAL required.
- Allowlist-compatible candidate required.
- Missing evidence blocks.
- Audit must be written before artifacts are considered valid.
- No live trading.
- No runtime execution in this module.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Literal

from si_v2.apply_actuator.controlled_apply_actuator import (
    create_rollback_plan,
    write_overlay_file,
)
from si_v2.pipeline.candidate_to_apply import (
    CandidateApplyInput,
    CandidatePipelineResult,
    candidate_to_apply_pipeline,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_STATE_DIR: Final[Path] = Path(
    "/opt/data/profiles/orchestrator/state/si_v2_controlled_apply"
)

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AutonomousDryRunExecutorInput:
    """All inputs needed for the autonomous dry-run executor.

    Every field must be populated from real runtime evidence — no mocked,
    simulated, or hardcoded values.
    """

    candidate: CandidateApplyInput
    """The candidate to apply."""

    pre_apply_config: dict[str, object]
    """Pre-apply config dict (must contain ``dry_run``)."""

    kill_switch_mode: str
    """Real kill switch mode from runtime evidence."""

    riskguard_status: str
    """Real RiskGuard status from runtime evidence."""

    allowlist_compatible: bool
    """Real allowlist compatibility from evidence."""

    active_measurement_candidate_id: str | None = None
    """Currently active measurement candidate ID, if any."""

    evidence_refs: tuple[str, ...] = ()
    """References to evidence artifacts (reports, cycle IDs).

    Must not be empty for autonomous dry-run apply.
    """

    change_id: str = ""
    """Unique change identifier for this apply attempt.

    Must not be empty.
    """

    source_cycle: str = ""
    """Source cycle ID that produced this candidate."""


@dataclass(frozen=True)
class AutonomousDryRunExecutorResult:
    """Structured result from the autonomous dry-run executor."""

    status: Literal[
        "EXECUTOR_READY",
        "EXECUTOR_BLOCKED",
        "EXECUTOR_DRY_RUN_APPLY_PREPARED",
        "EXECUTOR_RUNTIME_ACTION_NOT_ENABLED",
    ]
    change_id: str
    candidate_id: str
    target_bot: str
    policy_status: str
    overlay_path: str
    overlay_sha256: str
    rollback_plan_path: str
    audit_path: str
    runtime_action_required: bool
    measurement_window_required: bool
    blocked_reasons: tuple[str, ...]
    next_step: str

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "change_id": self.change_id,
            "candidate_id": self.candidate_id,
            "target_bot": self.target_bot,
            "policy_status": self.policy_status,
            "overlay_path": self.overlay_path,
            "overlay_sha256": self.overlay_sha256,
            "rollback_plan_path": self.rollback_plan_path,
            "audit_path": self.audit_path,
            "runtime_action_required": self.runtime_action_required,
            "measurement_window_required": self.measurement_window_required,
            "blocked_reasons": list(self.blocked_reasons),
            "next_step": self.next_step,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_audit_event(
    event: dict[str, object],
    audit_dir: Path,
) -> str:
    """Write an append-only JSONL audit event.

    Returns the path to the audit file.
    """
    audit_dir.mkdir(parents=True, exist_ok=True)
    audit_path = audit_dir / "autonomous_dry_run_executor.jsonl"
    with open(audit_path, "a") as f:
        f.write(json.dumps(event, default=str) + "\n")
    return str(audit_path)


def _write_measurement_start_plan(
    change_id: str,
    candidate_id: str,
    target_bot: str,
    overlay_sha256: str,
    baseline_config_snapshot: dict[str, object],
    plan_dir: Path,
) -> str:
    """Write a measurement start plan file.

    Returns the path to the plan file.
    """
    plan_dir.mkdir(parents=True, exist_ok=True)
    plan = {
        "change_id": change_id,
        "candidate_id": candidate_id,
        "target_bot": target_bot,
        "t0_timestamp_utc": datetime.now(UTC).isoformat(),
        "overlay_sha256": overlay_sha256,
        "baseline_config_snapshot": {
            k: v for k, v in baseline_config_snapshot.items()
            if k in ("dry_run", "max_open_trades", "stoploss_pct",
                     "take_profit_pct", "rsi_period", "stake_factor",
                     "cooldown_candles")
        },
        "expected_measurement_policy": "canary_vs_control_comparison",
        "next_required_component": "autonomous_measurement_watcher",
    }
    filename = f"measurement_start_{change_id[:16]}.json"
    path = plan_dir / filename
    tmp = path.with_suffix(f".json.tmp.{id(plan)}")
    tmp.write_text(json.dumps(plan, indent=2))
    tmp.replace(path)
    return str(path)


# ---------------------------------------------------------------------------
# Main executor function
# ---------------------------------------------------------------------------


def prepare_autonomous_dry_run_apply(
    input_: AutonomousDryRunExecutorInput,
    *,
    execute_runtime: bool = False,
    state_dir: Path | None = None,
    overlay_dir: Path | None = None,
    plan_dir: Path | None = None,
    audit_dir: Path | None = None,
) -> AutonomousDryRunExecutorResult:
    """Prepare an autonomous dry-run apply.

    With ``execute_runtime=False`` (default):
    - Evaluates the candidate through the policy pipeline.
    - If approved, writes overlay, rollback plan, audit event, and
      measurement start plan.
    - Does NOT execute any external runtime action or scheduler change.

    With ``execute_runtime=True``:
    - Returns ``EXECUTOR_RUNTIME_ACTION_NOT_ENABLED`` in Phase 6B.
    - A future runtime ceremony task can enable this path.

    Args:
        input_: All inputs for the executor.
        execute_runtime: If True, attempt runtime execution (blocked in Phase 6B).
        state_dir: Override for state directory.
        overlay_dir: Override for overlay output directory.
        plan_dir: Override for rollback/measurement plan directory.
        audit_dir: Override for audit log directory.

    Returns:
        ``AutonomousDryRunExecutorResult`` with status and artifact paths.
    """
    resolved_state_dir = state_dir or DEFAULT_STATE_DIR
    resolved_overlay_dir = overlay_dir or (resolved_state_dir / "overlays")
    resolved_plan_dir = plan_dir or (resolved_state_dir / "rollback_plans")
    resolved_audit_dir = audit_dir or (resolved_state_dir / "audit")

    now_utc = datetime.now(UTC).isoformat()

    # --- Input validation ---

    if not input_.change_id:
        return AutonomousDryRunExecutorResult(
            status="EXECUTOR_BLOCKED",
            change_id="",
            candidate_id=input_.candidate.candidate_id,
            target_bot=input_.candidate.target_bot,
            policy_status="INPUT_VALIDATION_FAILED",
            overlay_path="",
            overlay_sha256="",
            rollback_plan_path="",
            audit_path="",
            runtime_action_required=False,
            measurement_window_required=False,
            blocked_reasons=("change_id_required: change_id must not be empty",),
            next_step="Provide a non-empty change_id.",
        )

    if not input_.evidence_refs:
        return AutonomousDryRunExecutorResult(
            status="EXECUTOR_BLOCKED",
            change_id=input_.change_id,
            candidate_id=input_.candidate.candidate_id,
            target_bot=input_.candidate.target_bot,
            policy_status="INPUT_VALIDATION_FAILED",
            overlay_path="",
            overlay_sha256="",
            rollback_plan_path="",
            audit_path="",
            runtime_action_required=False,
            measurement_window_required=False,
            blocked_reasons=(
                "evidence_refs_required: evidence_refs must not be empty "
                "for autonomous dry-run apply",
            ),
            next_step="Provide evidence references from the active cycle.",
        )

    # --- Policy evaluation ---

    pipeline_result: CandidatePipelineResult = candidate_to_apply_pipeline(
        candidate=input_.candidate,
        pre_apply_config=input_.pre_apply_config,
        active_measurement_candidate_id=input_.active_measurement_candidate_id,
        kill_switch_mode=input_.kill_switch_mode,
        riskguard_status=input_.riskguard_status,
        allowlist_compatible=input_.allowlist_compatible,
    )

    policy_status = pipeline_result.decision.status
    allowed_statuses = ("READY_FOR_AUTONOMOUS_DRY_RUN_APPLY", "AUTO_DRY_RUN_APPROVED")

    if pipeline_result.decision.status not in allowed_statuses:
        return AutonomousDryRunExecutorResult(
            status="EXECUTOR_BLOCKED",
            change_id=input_.change_id,
            candidate_id=input_.candidate.candidate_id,
            target_bot=input_.candidate.target_bot,
            policy_status=policy_status,
            overlay_path="",
            overlay_sha256="",
            rollback_plan_path="",
            audit_path="",
            runtime_action_required=False,
            measurement_window_required=False,
            blocked_reasons=pipeline_result.decision.blocked_reasons,
            next_step=pipeline_result.decision.next_step,
        )

    # --- execute_runtime gate ---

    if execute_runtime:
        return AutonomousDryRunExecutorResult(
            status="EXECUTOR_RUNTIME_ACTION_NOT_ENABLED",
            change_id=input_.change_id,
            candidate_id=input_.candidate.candidate_id,
            target_bot=input_.candidate.target_bot,
            policy_status=policy_status,
            overlay_path="",
            overlay_sha256="",
            rollback_plan_path="",
            audit_path="",
            runtime_action_required=True,
            measurement_window_required=True,
            blocked_reasons=(
                "runtime_action_not_enabled_in_phase_6b: "
                "execute_runtime=True is not implemented. "
                "Requires separate runtime ceremony task.",
            ),
            next_step="Wire runtime execution in a separate ceremony task.",
        )

    # --- Build parameter overlay ---

    overlay: dict[str, int | float] = {}
    if (input_.candidate.parameter
            and input_.candidate.proposed_value is not None
            and isinstance(input_.candidate.proposed_value, (int, float))):
        overlay = {input_.candidate.parameter: input_.candidate.proposed_value}  # type: ignore[assignment]

    # --- Write overlay ---

    overlay_path, overlay_sha256 = write_overlay_file(
        candidate_sha=input_.candidate.candidate_id,
        overlay=overlay,
        overlay_dir=resolved_overlay_dir,
    )

    # --- Write rollback plan ---

    rollback_path = create_rollback_plan(
        candidate_sha=input_.candidate.candidate_id,
        bot_id=input_.candidate.target_bot,
        overlay_path=overlay_path,
        pre_apply_config=dict(input_.pre_apply_config),
        plan_dir=resolved_plan_dir,
    )

    # --- Write audit event ---

    audit_event = {
        "event": "autonomous_dry_run_apply_prepared",
        "change_id": input_.change_id,
        "candidate_id": input_.candidate.candidate_id,
        "target_bot": input_.candidate.target_bot,
        "policy_status": policy_status,
        "overlay_path": overlay_path,
        "rollback_plan_path": rollback_path,
        "evidence_refs": list(input_.evidence_refs),
        "source_cycle": input_.source_cycle,
        "timestamp_utc": now_utc,
    }
    audit_path = _write_audit_event(audit_event, resolved_audit_dir)

    # --- Write measurement start plan ---

    _write_measurement_start_plan(
        change_id=input_.change_id,
        candidate_id=input_.candidate.candidate_id,
        target_bot=input_.candidate.target_bot,
        overlay_sha256=overlay_sha256,
        baseline_config_snapshot=dict(input_.pre_apply_config),
        plan_dir=resolved_plan_dir,
    )

    return AutonomousDryRunExecutorResult(
        status="EXECUTOR_DRY_RUN_APPLY_PREPARED",
        change_id=input_.change_id,
        candidate_id=input_.candidate.candidate_id,
        target_bot=input_.candidate.target_bot,
        policy_status=policy_status,
        overlay_path=overlay_path,
        overlay_sha256=overlay_sha256,
        rollback_plan_path=rollback_path,
        audit_path=audit_path,
        runtime_action_required=True,
        measurement_window_required=True,
        blocked_reasons=(),
        next_step=(
            "All artifacts prepared. Next: runtime ceremony to apply overlay, "
            "restart canary, and start measurement window."
        ),
    )
