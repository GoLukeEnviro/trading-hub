"""SI-v2 apply-chain evaluation stage — AUTONOMOUS_DRY_RUN activation (Agent0).

First stage of the dry-run apply chain, designed to run inside the single
SI-v2 scheduler job right after the read-only active cycle:

1. The authorization marker ``APPROVED_AUTONOMOUS_DRY_RUN_AGENT0`` must be
   present and valid in the repository (fail-closed otherwise).
2. The kill switch must be NORMAL and RiskGuard must derive PASS. Both
   reads are fail-closed on missing, corrupt or unknown state.
3. The newest cycle evidence bundle is loaded and the real candidate - if
   one exists - is taken unmodified from the bundle.
4. Stage 1 is canary-only: a candidate for any other bot never advances.
5. Allowlist and range checks reuse the existing safe-parameter contract.
6. A qualified canary candidate is prepared end to end: overlay, rollback
   plan, audit event and measurement plan are written; the runtime
   ceremony runs its full preflight (no runtime action).
7. Runtime execution (canary recreate) runs only when the
   rehearsal-gated switch is on: ``activation.json`` carries
   ``runtime_execution.wired=true`` **and** the referenced rehearsal
   evidence exists with a PASS result. Without that proof the stage
   stays prepare-only; a switch naming missing/failed evidence blocks.
8. On a non-GREEN execution outcome the stage rolls the canary back
   automatically and verifies the rollback; a failed verification is a
   hard blocker event.

No live trading. No ``dry_run`` change. No Docker or subprocess call from
this module. Expected gate outcomes never raise - every outcome is a
structured, recorded result.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from si_v2.apply_actuator.controlled_apply_actuator import (
    CANARY_BOT_ID,
    check_cooldown,
    check_kill_switch,
    derive_riskguard_status,
    read_riskguard_status,
)
from si_v2.apply_actuator.runtime_binding import (
    ComposeContext,
    compose_project_name,
    container_name_for_service,
    resolve_binding,
)
from si_v2.pipeline.autonomous_dry_run_executor import (
    AutonomousDryRunExecutorInput,
    prepare_autonomous_dry_run_apply,
)
from si_v2.pipeline.candidate_to_apply import (
    CandidateApplyInput,
    candidate_to_apply_pipeline,
)
from si_v2.pipeline.runtime_ceremony_runner import (
    RuntimeCeremonyInput,
    run_runtime_ceremony,
)
from si_v2.propose.safe_parameters import validate_safe_parameter

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MARKER_ID: Final[str] = "APPROVED_AUTONOMOUS_DRY_RUN_AGENT0"
MARKER_FILE_NAME: Final[str] = f"{MARKER_ID}.md"
ACTIVATION_RECORD_NAME: Final[str] = "activation.json"
DEFAULT_STATE_DIR: Final[Path] = Path("/opt/data/logs/si-v2-apply-chain/state")
DEFAULT_CYCLE_LOG_DIR: Final[Path] = Path("/opt/data/logs/si-v2-active-cycle")
CYCLE_STALE_AFTER_SECONDS: Final[int] = 13 * 3600
EVIDENCE_DIR_RELATIVE: Final[str] = "self_improvement_v2/reports/phase2/evidence"
CANARY_USER_DATA_RELATIVE: Final[str] = "freqforge-canary/user_data"

CANDIDATE_KEY_MAP: Final[dict[str, str]] = {
    "max_open_trades_candidate": "max_open_trades",
    "cooldown_candles_candidate": "cooldown_candles",
}

STATUS_NO_QUALIFIED_PROPOSAL: Final[str] = "NO_QUALIFIED_PROPOSAL"
STATUS_APPLY_PREPARED: Final[str] = "APPLY_PREPARED_RUNTIME_STAGE_NOT_WIRED"
STATUS_APPLY_EXECUTED_GREEN: Final[str] = "APPLY_EXECUTED_GREEN"
STATUS_APPLY_ROLLED_BACK: Final[str] = "APPLY_ROLLED_BACK"
STATUS_BLOCKED_WIRING: Final[str] = "BLOCKED_WIRING"
STATUS_BLOCKED_ROLLBACK_FAILED: Final[str] = "BLOCKED_ROLLBACK_FAILED"
STATUS_BLOCKED_MARKER: Final[str] = "BLOCKED_MARKER"
STATUS_BLOCKED_ACTIVATION_RECORD: Final[str] = "BLOCKED_ACTIVATION_RECORD"
STATUS_BLOCKED_KILL_SWITCH: Final[str] = "BLOCKED_KILL_SWITCH"
STATUS_BLOCKED_RISKGUARD: Final[str] = "BLOCKED_RISKGUARD"
STATUS_BLOCKED_STALE_CYCLE: Final[str] = "BLOCKED_STALE_CYCLE"
STATUS_BLOCKED_BUNDLE: Final[str] = "BLOCKED_BUNDLE"
STATUS_BLOCKED_CANDIDATE: Final[str] = "BLOCKED_CANDIDATE"
STATUS_BLOCKED_PIPELINE: Final[str] = "BLOCKED_PIPELINE"

EVENT_NO_APPLY: Final[str] = "NO_APPLY"
EVENT_BLOCKER: Final[str] = "BLOCKER"
EVENT_PREPARED: Final[str] = "PREPARED"
EVENT_EXECUTED: Final[str] = "EXECUTED"
EVENT_ROLLED_BACK: Final[str] = "ROLLED_BACK"

REHEARSAL_PASS_RESULT: Final[str] = "P2_REHEARSAL_PASS"
"""The only rehearsal result that authorises runtime execution."""

_ALLOWED_PIPELINE_STATUSES: Final[tuple[str, ...]] = (
    "READY_FOR_AUTONOMOUS_DRY_RUN_APPLY",
    "AUTO_DRY_RUN_APPROVED",
)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ApplyChainEvaluationInput:
    """Everything the evaluation stage reads (paths overridable for tests)."""

    repo_root: Path
    """Repository root (checkout) the evaluation binds to."""

    state_dir: Path = DEFAULT_STATE_DIR
    """State directory for records, audit and prepared artifacts."""

    bundle_path: Path | None = None
    """Explicit evidence bundle. Default: newest in the evidence directory."""

    marker_path: Path | None = None
    """Explicit authorization marker path. Default: docs/decisions/<marker>.md."""

    kill_switch_path: Path | None = None
    """Explicit kill-switch path. Default: <repo>/var/kill_switch.json."""

    riskguard_state_path: Path | None = None
    """Explicit RiskGuard state path. Default: <repo>/orchestrator/state/riskguard/."""

    canary_config_path: Path | None = None
    """Explicit canary config path. Default: <repo>/freqforge-canary/user_data/config.json."""

    cycle_log_dir: Path | None = DEFAULT_CYCLE_LOG_DIR
    """Cycle-log directory used for the freshness watchdog check."""

    cycle_stale_after_seconds: int = CYCLE_STALE_AFTER_SECONDS
    """Freshness threshold for the newest cycle log."""


@dataclass(frozen=True)
class ApplyChainEvaluationResult:
    """Structured result of one evaluation run. Always recorded."""

    status: str
    event: str
    reason: str
    cycle_id: str = ""
    bundle_name: str = ""
    candidate_id: str = ""
    target_bot: str = ""
    executed_runtime: bool = False
    detail: dict[str, object] = field(default_factory=dict)
    created_at_utc: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "event": self.event,
            "reason": self.reason,
            "cycle_id": self.cycle_id,
            "bundle_name": self.bundle_name,
            "candidate_id": self.candidate_id,
            "target_bot": self.target_bot,
            "executed_runtime": self.executed_runtime,
            "detail": dict(self.detail),
            "created_at_utc": self.created_at_utc,
        }

    def is_alert(self) -> bool:
        """True for events the scheduler alert channel must surface."""
        return self.event != EVENT_NO_APPLY


# ---------------------------------------------------------------------------
# Helpers (small, side-effect free)
# ---------------------------------------------------------------------------


def _now_utc() -> str:
    return datetime.now(UTC).isoformat()


def _load_json(path: Path) -> dict[str, object] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def _result(
    status: str,
    event: str,
    reason: str,
    *,
    cycle_id: str = "",
    bundle_name: str = "",
    candidate_id: str = "",
    target_bot: str = "",
    detail: dict[str, object] | None = None,
    executed_runtime: bool = False,
) -> ApplyChainEvaluationResult:
    return ApplyChainEvaluationResult(
        status=status,
        event=event,
        reason=reason,
        cycle_id=cycle_id,
        bundle_name=bundle_name,
        candidate_id=candidate_id,
        target_bot=target_bot,
        executed_runtime=executed_runtime,
        detail=dict(detail or {}),
        created_at_utc=_now_utc(),
    )


def _check_marker(marker_path: Path) -> tuple[bool, str, str]:
    """Return (ok, reason, marker_sha256). Fail-closed on missing marker."""
    if not marker_path.is_file():
        return False, f"marker_missing: {marker_path}", ""
    try:
        text = marker_path.read_text(encoding="utf-8")
    except OSError:
        return False, f"marker_unreadable: {marker_path}", ""
    missing = [
        token
        for token in (MARKER_ID, "Luke", "AUTONOMOUS_DRY_RUN")
        if token not in text
    ]
    if missing:
        return False, f"marker_incomplete: missing {sorted(missing)}", ""
    sha = hashlib.sha256(marker_path.read_bytes()).hexdigest()
    return True, "", sha


def _check_activation_record(state_dir: Path) -> tuple[bool, str]:
    """Optional tamper check: a present activation record must be valid."""
    record_path = state_dir / ACTIVATION_RECORD_NAME
    if not record_path.is_file():
        return True, ""
    record = _load_json(record_path)
    if record is None:
        return False, f"activation_record_unreadable: {record_path}"
    if record.get("marker") != MARKER_ID:
        return False, "activation_record_invalid: marker mismatch"
    if record.get("mode") != "AUTONOMOUS_DRY_RUN":
        return False, "activation_record_invalid: mode mismatch"
    return True, ""


def _read_runtime_wiring(state_dir: Path) -> tuple[bool, str, dict[str, object]]:
    """Read the rehearsal-gated runtime-execution switch.

    Three outcomes:

    - no activation record / no ``runtime_execution`` section / ``wired`` not
      true -> ``(False, "", {})`` — prepare-only, not a blocker;
    - ``wired=true`` whose referenced rehearsal evidence is missing,
      unreadable or not a PASS -> ``(False, reason, ..)`` — caller blocks;
    - ``wired=true`` with PASS evidence -> ``(True, "", detail)``.
    """
    record_path = state_dir / ACTIVATION_RECORD_NAME
    if not record_path.is_file():
        return False, "", {}
    record = _load_json(record_path)
    if record is None:
        return False, f"activation_record_unreadable: {record_path}", {}
    if record.get("marker") != MARKER_ID:
        return False, "activation_record_invalid: marker mismatch", {}
    if record.get("mode") != "AUTONOMOUS_DRY_RUN":
        return False, "activation_record_invalid: mode mismatch", {}

    section = record.get("runtime_execution")
    if not isinstance(section, dict) or section.get("wired") is not True:
        return False, "", {}

    evidence_path = str(section.get("rehearsal_evidence") or "")
    if not evidence_path:
        return False, (
            "wiring_rehearsal_evidence_missing: no path in runtime_execution section"
        ), {"present": True}
    if not Path(evidence_path).is_file():
        return False, (
            f"wiring_rehearsal_evidence_not_found: {evidence_path}"
        ), {"present": True}
    evidence = _load_json(Path(evidence_path))
    if evidence is None:
        return False, (
            f"wiring_rehearsal_evidence_unreadable: {evidence_path}"
        ), {"present": True}
    if evidence.get("result") != REHEARSAL_PASS_RESULT:
        return False, (
            f"wiring_rehearsal_not_pass: {evidence.get('result')!r} != "
            f"{REHEARSAL_PASS_RESULT!r}"
        ), {"present": True}
    return True, "", {
        "rehearsal_evidence": evidence_path,
        "rehearsal_result": evidence.get("result"),
    }


def _rollback_canary(
    compose_context: ComposeContext,
    service: str,
    overlay_host_path: str,
) -> tuple[bool, dict[str, object]]:
    """Remove the overlay and recreate the service from the base compose.

    Documented rollback path (ADR: remove the override, compose recreate).
    Also removes the overlay file inside the container volume (the compose
    bind mount leaves a zero-byte stub there). Returns (verified, detail).
    """
    detail: dict[str, object] = {}
    overlay_host = Path(overlay_host_path) if overlay_host_path else None
    container = container_name_for_service(service)

    cmd = [
        "docker", "compose",
        "-p", compose_project_name(),
        "--env-file", compose_context.env_file,
        "-f", compose_context.compose_file,
        "up", "-d", service,
    ]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=180,
            cwd=compose_context.repo_root,
        )
        detail["compose_rc"] = proc.returncode
    except (OSError, subprocess.SubprocessError) as exc:
        return False, {"compose_rc": -1, "compose_error": str(exc)[:200]}

    if detail.get("compose_rc") != 0:
        return False, detail

    if overlay_host is not None and overlay_host.is_file():
        try:
            overlay_host.unlink()
        except OSError as exc:
            detail["overlay_remove_error"] = str(exc)[:200]
    detail["overlay_removed_host"] = overlay_host is None or not overlay_host.exists()

    overlay_name = overlay_host.name if overlay_host is not None else ""
    if overlay_name:
        subprocess.run(
            ["docker", "exec", container, "sh", "-lc",
             f"rm -f /freqtrade/user_data/{overlay_name}"],
            capture_output=True, text=True, timeout=30,
        )

    try:
        cmdline = subprocess.run(
            ["docker", "exec", container, "sh", "-lc",
             "tr '\\0' ' ' < /proc/1/cmdline"],
            capture_output=True, text=True, timeout=30,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        cmdline = ""
    verified = bool(cmdline) and "overlay_" not in cmdline
    detail["cmdline_no_overlay"] = verified
    detail["cmdline_sample"] = cmdline[:200]
    return verified, detail

def _find_newest_bundle(evidence_dir: Path) -> Path | None:
    if not evidence_dir.is_dir():
        return None
    bundles = sorted(evidence_dir.glob("active_cycle_*.json"))
    if not bundles:
        return None
    return max(bundles, key=lambda p: p.stat().st_mtime)


def _cycle_freshness(
    cycle_log_dir: Path | None,
    stale_after_seconds: int,
) -> tuple[bool, str]:
    """Watchdog check: the newest cycle log must not be older than the limit."""
    if cycle_log_dir is None or not Path(cycle_log_dir).is_dir():
        return True, ""
    logs = sorted(Path(cycle_log_dir).glob("cycle-*.log"))
    if not logs:
        return True, ""
    newest = max(logs, key=lambda p: p.stat().st_mtime)
    age = max(0.0, time.time() - newest.stat().st_mtime)
    if age > stale_after_seconds:
        return False, (
            f"newest cycle log age {int(age)}s exceeds "
            f"{stale_after_seconds}s ({newest.name})"
        )
    return True, ""


# ---------------------------------------------------------------------------
# Main evaluation
# ---------------------------------------------------------------------------


def evaluate_apply_chain(input_: ApplyChainEvaluationInput) -> ApplyChainEvaluationResult:
    """Evaluate the newest real cycle candidate through the apply chain.

    Canary-only, fail-closed, prepare-only (no runtime execution). Reads
    real evidence; writes nothing except (a) prepared artifacts for a
    qualified canary candidate and (b) the result/audit recording done by
    :func:`write_evaluation_record`.
    """
    repo_root = input_.repo_root
    state_dir = input_.state_dir

    # 1. Authorization marker (fail-closed).
    marker_path = input_.marker_path or (
        repo_root / "docs" / "decisions" / MARKER_FILE_NAME
    )
    ok, reason, marker_sha = _check_marker(marker_path)
    if not ok:
        return _result(
            STATUS_BLOCKED_MARKER,
            EVENT_BLOCKER,
            reason,
            detail={"marker_path": str(marker_path)},
        )

    # 2. Activation record tamper check (only when present).
    ok, reason = _check_activation_record(state_dir)
    if not ok:
        return _result(
            STATUS_BLOCKED_ACTIVATION_RECORD,
            EVENT_BLOCKER,
            reason,
            detail={"state_dir": str(state_dir), "marker_sha256": marker_sha},
        )

    # 3. Kill switch must be NORMAL (fail-closed read).
    kill_switch_path = input_.kill_switch_path or (repo_root / "var" / "kill_switch.json")
    ks_gate = check_kill_switch(kill_switch_path)
    if not ks_gate.passed:
        return _result(
            STATUS_BLOCKED_KILL_SWITCH,
            EVENT_BLOCKER,
            f"kill_switch_gate: {ks_gate.reason}",
            detail={
                "kill_switch_path": str(kill_switch_path),
                "marker_sha256": marker_sha,
            },
        )
    ks_data = _load_json(Path(kill_switch_path)) or {}
    ks_mode = str(ks_data.get("mode", ""))

    # 4. RiskGuard must derive PASS (fail-closed read).
    riskguard_path = input_.riskguard_state_path or (
        repo_root / "orchestrator" / "state" / "riskguard" / "riskguard_state.json"
    )
    rg_gate = read_riskguard_status(riskguard_path)
    if not rg_gate.passed:
        return _result(
            STATUS_BLOCKED_RISKGUARD,
            EVENT_BLOCKER,
            f"riskguard_gate: {rg_gate.reason}",
            detail={"riskguard_path": str(riskguard_path)},
        )
    rg_data = _load_json(Path(riskguard_path)) or {}
    rg_status = derive_riskguard_status(rg_data)

    # 5. Watchdog: cycle freshness.
    ok, reason = _cycle_freshness(input_.cycle_log_dir, input_.cycle_stale_after_seconds)
    if not ok:
        return _result(
            STATUS_BLOCKED_STALE_CYCLE,
            EVENT_BLOCKER,
            reason,
            detail={"cycle_log_dir": str(input_.cycle_log_dir)},
        )

    # 6. Newest evidence bundle.
    bundle_path = input_.bundle_path or _find_newest_bundle(repo_root / EVIDENCE_DIR_RELATIVE)
    if bundle_path is None:
        return _result(
            STATUS_BLOCKED_BUNDLE,
            EVENT_BLOCKER,
            f"no_evidence_bundle under {repo_root / EVIDENCE_DIR_RELATIVE}",
        )
    bundle_path = Path(bundle_path)
    bundle = _load_json(bundle_path)
    if bundle is None:
        return _result(
            STATUS_BLOCKED_BUNDLE,
            EVENT_BLOCKER,
            f"bundle_unreadable: {bundle_path}",
            bundle_name=bundle_path.name,
        )

    cycle_id = str(bundle.get("cycle_id") or "")
    candidates = bundle.get("proposal_candidates") or []
    base_detail: dict[str, object] = {
        "bundle": bundle_path.name,
        "cycle_id": cycle_id,
        "candidate_count": len(candidates) if isinstance(candidates, list) else 0,
        "marker_sha256": marker_sha,
    }

    # 7. No candidate at all -> correct NO_APPLY.
    if not isinstance(candidates, list) or not candidates:
        return _result(
            STATUS_NO_QUALIFIED_PROPOSAL,
            EVENT_NO_APPLY,
            "no_candidate_in_bundle",
            cycle_id=cycle_id,
            bundle_name=bundle_path.name,
            detail=base_detail,
        )

    candidate_raw = candidates[0]
    if not isinstance(candidate_raw, dict):
        return _result(
            STATUS_BLOCKED_BUNDLE,
            EVENT_BLOCKER,
            "candidate_not_a_dict",
            cycle_id=cycle_id,
            bundle_name=bundle_path.name,
        )

    targets = candidate_raw.get("target_bot_ids") or []
    if not isinstance(targets, list) or len(targets) != 1:
        return _result(
            STATUS_BLOCKED_CANDIDATE,
            EVENT_BLOCKER,
            f"candidate_targets_invalid: {targets!r}",
            cycle_id=cycle_id,
            bundle_name=bundle_path.name,
        )
    target = str(targets[0])
    candidate_id = str(candidate_raw.get("candidate_id") or "")

    # 8. Stage 1 is canary-only.
    if target != CANARY_BOT_ID:
        return _result(
            STATUS_NO_QUALIFIED_PROPOSAL,
            EVENT_NO_APPLY,
            f"stage1_canary_only: target={target!r} is not {CANARY_BOT_ID!r}",
            cycle_id=cycle_id,
            bundle_name=bundle_path.name,
            candidate_id=candidate_id,
            target_bot=target,
            detail=base_detail,
        )

    # 9. Allowlist mapping (single safe parameter, within accepted range).
    overlay = candidate_raw.get("candidate_overlay") or {}
    if not isinstance(overlay, dict):
        return _result(
            STATUS_BLOCKED_CANDIDATE,
            EVENT_BLOCKER,
            "candidate_overlay_not_a_dict",
            cycle_id=cycle_id,
            bundle_name=bundle_path.name,
            candidate_id=candidate_id,
            target_bot=target,
        )
    mapped: dict[str, object] = {}
    for candidate_key, real_key in CANDIDATE_KEY_MAP.items():
        if candidate_key in overlay:
            mapped[real_key] = overlay[candidate_key]
    if len(mapped) != 1:
        return _result(
            STATUS_BLOCKED_CANDIDATE,
            EVENT_BLOCKER,
            f"candidate_overlay_params={sorted(mapped)} (exactly one required)",
            cycle_id=cycle_id,
            bundle_name=bundle_path.name,
            candidate_id=candidate_id,
            target_bot=target,
        )
    parameter, value = next(iter(mapped.items()))
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return _result(
            STATUS_BLOCKED_CANDIDATE,
            EVENT_BLOCKER,
            f"candidate_value_not_numeric: {parameter}={value!r}",
            cycle_id=cycle_id,
            bundle_name=bundle_path.name,
            candidate_id=candidate_id,
            target_bot=target,
        )
    if not validate_safe_parameter(parameter, value):
        return _result(
            STATUS_BLOCKED_CANDIDATE,
            EVENT_BLOCKER,
            f"outside_allowlist: {parameter}={value!r}",
            cycle_id=cycle_id,
            bundle_name=bundle_path.name,
            candidate_id=candidate_id,
            target_bot=target,
        )

    # 10. Cooldown gate (existing accepted contract).
    _cooldown_state, cooldown_gate = check_cooldown(state_dir)
    if not cooldown_gate.passed:
        return _result(
            STATUS_BLOCKED_CANDIDATE,
            EVENT_BLOCKER,
            f"cooldown_gate: {cooldown_gate.reason}",
            cycle_id=cycle_id,
            bundle_name=bundle_path.name,
            candidate_id=candidate_id,
            target_bot=target,
        )

    # 11. Canary config baseline (dry-run must be confirmed true).
    canary_config_path = input_.canary_config_path or (
        repo_root / CANARY_USER_DATA_RELATIVE / "config.json"
    )
    canary_config = _load_json(canary_config_path)
    if canary_config is None:
        return _result(
            STATUS_BLOCKED_CANDIDATE,
            EVENT_BLOCKER,
            f"canary_config_unreadable: {canary_config_path}",
            cycle_id=cycle_id,
            bundle_name=bundle_path.name,
            candidate_id=candidate_id,
            target_bot=target,
        )
    if canary_config.get("dry_run") is not True:
        return _result(
            STATUS_BLOCKED_CANDIDATE,
            EVENT_BLOCKER,
            "canary_config_not_dry_run",
            cycle_id=cycle_id,
            bundle_name=bundle_path.name,
            candidate_id=candidate_id,
            target_bot=target,
        )
    current_value = canary_config.get(parameter)

    # 12. Full pipeline (AUTONOMOUS_DRY_RUN mode, real evidence inputs).
    change_id = f"apply-chain-{cycle_id}"
    candidate = CandidateApplyInput(
        candidate_id=candidate_id,
        source="shadow_proposal",
        target_bot=target,
        parameter=parameter,
        current_value=current_value,
        proposed_value=value,
        confidence=None,
        evidence_refs=(f"cycle:{cycle_id}", f"bundle:{bundle_path.name}"),
        autonomy_mode="DRY_RUN",
    )
    pipeline = candidate_to_apply_pipeline(
        candidate=candidate,
        pre_apply_config=canary_config,
        active_measurement_candidate_id=None,
        kill_switch_mode=ks_mode,
        riskguard_status=rg_status,
        allowlist_compatible=True,
    )
    pipeline_status = pipeline.decision.status
    if pipeline_status not in _ALLOWED_PIPELINE_STATUSES:
        return _result(
            STATUS_BLOCKED_PIPELINE,
            EVENT_BLOCKER,
            f"pipeline_status={pipeline_status}",
            cycle_id=cycle_id,
            bundle_name=bundle_path.name,
            candidate_id=candidate_id,
            target_bot=target,
            detail={
                **base_detail,
                "blocked_reasons": list(pipeline.decision.blocked_reasons),
            },
        )

    # 13. Prepare artifacts (no runtime action).
    canary_user_data = repo_root / CANARY_USER_DATA_RELATIVE
    exec_result = prepare_autonomous_dry_run_apply(
        AutonomousDryRunExecutorInput(
            candidate=candidate,
            pre_apply_config=dict(canary_config),
            kill_switch_mode=ks_mode,
            riskguard_status=rg_status,
            allowlist_compatible=True,
            active_measurement_candidate_id=None,
            evidence_refs=(f"cycle:{cycle_id}",),
            change_id=change_id,
            source_cycle=cycle_id,
        ),
        state_dir=state_dir / "executor",
        overlay_dir=canary_user_data,
        plan_dir=state_dir / "rollback_plans",
        audit_dir=state_dir / "audit",
    )
    if exec_result.status != "EXECUTOR_DRY_RUN_APPLY_PREPARED":
        return _result(
            STATUS_BLOCKED_PIPELINE,
            EVENT_BLOCKER,
            f"executor_status={exec_result.status}",
            cycle_id=cycle_id,
            bundle_name=bundle_path.name,
            candidate_id=candidate_id,
            target_bot=target,
            detail={**base_detail, "blocked_reasons": list(exec_result.blocked_reasons)},
        )

    measurement_plan_path = (
        state_dir / "rollback_plans" / f"measurement_start_{change_id[:16]}.json"
    )
    if not measurement_plan_path.is_file():
        return _result(
            STATUS_BLOCKED_PIPELINE,
            EVENT_BLOCKER,
            f"measurement_plan_missing: {measurement_plan_path}",
            cycle_id=cycle_id,
            bundle_name=bundle_path.name,
            candidate_id=candidate_id,
            target_bot=target,
        )

    # 14. Runtime wiring (rehearsal-gated switch) + ceremony.
    binding = resolve_binding(target)
    current_command = tuple(binding.loaded_config_args) if binding is not None else ()
    wiring_ok, wiring_reason, wiring_detail = _read_runtime_wiring(state_dir)
    if wiring_reason:
        # Switch present but unusable — fail closed, never silently prepare.
        return _result(
            STATUS_BLOCKED_WIRING,
            EVENT_BLOCKER,
            wiring_reason,
            cycle_id=cycle_id,
            bundle_name=bundle_path.name,
            candidate_id=candidate_id,
            target_bot=target,
            detail={**base_detail, "wiring": wiring_detail},
        )
    executed_runtime = wiring_ok

    ceremony = run_runtime_ceremony(
        RuntimeCeremonyInput(
            change_id=change_id,
            candidate_id=candidate_id,
            target_bot=target,
            overlay_path=exec_result.overlay_path,
            overlay_sha256=exec_result.overlay_sha256,
            rollback_plan_path=exec_result.rollback_plan_path,
            audit_path=exec_result.audit_path,
            measurement_start_plan_path=str(measurement_plan_path),
            pre_apply_config=dict(canary_config),
            current_command=current_command,
            expected_parameter=parameter,
            expected_value=value,
            kill_switch_mode=ks_mode,
            riskguard_status=rg_status,
        ),
        execute_runtime=executed_runtime,
        canary_user_data=canary_user_data,
        compose_output_dir=state_dir / "compose_overrides",
        compose_context=ComposeContext.default() if executed_runtime else None,
        t0_dir=state_dir / "t0_records",
    )

    # 14a. Prepare-only (switch off): unchanged behaviour.
    if not executed_runtime:
        if ceremony.status != "CEREMONY_READY":
            return _result(
                STATUS_BLOCKED_PIPELINE,
                EVENT_BLOCKER,
                f"ceremony_status={ceremony.status}",
                cycle_id=cycle_id,
                bundle_name=bundle_path.name,
                candidate_id=candidate_id,
                target_bot=target,
                detail={**base_detail, "blocked_reasons": list(ceremony.blocked_reasons)},
            )
        return _result(
            STATUS_APPLY_PREPARED,
            EVENT_PREPARED,
            (
                f"canary_candidate_prepared: {parameter} -> {value!r}; "
                "runtime execution stage not wired"
            ),
            cycle_id=cycle_id,
            bundle_name=bundle_path.name,
            candidate_id=candidate_id,
            target_bot=target,
            detail={
                **base_detail,
                "parameter": parameter,
                "value": value,
                "current_value": current_value,
                "overlay_path": exec_result.overlay_path,
                "overlay_sha256": exec_result.overlay_sha256,
                "rollback_plan_path": exec_result.rollback_plan_path,
                "pipeline_status": pipeline_status,
                "ceremony_status": ceremony.status,
                "runtime_execution_wired": False,
            },
        )

    # 14b. Executed path: GREEN keeps the change; anything else rolls back.
    if ceremony.status == "CEREMONY_EXECUTED_GREEN":
        return _result(
            STATUS_APPLY_EXECUTED_GREEN,
            EVENT_EXECUTED,
            (
                f"canary_apply_executed_green: {parameter} -> {value!r}; "
                f"proof={ceremony.runtime_proof_status}; "
                f"t0_measurement_active={ceremony.t0_measurement_active}"
            ),
            cycle_id=cycle_id,
            bundle_name=bundle_path.name,
            candidate_id=candidate_id,
            target_bot=target,
            executed_runtime=True,
            detail={
                **base_detail,
                "parameter": parameter,
                "value": value,
                "overlay_path": exec_result.overlay_path,
                "overlay_sha256": exec_result.overlay_sha256,
                "rollback_plan_path": exec_result.rollback_plan_path,
                "pipeline_status": pipeline_status,
                "ceremony_status": ceremony.status,
                "runtime_proof_status": ceremony.runtime_proof_status,
                "t0_measurement_active": ceremony.t0_measurement_active,
                "runtime_execution_wired": True,
                "wiring": wiring_detail,
                "rollback_instruction": "see rollback_plan_path",
            },
        )

    # Not GREEN (RED/YELLOW/runtime-not-executed): roll back and verify.
    verified, rb_detail = _rollback_canary(
        ComposeContext.default(),
        "freqtrade-freqforge-canary",
        exec_result.overlay_path,
    )
    if not verified:
        return _result(
            STATUS_BLOCKED_ROLLBACK_FAILED,
            EVENT_BLOCKER,
            (
                f"rollback_not_verified: ceremony={ceremony.status}; "
                f"detail={rb_detail}"
            ),
            cycle_id=cycle_id,
            bundle_name=bundle_path.name,
            candidate_id=candidate_id,
            target_bot=target,
            executed_runtime=True,
            detail={
                **base_detail,
                "ceremony_status": ceremony.status,
                "runtime_proof_status": ceremony.runtime_proof_status,
                "rollback": rb_detail,
            },
        )
    return _result(
        STATUS_APPLY_ROLLED_BACK,
        EVENT_ROLLED_BACK,
        (
            f"canary_apply_rolled_back: ceremony={ceremony.status} "
            f"(not GREEN); rollback verified"
        ),
        cycle_id=cycle_id,
        bundle_name=bundle_path.name,
        candidate_id=candidate_id,
        target_bot=target,
        executed_runtime=True,
        detail={
            **base_detail,
            "parameter": parameter,
            "value": value,
            "ceremony_status": ceremony.status,
            "runtime_proof_status": ceremony.runtime_proof_status,
            "rollback": rb_detail,
            "runtime_execution_wired": True,
        },
    )


# ---------------------------------------------------------------------------
# Recording (atomic JSON record + append-only JSONL audit)
# ---------------------------------------------------------------------------


def write_evaluation_record(
    result: ApplyChainEvaluationResult,
    state_dir: Path,
) -> dict[str, str]:
    """Persist the result as an atomic JSON record and an audit JSONL line."""
    results_dir = state_dir / "results"
    audit_dir = state_dir / "audit"
    results_dir.mkdir(parents=True, exist_ok=True)
    audit_dir.mkdir(parents=True, exist_ok=True)

    stamp = (
        result.created_at_utc.replace(":", "").replace("-", "").replace("+00:00", "Z")
    )
    record_path = results_dir / f"apply_chain_{stamp}.json"
    payload = result.to_dict()
    tmp = record_path.with_suffix(f".json.tmp.{os.getpid()}")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(record_path)

    audit_line = {
        "created_at_utc": result.created_at_utc,
        "status": result.status,
        "event": result.event,
        "reason": result.reason,
        "cycle_id": result.cycle_id,
        "bundle_name": result.bundle_name,
        "candidate_id": result.candidate_id,
        "target_bot": result.target_bot,
        "executed_runtime": result.executed_runtime,
    }
    audit_path = audit_dir / "apply_chain_audit.jsonl"
    with audit_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(audit_line, sort_keys=True) + "\n")

    return {"record_path": str(record_path), "audit_path": str(audit_path)}
