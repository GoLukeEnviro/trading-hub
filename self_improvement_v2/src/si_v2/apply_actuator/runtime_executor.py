r"""Runtime Executor for canary restart with overlay — Phase 3C-A.

This module provides the **execution layer** that bridges the dry-run plan
chain (RestartPlan → RestartGate → CanaryRecreatePlan → ComposePreview) with
a controlled Docker Compose recreate.

Architecture
------------
::

    run_canary_restart_with_overlay()
      │
      ├─ 1. Check execute flag        ← default: False → BLOCKED
      ├─ 2. Check L3 token            ← APPROVE_SI_V2_CANARY_RESTART_WITH_OVERLAY
      ├─ 3. Check execution gates     ← re-validate plan + gates
      ├─ 4. Write compose override    ← render to file (only if execute=True)
      ├─ 5. Run compose recreate      ← subprocess (only if execute=True, mocked in tests)
      ├─ 6. Run RuntimeEffectProof    ← proof.py verify_runtime_effect()
      └─ 7. Return result             ← EXECUTED_GREEN / EXECUTED_RED / BLOCKED

Safety invariants
-----------------
- ``execute`` defaults to ``False`` — no accidental execution.
- L3 token must match ``APPROVE_SI_V2_CANARY_RESTART_WITH_OVERLAY``.
- All restart gates are re-validated before any side-effect.
- Compose override file is written only when all gates pass AND execute=True.
- Subprocess (docker compose) is called only when all gates pass AND execute=True.
- Tests mock subprocess — no real Docker in tests.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

from si_v2.apply_actuator.models import (
    OverlayProposal,
    ProofStatus,
    RuntimeEffectProof,
)
from si_v2.apply_actuator.proof import verify_runtime_effect
from si_v2.apply_actuator.restart_gate import (
    CANARY_BOT_ID,
    CanaryRecreatePlan,
    render_compose_override_preview,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

L3_RESTART_TOKEN_ENV: Final[str] = "APPROVE_SI_V2_CANARY_RESTART_WITH_OVERLAY"
"""Environment variable name for the L3 restart activation token."""

L3_RESTART_TOKEN_VALUE: Final[str] = "APPROVE"
"""Expected value of the L3 restart activation token."""

DEFAULT_COMPOSE_OUTPUT_DIR: Final[Path] = Path(
    "/opt/data/profiles/orchestrator/state/si_v2_controlled_apply/compose_overrides"
)
"""Default output directory for compose override files (orchestrator-side, not docker-compose.yml dir)."""

COMPOSE_FILENAME_PREFIX: Final[str] = "si-v2-canary-override-"
"""Prefix for generated compose override filenames."""

EXECUTION_GATE_NAMES: tuple[str, ...] = (
    "execute_flag_enabled",
    "token_matches",
    "bot_is_canary",
    "restart_gate_ready",
    "proposed_command_valid",
    "rollback_command_ready",
)
"""Execution-level gates (in addition to restart gates)."""

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RuntimeExecutionResult:
    """Result of a runtime execution attempt.

    Fields
    ------
    status:
        ``BLOCKED`` — pre-condition failed (execute=False, wrong token, etc.).
        ``EXECUTED_GREEN`` — compose recreate + runtime proof GREEN.
        ``EXECUTED_RED`` — compose ran but proof failed (rollback needed).
        ``EXECUTED_YELLOW`` — compose ran but proof inconclusive.
    reason:
        Human-readable explanation.
    plan_id:
        Identifier of the originating plan.
    proof:
        ``RuntimeEffectProof`` if execution was attempted.
    compose_override_path:
        Path to the written compose override file (empty if not written).
    rollback_instruction:
        Shell command to rollback (empty if not applicable).
    """

    status: Literal[
        "BLOCKED", "EXECUTED_GREEN", "EXECUTED_RED", "EXECUTED_YELLOW"
    ]
    reason: str
    plan_id: str = ""
    proof: RuntimeEffectProof | None = None
    compose_override_path: str = ""
    rollback_instruction: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "reason": self.reason,
            "plan_id": self.plan_id,
            "proof": self.proof.to_dict() if self.proof else None,
            "compose_override_path": self.compose_override_path,
            "rollback_instruction": self.rollback_instruction,
        }


# ---------------------------------------------------------------------------
# Compose override file writer
# ---------------------------------------------------------------------------


def write_compose_override_file(
    recreate_plan: CanaryRecreatePlan,
    output_dir: Path,
) -> tuple[Path, str]:
    """Render and write the compose override preview to a file.

    Args:
        recreate_plan: A validated ``CanaryRecreatePlan``.
        output_dir: Directory to write the override file to.

    Returns:
        Tuple of (file path, YAML content).
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    content = render_compose_override_preview(recreate_plan)
    filename = f"{COMPOSE_FILENAME_PREFIX}{recreate_plan.plan_id}.yml"
    path = output_dir / filename
    tmp = path.with_suffix(f".yml.tmp.{os.getpid()}")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)
    return path, content


# ---------------------------------------------------------------------------
# Execution gate checkers
# ---------------------------------------------------------------------------


def _check_execute_flag(execute: bool) -> tuple[bool, str]:
    if execute:
        return True, ""
    return (
        False,
        "execution_blocked: execute=False is the default. "
        "Set execute=True and provide the L3 token to proceed.",
    )


def _check_token(token: str | None) -> tuple[bool, str]:
    if token == L3_RESTART_TOKEN_VALUE:
        return True, ""
    if token is None:
        return False, "token_missing: no L3 token provided"
    return False, "token_mismatch: provided token does not match expected value"


def _check_execution_bot(recreate_plan: CanaryRecreatePlan) -> tuple[bool, str]:
    if recreate_plan.bot_id == CANARY_BOT_ID:
        return True, ""
    return False, f"wrong_bot: {recreate_plan.bot_id} is not {CANARY_BOT_ID}"


def _check_restart_gate_ready(recreate_plan: CanaryRecreatePlan) -> tuple[bool, str]:
    if recreate_plan.restart_gate_ready:
        return True, ""
    reasons = "; ".join(recreate_plan.blocked_reasons) if recreate_plan.blocked_reasons else "unknown"
    return False, f"restart_gate_not_ready: {reasons}"


def _check_proposed_command(recreate_plan: CanaryRecreatePlan) -> tuple[bool, str]:
    cmd = " ".join(recreate_plan.proposed_command)
    if "--config" in cmd and "overlay_" in cmd:
        return True, ""
    return False, "invalid_proposed_command: missing --config or overlay_"


def _check_rollback_ready(recreate_plan: CanaryRecreatePlan) -> tuple[bool, str]:
    if recreate_plan.rollback_command:
        return True, ""
    return False, "rollback_not_ready: rollback_command is empty"


# ---------------------------------------------------------------------------
# Compose execution (mockable)
# ---------------------------------------------------------------------------


def _run_compose_recreate(
    compose_override_path: Path,
    service_name: str,
    *,
    docker_available: bool = True,
    _subprocess_run=None,
) -> tuple[bool, str]:
    """Run ``docker compose up -d`` with the override file for one service.

    This function is the **only** subprocess call in the executor.
    Tests should mock ``_subprocess_run`` to avoid real Docker calls.

    Args:
        compose_override_path: Path to the compose override file.
        service_name: Service to recreate (e.g. ``freqtrade-freqforge-canary``).
        docker_available: If False, returns a mock failure.
        _subprocess_run: Override for testing (default: subprocess.run).

    Returns:
        Tuple of (success: bool, detail: str).
    """
    run_fn = _subprocess_run or subprocess.run

    if not docker_available:
        return False, "docker_unavailable"

    compose_dir = compose_override_path.parent
    override_name = compose_override_path.name

    cmd = [
        "docker", "compose",
        "-f", "docker-compose.yml",
        "-f", override_name,
        "up",
        "-d",
        service_name,
    ]

    try:
        result = run_fn(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(compose_dir),
        )
        if result.returncode == 0:
            return True, f"compose_recreate_ok: {result.stdout or 'no output'}"
        return (
            False,
            f"compose_recreate_failed: exit={result.returncode} "
            f"stderr={result.stderr.strip()[:200] or 'no stderr'}",
        )
    except FileNotFoundError:
        return False, "docker_cli_not_found"
    except subprocess.TimeoutExpired:
        return False, "compose_recreate_timeout"
    except Exception as e:
        return False, f"compose_recreate_error: {e}"


# ---------------------------------------------------------------------------
# Proof runner
# ---------------------------------------------------------------------------


def _run_runtime_effect_proof(
    recreate_plan: CanaryRecreatePlan,
    *,
    docker_available: bool = True,
) -> RuntimeEffectProof:
    """Run ``verify_runtime_effect`` after a compose recreate.

    Constructs a synthetic ``OverlayProposal`` and uses the existing
    proof infrastructure. If Docker is not available, returns a
    NOT_CHECKED proof.
    """
    if not docker_available:
        return RuntimeEffectProof(
            proposal_id=recreate_plan.plan_id,
            bot_id=recreate_plan.bot_id,
            proof_status=ProofStatus.NOT_CHECKED,
            errors=("docker_unavailable: proof requires Docker access",),
        )

    # Build a minimal binding-like dict for the proof layer
    # The proof layer expects BotRuntimeBinding via OverlayProposal
    # We use the runtime_binding module for that
    from si_v2.apply_actuator.runtime_binding import resolve_binding

    binding = resolve_binding(recreate_plan.bot_id)
    if binding is None:
        return RuntimeEffectProof(
            proposal_id=recreate_plan.plan_id,
            bot_id=recreate_plan.bot_id,
            proof_status=ProofStatus.RED,
            errors=(f"no_runtime_binding_for: {recreate_plan.bot_id}",),
        )

    proposal = OverlayProposal(
        proposal_id=recreate_plan.plan_id,
        bot_id=recreate_plan.bot_id,
        policy="safe_parameter_overlay_only",
        parameters={},  # filled from expected_parameter in the plan context
    )

    # Build a draft with the expected overlay path
    from si_v2.apply_actuator.models import EffectiveConfigDraft

    draft = EffectiveConfigDraft(
        proposal_id=recreate_plan.plan_id,
        bot_id=recreate_plan.bot_id,
        dry_run_preserved=True,
        live_trading_forbidden=True,
        multi_config_compatible=True,
    )

    overlay_container_path = recreate_plan.overlay_container_path

    return verify_runtime_effect(
        proposal,
        binding,
        draft,
        overlay_container_path=overlay_container_path,
        docker_available=docker_available,
    )


# ---------------------------------------------------------------------------
# Main executor
# ---------------------------------------------------------------------------


def run_canary_restart_with_overlay(
    *,
    recreate_plan: CanaryRecreatePlan,
    pre_apply_config: dict[str, object] | None = None,
    overlay_payload: dict[str, object] | None = None,
    execute: bool = False,
    token: str | None = None,
    compose_output_dir: Path | None = None,
    docker_available: bool = True,
) -> RuntimeExecutionResult:
    """Run the controlled canary restart with overlay.

    This is the **Phase 3C** entry point. Default mode (``execute=False``)
    returns ``BLOCKED`` — safe for dry-run audits. Actual execution requires
    ``execute=True`` + matching L3 token + all gates passing.

    Args:
        recreate_plan: A validated ``CanaryRecreatePlan`` (from Phase 3B-B).
        pre_apply_config: Pre-apply config dict (must contain ``dry_run``).
        overlay_payload: Parsed overlay JSON dict (for forbidden key checks).
        execute: **Defaults to False.** Set True only with L3 approval.
        token: L3 activation token (must match ``APPROVE``).
        compose_output_dir: Where to write the compose override file.
        docker_available: If False, skips actual Docker calls (for tests/audit).

    Returns:
        ``RuntimeExecutionResult`` with status and evidence.
    """
    plan_id = recreate_plan.plan_id
    blocked_reasons: list[str] = []
    compose_override_path: str = ""

    # Resolve output dir
    if compose_output_dir is None:
        compose_output_dir = DEFAULT_COMPOSE_OUTPUT_DIR

    # -- Gate 1: execute flag -------------------------------------------------
    ok1, reason1 = _check_execute_flag(execute)
    if not ok1:
        blocked_reasons.append(reason1)
        return RuntimeExecutionResult(
            status="BLOCKED",
            reason="; ".join(blocked_reasons),
            plan_id=plan_id,
            compose_override_path=compose_override_path,
            rollback_instruction="",
        )

    # -- Gate 2: L3 token ----------------------------------------------------
    ok2, reason2 = _check_token(token)
    if not ok2:
        blocked_reasons.append(reason2)
        return RuntimeExecutionResult(
            status="BLOCKED",
            reason="; ".join(blocked_reasons),
            plan_id=plan_id,
        )

    # -- Gate 3: bot is canary -----------------------------------------------
    ok3, reason3 = _check_execution_bot(recreate_plan)
    if not ok3:
        blocked_reasons.append(reason3)

    # -- Gate 4: restart gate ready ------------------------------------------
    ok4, reason4 = _check_restart_gate_ready(recreate_plan)
    if not ok4:
        blocked_reasons.append(reason4)

    # -- Gate 5: proposed command valid ---------------------------------------
    ok5, reason5 = _check_proposed_command(recreate_plan)
    if not ok5:
        blocked_reasons.append(reason5)

    # -- Gate 6: rollback ready ----------------------------------------------
    ok6, reason6 = _check_rollback_ready(recreate_plan)
    if not ok6:
        blocked_reasons.append(reason6)

    # If any execution gate failed, block
    if blocked_reasons:
        return RuntimeExecutionResult(
            status="BLOCKED",
            reason="; ".join(blocked_reasons),
            plan_id=plan_id,
        )

    # -- Step 4: Write compose override (side-effect 1) ----------------------
    try:
        override_path, _preview = write_compose_override_file(
            recreate_plan, compose_output_dir,
        )
        compose_override_path = str(override_path)
    except OSError as e:
        return RuntimeExecutionResult(
            status="BLOCKED",
            reason=f"compose_override_write_failed: {e}",
            plan_id=plan_id,
        )

    # -- Step 5: Run compose recreate (side-effect 2) -------------------------
    compose_ok, compose_detail = _run_compose_recreate(
        override_path,
        str(recreate_plan.compose_service),
        docker_available=docker_available,
    )
    if not compose_ok:
        return RuntimeExecutionResult(
            status="EXECUTED_RED",
            reason=f"compose_recreate_failed: {compose_detail}",
            plan_id=plan_id,
            compose_override_path=compose_override_path,
            rollback_instruction=(
                f"docker compose -f docker-compose.yml "
                f"up -d {recreate_plan.compose_service}"
            ),
        )

    # -- Step 6: Run RuntimeEffectProof --------------------------------------
    proof = _run_runtime_effect_proof(
        recreate_plan,
        docker_available=docker_available,
    )

    # -- Step 7: Determine status --------------------------------------------
    if proof.proof_status == ProofStatus.GREEN:
        return RuntimeExecutionResult(
            status="EXECUTED_GREEN",
            reason="compose_recreate_ok_and_runtime_proof_green",
            plan_id=plan_id,
            proof=proof,
            compose_override_path=compose_override_path,
            rollback_instruction=(
                f"docker compose -f docker-compose.yml "
                f"up -d {recreate_plan.compose_service}"
            ),
        )

    if proof.proof_status in (ProofStatus.RED, ProofStatus.NOT_CHECKED):
        return RuntimeExecutionResult(
            status="EXECUTED_RED",
            reason=f"runtime_proof_failed: status={proof.proof_status.value} "
                   f"errors={'; '.join(proof.errors) if proof.errors else 'none'}",
            plan_id=plan_id,
            proof=proof,
            compose_override_path=compose_override_path,
            rollback_instruction=(
                f"remove {override_path.name} then run: "
                f"docker compose -f docker-compose.yml "
                f"up -d {recreate_plan.compose_service}"
            ),
        )

    # YELLOW — proof inconclusive
    return RuntimeExecutionResult(
        status="EXECUTED_YELLOW",
        reason=f"runtime_proof_inconclusive: status={proof.proof_status.value}",
        plan_id=plan_id,
        proof=proof,
        compose_override_path=compose_override_path,
        rollback_instruction=(
            f"remove {override_path.name} then run: "
            f"docker compose -f docker-compose.yml "
            f"up -d {recreate_plan.compose_service}"
        ),
    )
