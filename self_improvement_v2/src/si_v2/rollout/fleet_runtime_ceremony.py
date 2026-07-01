"""SI-v2 Phase 9C — Controlled Fleet Runtime Ceremony.

Consumes Phase-9B fleet rollout plan artifacts and executes per-target
controlled dry-run-only runtime ceremonies through a mockable runtime executor.

This module is **dry-run-only**. It does NOT:
- Enable live trading
- Enable schedulers or watchers
- Execute uncontrolled fleet apply
- Modify bot configs outside the ceremony path
- Execute runtime actions without explicit ``execute_runtime=True``
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FleetRuntimeCeremonyInput:
    """All inputs for the fleet runtime ceremony.

    Attributes:
        fleet_rollout_plan_path: Path to the Phase-9B fleet_rollout_plan.json.
        execute_runtime: If True, actually execute runtime actions through
            the runtime_executor. If False (default), only validate and
            prepare preflight artifacts.
        require_dry_run: If True, all target plans must reference dry-run bots.
    """

    fleet_rollout_plan_path: str
    execute_runtime: bool = False
    require_dry_run: bool = True


@dataclass(frozen=True)
class TargetRuntimeCeremonyResult:
    """Result of a single target bot's runtime ceremony."""

    target_bot: str
    status: str
    pre_apply_snapshot_path: str
    audit_event_path: str
    runtime_effect_proof_path: str
    measurement_start_path: str
    blocked_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "target_bot": self.target_bot,
            "status": self.status,
            "pre_apply_snapshot_path": self.pre_apply_snapshot_path,
            "audit_event_path": self.audit_event_path,
            "runtime_effect_proof_path": self.runtime_effect_proof_path,
            "measurement_start_path": self.measurement_start_path,
            "blocked_reasons": list(self.blocked_reasons),
        }


@dataclass(frozen=True)
class FleetRuntimeCeremonyResult:
    """Aggregate result of the fleet runtime ceremony."""

    status: Literal[
        "FLEET_CEREMONY_READY",
        "FLEET_CEREMONY_EXECUTED_GREEN",
        "FLEET_CEREMONY_EXECUTED_YELLOW",
        "FLEET_CEREMONY_BLOCKED",
    ]
    change_id: str
    candidate_id: str
    target_results: tuple[TargetRuntimeCeremonyResult, ...]
    blocked_reasons: tuple[str, ...]
    next_step: str

    def to_dict(self) -> dict[str, object]:
        return {
            "event": "fleet_runtime_ceremony_result",
            "status": self.status,
            "change_id": self.change_id,
            "candidate_id": self.candidate_id,
            "target_results": [r.to_dict() for r in self.target_results],
            "blocked_reasons": list(self.blocked_reasons),
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
# Main ceremony function
# ---------------------------------------------------------------------------


def run_fleet_runtime_ceremony(
    input_: FleetRuntimeCeremonyInput,
    *,
    ceremony_output_dir: Path | None = None,
    runtime_executor: object | None = None,
    now_utc: str | None = None,
) -> FleetRuntimeCeremonyResult:
    """Run the controlled fleet runtime ceremony.

    Args:
        input_: Ceremony input with plan path and execution flags.
        ceremony_output_dir: Override for ceremony artifact output directory.
        runtime_executor: Callable for actual runtime actions. Must be
            provided when ``execute_runtime=True``. In tests, this is mocked.
        now_utc: Override for current UTC time (testing).

    Returns:
        ``FleetRuntimeCeremonyResult`` with per-target ceremony results.
    """
    resolved_now = now_utc or datetime.now(UTC).isoformat()
    resolved_dir = ceremony_output_dir or Path("var/si_v2/fleet_ceremony")

    blocked: list[str] = []

    # ------------------------------------------------------------------
    # Step 1: Read fleet rollout plan
    # ------------------------------------------------------------------

    plan = _read_json(input_.fleet_rollout_plan_path)

    if plan is None:
        return FleetRuntimeCeremonyResult(
            status="FLEET_CEREMONY_BLOCKED",
            change_id="",
            candidate_id="",
            target_results=(),
            blocked_reasons=(
                f"fleet_rollout_plan_not_readable: "
                f"{input_.fleet_rollout_plan_path}",
            ),
            next_step="Provide a valid fleet rollout plan path and retry.",
        )

    change_id = str(plan.get("change_id", ""))
    candidate_id = str(plan.get("candidate_id", ""))
    selected_targets_raw = plan.get("selected_targets", [])
    selected_targets: list[str] = (
        [str(t) for t in selected_targets_raw]
        if isinstance(selected_targets_raw, list)
        else []
    )

    # ------------------------------------------------------------------
    # Step 2: Validate fleet rollout plan
    # ------------------------------------------------------------------

    event = plan.get("event")
    if event != "fleet_rollout_artifact_plan":
        blocked.append(
            f"unexpected_event: {event!r} != fleet_rollout_artifact_plan"
        )

    plan_status = plan.get("status")
    if plan_status != "ROLLOUT_PLAN_READY":
        blocked.append(
            f"plan_not_ready: {plan_status!r} != ROLLOUT_PLAN_READY"
        )

    runtime_mutation = plan.get("runtime_mutation")
    if runtime_mutation != "NONE":
        blocked.append(
            f"runtime_mutation_not_none: {runtime_mutation!r}"
        )

    next_component = plan.get("next_required_component")
    if next_component != "fleet_rollout_runtime_ceremony":
        blocked.append(
            f"wrong_next_component: {next_component!r} != "
            f"fleet_rollout_runtime_ceremony"
        )

    target_plans_raw = plan.get("target_plans", [])
    if not target_plans_raw or not isinstance(target_plans_raw, list):
        blocked.append("empty_target_plans: no target plans in rollout plan")

    if not change_id:
        blocked.append("change_id_missing: rollout plan has no change_id")

    if blocked:
        return FleetRuntimeCeremonyResult(
            status="FLEET_CEREMONY_BLOCKED",
            change_id=change_id,
            candidate_id=candidate_id,
            target_results=(),
            blocked_reasons=tuple(blocked),
            next_step="Review blocked reasons and fix before retrying ceremony.",
        )

    # ------------------------------------------------------------------
    # Step 3: Validate each target plan
    # ------------------------------------------------------------------

    target_results: list[TargetRuntimeCeremonyResult] = []
    ceremony_blocked: list[str] = []
    target_failures: list[str] = []

    for target_plan in target_plans_raw:
        if not isinstance(target_plan, dict):
            ceremony_blocked.append("invalid_target_plan: not a dict")
            continue

        target_bot = str(target_plan.get("target_bot", ""))
        if not target_bot:
            ceremony_blocked.append("target_bot_missing: target plan has no target_bot")
            continue

        # Check canary
        if "canary" in target_bot.lower():
            ceremony_blocked.append(
                f"canary_target: {target_bot} is a canary and cannot be a "
                f"runtime ceremony target"
            )
            continue

        # Check target is in selected_targets
        if target_bot not in selected_targets:
            ceremony_blocked.append(
                f"target_not_selected: {target_bot} not in selected_targets"
            )
            continue

        # Check overlay
        overlay_path = str(target_plan.get("overlay_path", ""))
        if not overlay_path:
            ceremony_blocked.append(
                f"missing_overlay: {target_bot} has no overlay_path"
            )
            continue

        overlay_sha256 = str(target_plan.get("overlay_sha256", ""))
        if not overlay_sha256:
            ceremony_blocked.append(
                f"missing_overlay_hash: {target_bot} has no overlay_sha256"
            )
            continue

        # Verify overlay file exists and hash matches
        overlay_file = Path(overlay_path)
        if not overlay_file.exists():
            ceremony_blocked.append(
                f"overlay_file_missing: {target_bot} overlay not found at "
                f"{overlay_path}"
            )
            continue

        import hashlib
        actual_sha = hashlib.sha256(overlay_file.read_bytes()).hexdigest()
        if actual_sha != overlay_sha256:
            ceremony_blocked.append(
                f"overlay_hash_mismatch: {target_bot} expected "
                f"{overlay_sha256} actual {actual_sha}"
            )
            continue

        # Check rollback plan
        rollback_plan_path = str(target_plan.get("rollback_plan_path", ""))
        if not rollback_plan_path:
            ceremony_blocked.append(
                f"missing_rollback_plan: {target_bot} has no rollback_plan_path"
            )
            continue

        # Check snapshot plan
        snapshot_plan_path = str(target_plan.get("pre_apply_snapshot_path", ""))
        if not snapshot_plan_path:
            ceremony_blocked.append(
                f"missing_snapshot_plan: {target_bot} has no "
                f"pre_apply_snapshot_path"
            )
            continue

        # Check config path
        config_path = str(target_plan.get("config_path", ""))
        if not config_path:
            ceremony_blocked.append(
                f"missing_config_path: {target_bot} has no config_path"
            )
            continue

        # Check dry_run requirement
        if input_.require_dry_run:
            validation_checks = target_plan.get("validation_checks", [])
            if isinstance(validation_checks, list):
                checks_str = " ".join(str(c) for c in validation_checks)
                if "dry_run" not in checks_str:
                    ceremony_blocked.append(
                        f"dry_run_not_required: {target_bot} validation_checks "
                        f"do not include dry_run check"
                    )
                    continue

    if ceremony_blocked:
        return FleetRuntimeCeremonyResult(
            status="FLEET_CEREMONY_BLOCKED",
            change_id=change_id,
            candidate_id=candidate_id,
            target_results=(),
            blocked_reasons=tuple(ceremony_blocked),
            next_step="Review target validation failures and fix before retrying.",
        )

    # ------------------------------------------------------------------
    # Step 4: Execute or prepare per-target ceremony
    # ------------------------------------------------------------------

    if input_.execute_runtime:
        # Runtime execution requires a runtime_executor
        if runtime_executor is None:
            return FleetRuntimeCeremonyResult(
                status="FLEET_CEREMONY_BLOCKED",
                change_id=change_id,
                candidate_id=candidate_id,
                target_results=(),
                blocked_reasons=(
                    "runtime_executor_required: execute_runtime=True but "
                    "runtime_executor is None",
                ),
                next_step="Provide a runtime_executor and retry.",
            )

        # Execute per-target ceremony
        for target_plan in target_plans_raw:
            if not isinstance(target_plan, dict):
                continue
            target_bot = str(target_plan.get("target_bot", ""))
            if not target_bot:
                continue

            target_dir = resolved_dir / change_id[:24] / "targets" / target_bot

            pre_apply_snapshot_path = str(
                target_dir / "pre_apply_snapshot.json"
            )
            audit_event_path = str(target_dir / "runtime_apply_audit.json")
            runtime_effect_proof_path = str(
                target_dir / "runtime_effect_proof.json"
            )
            measurement_start_path = str(
                target_dir / "measurement_start_record.json"
            )

            try:
                # 4a. Write pre-apply snapshot
                snapshot = {
                    "event": "pre_apply_snapshot",
                    "target_bot": target_bot,
                    "config_path": target_plan.get("config_path", ""),
                    "snapshot_taken_at_utc": resolved_now,
                    "runtime_mutation": "NONE",
                }
                _atomic_write_json(
                    target_dir / "pre_apply_snapshot.json", snapshot
                )

                # 4b. Execute runtime action via executor
                # The executor is a callable that takes (target_bot, overlay_path)
                # and returns a dict with success/error info.
                executor_result = runtime_executor(target_bot, overlay_path)  # type: ignore[operator]

                # 4c. Write audit event
                audit = {
                    "event": "runtime_apply_audit",
                    "target_bot": target_bot,
                    "overlay_path": overlay_path,
                    "overlay_sha256": overlay_sha256,
                    "executor_status": executor_result.get("status", "unknown"),
                    "executor_detail": executor_result.get("detail", ""),
                    "applied_at_utc": resolved_now,
                    "runtime_mutation": "NONE",
                }
                _atomic_write_json(
                    target_dir / "runtime_apply_audit.json", audit
                )

                # 4d. Write RuntimeEffectProof
                effect_proof = {
                    "event": "runtime_effect_proof",
                    "target_bot": target_bot,
                    "ceremony_status": "EXECUTED",
                    "executor_status": executor_result.get("status", "unknown"),
                    "pre_apply_snapshot": pre_apply_snapshot_path,
                    "audit_event": audit_event_path,
                    "proven_at_utc": resolved_now,
                    "runtime_mutation": "NONE",
                }
                _atomic_write_json(
                    target_dir / "runtime_effect_proof.json", effect_proof
                )

                # 4e. Write measurement start record
                measurement_start = {
                    "event": "measurement_start_record",
                    "target_bot": target_bot,
                    "ceremony_status": "EXECUTED",
                    "measurement_started_at_utc": resolved_now,
                    "expected_parameter": target_plan.get(
                        "expected_parameter", ""
                    ),
                    "expected_value": target_plan.get("expected_value", 0),
                    "runtime_mutation": "NONE",
                }
                _atomic_write_json(
                    target_dir / "measurement_start_record.json",
                    measurement_start,
                )

                target_results.append(
                    TargetRuntimeCeremonyResult(
                        target_bot=target_bot,
                        status="EXECUTED_GREEN",
                        pre_apply_snapshot_path=pre_apply_snapshot_path,
                        audit_event_path=audit_event_path,
                        runtime_effect_proof_path=runtime_effect_proof_path,
                        measurement_start_path=measurement_start_path,
                        blocked_reasons=(),
                    )
                )

            except Exception as e:
                target_failures.append(
                    f"{target_bot}: runtime_executor failed: {e}"
                )
                target_results.append(
                    TargetRuntimeCeremonyResult(
                        target_bot=target_bot,
                        status="EXECUTED_YELLOW",
                        pre_apply_snapshot_path=pre_apply_snapshot_path,
                        audit_event_path=audit_event_path,
                        runtime_effect_proof_path=runtime_effect_proof_path,
                        measurement_start_path=measurement_start_path,
                        blocked_reasons=(
                            f"runtime_executor_failed: {e}",
                        ),
                    )
                )

        if target_failures:
            return FleetRuntimeCeremonyResult(
                status="FLEET_CEREMONY_EXECUTED_YELLOW",
                change_id=change_id,
                candidate_id=candidate_id,
                target_results=tuple(target_results),
                blocked_reasons=tuple(target_failures),
                next_step=(
                    "Review partial target failures. "
                    "Re-run ceremony for failed targets."
                ),
            )

        return FleetRuntimeCeremonyResult(
            status="FLEET_CEREMONY_EXECUTED_GREEN",
            change_id=change_id,
            candidate_id=candidate_id,
            target_results=tuple(target_results),
            blocked_reasons=(),
            next_step="All targets executed. Begin measurement phase.",
        )

    # ------------------------------------------------------------------
    # execute_runtime=False: preflight mode
    # ------------------------------------------------------------------

    for target_plan in target_plans_raw:
        if not isinstance(target_plan, dict):
            continue
        target_bot = str(target_plan.get("target_bot", ""))
        if not target_bot:
            continue

        target_dir = resolved_dir / change_id[:24] / "targets" / target_bot

        pre_apply_snapshot_path = str(
            target_dir / "pre_apply_snapshot.json"
        )
        audit_event_path = str(target_dir / "runtime_apply_audit.json")
        runtime_effect_proof_path = str(
            target_dir / "runtime_effect_proof.json"
        )
        measurement_start_path = str(
            target_dir / "measurement_start_record.json"
        )

        # Write preflight artifacts (planned paths, not actual data)
        preflight = {
            "event": "preflight_ceremony_artifact",
            "target_bot": target_bot,
            "planned_pre_apply_snapshot_path": pre_apply_snapshot_path,
            "planned_audit_event_path": audit_event_path,
            "planned_runtime_effect_proof_path": runtime_effect_proof_path,
            "planned_measurement_start_path": measurement_start_path,
            "runtime_mutation": "NONE",
            "created_at_utc": resolved_now,
        }
        _atomic_write_json(
            target_dir / "preflight_ceremony_artifact.json", preflight
        )

        target_results.append(
            TargetRuntimeCeremonyResult(
                target_bot=target_bot,
                status="PREFLIGHT_READY",
                pre_apply_snapshot_path=pre_apply_snapshot_path,
                audit_event_path=audit_event_path,
                runtime_effect_proof_path=runtime_effect_proof_path,
                measurement_start_path=measurement_start_path,
                blocked_reasons=(),
            )
        )

    return FleetRuntimeCeremonyResult(
        status="FLEET_CEREMONY_READY",
        change_id=change_id,
        candidate_id=candidate_id,
        target_results=tuple(target_results),
        blocked_reasons=(),
        next_step=(
            "Preflight artifacts written. Set execute_runtime=True and "
            "provide a runtime_executor to execute the ceremony."
        ),
    )
