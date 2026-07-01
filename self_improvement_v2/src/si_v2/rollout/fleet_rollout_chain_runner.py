"""SI-v2 Phase 10 — Fleet Rollout Chain Active-Cycle Integration.

Orchestrates Phase 9A (rollout policy), Phase 9B (artifact planner), and
Phase 9C (runtime ceremony) into a controlled chain runner that can be
invoked from the SI-v2 Active Cycle.

This module is **dry-run-only by default**. It does NOT:
- Enable live trading
- Enable schedulers or watchers
- Execute uncontrolled fleet apply
- Execute runtime actions without explicit ``execute_fleet_runtime=True``
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from si_v2.rollout.fleet_rollout_artifact_planner import (
    FleetRolloutPlannerInput,
    TargetBotRuntimeSpec,
    build_fleet_rollout_artifacts,
)
from si_v2.rollout.fleet_rollout_policy import (
    FleetBot,
    FleetRolloutPolicyInput,
    evaluate_fleet_rollout_policy,
)
from si_v2.rollout.fleet_runtime_ceremony import (
    FleetRuntimeCeremonyInput,
    run_fleet_runtime_ceremony,
)

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FleetRolloutChainInput:
    """All inputs for the fleet rollout chain runner.

    Attributes:
        decision_pack_path: Path to the Measurement Watcher decision pack JSON.
        fleet_bots: Available fleet bots with roles and flags.
        allowed_target_bots: Bot IDs explicitly allowed as promotion targets.
        target_runtime_specs: Runtime specs for each candidate target bot.
        source_overlay_path: Path to the source overlay JSON.
        source_overlay_sha256: Expected SHA-256 hash of the source overlay.
        expected_parameter: The parameter being rolled out.
        expected_value: The expected value of the parameter.
        execute_fleet_runtime: If True, execute runtime actions through
            the runtime_executor. Default False (READY-only).
        require_statistical_evidence: If True, statistical evidence required.
        min_stat_evidence_grade: Minimum statistical evidence grade.
        max_targets: Maximum number of targets for a single rollout.
    """

    decision_pack_path: str
    fleet_bots: tuple[FleetBot, ...]
    allowed_target_bots: tuple[str, ...]
    target_runtime_specs: tuple[TargetBotRuntimeSpec, ...]
    source_overlay_path: str
    source_overlay_sha256: str
    expected_parameter: str
    expected_value: int | float
    execute_fleet_runtime: bool = False
    require_statistical_evidence: bool = True
    min_stat_evidence_grade: Literal["STRONG", "MODERATE", "WEAK"] = "MODERATE"
    max_targets: int = 1


@dataclass(frozen=True)
class FleetRolloutChainResult:
    """Aggregate result of the fleet rollout chain."""

    status: Literal[
        "FLEET_CHAIN_READY",
        "FLEET_CHAIN_EXECUTED_GREEN",
        "FLEET_CHAIN_EXECUTED_YELLOW",
        "FLEET_CHAIN_NOT_ELIGIBLE",
        "FLEET_CHAIN_BLOCKED",
    ]
    change_id: str
    candidate_id: str
    policy_status: str
    planner_status: str
    ceremony_status: str
    rollout_policy_path: str
    rollout_plan_path: str
    chain_audit_path: str
    blocked_reasons: tuple[str, ...]
    next_step: str

    def to_dict(self) -> dict[str, object]:
        return {
            "event": "fleet_rollout_chain_result",
            "status": self.status,
            "change_id": self.change_id,
            "candidate_id": self.candidate_id,
            "policy_status": self.policy_status,
            "planner_status": self.planner_status,
            "ceremony_status": self.ceremony_status,
            "rollout_policy_path": self.rollout_policy_path,
            "rollout_plan_path": self.rollout_plan_path,
            "chain_audit_path": self.chain_audit_path,
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
# Chain audit writer
# ---------------------------------------------------------------------------


def _write_chain_audit(
    *,
    change_id: str,
    candidate_id: str,
    status: str,
    decision_pack_path: str,
    rollout_policy_path: str,
    rollout_plan_path: str,
    ceremony_status: str,
    execute_fleet_runtime: bool,
    selected_targets: list[str],
    blocked_reasons: list[str],
    chain_audit_dir: Path,
    now_utc: str,
) -> str:
    """Write the chain audit artifact.

    Determines next_required_component based on execution state.
    """
    if execute_fleet_runtime and ceremony_status in (
        "FLEET_CEREMONY_EXECUTED_GREEN",
        "FLEET_CEREMONY_EXECUTED_YELLOW",
    ):
        next_component = "post_fleet_measurement_watcher"
    else:
        next_component = "fleet_runtime_ceremony_execution"

    audit: dict[str, object] = {
        "event": "fleet_rollout_chain_audit",
        "change_id": change_id,
        "candidate_id": candidate_id,
        "status": status,
        "decision_pack_path": decision_pack_path,
        "rollout_policy_path": rollout_policy_path,
        "rollout_plan_path": rollout_plan_path,
        "ceremony_status": ceremony_status,
        "execute_fleet_runtime": execute_fleet_runtime,
        "runtime_mutation": "NONE",
        "selected_targets": selected_targets,
        "blocked_reasons": blocked_reasons,
        "next_required_component": next_component,
        "created_at_utc": now_utc,
    }
    path = chain_audit_dir / "chain_audit.json"
    _atomic_write_json(path, audit)
    return str(path)


# ---------------------------------------------------------------------------
# Main chain runner
# ---------------------------------------------------------------------------


def run_fleet_rollout_chain(
    input_: FleetRolloutChainInput,
    *,
    chain_output_dir: Path | None = None,
    runtime_executor: object | None = None,
    now_utc: str | None = None,
) -> FleetRolloutChainResult:
    """Run the controlled fleet rollout chain: 9A → 9B → 9C.

    Args:
        input_: All inputs for the chain.
        chain_output_dir: Override for chain artifact output directory.
        runtime_executor: Callable for actual runtime actions. Required
            when ``execute_fleet_runtime=True``.
        now_utc: Override for current UTC time (testing).

    Returns:
        ``FleetRolloutChainResult`` with per-phase status and audit path.
    """
    resolved_now = now_utc or datetime.now(UTC).isoformat()
    resolved_dir = chain_output_dir or Path("var/si_v2/fleet_rollout_chain")

    blocked: list[str] = []

    # ------------------------------------------------------------------
    # Step 1: Read decision pack
    # ------------------------------------------------------------------

    pack = _read_json(input_.decision_pack_path)
    if pack is None:
        return FleetRolloutChainResult(
            status="FLEET_CHAIN_BLOCKED",
            change_id="",
            candidate_id="",
            policy_status="",
            planner_status="",
            ceremony_status="",
            rollout_policy_path="",
            rollout_plan_path="",
            chain_audit_path="",
            blocked_reasons=(
                f"decision_pack_not_readable: {input_.decision_pack_path}",
            ),
            next_step="Provide a valid decision pack path and retry.",
        )

    change_id = str(pack.get("change_id", ""))
    candidate_id = str(pack.get("candidate_id", ""))

    # ------------------------------------------------------------------
    # Step 2: Phase 9A — Fleet Rollout Policy
    # ------------------------------------------------------------------

    policy_input = FleetRolloutPolicyInput(
        decision_pack_path=input_.decision_pack_path,
        fleet_bots=input_.fleet_bots,
        allowed_target_bots=input_.allowed_target_bots,
        min_stat_evidence_grade=input_.min_stat_evidence_grade,
        require_statistical_evidence=input_.require_statistical_evidence,
        max_targets=input_.max_targets,
    )

    policy_result = evaluate_fleet_rollout_policy(
        policy_input,
        rollout_policy_dir=resolved_dir / change_id[:24] / "rollout_policy",
        now_utc=resolved_now,
    )

    policy_status = policy_result.status
    rollout_policy_path = policy_result.rollout_policy_path

    # Handle non-eligible / blocked policy results
    if policy_status == "PROMOTION_NOT_ELIGIBLE":
        audit_path = _write_chain_audit(
            change_id=change_id,
            candidate_id=candidate_id,
            status="FLEET_CHAIN_NOT_ELIGIBLE",
            decision_pack_path=input_.decision_pack_path,
            rollout_policy_path=rollout_policy_path,
            rollout_plan_path="",
            ceremony_status="",
            execute_fleet_runtime=input_.execute_fleet_runtime,
            selected_targets=list(policy_result.selected_targets),
            blocked_reasons=list(policy_result.blocked_reasons),
            chain_audit_dir=resolved_dir / change_id[:24],
            now_utc=resolved_now,
        )
        return FleetRolloutChainResult(
            status="FLEET_CHAIN_NOT_ELIGIBLE",
            change_id=change_id,
            candidate_id=candidate_id,
            policy_status=policy_status,
            planner_status="",
            ceremony_status="",
            rollout_policy_path=rollout_policy_path,
            rollout_plan_path="",
            chain_audit_path=audit_path,
            blocked_reasons=policy_result.blocked_reasons,
            next_step=policy_result.next_step,
        )

    if policy_status == "PROMOTION_EXTEND_MEASUREMENT":
        audit_path = _write_chain_audit(
            change_id=change_id,
            candidate_id=candidate_id,
            status="FLEET_CHAIN_NOT_ELIGIBLE",
            decision_pack_path=input_.decision_pack_path,
            rollout_policy_path=rollout_policy_path,
            rollout_plan_path="",
            ceremony_status="",
            execute_fleet_runtime=input_.execute_fleet_runtime,
            selected_targets=list(policy_result.selected_targets),
            blocked_reasons=list(policy_result.blocked_reasons),
            chain_audit_dir=resolved_dir / change_id[:24],
            now_utc=resolved_now,
        )
        return FleetRolloutChainResult(
            status="FLEET_CHAIN_NOT_ELIGIBLE",
            change_id=change_id,
            candidate_id=candidate_id,
            policy_status=policy_status,
            planner_status="",
            ceremony_status="",
            rollout_policy_path=rollout_policy_path,
            rollout_plan_path="",
            chain_audit_path=audit_path,
            blocked_reasons=policy_result.blocked_reasons,
            next_step=policy_result.next_step,
        )

    if policy_status == "PROMOTION_BLOCKED":
        audit_path = _write_chain_audit(
            change_id=change_id,
            candidate_id=candidate_id,
            status="FLEET_CHAIN_BLOCKED",
            decision_pack_path=input_.decision_pack_path,
            rollout_policy_path=rollout_policy_path,
            rollout_plan_path="",
            ceremony_status="",
            execute_fleet_runtime=input_.execute_fleet_runtime,
            selected_targets=list(policy_result.selected_targets),
            blocked_reasons=list(policy_result.blocked_reasons),
            chain_audit_dir=resolved_dir / change_id[:24],
            now_utc=resolved_now,
        )
        return FleetRolloutChainResult(
            status="FLEET_CHAIN_BLOCKED",
            change_id=change_id,
            candidate_id=candidate_id,
            policy_status=policy_status,
            planner_status="",
            ceremony_status="",
            rollout_policy_path=rollout_policy_path,
            rollout_plan_path="",
            chain_audit_path=audit_path,
            blocked_reasons=policy_result.blocked_reasons,
            next_step=policy_result.next_step,
        )

    # policy_status must be PROMOTION_ELIGIBLE at this point
    selected_targets = list(policy_result.selected_targets)

    # ------------------------------------------------------------------
    # Step 3: Phase 9B — Fleet Rollout Artifact Planner
    # ------------------------------------------------------------------

    planner_input = FleetRolloutPlannerInput(
        rollout_policy_path=rollout_policy_path,
        target_runtime_specs=input_.target_runtime_specs,
        source_overlay_path=input_.source_overlay_path,
        source_overlay_sha256=input_.source_overlay_sha256,
        expected_parameter=input_.expected_parameter,
        expected_value=input_.expected_value,
    )

    planner_result = build_fleet_rollout_artifacts(
        planner_input,
        rollout_plan_dir=resolved_dir / change_id[:24] / "rollout_plan",
        now_utc=resolved_now,
    )

    planner_status = planner_result.status
    rollout_plan_path = planner_result.rollout_plan_path

    if planner_status != "ROLLOUT_PLAN_READY":
        blocked.extend(planner_result.blocked_reasons)
        audit_path = _write_chain_audit(
            change_id=change_id,
            candidate_id=candidate_id,
            status="FLEET_CHAIN_BLOCKED",
            decision_pack_path=input_.decision_pack_path,
            rollout_policy_path=rollout_policy_path,
            rollout_plan_path=rollout_plan_path,
            ceremony_status="",
            execute_fleet_runtime=input_.execute_fleet_runtime,
            selected_targets=selected_targets,
            blocked_reasons=blocked,
            chain_audit_dir=resolved_dir / change_id[:24],
            now_utc=resolved_now,
        )
        return FleetRolloutChainResult(
            status="FLEET_CHAIN_BLOCKED",
            change_id=change_id,
            candidate_id=candidate_id,
            policy_status=policy_status,
            planner_status=planner_status,
            ceremony_status="",
            rollout_policy_path=rollout_policy_path,
            rollout_plan_path=rollout_plan_path,
            chain_audit_path=audit_path,
            blocked_reasons=tuple(blocked),
            next_step=planner_result.next_step,
        )

    # ------------------------------------------------------------------
    # Step 4: Phase 9C — Fleet Runtime Ceremony
    # ------------------------------------------------------------------

    ceremony_input = FleetRuntimeCeremonyInput(
        fleet_rollout_plan_path=rollout_plan_path,
        execute_runtime=input_.execute_fleet_runtime,
    )

    ceremony_result = run_fleet_runtime_ceremony(
        ceremony_input,
        ceremony_output_dir=resolved_dir / change_id[:24] / "ceremony",
        runtime_executor=runtime_executor,
        now_utc=resolved_now,
    )

    ceremony_status = ceremony_result.status

    # ------------------------------------------------------------------
    # Step 5: Map ceremony status to chain status
    # ------------------------------------------------------------------

    if ceremony_status == "FLEET_CEREMONY_READY":
        chain_status: str = "FLEET_CHAIN_READY"
    elif ceremony_status == "FLEET_CEREMONY_EXECUTED_GREEN":
        chain_status = "FLEET_CHAIN_EXECUTED_GREEN"
    elif ceremony_status == "FLEET_CEREMONY_EXECUTED_YELLOW":
        chain_status = "FLEET_CHAIN_EXECUTED_YELLOW"
    else:
        chain_status = "FLEET_CHAIN_BLOCKED"
        blocked.extend(ceremony_result.blocked_reasons)

    # ------------------------------------------------------------------
    # Step 6: Write chain audit
    # ------------------------------------------------------------------

    audit_path = _write_chain_audit(
        change_id=change_id,
        candidate_id=candidate_id,
        status=chain_status,
        decision_pack_path=input_.decision_pack_path,
        rollout_policy_path=rollout_policy_path,
        rollout_plan_path=rollout_plan_path,
        ceremony_status=ceremony_status,
        execute_fleet_runtime=input_.execute_fleet_runtime,
        selected_targets=selected_targets,
        blocked_reasons=blocked,
        chain_audit_dir=resolved_dir / change_id[:24],
        now_utc=resolved_now,
    )

    # Determine next step
    if chain_status == "FLEET_CHAIN_READY":
        next_step = (
            "Chain preflight complete. Set execute_fleet_runtime=True and "
            "provide a runtime_executor to execute the ceremony."
        )
    elif chain_status == "FLEET_CHAIN_EXECUTED_GREEN":
        next_step = (
            "All targets executed. Begin measurement phase."
        )
    elif chain_status == "FLEET_CHAIN_EXECUTED_YELLOW":
        next_step = (
            "Partial target failures. Review and re-run ceremony for "
            "failed targets."
        )
    else:
        next_step = "Review blocked reasons and fix before retrying."

    return FleetRolloutChainResult(
        status=chain_status,
        change_id=change_id,
        candidate_id=candidate_id,
        policy_status=policy_status,
        planner_status=planner_status,
        ceremony_status=ceremony_status,
        rollout_policy_path=rollout_policy_path,
        rollout_plan_path=rollout_plan_path,
        chain_audit_path=audit_path,
        blocked_reasons=tuple(blocked),
        next_step=next_step,
    )


# ---------------------------------------------------------------------------
# Active Cycle Hook
# ---------------------------------------------------------------------------


def maybe_run_fleet_rollout_chain_from_active_cycle(
    decision_pack_path: str,
    fleet_bots: tuple[FleetBot, ...],
    allowed_target_bots: tuple[str, ...],
    target_runtime_specs: tuple[TargetBotRuntimeSpec, ...],
    source_overlay_path: str,
    source_overlay_sha256: str,
    expected_parameter: str,
    expected_value: int | float,
    *,
    fleet_rollout_chain_enabled: bool = False,
    chain_output_dir: Path | None = None,
    runtime_executor: object | None = None,
    now_utc: str | None = None,
) -> FleetRolloutChainResult | None:
    """Optional Active Cycle hook for the fleet rollout chain.

    When ``fleet_rollout_chain_enabled`` is False (default), this function
    returns None and does nothing.

    When enabled, it builds a ``FleetRolloutChainInput`` and calls
    ``run_fleet_rollout_chain()`` with default ``execute_fleet_runtime=False``.

    This function is designed to be called from the Active Cycle runner
    without breaking existing behavior.

    Args:
        decision_pack_path: Path to the Measurement Watcher decision pack.
        fleet_bots: Available fleet bots.
        allowed_target_bots: Allowed promotion targets.
        target_runtime_specs: Runtime specs for target bots.
        source_overlay_path: Path to the source overlay.
        source_overlay_sha256: Expected overlay hash.
        expected_parameter: Parameter being rolled out.
        expected_value: Expected parameter value.
        fleet_rollout_chain_enabled: Master switch. Default False.
        chain_output_dir: Override for chain output directory.
        runtime_executor: Optional runtime executor.
        now_utc: Override for current UTC time.

    Returns:
        ``FleetRolloutChainResult`` when enabled, None otherwise.
    """
    if not fleet_rollout_chain_enabled:
        return None

    chain_input = FleetRolloutChainInput(
        decision_pack_path=decision_pack_path,
        fleet_bots=fleet_bots,
        allowed_target_bots=allowed_target_bots,
        target_runtime_specs=target_runtime_specs,
        source_overlay_path=source_overlay_path,
        source_overlay_sha256=source_overlay_sha256,
        expected_parameter=expected_parameter,
        expected_value=expected_value,
        execute_fleet_runtime=False,
    )

    return run_fleet_rollout_chain(
        chain_input,
        chain_output_dir=chain_output_dir,
        runtime_executor=runtime_executor,
        now_utc=now_utc,
    )
