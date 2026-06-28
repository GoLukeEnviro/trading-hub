r"""Rollback Executor Boundary — Phase 5B.

Provides the **execution boundary layer** that bridges the read-only rollback
planning (``rollback_rehearsal.py``) with a hard-gated, canary-only, dry-run-only
rollback execution path.

This module does NOT execute any rollback. It builds the plan, checks the gate,
and returns a result that says "ready for L3 rollback" — but actual execution
requires a separate Phase 5C sprint with explicit Luke approval or Safety-RED.

Architecture
------------
::

    build_rollback_execution_plan()   → RollbackExecutionPlan   ← THIS
    check_rollback_execution_gate()   → RollbackExecutionGate   ← THIS
    execute_canary_rollback_boundary() → RollbackExecutionResult ← THIS
    render_rollback_execution_audit() → str (markdown)          ← THIS

Safety invariants
-----------------
- Canary-only: ``target_bot`` must be ``freqtrade-freqforge-canary``.
- ``dry_run`` must be confirmed via gate field.
- L3 approval requires a candidate-specific token (not generic ``APPROVE``).
- ``safety_red`` or ``luke_override`` required for gate to pass.
- ``execute=True`` is hard-blocked in Phase 5B.
- No subprocess, no Docker, no filesystem writes.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final, Literal

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CANARY_BOT_ID: Final[str] = "freqtrade-freqforge-canary"
"""The only bot ID accepted by the rollback executor."""

EXPECTED_L3_APPROVAL_PREFIX: Final[str] = "APPROVE_ROLLBACK_"
"""Prefix for the candidate-specific L3 rollback approval token."""

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RollbackExecutionPlan:
    """A fully specified, ready-to-audit rollback execution plan.

    All fields are populated at plan-creation time. Immutable and JSON-
    serialisable via ``to_dict()``.
    """

    candidate_id: str
    """Candidate identifier (e.g. ``max_open_trades_3_to_2``)."""

    target_bot: str
    """Target bot ID — must be ``freqtrade-freqforge-canary``."""

    canary_only: bool
    """If True, the plan is restricted to the canary bot."""

    dry_run_only: bool
    """If True, dry-run is confirmed for the target bot."""

    rollback_source: str
    """Source of the rollback plan (e.g. ``rollback_rehearsal``)."""

    restore_mode: Literal[
        "restore_pre_overlay_container",
        "recreate_without_overlay",
        "remove_overlay_from_command",
        "blocked",
    ]
    """How the rollback would restore the bot."""

    expected_parameter: str
    """The parameter name being rolled back (e.g. ``max_open_trades``)."""

    current_value: object
    """The current runtime value (e.g. ``2``)."""

    rollback_value: object
    """The value to restore on rollback (e.g. ``3``)."""

    pre_rollback_snapshot_path: str
    """Path where a pre-rollback snapshot would be written."""

    post_rollback_proof_path: str
    """Path where a post-rollback proof would be written."""

    audit_path: str
    """Path where the rollback audit record would be written."""

    command_preview: tuple[str, ...]
    """The rollback command as a tuple of args (preview only, never executed)."""

    blocked_reasons: tuple[str, ...]
    """Reasons the plan is blocked (empty if ready)."""

    def to_dict(self) -> dict[str, object]:
        return {
            "candidate_id": self.candidate_id,
            "target_bot": self.target_bot,
            "canary_only": self.canary_only,
            "dry_run_only": self.dry_run_only,
            "rollback_source": self.rollback_source,
            "restore_mode": self.restore_mode,
            "expected_parameter": self.expected_parameter,
            "current_value": self.current_value,
            "rollback_value": self.rollback_value,
            "pre_rollback_snapshot_path": self.pre_rollback_snapshot_path,
            "post_rollback_proof_path": self.post_rollback_proof_path,
            "audit_path": self.audit_path,
            "command_preview": list(self.command_preview),
            "blocked_reasons": list(self.blocked_reasons),
        }


@dataclass(frozen=True)
class RollbackExecutionGate:
    """Result of the rollback execution gate evaluation.

    ``allowed`` is ``True`` only when all safety conditions are met.
    """

    allowed: bool
    """If True, the rollback execution is permitted (pending execute flag)."""

    candidate_id: str
    """Candidate identifier."""

    target_bot: str
    """Target bot ID."""

    requires_l3_approval: bool
    """If True, L3 approval is required for execution."""

    l3_approval_present: bool
    """If True, a valid L3 approval token was provided."""

    safety_red_required_or_luke_override: bool
    """If True, safety_red or luke_override was required and satisfied."""

    dry_run_confirmed: bool
    """If True, dry-run was confirmed for the target bot."""

    canary_confirmed: bool
    """If True, the target bot is the canary."""

    rollback_plan_valid: bool
    """If True, the rollback plan passed validation."""

    blocked_reasons: tuple[str, ...]
    """Reasons the gate is blocked (empty if allowed)."""

    def to_dict(self) -> dict[str, object]:
        return {
            "allowed": self.allowed,
            "candidate_id": self.candidate_id,
            "target_bot": self.target_bot,
            "requires_l3_approval": self.requires_l3_approval,
            "l3_approval_present": self.l3_approval_present,
            "safety_red_required_or_luke_override": self.safety_red_required_or_luke_override,
            "dry_run_confirmed": self.dry_run_confirmed,
            "canary_confirmed": self.canary_confirmed,
            "rollback_plan_valid": self.rollback_plan_valid,
            "blocked_reasons": list(self.blocked_reasons),
        }


@dataclass(frozen=True)
class RollbackExecutionResult:
    """Result of a rollback execution boundary attempt.

    In Phase 5B, ``execute=True`` always returns ``EXECUTION_NOT_ALLOWED_IN_PHASE_5B``.
    Actual rollback execution requires Phase 5C.
    """

    status: Literal[
        "READY_FOR_L3_ROLLBACK",
        "BLOCKED",
        "NOT_EXECUTED",
        "EXECUTION_NOT_ALLOWED_IN_PHASE_5B",
    ]
    """Final status of the rollback boundary check."""

    candidate_id: str
    """Candidate identifier."""

    target_bot: str
    """Target bot ID."""

    plan: RollbackExecutionPlan | None
    """The rollback execution plan (None if blocked)."""

    gate: RollbackExecutionGate
    """The rollback execution gate result."""

    audit_record: Mapping[str, object]
    """Audit record with evidence (no secrets)."""

    next_step: str
    """Exactly one next step."""

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "candidate_id": self.candidate_id,
            "target_bot": self.target_bot,
            "plan": self.plan.to_dict() if self.plan else None,
            "gate": self.gate.to_dict(),
            "audit_record": dict(self.audit_record),
            "next_step": self.next_step,
        }


# ---------------------------------------------------------------------------
# Plan builder
# ---------------------------------------------------------------------------


def _build_expected_token(candidate_id: str) -> str:
    """Build the expected L3 approval token for a candidate.

    Pattern: ``APPROVE_ROLLBACK_<candidate_id>_CANARY``
    """
    safe_id = candidate_id.replace("-", "_").replace(" ", "_")
    return f"{EXPECTED_L3_APPROVAL_PREFIX}{safe_id}_CANARY"


def _determine_restore_mode(
    rollback_plan: object,
) -> Literal[
    "restore_pre_overlay_container",
    "recreate_without_overlay",
    "remove_overlay_from_command",
    "blocked",
]:
    """Determine the restore mode from a rollback plan.

    Uses duck-typing on the rollback plan object. If the plan has a
    ``rollback_command`` that removes overlay, returns
    ``remove_overlay_from_command``. Otherwise returns ``blocked``.
    """
    if hasattr(rollback_plan, "rollback_command"):
        cmd = rollback_plan.rollback_command  # type: ignore[attr-defined]
        if cmd and isinstance(cmd, (tuple, list)) and len(cmd) > 0:
            cmd_str = " ".join(str(a) for a in cmd)
            if "overlay_" not in cmd_str:
                return "remove_overlay_from_command"
    return "blocked"


def build_rollback_execution_plan(
    *,
    rollback_plan: object,
    candidate_id: str,
    target_bot: str,
    current_value: object,
    rollback_value: object,
    report_root: str = "docs/reports",
) -> RollbackExecutionPlan:
    """Build a ``RollbackExecutionPlan`` from a rollback rehearsal plan.

    This function:
    - Extracts fields from the rollback plan via duck-typing.
    - Enforces canary-only and dry-run-only.
    - Does NOT write any files.
    - Does NOT execute any commands.
    - Builds a ``command_preview`` as text only.

    Args:
        rollback_plan: A ``RollbackPlan`` from ``rollback_rehearsal.py``
            (or any object with compatible attributes).
        candidate_id: Candidate identifier.
        target_bot: Target bot ID.
        current_value: Current runtime value (e.g. ``2``).
        rollback_value: Value to restore on rollback (e.g. ``3``).
        report_root: Root path for report files.

    Returns:
        ``RollbackExecutionPlan`` with all fields populated.
    """
    blocked: list[str] = []

    # Canary-only check
    canary_ok = target_bot == CANARY_BOT_ID
    if not canary_ok:
        blocked.append(f"not_canary: target_bot={target_bot!r} is not {CANARY_BOT_ID!r}")

    # Dry-run check from rollback plan
    dry_run_ok = False
    if hasattr(rollback_plan, "dry_run_required"):
        dry_run_ok = bool(rollback_plan.dry_run_required)
    if not dry_run_ok:
        blocked.append("dry_run_not_confirmed: rollback plan does not require dry_run")

    # Determine restore mode
    restore_mode = _determine_restore_mode(rollback_plan)

    # Build command preview
    command_preview: tuple[str, ...] = ()
    if hasattr(rollback_plan, "rollback_command"):
        cmd = rollback_plan.rollback_command
        if cmd and isinstance(cmd, (tuple, list)):
            command_preview = tuple(str(a) for a in cmd)

    # Build snapshot/proof/audit paths
    now = datetime.now(UTC)
    date_str = now.strftime("%Y-%m-%d")
    ts = now.strftime("%Y%m%dT%H%M%SZ")
    pre_snapshot = f"{report_root}/si-v2-rollback-pre-snapshot-{candidate_id}-{ts}.md"
    post_proof = f"{report_root}/si-v2-rollback-post-proof-{candidate_id}-{ts}.md"
    audit = f"{report_root}/si-v2-rollback-audit-{candidate_id}-{date_str}.md"

    return RollbackExecutionPlan(
        candidate_id=candidate_id,
        target_bot=target_bot,
        canary_only=canary_ok,
        dry_run_only=dry_run_ok,
        rollback_source="rollback_rehearsal",
        restore_mode=restore_mode,
        expected_parameter="max_open_trades",
        current_value=current_value,
        rollback_value=rollback_value,
        pre_rollback_snapshot_path=pre_snapshot,
        post_rollback_proof_path=post_proof,
        audit_path=audit,
        command_preview=command_preview,
        blocked_reasons=tuple(blocked),
    )


# ---------------------------------------------------------------------------
# Gate checker
# ---------------------------------------------------------------------------


def check_rollback_execution_gate(
    *,
    plan: RollbackExecutionPlan,
    safety_red: bool,
    luke_override: bool,
    l3_approval: str | None,
    expected_l3_approval: str | None = None,
) -> RollbackExecutionGate:
    """Evaluate all rollback execution gates.

    Gate rules:
    - ``allowed`` only if ``canary_confirmed``.
    - ``allowed`` only if ``dry_run_confirmed``.
    - ``allowed`` only if ``rollback_plan_valid``.
    - ``allowed`` only if ``safety_red=True`` or ``luke_override=True``.
    - ``allowed`` only with a valid candidate-specific L3 token.

    Args:
        plan: A validated ``RollbackExecutionPlan``.
        safety_red: If True, safety evaluation is RED (rollback warranted).
        luke_override: If True, Luke explicitly overrides safety.
        l3_approval_token: The L3 approval token provided by the caller.
        expected_l3_token: Expected token value. If None, derived from
            ``plan.candidate_id``.

    Returns:
        ``RollbackExecutionGate`` with ``allowed=True`` only when all
        conditions are met.
    """
    blocked: list[str] = []

    # Derive expected approval token if not provided
    if expected_l3_approval is None:
        expected_l3_approval = _build_expected_token(plan.candidate_id)

    # 1. Canary confirmed
    canary_confirmed = plan.canary_only
    if not canary_confirmed:
        blocked.append("canary_not_confirmed: plan is not canary-only")

    # 2. Dry-run confirmed
    dry_run_confirmed = plan.dry_run_only
    if not dry_run_confirmed:
        blocked.append("dry_run_not_confirmed: plan does not confirm dry_run")

    # 3. Rollback plan valid
    rollback_plan_valid = len(plan.blocked_reasons) == 0
    if not rollback_plan_valid:
        blocked.append(f"rollback_plan_invalid: {'; '.join(plan.blocked_reasons)}")

    # 4. Safety RED or Luke override
    safety_red_ok = safety_red or luke_override
    if not safety_red_ok:
        blocked.append(
            "safety_not_red_and_no_luke_override: "
            "rollback requires safety_red=True or luke_override=True"
        )

    # 5. L3 approval validation
    l3_approval_present = False
    if l3_approval is None:
        blocked.append("l3_token_missing: no L3 approval token provided")
    elif l3_approval == expected_l3_approval:
        l3_approval_present = True
    else:
        blocked.append(
            f"l3_token_mismatch: provided token does not match expected "
            f"candidate-specific token for {plan.candidate_id}"
        )

    allowed = len(blocked) == 0

    return RollbackExecutionGate(
        allowed=allowed,
        candidate_id=plan.candidate_id,
        target_bot=plan.target_bot,
        requires_l3_approval=True,
        l3_approval_present=l3_approval_present,
        safety_red_required_or_luke_override=safety_red_ok,
        dry_run_confirmed=dry_run_confirmed,
        canary_confirmed=canary_confirmed,
        rollback_plan_valid=rollback_plan_valid,
        blocked_reasons=tuple(blocked),
    )


# ---------------------------------------------------------------------------
# Executor boundary
# ---------------------------------------------------------------------------


def execute_canary_rollback_boundary(
    *,
    plan: RollbackExecutionPlan,
    gate: RollbackExecutionGate,
    execute: bool = False,
) -> RollbackExecutionResult:
    """Evaluate the rollback execution boundary.

    This is the **Phase 5B** entry point. Default mode (``execute=False``)
    returns ``NOT_EXECUTED`` or ``READY_FOR_L3_ROLLBACK`` — safe for dry-run
    audits. Actual execution (``execute=True``) is hard-blocked in Phase 5B.

    Args:
        plan: A validated ``RollbackExecutionPlan``.
        gate: A ``RollbackExecutionGate`` from ``check_rollback_execution_gate()``.
        execute: **Defaults to False.** In Phase 5B, setting ``execute=True``
            returns ``EXECUTION_NOT_ALLOWED_IN_PHASE_5B``.

    Returns:
        ``RollbackExecutionResult`` with status and evidence.
    """
    now = datetime.now(UTC)
    now_str = now.isoformat()

    # Phase 5B: execute=True is always blocked
    if execute:
        return RollbackExecutionResult(
            status="EXECUTION_NOT_ALLOWED_IN_PHASE_5B",
            candidate_id=plan.candidate_id,
            target_bot=plan.target_bot,
            plan=plan,
            gate=gate,
            audit_record={
                "timestamp_utc": now_str,
                "execute_requested": True,
                "execution_disabled_in_phase_5b": True,
                "phase": "5B",
                "candidate_id": plan.candidate_id,
            },
            next_step="Phase 5C required for actual rollback execution. "
            "No runtime mutation performed.",
        )

    # execute=False: check gate
    if not gate.allowed:
        return RollbackExecutionResult(
            status="BLOCKED",
            candidate_id=plan.candidate_id,
            target_bot=plan.target_bot,
            plan=plan,
            gate=gate,
            audit_record={
                "timestamp_utc": now_str,
                "execute_requested": False,
                "gate_allowed": False,
                "blocked_reasons": list(gate.blocked_reasons),
                "phase": "5B",
                "candidate_id": plan.candidate_id,
            },
            next_step="Fix blocked reasons and re-check gate. "
            "No runtime mutation performed.",
        )

    # Gate passed, execute=False → ready for L3
    return RollbackExecutionResult(
        status="READY_FOR_L3_ROLLBACK",
        candidate_id=plan.candidate_id,
        target_bot=plan.target_bot,
        plan=plan,
        gate=gate,
        audit_record={
            "timestamp_utc": now_str,
            "execute_requested": False,
            "gate_allowed": True,
            "phase": "5B",
            "candidate_id": plan.candidate_id,
            "token_valid": True,
            "token_secret_not_logged": True,
        },
        next_step="Phase 5C: execute rollback with L3 approval. "
        "No runtime mutation performed in Phase 5B.",
    )


# ---------------------------------------------------------------------------
# Audit renderer
# ---------------------------------------------------------------------------


def render_rollback_execution_audit(
    result: RollbackExecutionResult,
) -> str:
    """Render a rollback execution audit as markdown.

    Args:
        result: A ``RollbackExecutionResult``.

    Returns:
        A markdown string suitable for human review.
    """
    lines: list[str] = []
    lines.append("# SI-v2 Rollback Execution Audit")
    lines.append("")
    lines.append(f"**Status:** {result.status}")
    lines.append(f"**Candidate:** {result.candidate_id}")
    lines.append(f"**Target Bot:** {result.target_bot}")
    lines.append("")
    lines.append("## Gate")
    lines.append("")
    lines.append("| Check | Result |")
    lines.append("|-------|--------|")
    lines.append(f"| Allowed | {result.gate.allowed} |")
    lines.append(f"| Canary confirmed | {result.gate.canary_confirmed} |")
    lines.append(f"| Dry-run confirmed | {result.gate.dry_run_confirmed} |")
    lines.append(f"| Rollback plan valid | {result.gate.rollback_plan_valid} |")
    lines.append(f"| Safety RED or Luke override | {result.gate.safety_red_required_or_luke_override} |")
    lines.append(f"| L3 approval present | {result.gate.l3_approval_present} |")
    lines.append(f"| Requires L3 approval | {result.gate.requires_l3_approval} |")
    if result.gate.blocked_reasons:
        lines.append("")
        lines.append("### Blocked Reasons")
        for r in result.gate.blocked_reasons:
            lines.append(f"- {r}")
    lines.append("")
    lines.append("## Plan")
    lines.append("")
    if result.plan:
        lines.append(f"**Candidate:** {result.plan.candidate_id}")
        lines.append(f"**Target Bot:** {result.plan.target_bot}")
        lines.append(f"**Canary only:** {result.plan.canary_only}")
        lines.append(f"**Dry-run only:** {result.plan.dry_run_only}")
        lines.append(f"**Restore mode:** {result.plan.restore_mode}")
        lines.append(f"**Parameter:** {result.plan.expected_parameter}")
        lines.append(f"**Current value:** {result.plan.current_value!r}")
        lines.append(f"**Rollback value:** {result.plan.rollback_value!r}")
        lines.append("")
        lines.append("### Command Preview")
        lines.append("")
        lines.append("```")
        lines.append(" ".join(result.plan.command_preview))
        lines.append("```")
        lines.append("")
        lines.append("### Snapshot / Proof / Audit Paths")
        lines.append("")
        lines.append(f"- Pre-rollback snapshot: `{result.plan.pre_rollback_snapshot_path}`")
        lines.append(f"- Post-rollback proof: `{result.plan.post_rollback_proof_path}`")
        lines.append(f"- Audit record: `{result.plan.audit_path}`")
    else:
        lines.append("No plan available.")
    lines.append("")
    lines.append("## Execution")
    lines.append("")
    lines.append("- **Not executed.** Phase 5B is boundary-only.")
    lines.append(f"- execute_requested: {result.audit_record.get('execute_requested', 'unknown')}")
    lines.append("")
    lines.append("## Next Step")
    lines.append("")
    lines.append(result.next_step)
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(f"*Audit generated at: {result.audit_record.get('timestamp_utc', 'unknown')}*")
    lines.append("*No runtime mutation was performed.*")

    return "\n".join(lines)
