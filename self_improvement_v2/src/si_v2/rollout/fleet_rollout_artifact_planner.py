"""SI-v2 Phase 9B — Fleet Rollout Artifact Planner.

Read-only planner that consumes Phase-9A rollout policy artifacts and
generates concrete, audit-ready per-target rollout plan artifacts:

- Planned overlay copy (verification artifact, not runtime write)
- Pre-apply snapshot plan (describes what Phase 9C must snapshot)
- Rollback plan (describes how Phase 9C can revert)
- Fleet rollout plan (aggregates all per-target plans)

This module is **read-only**. It does NOT:
- Execute any runtime mutation (restart, Docker, compose)
- Apply overlays to fleet bots
- Write to bot config paths or user_data directories
- Enable schedulers or watchers
- Execute rollback
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TargetBotRuntimeSpec:
    """Runtime specification for a target bot.

    Describes the bot's current configuration so the planner can generate
    accurate plan artifacts without touching runtime.
    """

    bot_id: str
    role: Literal["control", "experimental", "freqai"]
    dry_run: bool
    config_path: str
    user_data_dir: str
    current_command: tuple[str, ...]


@dataclass(frozen=True)
class FleetRolloutPlannerInput:
    """All inputs for the fleet rollout artifact planner."""

    rollout_policy_path: str
    """Path to the Phase-9A rollout_policy.json artifact."""

    target_runtime_specs: tuple[TargetBotRuntimeSpec, ...]
    """Runtime specs for each candidate target bot."""

    source_overlay_path: str
    """Path to the source overlay JSON (from the canary apply)."""

    source_overlay_sha256: str
    """Expected SHA-256 hash of the source overlay file."""

    expected_parameter: str
    """The parameter being rolled out (e.g. ``max_open_trades``)."""

    expected_value: int | float
    """The expected value of the parameter in the overlay."""

    require_dry_run: bool = True
    """If True, all target bots must have dry_run=True."""


@dataclass(frozen=True)
class TargetRolloutPlan:
    """A single target bot's rollout plan."""

    target_bot: str
    role: str
    config_path: str
    user_data_dir: str
    overlay_path: str
    overlay_sha256: str
    expected_parameter: str
    expected_value: int | float
    pre_apply_snapshot_path: str
    rollback_plan_path: str
    validation_checks: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "target_bot": self.target_bot,
            "role": self.role,
            "config_path": self.config_path,
            "user_data_dir": self.user_data_dir,
            "overlay_path": self.overlay_path,
            "overlay_sha256": self.overlay_sha256,
            "expected_parameter": self.expected_parameter,
            "expected_value": self.expected_value,
            "pre_apply_snapshot_path": self.pre_apply_snapshot_path,
            "rollback_plan_path": self.rollback_plan_path,
            "validation_checks": list(self.validation_checks),
        }


@dataclass(frozen=True)
class FleetRolloutPlannerResult:
    """Structured result from the fleet rollout artifact planner."""

    status: Literal[
        "ROLLOUT_PLAN_READY",
        "ROLLOUT_PLAN_BLOCKED",
        "ROLLOUT_PLAN_NOT_ELIGIBLE",
    ]
    change_id: str
    candidate_id: str
    source_bot: str
    target_plans: tuple[TargetRolloutPlan, ...]
    blocked_reasons: tuple[str, ...]
    rollout_plan_path: str
    next_step: str

    def to_dict(self) -> dict[str, object]:
        return {
            "event": "fleet_rollout_artifact_plan",
            "status": self.status,
            "change_id": self.change_id,
            "candidate_id": self.candidate_id,
            "source_bot": self.source_bot,
            "target_plans": [p.to_dict() for p in self.target_plans],
            "blocked_reasons": list(self.blocked_reasons),
            "rollout_plan_path": self.rollout_plan_path,
            "next_step": self.next_step,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALIDATION_CHECKS: tuple[str, ...] = (
    "dry_run_true_required",
    "overlay_hash_match_required",
    "config_path_required",
    "rollback_plan_required",
)


def _sha256_file(path: Path) -> str:
    """Compute SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _atomic_write_json(path: Path, data: dict[str, object]) -> None:
    """Write JSON atomically via temp file + replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp.{abs(hash(str(data)))}")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True))
    tmp.replace(path)


# ---------------------------------------------------------------------------
# Rollout policy reader
# ---------------------------------------------------------------------------


def _read_rollout_policy(path: str) -> dict[str, object] | None:
    """Read and parse a rollout policy JSON file.

    Returns None if the file cannot be read or parsed.
    """
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
# Main planner
# ---------------------------------------------------------------------------


def build_fleet_rollout_artifacts(
    input_: FleetRolloutPlannerInput,
    *,
    rollout_plan_dir: Path | None = None,
    now_utc: str | None = None,
) -> FleetRolloutPlannerResult:
    """Build fleet rollout plan artifacts from a Phase-9A rollout policy.

    This function is PURE and READ-ONLY. It does not:
    - Execute runtime actions
    - Apply overlays to bot config paths
    - Touch Docker or Docker Compose
    - Enable schedulers

    Args:
        input_: All inputs for artifact planning.
        rollout_plan_dir: Override for artifact output directory.
        now_utc: Override for current UTC time (testing).

    Returns:
        ``FleetRolloutPlannerResult`` with per-target plans and status.
    """
    resolved_now = now_utc or datetime.now(UTC).isoformat()
    resolved_dir = rollout_plan_dir or Path("var/si_v2/fleet_rollout_plans")

    blocked: list[str] = []

    # ------------------------------------------------------------------
    # Step 1: Read rollout policy
    # ------------------------------------------------------------------

    policy = _read_rollout_policy(input_.rollout_policy_path)

    if policy is None:
        return FleetRolloutPlannerResult(
            status="ROLLOUT_PLAN_BLOCKED",
            change_id="",
            candidate_id="",
            source_bot="",
            target_plans=(),
            blocked_reasons=(
                f"rollout_policy_not_readable: {input_.rollout_policy_path}",
            ),
            rollout_plan_path="",
            next_step="Provide a valid rollout policy path and retry.",
        )

    change_id = str(policy.get("change_id", ""))
    candidate_id = str(policy.get("candidate_id", ""))
    source_bot = str(policy.get("source_bot", ""))
    selected_targets_raw = policy.get("selected_targets", [])
    selected_targets: list[str] = (
        [str(t) for t in selected_targets_raw]
        if isinstance(selected_targets_raw, list)
        else []
    )

    # ------------------------------------------------------------------
    # Step 2: Validate rollout policy
    # ------------------------------------------------------------------

    event = policy.get("event")
    if event != "fleet_rollout_policy_decision":
        blocked.append(
            f"unexpected_event: {event!r} != fleet_rollout_policy_decision"
        )

    policy_status = policy.get("status")
    if policy_status != "PROMOTION_ELIGIBLE":
        blocked.append(
            f"policy_not_eligible: {policy_status!r} != PROMOTION_ELIGIBLE"
        )

    runtime_mutation = policy.get("runtime_mutation")
    if runtime_mutation != "NONE":
        blocked.append(
            f"runtime_mutation_not_none: {runtime_mutation!r}"
        )

    next_component = policy.get("next_required_component")
    if next_component != "fleet_rollout_artifact_planner":
        blocked.append(
            f"wrong_next_component: {next_component!r} != "
            f"fleet_rollout_artifact_planner"
        )

    if not selected_targets:
        blocked.append("empty_selected_targets: no targets in rollout policy")

    if not change_id:
        blocked.append("change_id_missing: rollout policy has no change_id")

    if blocked:
        return FleetRolloutPlannerResult(
            status="ROLLOUT_PLAN_BLOCKED",
            change_id=change_id,
            candidate_id=candidate_id,
            source_bot=source_bot,
            target_plans=(),
            blocked_reasons=tuple(blocked),
            rollout_plan_path="",
            next_step="Review blocked reasons and fix before retrying plan generation.",
        )

    # ------------------------------------------------------------------
    # Step 3: Validate source overlay
    # ------------------------------------------------------------------

    overlay_path = Path(input_.source_overlay_path)
    if not overlay_path.exists():
        return FleetRolloutPlannerResult(
            status="ROLLOUT_PLAN_BLOCKED",
            change_id=change_id,
            candidate_id=candidate_id,
            source_bot=source_bot,
            target_plans=(),
            blocked_reasons=(
                f"source_overlay_missing: {input_.source_overlay_path}",
            ),
            rollout_plan_path="",
            next_step="Provide a valid source overlay path and retry.",
        )

    actual_sha = _sha256_file(overlay_path)
    if actual_sha != input_.source_overlay_sha256:
        return FleetRolloutPlannerResult(
            status="ROLLOUT_PLAN_BLOCKED",
            change_id=change_id,
            candidate_id=candidate_id,
            source_bot=source_bot,
            target_plans=(),
            blocked_reasons=(
                f"overlay_hash_mismatch: expected={input_.source_overlay_sha256} "
                f"actual={actual_sha}",
            ),
            rollout_plan_path="",
            next_step="Verify source overlay integrity and retry.",
        )

    # ------------------------------------------------------------------
    # Step 4: Validate target runtime specs and build plans
    # ------------------------------------------------------------------

    spec_by_bot: dict[str, TargetBotRuntimeSpec] = {
        spec.bot_id: spec for spec in input_.target_runtime_specs
    }

    target_plans: list[TargetRolloutPlan] = []

    for target_id in selected_targets:
        spec = spec_by_bot.get(target_id)
        if spec is None:
            blocked.append(
                f"missing_runtime_spec: no TargetBotRuntimeSpec for {target_id}"
            )
            continue

        if input_.require_dry_run and not spec.dry_run:
            blocked.append(
                f"target_not_dry_run: {target_id} does not have dry_run enabled"
            )
            continue

        if not spec.config_path:
            blocked.append(
                f"empty_config_path: {target_id} has empty config_path"
            )
            continue

        if not spec.user_data_dir:
            blocked.append(
                f"empty_user_data_dir: {target_id} has empty user_data_dir"
            )
            continue

        if not spec.current_command:
            blocked.append(
                f"empty_command: {target_id} has empty current_command"
            )
            continue

        # Check command contains a config reference
        cmd_str = " ".join(spec.current_command)
        if "--config" not in cmd_str and "config" not in cmd_str.lower():
            blocked.append(
                f"command_without_config_reference: {target_id} command "
                f"has no --config reference"
            )
            continue

        # Build per-target plan
        target_dir = resolved_dir / change_id[:24] / "targets" / target_id

        planned_overlay_path = str(target_dir / "planned_overlay.json")
        snapshot_plan_path = str(target_dir / "pre_apply_snapshot_plan.json")
        rollback_plan_path = str(target_dir / "rollback_plan.json")

        plan = TargetRolloutPlan(
            target_bot=target_id,
            role=spec.role,
            config_path=spec.config_path,
            user_data_dir=spec.user_data_dir,
            overlay_path=planned_overlay_path,
            overlay_sha256=input_.source_overlay_sha256,
            expected_parameter=input_.expected_parameter,
            expected_value=input_.expected_value,
            pre_apply_snapshot_path=snapshot_plan_path,
            rollback_plan_path=rollback_plan_path,
            validation_checks=_VALIDATION_CHECKS,
        )
        target_plans.append(plan)

    if blocked or not target_plans:
        return FleetRolloutPlannerResult(
            status="ROLLOUT_PLAN_BLOCKED",
            change_id=change_id,
            candidate_id=candidate_id,
            source_bot=source_bot,
            target_plans=(),
            blocked_reasons=tuple(blocked) if blocked else (
                "no_valid_target_plans: all targets failed validation",
            ),
            rollout_plan_path="",
            next_step="Review target validation failures and fix before retrying.",
        )

    # ------------------------------------------------------------------
    # Step 5: Write per-target artifacts
    # ------------------------------------------------------------------

    try:
        # Read source overlay content for planned copy
        overlay_content = json.loads(overlay_path.read_text())

        for plan in target_plans:
            target_dir = Path(plan.overlay_path).parent

            # 5a. Planned overlay copy
            planned_overlay = {
                "event": "planned_overlay_copy",
                "target_bot": plan.target_bot,
                "source_overlay_sha256": plan.overlay_sha256,
                "expected_parameter": plan.expected_parameter,
                "expected_value": plan.expected_value,
                "overlay_content": overlay_content,
                "runtime_mutation": "NONE",
                "created_at_utc": resolved_now,
            }
            _atomic_write_json(target_dir / "planned_overlay.json", planned_overlay)

            # 5b. Pre-apply snapshot plan
            snapshot_plan = {
                "event": "pre_apply_snapshot_plan",
                "target_bot": plan.target_bot,
                "config_path": plan.config_path,
                "user_data_dir": plan.user_data_dir,
                "what_to_snapshot": [
                    "config_json",
                    "strategy_state",
                    "trade_history",
                ],
                "snapshot_instruction": (
                    "Phase 9C must snapshot the current config JSON and "
                    "strategy state before applying the overlay."
                ),
                "runtime_mutation": "NONE",
                "created_at_utc": resolved_now,
            }
            _atomic_write_json(
                target_dir / "pre_apply_snapshot_plan.json", snapshot_plan,
            )

            # 5c. Rollback plan
            rollback_plan = {
                "event": "rollback_plan",
                "target_bot": plan.target_bot,
                "config_path": plan.config_path,
                "rollback_instruction": (
                    "Phase 9C must restore the pre-apply config from "
                    "snapshot and remove the overlay --config reference "
                    "from the command."
                ),
                "rollback_command_prefix": list(spec_by_bot[plan.target_bot].current_command),
                "runtime_mutation": "NONE",
                "created_at_utc": resolved_now,
            }
            _atomic_write_json(target_dir / "rollback_plan.json", rollback_plan)

        # 5d. Fleet rollout plan (aggregate)
        fleet_plan = {
            "event": "fleet_rollout_artifact_plan",
            "change_id": change_id,
            "candidate_id": candidate_id,
            "source_bot": source_bot,
            "status": "ROLLOUT_PLAN_READY",
            "selected_targets": selected_targets,
            "target_plans": [p.to_dict() for p in target_plans],
            "runtime_mutation": "NONE",
            "next_required_component": "fleet_rollout_runtime_ceremony",
            "created_at_utc": resolved_now,
        }
        plan_dir = resolved_dir / change_id[:24]
        plan_path = plan_dir / "fleet_rollout_plan.json"
        _atomic_write_json(plan_path, fleet_plan)

    except OSError as e:
        return FleetRolloutPlannerResult(
            status="ROLLOUT_PLAN_BLOCKED",
            change_id=change_id,
            candidate_id=candidate_id,
            source_bot=source_bot,
            target_plans=(),
            blocked_reasons=(f"artifact_write_error: {e}",),
            rollout_plan_path="",
            next_step="Fix artifact write path and retry.",
        )

    return FleetRolloutPlannerResult(
        status="ROLLOUT_PLAN_READY",
        change_id=change_id,
        candidate_id=candidate_id,
        source_bot=source_bot,
        target_plans=tuple(target_plans),
        blocked_reasons=(),
        rollout_plan_path=str(plan_path),
        next_step=(
            f"ROLLOUT_PLAN_READY for candidate {candidate_id}. "
            f"Targets: {selected_targets}. "
            f"Proceed to Phase 9C Fleet Rollout Runtime Ceremony."
        ),
    )
