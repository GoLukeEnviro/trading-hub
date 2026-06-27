r"""Rollback Rehearsal Gate — Phase 5A.

Provides the **rollback planning layer** that mirrors the apply chain but
in reverse. This module builds a ``RollbackPlan``, checks rollback-readiness
gates (G1-G10), and renders a compose preview — all **read-only** with no
Docker, no subprocess, and no runtime mutation.

Architecture
------------
::

    plan_canary_rollback_from_overlay()  → RollbackPlan       ← THIS
    check_rollback_gate()                → RollbackGateResult ← THIS
    build_rollback_preview()             → RollbackPreview    ← THIS
    render_rollback_compose_preview()    → str (YAML)         ← THIS
    execute_canary_rollback()            → HARD-BLOCKED       ← THIS

Safety invariants
-----------------
- Canary-only: ``bot_id`` must be ``freqtrade-freqforge-canary``.
- ``dry_run`` must be ``True`` in the pre-apply config.
- Rollback means **command-only**: remove overlay ``--config``, keep base
  ``--config``. Does NOT delete overlay files.
- All gates must pass before ``ready=True``.
- ``execution_enabled`` is always forced to ``False`` in Phase 5A.
- No subprocess, no Docker, no filesystem writes.
- Measurement state (T2/T3) is never touched.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from si_v2.apply_actuator.restart_with_overlay import (
    CANARY_BOT_ID,
    CANARY_CONTAINER_NAME,
    CANARY_SERVICE_NAME,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EXPECTED_BASELINE_MAX_OPEN_TRADES: Final[int] = 3
"""The pre-apply baseline value for ``max_open_trades`` to restore on rollback."""

CANARY_COMPOSE_SERVICE: Final[str] = CANARY_SERVICE_NAME
"""Docker Compose service name for the canary."""

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RollbackPlan:
    """Deterministic plan for rolling back the canary to its base config.

    All fields are populated at plan-creation time. Immutable and JSON-
    serialisable via ``to_dict()``.
    """

    plan_id: str
    bot_id: str
    container_name: str
    service_name: str | None
    candidate_id: str
    current_overlay_path: str | None
    current_overlay_sha256: str | None
    base_config_container_path: str
    current_command: tuple[str, ...]
    rollback_command: tuple[str, ...]
    expected_before_parameter: str
    expected_before_value: object
    expected_after_parameter: str
    expected_after_value: object
    dry_run_required: bool
    rollback_reason: str
    safety_checks: dict[str, bool]
    blocked_reasons: tuple[str, ...]
    created_at_utc: str

    def to_dict(self) -> dict[str, object]:
        return {
            "plan_id": self.plan_id,
            "bot_id": self.bot_id,
            "container_name": self.container_name,
            "service_name": self.service_name,
            "candidate_id": self.candidate_id,
            "current_overlay_path": self.current_overlay_path,
            "current_overlay_sha256": self.current_overlay_sha256,
            "base_config_container_path": self.base_config_container_path,
            "current_command": list(self.current_command),
            "rollback_command": list(self.rollback_command),
            "expected_before_parameter": self.expected_before_parameter,
            "expected_before_value": self.expected_before_value,
            "expected_after_parameter": self.expected_after_parameter,
            "expected_after_value": self.expected_after_value,
            "dry_run_required": self.dry_run_required,
            "rollback_reason": self.rollback_reason,
            "safety_checks": dict(self.safety_checks),
            "blocked_reasons": list(self.blocked_reasons),
            "created_at_utc": self.created_at_utc,
        }


@dataclass(frozen=True)
class RollbackGateResult:
    """Result of rollback gate evaluation.

    ``ready`` is ``True`` only when all 10 gates pass.
    """

    ready: bool
    gate_results: dict[str, bool]
    blocked_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "ready": self.ready,
            "gate_results": dict(self.gate_results),
            "blocked_reasons": list(self.blocked_reasons),
        }


@dataclass(frozen=True)
class RollbackPreview:
    """Read-only preview of a rollback operation."""

    plan_id: str
    bot_id: str
    service_name: str | None
    current_command: tuple[str, ...]
    rollback_command: tuple[str, ...]
    current_overlay_path: str | None
    dry_run_confirmed: bool
    rollback_gate_ready: bool
    blocked_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "plan_id": self.plan_id,
            "bot_id": self.bot_id,
            "service_name": self.service_name,
            "current_command": list(self.current_command),
            "rollback_command": list(self.rollback_command),
            "current_overlay_path": self.current_overlay_path,
            "dry_run_confirmed": self.dry_run_confirmed,
            "rollback_gate_ready": self.rollback_gate_ready,
            "blocked_reasons": list(self.blocked_reasons),
        }


@dataclass(frozen=True)
class RollbackExecutionResult:
    """Result of a rollback execution attempt — hard-blocked in Phase 5A."""

    status: str  # Always "NOT_IMPLEMENTED" in Phase 5A
    reason: str
    plan_id: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "reason": self.reason,
            "plan_id": self.plan_id,
        }


# ---------------------------------------------------------------------------
# Command helpers
# ---------------------------------------------------------------------------


def _parse_command(command: Sequence[str]) -> tuple[str, ...]:
    return tuple(str(arg) for arg in command)


def _build_rollback_command_from_overlay(
    current_command: tuple[str, ...],
) -> tuple[str, ...]:
    """Remove all ``--config`` args whose value contains ``overlay_``.

    Preserves the first ``--config`` (the base config) and all non-config args
    (strategy, etc.).
    """
    result: list[str] = []
    skip_next = False
    for i, arg in enumerate(current_command):
        if skip_next:
            skip_next = False
            continue
        if arg == "--config" and i + 1 < len(current_command):
            next_val = current_command[i + 1]
            if "overlay_" in next_val:
                skip_next = True
                continue
        result.append(arg)
    return tuple(result)


def _find_overlay_config_args(
    command: tuple[str, ...],
) -> list[int]:
    """Return indices of ``--config`` arguments that point to overlay files."""
    indices: list[int] = []
    for i, arg in enumerate(command):
        if arg == "--config" and i + 1 < len(command) and "overlay_" in command[i + 1]:
                indices.append(i)
    return indices


# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------


def plan_canary_rollback_from_overlay(
    *,
    bot_id: str,
    candidate_id: str,
    current_command: Sequence[str],
    base_config_container_path: str,
    current_overlay_path: Path | None,
    expected_before_parameter: str,
    expected_before_value: object,
    expected_after_parameter: str,
    expected_after_value: object,
    pre_apply_config: Mapping[str, object],
    rollback_reason: str,
) -> RollbackPlan:
    """Build a read-only rollback plan for the canary bot.

    This function performs **zero** side effects:
    - No subprocess calls
    - No Docker interaction
    - No filesystem writes
    - No config mutations
    - No overlay deletion
    """
    blocked: list[str] = []
    safety_checks: dict[str, bool] = {}

    # 1. Canary-only check
    bot_ok = bot_id == CANARY_BOT_ID
    safety_checks["canary_only"] = bot_ok
    if not bot_ok:
        blocked.append(f"not_canary: bot_id={bot_id!r} is not {CANARY_BOT_ID!r}")

    # 2. dry_run check
    dry_run_val = pre_apply_config.get("dry_run")
    dry_ok = dry_run_val is True
    safety_checks["dry_run_true"] = dry_ok
    if not dry_ok:
        msg = "dry_run_not_found" if dry_run_val is None else f"dry_run_not_true: {dry_run_val!r}"
        blocked.append(msg)

    # 3. Parse current command
    cmd = _parse_command(current_command)
    safety_checks["current_command_parsed"] = True

    # 4. Check current command has overlay
    overlay_indices = _find_overlay_config_args(cmd)
    has_overlay = len(overlay_indices) > 0
    safety_checks["current_command_has_overlay"] = has_overlay
    if not has_overlay:
        blocked.append("current_command_no_overlay")
    if not cmd:
        blocked.append("current_command_empty")

    # 5. Build rollback command
    rollback_cmd = _build_rollback_command_from_overlay(cmd)
    rollback_removes = not _find_overlay_config_args(rollback_cmd)
    safety_checks["rollback_removes_overlay"] = rollback_removes
    if not rollback_removes:
        blocked.append("rollback_still_has_overlay")

    # 6. Rollback keeps base config
    has_base = "--config" in rollback_cmd
    safety_checks["rollback_keeps_base_config"] = has_base
    if not has_base:
        blocked.append("rollback_missing_base_config")

    # 7. Rollback keeps strategy unchanged — detect strategy args
    strategy_args = [
        cmd[i + 1] for i, a in enumerate(cmd)
        if a == "--strategy" and i + 1 < len(cmd)
    ]
    rollback_strategy = [
        rollback_cmd[i + 1] for i, a in enumerate(rollback_cmd)
        if a == "--strategy" and i + 1 < len(rollback_cmd)
    ]
    strategy_unchanged = strategy_args == rollback_strategy
    safety_checks["rollback_keeps_strategy"] = strategy_unchanged
    if not strategy_unchanged:
        blocked.append("rollback_changes_strategy")

    # 8. Overlay path / SHA (optional)
    overlay_path_str: str | None = str(current_overlay_path) if current_overlay_path else None
    overlay_sha: str | None = None
    if current_overlay_path and current_overlay_path.exists():
        import hashlib
        overlay_sha = hashlib.sha256(current_overlay_path.read_bytes()).hexdigest()

    # 9. Reason
    reason_ok = bool(rollback_reason and rollback_reason.strip())
    safety_checks["rollback_reason_present"] = reason_ok
    if not reason_ok:
        blocked.append("rollback_reason_missing")

    # 10. Plan ID
    plan_id = f"rollback_{candidate_id[:16]}" if candidate_id else "rollback_unknown"

    return RollbackPlan(
        plan_id=plan_id,
        bot_id=bot_id,
        container_name=CANARY_CONTAINER_NAME,
        service_name=CANARY_SERVICE_NAME,
        candidate_id=candidate_id,
        current_overlay_path=overlay_path_str,
        current_overlay_sha256=overlay_sha,
        base_config_container_path=base_config_container_path,
        current_command=cmd,
        rollback_command=rollback_cmd,
        expected_before_parameter=expected_before_parameter,
        expected_before_value=expected_before_value,
        expected_after_parameter=expected_after_parameter,
        expected_after_value=expected_after_value,
        dry_run_required=True,
        rollback_reason=rollback_reason,
        safety_checks=safety_checks,
        blocked_reasons=tuple(blocked),
        created_at_utc=datetime.now(UTC).isoformat(),
    )


# ---------------------------------------------------------------------------
# Gate checker
# ---------------------------------------------------------------------------


def _g1_plan_exists(plan: RollbackPlan | None) -> tuple[bool, str]:
    if plan is None:
        return False, "G1: plan is None"
    return True, ""


def _g2_bot_is_canary(plan: RollbackPlan) -> tuple[bool, str]:
    if plan.bot_id == CANARY_BOT_ID:
        return True, ""
    return False, f"G2: bot_id={plan.bot_id!r} is not {CANARY_BOT_ID!r}"


def _g3_current_has_overlay(plan: RollbackPlan) -> tuple[bool, str]:
    cmd = " ".join(plan.current_command)
    if "--config" in cmd and "overlay_" in cmd:
        return True, ""
    return False, "G3: current_command missing overlay config"


def _g4_rollback_removes_overlay(plan: RollbackPlan) -> tuple[bool, str]:
    cmd = " ".join(plan.rollback_command)
    if "overlay_" in cmd:
        return False, "G4: rollback_command still contains overlay"
    return True, ""


def _g5_rollback_keeps_base(plan: RollbackPlan) -> tuple[bool, str]:
    if "--config" in plan.rollback_command:
        return True, ""
    return False, "G5: rollback_command missing base --config"


def _g6_dry_run_true(pre_apply_config: Mapping[str, object]) -> tuple[bool, str]:
    val = pre_apply_config.get("dry_run")
    if val is True:
        return True, ""
    if val is None:
        return False, "G6: dry_run key missing from pre_apply_config"
    return False, f"G6: dry_run={val!r} (expected True)"


def _g7_runtime_matches_before(
    current_runtime_value: object,
    expected_before_value: object,
) -> tuple[bool, str]:
    if current_runtime_value == expected_before_value:
        return True, ""
    return False, f"G7: current_runtime={current_runtime_value!r} != expected_before={expected_before_value!r}"


def _g8_after_matches_baseline(
    expected_after_value: object,
    baseline_value: object = EXPECTED_BASELINE_MAX_OPEN_TRADES,
) -> tuple[bool, str]:
    if expected_after_value == baseline_value:
        return True, ""
    return False, f"G8: expected_after={expected_after_value!r} != baseline={baseline_value!r}"


def _g9_reason_present(plan: RollbackPlan) -> tuple[bool, str]:
    if plan.rollback_reason and plan.rollback_reason.strip():
        return True, ""
    return False, "G9: rollback_reason is empty"


def _g10_execution_still_blocked(execution_enabled: bool) -> tuple[bool, str]:
    if execution_enabled:
        return False, "G10: runtime_execution_not_allowed_in_phase_5a"
    return True, ""


def check_rollback_gate(
    plan: RollbackPlan,
    *,
    pre_apply_config: Mapping[str, object],
    current_runtime_value: object,
    execution_enabled: bool = False,
) -> RollbackGateResult:
    """Evaluate all 10 rollback gates.

    Pure Python — no subprocess, no Docker, no filesystem writes.
    """
    blocked: list[str] = []
    gates: dict[str, bool] = {}

    # G1
    ok, reason = _g1_plan_exists(plan)
    gates["plan_exists"] = ok
    if not ok:
        blocked.append(reason)

    if ok:
        ok, reason = _g2_bot_is_canary(plan)
        gates["bot_is_canary"] = ok
        if not ok:
            blocked.append(reason)
    else:
        gates["bot_is_canary"] = False

    if ok:
        ok, reason = _g3_current_has_overlay(plan)
        gates["current_command_contains_overlay"] = ok
        if not ok:
            blocked.append(reason)
    else:
        gates["current_command_contains_overlay"] = False

    if ok:
        ok, reason = _g4_rollback_removes_overlay(plan)
        gates["rollback_command_removes_overlay"] = ok
        if not ok:
            blocked.append(reason)
    else:
        gates["rollback_command_removes_overlay"] = False

    if ok:
        ok, reason = _g5_rollback_keeps_base(plan)
        gates["rollback_command_keeps_base_config"] = ok
        if not ok:
            blocked.append(reason)
    else:
        gates["rollback_command_keeps_base_config"] = False

    # G6 — independent
    ok, reason = _g6_dry_run_true(pre_apply_config)
    gates["dry_run_true"] = ok
    if not ok:
        blocked.append(reason)

    # G7 — independent
    ok, reason = _g7_runtime_matches_before(current_runtime_value, plan.expected_before_value)
    gates["current_runtime_matches_expected_before"] = ok
    if not ok:
        blocked.append(reason)

    # G8 — independent
    ok, reason = _g8_after_matches_baseline(plan.expected_after_value)
    gates["expected_after_matches_baseline"] = ok
    if not ok:
        blocked.append(reason)

    # G9 — independent
    ok, reason = _g9_reason_present(plan)
    gates["rollback_reason_present"] = ok
    if not ok:
        blocked.append(reason)

    # G10 — independent
    ok, reason = _g10_execution_still_blocked(execution_enabled)
    gates["runtime_execution_still_blocked"] = ok
    if not ok:
        blocked.append(reason)

    return RollbackGateResult(
        ready=len(blocked) == 0,
        gate_results=gates,
        blocked_reasons=tuple(blocked),
    )


# ---------------------------------------------------------------------------
# Preview builder
# ---------------------------------------------------------------------------


def build_rollback_preview(
    plan: RollbackPlan,
    gate_result: RollbackGateResult,
) -> RollbackPreview:
    """Build a read-only rollback preview."""
    return RollbackPreview(
        plan_id=plan.plan_id,
        bot_id=plan.bot_id,
        service_name=plan.service_name,
        current_command=plan.current_command,
        rollback_command=plan.rollback_command,
        current_overlay_path=plan.current_overlay_path,
        dry_run_confirmed=gate_result.gate_results.get("dry_run_true", False),
        rollback_gate_ready=gate_result.ready,
        blocked_reasons=gate_result.blocked_reasons,
    )


# ---------------------------------------------------------------------------
# Compose preview
# ---------------------------------------------------------------------------


def render_rollback_compose_preview(
    preview: RollbackPreview,
) -> str:
    """Render a Docker Compose override YAML preview for the rollback.

    Returns a YAML-formatted string. Does NOT write any file. Does NOT
    execute any Docker/Compose command.
    """
    lines: list[str] = []
    lines.append("# SI-v2 Canary Rollback — Docker Compose Override Preview")
    lines.append("# Generated by: rollback_rehearsal.py:render_rollback_compose_preview()")
    lines.append("# This file is a READ-ONLY PREVIEW. No file was written.")
    lines.append("#")
    lines.append(f"# Plan ID: {preview.plan_id}")
    lines.append(f"# Bot: {preview.bot_id}")
    lines.append(f"# Overlay path: {preview.current_overlay_path or 'none'}")
    lines.append(f"# Dry-run confirmed: {preview.dry_run_confirmed}")
    lines.append(f"# Rollback gate ready: {preview.rollback_gate_ready}")
    lines.append("#")
    lines.append("services:")
    lines.append(f"  {preview.service_name}:")
    lines.append("    command:")
    for arg in preview.rollback_command:
        lines.append(f"      - {arg}")
    lines.append("")
    lines.append("# Note: This is a DESIGN DOCUMENT. Execution requires:")
    lines.append("#   - Phase 5B Rollback Executor Sprint")
    lines.append("#   - Separate L3 token")
    lines.append("#   - RollbackProof GREEN after restart")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Execution stub — hard-blocked
# ---------------------------------------------------------------------------


def execute_canary_rollback(
    plan: RollbackPlan,
    *,
    token: str | None = None,
    execute: bool = False,
) -> RollbackExecutionResult:
    """Execute a rollback — **intentionally hard-blocked in Phase 5A**.

    Always returns ``NOT_IMPLEMENTED``. A future sprint may implement
    actual rollback execution.
    """
    _ = token
    _ = execute
    return RollbackExecutionResult(
        status="NOT_IMPLEMENTED",
        reason=(
            "Rollback execution is intentionally not implemented "
            "in Phase 5A. Requires separate L3 approval and a "
            "rollback executor sprint."
        ),
        plan_id=plan.plan_id,
    )
