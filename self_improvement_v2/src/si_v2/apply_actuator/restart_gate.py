r"""Restart gate checker and Compose/Recreate plan preview — Phase 3B-B.

This module provides the **second planning layer** after ``restart_with_overlay.py``.
It takes a validated ``RestartPlan`` and:

  1. Checks restart-readiness gates (G1-G10).
  2. Builds a ``CanaryRecreatePlan`` that fully describes a controlled restart.
  3. Renders a **preview** of the Docker Compose override file (no write,
     no execution).

Architecture
------------
::

    plan_canary_restart_with_overlay()   → RestartPlan (Phase 3B-A)
    check_restart_gate(plan)              → RestartGateResult  ← THIS
    build_canary_recreate_plan(plan, gate) → CanaryRecreatePlan ← THIS
    render_compose_override_preview(plan)  → str (YAML preview) ← THIS
    ---
    execute_canary_restart_with_overlay()  → NOT_IMPLEMENTED (Phase 3C)

Safety invariants
-----------------
- All 10 restart gates must pass before ``ready=True``.
- ``execution_enabled`` is always forced to ``False`` in Phase 3B-B.
- Canary-only: only ``freqtrade-freqforge-canary`` accepted.
- ``dry_run`` must be ``True``; forbidden keys blocked.
- No subprocess, no Docker, no filesystem writes in this module.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from si_v2.apply_actuator.restart_with_overlay import (
    CANARY_BOT_ID,
    CANARY_CONTAINER_NAME,
    CANARY_SERVICE_NAME,
    RESTART_FORBIDDEN_KEYS,
    RestartPlan,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CANARY_COMPOSE_SERVICE: Final[str] = CANARY_SERVICE_NAME
"""Docker Compose service name for the canary (matches docker-compose.yml)."""

RESTART_GATE_NAMES: Final[tuple[str, ...]] = (
    "plan_exists",
    "plan_bot_is_canary",
    "overlay_path_is_canary_user_data",
    "overlay_sha_matches_plan",
    "dry_run_true",
    "forbidden_keys_absent",
    "proposed_command_contains_base_config",
    "proposed_command_contains_overlay_config",
    "rollback_command_available",
    "runtime_execution_still_blocked",
)
"""All 10 restart gates in evaluation order."""

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RestartGateResult:
    """Result of restart gate evaluation.

    ``ready`` is ``True`` only when all gates pass and no execution attempt
    is detected.
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
class CanaryRecreatePlan:
    """A fully validated, ready-to-audit canary recreate plan.

    This plan describes what WOULD happen during a controlled restart,
    without executing anything. It is the final preview before an L3-gated
    runtime executor sprint.
    """

    plan_id: str
    bot_id: str
    container_name: str
    service_name: str
    compose_service: str | None
    proposed_command: tuple[str, ...]
    rollback_command: tuple[str, ...]
    overlay_container_path: str
    overlay_sha256: str
    dry_run_confirmed: bool
    restart_gate_ready: bool
    blocked_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "plan_id": self.plan_id,
            "bot_id": self.bot_id,
            "container_name": self.container_name,
            "service_name": self.service_name,
            "compose_service": self.compose_service,
            "proposed_command": list(self.proposed_command),
            "rollback_command": list(self.rollback_command),
            "overlay_container_path": self.overlay_container_path,
            "overlay_sha256": self.overlay_sha256,
            "dry_run_confirmed": self.dry_run_confirmed,
            "restart_gate_ready": self.restart_gate_ready,
            "blocked_reasons": list(self.blocked_reasons),
        }


# ---------------------------------------------------------------------------
# Gate checkers
# ---------------------------------------------------------------------------


def _g1_plan_exists(plan: RestartPlan | None) -> tuple[bool, str]:
    if plan is None:
        return False, "G1: plan is None"
    return True, ""


def _g2_plan_bot_is_canary(plan: RestartPlan) -> tuple[bool, str]:
    if plan.bot_id == CANARY_BOT_ID:
        return True, ""
    return False, f"G2: bot_id={plan.bot_id!r} is not {CANARY_BOT_ID!r}"


def _g3_overlay_path_is_canary_user_data(
    plan: RestartPlan,
) -> tuple[bool, str]:
    if not plan.host_overlay_path:
        return False, "G3: host_overlay_path is empty"
    path = Path(plan.host_overlay_path)
    if not path.name.startswith("overlay_"):
        return False, f"G3: overlay filename does not start with 'overlay_': {path.name}"
    return True, ""


def _g4_overlay_sha_matches_plan(plan: RestartPlan) -> tuple[bool, str]:
    if not plan.overlay_sha256:
        return False, "G4: overlay_sha256 is empty"
    if len(plan.overlay_sha256) != 64:
        return False, f"G4: overlay_sha256 has unexpected length ({len(plan.overlay_sha256)})"
    return True, ""


def _g5_dry_run_true(pre_apply_config: Mapping[str, object]) -> tuple[bool, str]:
    dry_run_val = pre_apply_config.get("dry_run")
    if dry_run_val is True:
        return True, ""
    if dry_run_val is None:
        return False, "G5: dry_run key missing from pre_apply_config"
    return False, f"G5: dry_run={dry_run_val!r} (expected True)"


def _g6_forbidden_keys_absent(
    overlay_payload: Mapping[str, object],
) -> tuple[bool, list[str]]:
    blocked: list[str] = []
    for key in overlay_payload:
        if key in RESTART_FORBIDDEN_KEYS:
            blocked.append(f"G6: forbidden_key={key!r}")
    return (len(blocked) == 0, blocked)


def _g7_proposed_command_contains_base_config(
    plan: RestartPlan,
) -> tuple[bool, str]:
    cmd = " ".join(plan.proposed_command)
    if "--config /freqtrade/user_data/config.json" in cmd:
        return True, ""
    return False, "G7: proposed_command missing base config path"


def _g8_proposed_command_contains_overlay_config(
    plan: RestartPlan,
) -> tuple[bool, str]:
    cmd = " ".join(plan.proposed_command)
    if "--config /freqtrade/user_data/overlay_" in cmd:
        return True, ""
    return False, "G8: proposed_command missing overlay config path"


def _g9_rollback_command_available(plan: RestartPlan) -> tuple[bool, str]:
    if not plan.rollback_command:
        return False, "G9: rollback_command is empty"
    return True, ""


def _g10_runtime_execution_still_blocked(
    execution_enabled: bool,
) -> tuple[bool, str]:
    if execution_enabled:
        return (
            False,
            "G10: runtime_execution_not_allowed_in_phase_3b_b",
        )
    return True, ""


# ---------------------------------------------------------------------------
# Gate evaluation
# ---------------------------------------------------------------------------


def check_restart_gate(
    plan: RestartPlan,
    *,
    overlay_payload: Mapping[str, object],
    pre_apply_config: Mapping[str, object],
    execution_enabled: bool = False,
) -> RestartGateResult:
    """Evaluate all 10 restart gates against a validated RestartPlan.

    Pure Python — no subprocess, no Docker, no filesystem writes.

    Args:
        plan: A validated RestartPlan (from ``plan_canary_restart_with_overlay()``).
        overlay_payload: The parsed overlay dict (key-value pairs from overlay JSON).
        pre_apply_config: The pre-apply config dict (must contain ``dry_run``).
        execution_enabled: **Always False in Phase 3B-B.** Set True to test
            the gate blocks, but the gate will always fail.

    Returns:
        ``RestartGateResult`` with ``ready=True`` only when all 10 gates pass.
    """
    blocked: list[str] = []
    gate_results: dict[str, bool] = {}

    # G1
    ok, reason = _g1_plan_exists(plan)
    gate_results["plan_exists"] = ok
    if not ok:
        blocked.append(reason)

    if ok:
        # G2
        ok2, reason2 = _g2_plan_bot_is_canary(plan)
        gate_results["plan_bot_is_canary"] = ok2
        if not ok2:
            blocked.append(reason2)
    else:
        gate_results["plan_bot_is_canary"] = False

    if ok:
        # G3
        ok3, reason3 = _g3_overlay_path_is_canary_user_data(plan)
        gate_results["overlay_path_is_canary_user_data"] = ok3
        if not ok3:
            blocked.append(reason3)
    else:
        gate_results["overlay_path_is_canary_user_data"] = False

    if ok:
        # G4
        ok4, reason4 = _g4_overlay_sha_matches_plan(plan)
        gate_results["overlay_sha_matches_plan"] = ok4
        if not ok4:
            blocked.append(reason4)
    else:
        gate_results["overlay_sha_matches_plan"] = False

    # G5 — independent of G1
    ok5, reason5 = _g5_dry_run_true(pre_apply_config)
    gate_results["dry_run_true"] = ok5
    if not ok5:
        blocked.append(reason5)

    # G6 — independent
    ok6, reasons6 = _g6_forbidden_keys_absent(overlay_payload)
    gate_results["forbidden_keys_absent"] = ok6
    if not ok6:
        blocked.extend(reasons6)

    # G7
    if ok:
        ok7, reason7 = _g7_proposed_command_contains_base_config(plan)
        gate_results["proposed_command_contains_base_config"] = ok7
        if not ok7:
            blocked.append(reason7)
    else:
        gate_results["proposed_command_contains_base_config"] = False

    # G8
    if ok:
        ok8, reason8 = _g8_proposed_command_contains_overlay_config(plan)
        gate_results["proposed_command_contains_overlay_config"] = ok8
        if not ok8:
            blocked.append(reason8)
    else:
        gate_results["proposed_command_contains_overlay_config"] = False

    # G9
    if ok:
        ok9, reason9 = _g9_rollback_command_available(plan)
        gate_results["rollback_command_available"] = ok9
        if not ok9:
            blocked.append(reason9)
    else:
        gate_results["rollback_command_available"] = False

    # G10 — independent
    ok10, reason10 = _g10_runtime_execution_still_blocked(execution_enabled)
    gate_results["runtime_execution_still_blocked"] = ok10
    if not ok10:
        blocked.append(reason10)

    ready = len(blocked) == 0
    return RestartGateResult(
        ready=ready,
        gate_results=gate_results,
        blocked_reasons=tuple(blocked),
    )


# ---------------------------------------------------------------------------
# Canary Recreate Plan Builder
# ---------------------------------------------------------------------------


def build_canary_recreate_plan(
    restart_plan: RestartPlan,
    gate_result: RestartGateResult,
) -> CanaryRecreatePlan:
    """Build a ``CanaryRecreatePlan`` from a RestartPlan and its gate result.

    Pure Python — no subprocess, no Docker, no filesystem writes.

    Args:
        restart_plan: A validated RestartPlan.
        gate_result: The ``RestartGateResult`` from ``check_restart_gate()``.

    Returns:
        ``CanaryRecreatePlan`` describing the proposed container recreate.
    """
    return CanaryRecreatePlan(
        plan_id=restart_plan.plan_id,
        bot_id=restart_plan.bot_id,
        container_name=CANARY_CONTAINER_NAME,
        service_name=CANARY_SERVICE_NAME,
        compose_service=CANARY_COMPOSE_SERVICE,
        proposed_command=restart_plan.proposed_command,
        rollback_command=restart_plan.rollback_command,
        overlay_container_path=restart_plan.container_overlay_path,
        overlay_sha256=restart_plan.overlay_sha256,
        dry_run_confirmed=gate_result.gate_results.get("dry_run_true", False),
        restart_gate_ready=gate_result.ready,
        blocked_reasons=gate_result.blocked_reasons,
    )


# ---------------------------------------------------------------------------
# Compose override preview
# ---------------------------------------------------------------------------


def render_compose_override_preview(
    recreate_plan: CanaryRecreatePlan,
) -> str:
    """Render a Docker Compose override YAML preview for the canary service.

    This function:
    - Returns a YAML-formatted string describing the Compose override.
    - Does NOT write any file.
    - Does NOT execute any Docker/Compose command.
    - Contains ONLY the canary service (no other services affected).
    - Contains NO secrets (only the service command block).

    Args:
        recreate_plan: A validated ``CanaryRecreatePlan``.

    Returns:
        A YAML string ready for human review.
    """
    lines: list[str] = []
    lines.append("# SI-v2 Canary Restart — Docker Compose Override Preview")
    lines.append("# Generated by: restart_gate.py:render_compose_override_preview()")
    lines.append("# This file is a READ-ONLY PREVIEW. No file was written.")
    lines.append("#")
    lines.append(f"# Plan ID: {recreate_plan.plan_id}")
    lines.append(f"# Bot: {recreate_plan.bot_id}")
    lines.append(f"# Container: {recreate_plan.container_name}")
    lines.append(f"# Overlay SHA: {recreate_plan.overlay_sha256}")
    lines.append(f"# Dry-run confirmed: {recreate_plan.dry_run_confirmed}")
    lines.append(f"# Restart gate ready: {recreate_plan.restart_gate_ready}")
    lines.append("#")
    lines.append("services:")
    lines.append(f"  {recreate_plan.compose_service}:")
    lines.append("    command:")
    for arg in recreate_plan.proposed_command:
        lines.append(f"      - {arg}")
    lines.append("")
    lines.append("# Rollback: remove this override file and run:")
    lines.append(f"#   docker compose up -d {recreate_plan.compose_service}")
    lines.append("# The container will start with:")
    lines.append(f"#   {' '.join(recreate_plan.rollback_command)}")
    lines.append("#")
    lines.append("# Note: This is a DESIGN DOCUMENT. Execution requires:")
    lines.append("#   - Phase 3C Runtime Executor Sprint")
    lines.append("#   - Separate L3 token (APPROVE_SI_V2_CANARY_RESTART_WITH_OVERLAY)")
    lines.append("#   - RuntimeEffectProof GREEN after restart")
    return "\n".join(lines)
