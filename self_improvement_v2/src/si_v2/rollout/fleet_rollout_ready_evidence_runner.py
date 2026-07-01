"""SI-v2 Phase 10.2 — Real READY-only Fleet Chain Evidence Runner.

Consumes the Phase 10.1 resolver to produce a real, auditable READY-only
Fleet Rollout Chain evidence run. Proves that the resolver can feed real
SI-v2 artifacts into the chain and produce ``FLEET_CHAIN_READY`` plus
``chain_audit.json`` without runtime execution.

This module is **read-only and dry-run-only**. It does NOT:
- Execute any runtime mutation (restart, Docker, compose)
- Apply overlays to fleet bots
- Write to bot config paths or user_data directories
- Enable schedulers or watchers
- Execute rollback
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from si_v2.rollout.fleet_rollout_chain_runner import (
    run_fleet_rollout_chain,
)
from si_v2.rollout.fleet_rollout_input_resolver import (
    resolve_fleet_rollout_chain_input,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_EVIDENCE_OUTPUT_DIR: str = "var/si_v2/fleet_rollout_ready_evidence"

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FleetRolloutReadyEvidenceResult:
    """Structured result from the READY-only fleet chain evidence run.

    Attributes:
        status: Overall evidence status.
        resolver_status: Status from the input resolver.
        chain_status: Status from the fleet rollout chain.
        decision_pack_path: Resolved decision pack path.
        chain_audit_path: Path to the chain audit artifact.
        rollout_policy_path: Path to the rollout policy artifact.
        rollout_plan_path: Path to the rollout plan artifact.
        source_overlay_path: Path to the source overlay.
        source_overlay_sha256: SHA-256 of the source overlay.
        expected_parameter: Parameter being rolled out.
        expected_value: Expected parameter value.
        selected_targets: Selected target bot IDs.
        blocked_reasons: Human-readable reasons for blocking.
        runtime_mutation: Always "NONE" in Phase 10.2.
        evidence_report_path: Path to the evidence report artifact.
        next_step: Suggested next action.
    """

    status: Literal[
        "FLEET_READY_EVIDENCE_GREEN",
        "FLEET_READY_EVIDENCE_BLOCKED",
    ]
    resolver_status: str
    chain_status: str
    decision_pack_path: str
    chain_audit_path: str
    rollout_policy_path: str
    rollout_plan_path: str
    source_overlay_path: str
    source_overlay_sha256: str
    expected_parameter: str
    expected_value: int | float
    selected_targets: tuple[str, ...]
    blocked_reasons: tuple[str, ...]
    runtime_mutation: Literal["NONE"]
    evidence_report_path: str
    next_step: str

    def to_dict(self) -> dict[str, object]:
        return {
            "event": "phase_10_2_ready_evidence",
            "status": self.status,
            "resolver_status": self.resolver_status,
            "chain_status": self.chain_status,
            "decision_pack_path": self.decision_pack_path,
            "chain_audit_path": self.chain_audit_path,
            "rollout_policy_path": self.rollout_policy_path,
            "rollout_plan_path": self.rollout_plan_path,
            "source_overlay_path": self.source_overlay_path,
            "source_overlay_sha256": self.source_overlay_sha256,
            "expected_parameter": self.expected_parameter,
            "expected_value": self.expected_value,
            "selected_targets": list(self.selected_targets),
            "blocked_reasons": list(self.blocked_reasons),
            "runtime_mutation": self.runtime_mutation,
            "evidence_report_path": self.evidence_report_path,
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


def _now_utc() -> str:
    """Return current UTC timestamp string."""
    return datetime.now(UTC).isoformat()


# ---------------------------------------------------------------------------
# Evidence report writer
# ---------------------------------------------------------------------------


def _write_evidence_report(
    *,
    status: str,
    resolver_status: str,
    chain_status: str,
    decision_pack_path: str,
    chain_audit_path: str,
    rollout_policy_path: str,
    rollout_plan_path: str,
    source_overlay_path: str,
    source_overlay_sha256: str,
    expected_parameter: str,
    expected_value: int | float,
    selected_targets: tuple[str, ...],
    blocked_reasons: tuple[str, ...],
    evidence_dir: Path,
    now_utc: str,
) -> str:
    """Write the Phase 10.2 ready evidence report JSON.

    Returns the path to the written file.
    """
    report: dict[str, object] = {
        "event": "phase_10_2_ready_evidence",
        "status": status,
        "runtime_mutation": "NONE",
        "execute_fleet_runtime": False,
        "decision_pack_path": decision_pack_path,
        "resolver_status": resolver_status,
        "chain_status": chain_status,
        "rollout_policy_path": rollout_policy_path,
        "rollout_plan_path": rollout_plan_path,
        "chain_audit_path": chain_audit_path,
        "source_overlay_path": source_overlay_path,
        "source_overlay_sha256": source_overlay_sha256,
        "expected_parameter": expected_parameter,
        "expected_value": expected_value,
        "selected_targets": list(selected_targets),
        "blocked_reasons": list(blocked_reasons),
        "next_required_component": (
            "phase_10_3_controlled_dry_run_runtime_executor"
            if status == "FLEET_READY_EVIDENCE_GREEN"
            else "fix_phase_10_2_input_evidence"
        ),
        "created_at_utc": now_utc,
    }
    path = evidence_dir / "phase_10_2_ready_evidence_report.json"
    _atomic_write_json(path, report)
    return str(path)


# ---------------------------------------------------------------------------
# Main evidence runner
# ---------------------------------------------------------------------------


def run_fleet_rollout_ready_evidence(
    *,
    decision_pack_dir: str | Path,
    bot_registry_path: str | Path,
    output_dir: str | Path,
    explicit_decision_pack_path: str | Path | None = None,
    explicit_allowed_targets: tuple[str, ...] | None = None,
    explicit_overlay_path: str | Path | None = None,
    candidate_overlay: dict[str, object] | None = None,
    change_id_override: str | None = None,
    resolver_output_dir: str | Path | None = None,
) -> FleetRolloutReadyEvidenceResult:
    """Run a READY-only Fleet Rollout Chain evidence run.

    This is the primary entry point for Phase 10.2. It:
    1. Resolves chain input from real SI-v2 artifacts
    2. Runs the Fleet Rollout Chain in READY-only mode
    3. Writes a Phase 10.2 evidence report
    4. Returns a structured result

    Args:
        decision_pack_dir: Directory to search for qualified decision packs.
        bot_registry_path: Path to the fleet bot registry JSON.
        output_dir: Output directory for all evidence artifacts.
        explicit_decision_pack_path: Explicit decision pack path (skips lookup).
        explicit_allowed_targets: Explicit allowlist of target bot IDs.
        explicit_overlay_path: Explicit path to a source overlay JSON.
        candidate_overlay: Candidate overlay dict for materialization.
        change_id_override: Override change_id.
        resolver_output_dir: Override for resolver output directory.

    Returns:
        ``FleetRolloutReadyEvidenceResult`` with evidence status and paths.
    """
    resolved_output_dir = Path(output_dir)
    resolved_bot_registry = Path(bot_registry_path)
    resolved_decision_pack_dir = Path(decision_pack_dir)

    blocked: list[str] = []

    # ------------------------------------------------------------------
    # Step 1: Resolve chain input
    # ------------------------------------------------------------------

    resolution = resolve_fleet_rollout_chain_input(
        decision_pack_path=(
            str(explicit_decision_pack_path)
            if explicit_decision_pack_path
            else None
        ),
        decision_pack_dir=str(resolved_decision_pack_dir),
        bot_registry_path=str(resolved_bot_registry),
        explicit_allowed_targets=explicit_allowed_targets,
        explicit_overlay_path=(
            str(explicit_overlay_path) if explicit_overlay_path else None
        ),
        candidate_overlay=candidate_overlay,
        change_id_override=change_id_override,
        resolver_output_dir=(
            str(resolver_output_dir) if resolver_output_dir else None
        ),
    )

    resolver_status = resolution.status
    decision_pack_path = resolution.decision_pack_path
    source_overlay_path = resolution.source_overlay_path
    source_overlay_sha256 = resolution.source_overlay_sha256

    if resolver_status != "CHAIN_INPUT_READY":
        # Resolver blocked — write blocked evidence report
        evidence_dir = resolved_output_dir / "blocked"
        now = _now_utc()
        report_path = _write_evidence_report(
            status="FLEET_READY_EVIDENCE_BLOCKED",
            resolver_status=resolver_status,
            chain_status="",
            decision_pack_path=decision_pack_path,
            chain_audit_path="",
            rollout_policy_path="",
            rollout_plan_path="",
            source_overlay_path=source_overlay_path,
            source_overlay_sha256=source_overlay_sha256,
            expected_parameter="",
            expected_value=0,
            selected_targets=(),
            blocked_reasons=resolution.blocked_reasons,
            evidence_dir=evidence_dir,
            now_utc=now,
        )
        return FleetRolloutReadyEvidenceResult(
            status="FLEET_READY_EVIDENCE_BLOCKED",
            resolver_status=resolver_status,
            chain_status="",
            decision_pack_path=decision_pack_path,
            chain_audit_path="",
            rollout_policy_path="",
            rollout_plan_path="",
            source_overlay_path=source_overlay_path,
            source_overlay_sha256=source_overlay_sha256,
            expected_parameter="",
            expected_value=0,
            selected_targets=(),
            blocked_reasons=resolution.blocked_reasons,
            runtime_mutation="NONE",
            evidence_report_path=report_path,
            next_step=resolution.next_step,
        )

    # Resolver is ready — proceed
    assert resolution.chain_input is not None
    chain_input = resolution.chain_input

    # Guard: execute_fleet_runtime must be False
    if chain_input.execute_fleet_runtime:
        blocked.append(
            "execute_fleet_runtime_forbidden: chain input has "
            "execute_fleet_runtime=True in Phase 10.2"
        )
        evidence_dir = resolved_output_dir / "blocked"
        now = _now_utc()
        report_path = _write_evidence_report(
            status="FLEET_READY_EVIDENCE_BLOCKED",
            resolver_status=resolver_status,
            chain_status="",
            decision_pack_path=decision_pack_path,
            chain_audit_path="",
            rollout_policy_path="",
            rollout_plan_path="",
            source_overlay_path=source_overlay_path,
            source_overlay_sha256=source_overlay_sha256,
            expected_parameter=chain_input.expected_parameter,
            expected_value=chain_input.expected_value,
            selected_targets=chain_input.allowed_target_bots,
            blocked_reasons=tuple(blocked),
            evidence_dir=evidence_dir,
            now_utc=now,
        )
        return FleetRolloutReadyEvidenceResult(
            status="FLEET_READY_EVIDENCE_BLOCKED",
            resolver_status=resolver_status,
            chain_status="",
            decision_pack_path=decision_pack_path,
            chain_audit_path="",
            rollout_policy_path="",
            rollout_plan_path="",
            source_overlay_path=source_overlay_path,
            source_overlay_sha256=source_overlay_sha256,
            expected_parameter=chain_input.expected_parameter,
            expected_value=chain_input.expected_value,
            selected_targets=chain_input.allowed_target_bots,
            blocked_reasons=tuple(blocked),
            runtime_mutation="NONE",
            evidence_report_path=report_path,
            next_step="Fix chain input: execute_fleet_runtime must be False.",
        )

    # ------------------------------------------------------------------
    # Step 2: Run the Fleet Rollout Chain (READY-only)
    # ------------------------------------------------------------------

    chain_result = run_fleet_rollout_chain(
        chain_input,
        chain_output_dir=resolved_output_dir,
        runtime_executor=None,
    )

    chain_status = chain_result.status
    chain_audit_path = chain_result.chain_audit_path
    rollout_policy_path = chain_result.rollout_policy_path
    rollout_plan_path = chain_result.rollout_plan_path

    # Extract selected targets from rollout policy artifact
    selected_targets: tuple[str, ...] = ()
    if rollout_policy_path:
        try:
            policy_data = json.loads(Path(rollout_policy_path).read_text())
            raw_targets = policy_data.get("selected_targets", [])
            if isinstance(raw_targets, list):
                selected_targets = tuple(str(t) for t in raw_targets)
        except (json.JSONDecodeError, OSError):
            pass

    # ------------------------------------------------------------------
    # Step 3: Validate chain result
    # ------------------------------------------------------------------

    if chain_status != "FLEET_CHAIN_READY":
        blocked.extend(chain_result.blocked_reasons)
        evidence_dir = resolved_output_dir / "blocked"
        now = _now_utc()
        report_path = _write_evidence_report(
            status="FLEET_READY_EVIDENCE_BLOCKED",
            resolver_status=resolver_status,
            chain_status=chain_status,
            decision_pack_path=decision_pack_path,
            chain_audit_path=chain_audit_path,
            rollout_policy_path=rollout_policy_path,
            rollout_plan_path=rollout_plan_path,
            source_overlay_path=source_overlay_path,
            source_overlay_sha256=source_overlay_sha256,
            expected_parameter=chain_input.expected_parameter,
            expected_value=chain_input.expected_value,
            selected_targets=selected_targets,
            blocked_reasons=tuple(blocked),
            evidence_dir=evidence_dir,
            now_utc=now,
        )
        return FleetRolloutReadyEvidenceResult(
            status="FLEET_READY_EVIDENCE_BLOCKED",
            resolver_status=resolver_status,
            chain_status=chain_status,
            decision_pack_path=decision_pack_path,
            chain_audit_path=chain_audit_path,
            rollout_policy_path=rollout_policy_path,
            rollout_plan_path=rollout_plan_path,
            source_overlay_path=source_overlay_path,
            source_overlay_sha256=source_overlay_sha256,
            expected_parameter=chain_input.expected_parameter,
            expected_value=chain_input.expected_value,
            selected_targets=selected_targets,
            blocked_reasons=tuple(blocked),
            runtime_mutation="NONE",
            evidence_report_path="",
            next_step=chain_result.next_step,
        )

    # ------------------------------------------------------------------
    # Step 4: Validate chain_audit.json exists and runtime_mutation=NONE
    # ------------------------------------------------------------------

    if not chain_audit_path:
        blocked.append("chain_audit_missing: chain_audit_path is empty")
        evidence_dir = resolved_output_dir / "blocked"
        now = _now_utc()
        report_path = _write_evidence_report(
            status="FLEET_READY_EVIDENCE_BLOCKED",
            resolver_status=resolver_status,
            chain_status=chain_status,
            decision_pack_path=decision_pack_path,
            chain_audit_path=chain_audit_path,
            rollout_policy_path=rollout_policy_path,
            rollout_plan_path=rollout_plan_path,
            source_overlay_path=source_overlay_path,
            source_overlay_sha256=source_overlay_sha256,
            expected_parameter=chain_input.expected_parameter,
            expected_value=chain_input.expected_value,
            selected_targets=selected_targets,
            blocked_reasons=tuple(blocked),
            evidence_dir=evidence_dir,
            now_utc=now,
        )
        return FleetRolloutReadyEvidenceResult(
            status="FLEET_READY_EVIDENCE_BLOCKED",
            resolver_status=resolver_status,
            chain_status=chain_status,
            decision_pack_path=decision_pack_path,
            chain_audit_path=chain_audit_path,
            rollout_policy_path=rollout_policy_path,
            rollout_plan_path=rollout_plan_path,
            source_overlay_path=source_overlay_path,
            source_overlay_sha256=source_overlay_sha256,
            expected_parameter=chain_input.expected_parameter,
            expected_value=chain_input.expected_value,
            selected_targets=selected_targets,
            blocked_reasons=tuple(blocked),
            runtime_mutation="NONE",
            evidence_report_path="",
            next_step="Chain audit path is empty — investigate chain runner.",
        )

    audit_path_obj = Path(chain_audit_path)
    if not audit_path_obj.exists():
        blocked.append(
            f"chain_audit_not_found: {chain_audit_path} does not exist"
        )
        evidence_dir = resolved_output_dir / "blocked"
        now = _now_utc()
        report_path = _write_evidence_report(
            status="FLEET_READY_EVIDENCE_BLOCKED",
            resolver_status=resolver_status,
            chain_status=chain_status,
            decision_pack_path=decision_pack_path,
            chain_audit_path=chain_audit_path,
            rollout_policy_path=rollout_policy_path,
            rollout_plan_path=rollout_plan_path,
            source_overlay_path=source_overlay_path,
            source_overlay_sha256=source_overlay_sha256,
            expected_parameter=chain_input.expected_parameter,
            expected_value=chain_input.expected_value,
            selected_targets=selected_targets,
            blocked_reasons=tuple(blocked),
            evidence_dir=evidence_dir,
            now_utc=now,
        )
        return FleetRolloutReadyEvidenceResult(
            status="FLEET_READY_EVIDENCE_BLOCKED",
            resolver_status=resolver_status,
            chain_status=chain_status,
            decision_pack_path=decision_pack_path,
            chain_audit_path=chain_audit_path,
            rollout_policy_path=rollout_policy_path,
            rollout_plan_path=rollout_plan_path,
            source_overlay_path=source_overlay_path,
            source_overlay_sha256=source_overlay_sha256,
            expected_parameter=chain_input.expected_parameter,
            expected_value=chain_input.expected_value,
            selected_targets=selected_targets,
            blocked_reasons=tuple(blocked),
            runtime_mutation="NONE",
            evidence_report_path="",
            next_step="Chain audit file missing — investigate chain runner.",
        )

    # Verify runtime_mutation in audit
    try:
        audit_data = json.loads(audit_path_obj.read_text())
        audit_runtime_mutation = str(audit_data.get("runtime_mutation", ""))
        if audit_runtime_mutation != "NONE":
            blocked.append(
                f"runtime_mutation_not_none: audit says "
                f"{audit_runtime_mutation!r}"
            )
    except (json.JSONDecodeError, OSError) as e:
        blocked.append(f"chain_audit_unreadable: {e}")

    if blocked:
        evidence_dir = resolved_output_dir / "blocked"
        now = _now_utc()
        report_path = _write_evidence_report(
            status="FLEET_READY_EVIDENCE_BLOCKED",
            resolver_status=resolver_status,
            chain_status=chain_status,
            decision_pack_path=decision_pack_path,
            chain_audit_path=chain_audit_path,
            rollout_policy_path=rollout_policy_path,
            rollout_plan_path=rollout_plan_path,
            source_overlay_path=source_overlay_path,
            source_overlay_sha256=source_overlay_sha256,
            expected_parameter=chain_input.expected_parameter,
            expected_value=chain_input.expected_value,
            selected_targets=selected_targets,
            blocked_reasons=tuple(blocked),
            evidence_dir=evidence_dir,
            now_utc=now,
        )
        return FleetRolloutReadyEvidenceResult(
            status="FLEET_READY_EVIDENCE_BLOCKED",
            resolver_status=resolver_status,
            chain_status=chain_status,
            decision_pack_path=decision_pack_path,
            chain_audit_path=chain_audit_path,
            rollout_policy_path=rollout_policy_path,
            rollout_plan_path=rollout_plan_path,
            source_overlay_path=source_overlay_path,
            source_overlay_sha256=source_overlay_sha256,
            expected_parameter=chain_input.expected_parameter,
            expected_value=chain_input.expected_value,
            selected_targets=selected_targets,
            blocked_reasons=tuple(blocked),
            runtime_mutation="NONE",
            evidence_report_path="",
            next_step="Review blocked reasons and fix before retrying.",
        )

    # ------------------------------------------------------------------
    # Step 5: Write evidence report (GREEN)
    # ------------------------------------------------------------------

    evidence_dir = resolved_output_dir / "evidence"
    now = _now_utc()
    report_path = _write_evidence_report(
        status="FLEET_READY_EVIDENCE_GREEN",
        resolver_status=resolver_status,
        chain_status=chain_status,
        decision_pack_path=decision_pack_path,
        chain_audit_path=chain_audit_path,
        rollout_policy_path=rollout_policy_path,
        rollout_plan_path=rollout_plan_path,
        source_overlay_path=source_overlay_path,
        source_overlay_sha256=source_overlay_sha256,
        expected_parameter=chain_input.expected_parameter,
        expected_value=chain_input.expected_value,
        selected_targets=selected_targets,
        blocked_reasons=(),
        evidence_dir=evidence_dir,
        now_utc=now,
    )

    return FleetRolloutReadyEvidenceResult(
        status="FLEET_READY_EVIDENCE_GREEN",
        resolver_status=resolver_status,
        chain_status=chain_status,
        decision_pack_path=decision_pack_path,
        chain_audit_path=chain_audit_path,
        rollout_policy_path=rollout_policy_path,
        rollout_plan_path=rollout_plan_path,
        source_overlay_path=source_overlay_path,
        source_overlay_sha256=source_overlay_sha256,
        expected_parameter=chain_input.expected_parameter,
        expected_value=chain_input.expected_value,
        selected_targets=selected_targets,
        blocked_reasons=(),
        runtime_mutation="NONE",
        evidence_report_path=report_path,
        next_step=(
            "Phase 10.2 READY evidence complete. "
            "Proceed to Phase 10.3: Controlled Dry-Run Runtime Executor."
        ),
    )
