"""Controlled Apply Actuator — Phase 1 (Human Gate + Canary-First).

This module is the "connection cable" between a DeploymentPlan whose
status is ``ready_for_shadow`` and an actual, auditable config apply
on the canary bot (freqforge-canary).

Phase 1 constraints
-------------------
* Human gate is mandatory — no autonomous apply.
* Canary-first — only ``freqforge-canary`` is a valid target.
* Hard cooldown of 7 days between applies (enforced in-code).
* ``_execute_apply()`` writes a config delta file; no Docker restart.
* ``dry_run=True`` mode available for full gate testing without writes.

Gate pipeline (any failure → ActuatorResult.status == BLOCKED)
--------------------------------------------------------------
1.  Plan eligibility    : DeploymentPlan.status == "ready_for_shadow"
2.  Kill-Switch         : must report NORMAL
3.  RiskGuard           : must return PASS
4.  Mutation counter    : pre-apply value logged
5.  ShadowLogger        : ``apply_requested`` entry (mandatory)
6.  Human token         : generated + delivered; waits for confirmation
7.  Apply               : ``_execute_apply()`` writes config delta
8.  Mutation counter    : incremented + documented
9.  Rollback plan       : generated + persisted
10. ShadowLogger        : ``apply_executed`` + ``rollback_prepared`` entries
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any

from si_v2.deploy.deployment_plan import DeploymentPlan, DeploymentStatus
from si_v2.deploy.rollback_plan import RollbackPlanManager
from si_v2.deploy.shadow_logger import ShadowLogger


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CANARY_BOT_ID: str = "freqforge-canary"
COOLDOWN_DAYS: int = 7
APPLY_PHASE: str = "controlled_apply"

# Path where cooldown state is persisted (relative to repo root)
_COOLDOWN_STATE_FILE = Path("self_improvement_v2/data/apply_cooldown.json")

# Path where config deltas are written for the canary bot
_CANARY_CONFIG_DELTA_DIR = Path("freqforge-canary/config/si_v2_deltas")


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


class ActuatorStatus(StrEnum):
    """Top-level outcome of a controlled apply attempt."""

    BLOCKED = "blocked"
    PENDING_TOKEN = "pending_token"  # token generated, awaiting human
    APPLIED = "applied"              # full apply executed
    DRY_RUN_OK = "dry_run_ok"        # dry run passed all gates


@dataclass
class ActuatorResult:
    """Full audit record for a single controlled apply attempt."""

    status: ActuatorStatus
    plan_sha: str
    bot_id: str
    gate_log: list[dict[str, Any]] = field(default_factory=list)
    apply_token: str | None = None
    config_delta_path: str | None = None
    rollback_path: str | None = None
    mutation_counter_before: int = 0
    mutation_counter_after: int = 0
    blocked_reason: str | None = None
    timestamp_utc: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "plan_sha": self.plan_sha,
            "bot_id": self.bot_id,
            "apply_token": self.apply_token,
            "config_delta_path": self.config_delta_path,
            "rollback_path": self.rollback_path,
            "mutation_counter_before": self.mutation_counter_before,
            "mutation_counter_after": self.mutation_counter_after,
            "blocked_reason": self.blocked_reason,
            "timestamp_utc": self.timestamp_utc,
            "gate_log": self.gate_log,
        }


# ---------------------------------------------------------------------------
# Kill-Switch interface (thin wrapper — real impl in freqtrade/shared/)
# ---------------------------------------------------------------------------


class KillSwitchState(StrEnum):
    NORMAL = "NORMAL"
    EMERGENCY = "EMERGENCY"
    PAUSED = "PAUSED"


class KillSwitchAdapter:
    """Reads kill-switch state from the shared kill_switch file.

    Falls back to EMERGENCY if the file is unreadable — fail-safe.
    """

    def __init__(self, state_file: Path | None = None) -> None:
        self._state_file = state_file or Path(
            "freqtrade/shared/kill_switch_state.json"
        )

    def get_state(self) -> KillSwitchState:
        try:
            raw = json.loads(self._state_file.read_text())
            return KillSwitchState(raw.get("state", "EMERGENCY"))
        except Exception:  # noqa: BLE001
            return KillSwitchState.EMERGENCY


# ---------------------------------------------------------------------------
# RiskGuard interface
# ---------------------------------------------------------------------------


class RiskGuardVerdict(StrEnum):
    PASS = "PASS"
    BLOCK = "BLOCK"
    DOWNGRADE = "DOWNGRADE"


@dataclass
class RiskGuardResult:
    verdict: RiskGuardVerdict
    reason: str
    details: dict[str, Any] = field(default_factory=dict)


class RiskGuardAdapter:
    """Calls the RiskGuard module and returns a verdict.

    This is a thin adapter — swap in the real RiskGuard once available
    in `security/` or `si_v2/monitoring/`.
    """

    def evaluate(self, plan: DeploymentPlan) -> RiskGuardResult:
        """Evaluate whether the plan is safe to apply.

        Phase 1: conservative hard-coded checks.
        Phase 2: wire into the real RiskGuard from security/.
        """
        # Check candidate SHA is set
        if not plan.candidate_sha or plan.candidate_sha == "unknown":
            return RiskGuardResult(
                verdict=RiskGuardVerdict.BLOCK,
                reason="candidate_sha missing or unknown",
            )
        # Check plan has steps
        if not plan.steps:
            return RiskGuardResult(
                verdict=RiskGuardVerdict.BLOCK,
                reason="deployment plan has no steps — likely incomplete",
            )
        # Phase 1: only weight/parameter proposals (no strategy code)
        for step in plan.steps:
            if "strategy" in step.lower() and "adapter" not in step.lower():
                return RiskGuardResult(
                    verdict=RiskGuardVerdict.BLOCK,
                    reason=(
                        f"Phase 1 allows weight/parameter applies only; "
                        f"strategy mutation detected in step: {step!r}"
                    ),
                )
        return RiskGuardResult(
            verdict=RiskGuardVerdict.PASS,
            reason="all Phase 1 RiskGuard checks passed",
        )


# ---------------------------------------------------------------------------
# Mutation Counter
# ---------------------------------------------------------------------------


class MutationCounter:
    """Simple file-backed mutation counter — append-only ledger."""

    def __init__(self, ledger_file: Path | None = None) -> None:
        self._ledger = ledger_file or Path(
            "self_improvement_v2/data/mutation_counter_ledger.jsonl"
        )

    def read(self) -> int:
        """Return current mutation count (number of applied entries)."""
        if not self._ledger.exists():
            return 0
        lines = [l for l in self._ledger.read_text().splitlines() if l.strip()]
        return len(lines)

    def increment(self, plan_sha: str, bot_id: str, timestamp: str) -> int:
        """Append one entry and return new count."""
        self._ledger.parent.mkdir(parents=True, exist_ok=True)
        entry = json.dumps(
            {
                "plan_sha": plan_sha,
                "bot_id": bot_id,
                "timestamp_utc": timestamp,
                "type": "apply_executed",
            }
        )
        with self._ledger.open("a") as f:
            f.write(entry + "\n")
        return self.read()


# ---------------------------------------------------------------------------
# Cooldown enforcement
# ---------------------------------------------------------------------------


class CooldownEnforcer:
    """Ensures at most one apply per COOLDOWN_DAYS days."""

    def __init__(
        self,
        state_file: Path | None = None,
        cooldown_days: int = COOLDOWN_DAYS,
    ) -> None:
        self._state_file = state_file or _COOLDOWN_STATE_FILE
        self._cooldown = timedelta(days=cooldown_days)

    def is_cooled_down(self) -> tuple[bool, str]:
        """Return (True, reason) if cooldown has passed, else (False, reason)."""
        if not self._state_file.exists():
            return True, "no previous apply found — cooldown clear"
        try:
            raw = json.loads(self._state_file.read_text())
            last_apply = datetime.fromisoformat(raw["last_apply_utc"])
            elapsed = datetime.now(timezone.utc) - last_apply
            if elapsed >= self._cooldown:
                return True, f"cooldown passed ({elapsed.days}d elapsed)"
            remaining = self._cooldown - elapsed
            return False, f"cooldown active — {remaining.days}d {remaining.seconds//3600}h remaining"
        except Exception as exc:  # noqa: BLE001
            return False, f"cooldown state unreadable — fail-safe block: {exc}"

    def record_apply(self, plan_sha: str) -> None:
        """Persist the current timestamp as last apply time."""
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        self._state_file.write_text(
            json.dumps(
                {
                    "last_apply_utc": datetime.now(timezone.utc).isoformat(),
                    "plan_sha": plan_sha,
                }
            )
        )


# ---------------------------------------------------------------------------
# Human Token
# ---------------------------------------------------------------------------


class HumanTokenManager:
    """Generates and validates single-use human approval tokens."""

    def __init__(self, token_dir: Path | None = None) -> None:
        self._token_dir = token_dir or Path(
            "self_improvement_v2/data/pending_tokens"
        )

    def generate(self, plan_sha: str) -> str:
        """Generate a cryptographically-random token and persist it."""
        token = secrets.token_hex(16)
        self._token_dir.mkdir(parents=True, exist_ok=True)
        token_file = self._token_dir / f"{plan_sha[:12]}_{token[:8]}.json"
        token_file.write_text(
            json.dumps(
                {
                    "token": token,
                    "plan_sha": plan_sha,
                    "created_utc": datetime.now(timezone.utc).isoformat(),
                    "used": False,
                }
            )
        )
        return token

    def validate_and_consume(self, plan_sha: str, token: str) -> bool:
        """Return True and mark token as used if valid, else False."""
        prefix = plan_sha[:12]
        for tf in self._token_dir.glob(f"{prefix}_*.json"):
            try:
                data = json.loads(tf.read_text())
                if (
                    data["token"] == token
                    and data["plan_sha"] == plan_sha
                    and not data["used"]
                ):
                    data["used"] = True
                    data["consumed_utc"] = datetime.now(timezone.utc).isoformat()
                    tf.write_text(json.dumps(data))
                    return True
            except Exception:  # noqa: BLE001
                continue
        return False


# ---------------------------------------------------------------------------
# Core Actuator
# ---------------------------------------------------------------------------


class ControlledApplyActuator:
    """Executes a human-gated, canary-first, fully-audited config apply.

    Typical usage
    -------------
    .. code-block:: python

        actuator = ControlledApplyActuator(
            shadow_logger=shadow_logger,
            rollback_manager=rollback_manager,
        )

        # Step 1 — request apply (generates human token)
        result = actuator.request_apply(plan, dry_run=False)
        # result.status == ActuatorStatus.PENDING_TOKEN
        # result.apply_token contains the token to confirm

        # Step 2 — confirm apply (human supplies token)
        result = actuator.confirm_apply(plan, token=result.apply_token)
        # result.status == ActuatorStatus.APPLIED
    """

    def __init__(
        self,
        shadow_logger: ShadowLogger,
        rollback_manager: RollbackPlanManager,
        kill_switch: KillSwitchAdapter | None = None,
        risk_guard: RiskGuardAdapter | None = None,
        mutation_counter: MutationCounter | None = None,
        cooldown_enforcer: CooldownEnforcer | None = None,
        token_manager: HumanTokenManager | None = None,
        canary_config_dir: Path | None = None,
    ) -> None:
        self._logger = shadow_logger
        self._rollback = rollback_manager
        self._kill_switch = kill_switch or KillSwitchAdapter()
        self._risk_guard = risk_guard or RiskGuardAdapter()
        self._mutation_counter = mutation_counter or MutationCounter()
        self._cooldown = cooldown_enforcer or CooldownEnforcer()
        self._token_manager = token_manager or HumanTokenManager()
        self._canary_dir = canary_config_dir or _CANARY_CONFIG_DELTA_DIR

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def request_apply(
        self,
        plan: DeploymentPlan,
        dry_run: bool = True,
    ) -> ActuatorResult:
        """Run all pre-apply gates and — if passed — generate a human token.

        Args:
            plan: A DeploymentPlan from DeploymentPlanOrchestrator.
            dry_run: If True, no files are written and no token is generated.
                     All gates are still evaluated and logged.

        Returns:
            ActuatorResult with status BLOCKED, PENDING_TOKEN, or DRY_RUN_OK.
        """
        result = ActuatorResult(
            status=ActuatorStatus.BLOCKED,
            plan_sha=plan.candidate_sha,
            bot_id=plan.bot_id,
        )

        # Gate 1 — plan eligibility
        if not self._gate_eligibility(plan, result):
            return result

        # Gate 2 — canary-only enforcement
        if not self._gate_canary_only(plan, result):
            return result

        # Gate 3 — cooldown
        if not self._gate_cooldown(result):
            return result

        # Gate 4 — kill-switch
        if not self._gate_kill_switch(result):
            return result

        # Gate 5 — risk guard
        if not self._gate_risk_guard(plan, result):
            return result

        # Gate 6 — mutation counter pre-check (log only, not block)
        result.mutation_counter_before = self._mutation_counter.read()
        self._log(result, "mutation_counter_pre_check", "pass",
                  f"current count: {result.mutation_counter_before}")

        # Gate 7 — shadow logger mandatory write
        if not dry_run:
            if not self._gate_shadow_log_apply_requested(plan, result):
                return result

        # All gates passed
        if dry_run:
            result.status = ActuatorStatus.DRY_RUN_OK
            self._log(result, "dry_run_complete", "pass",
                      "all gates passed in dry-run mode — no writes performed")
            return result

        # Generate human token
        token = self._token_manager.generate(plan.candidate_sha)
        result.apply_token = token
        result.status = ActuatorStatus.PENDING_TOKEN
        self._log(result, "human_token_generated", "pass",
                  f"token generated — awaiting human confirmation")
        return result

    def confirm_apply(
        self,
        plan: DeploymentPlan,
        token: str,
        dry_run: bool = False,
    ) -> ActuatorResult:
        """Validate token and execute the actual apply on freqforge-canary.

        Args:
            plan: The same DeploymentPlan used in request_apply().
            token: The token returned by request_apply().
            dry_run: If True, validates token but skips config write.

        Returns:
            ActuatorResult with status APPLIED, BLOCKED, or DRY_RUN_OK.
        """
        result = ActuatorResult(
            status=ActuatorStatus.BLOCKED,
            plan_sha=plan.candidate_sha,
            bot_id=plan.bot_id,
        )

        # Re-validate eligibility gates (re-check, not trust prior state)
        if not self._gate_eligibility(plan, result):
            return result
        if not self._gate_canary_only(plan, result):
            return result
        if not self._gate_kill_switch(result):
            return result

        # Validate human token
        if not self._token_manager.validate_and_consume(plan.candidate_sha, token):
            result.blocked_reason = "invalid or already-used human token"
            self._log(result, "token_validation", "block", result.blocked_reason)
            return result
        self._log(result, "token_validation", "pass", "human token validated and consumed")

        if dry_run:
            result.status = ActuatorStatus.DRY_RUN_OK
            self._log(result, "dry_run_confirm", "pass",
                      "token valid — dry-run mode, no apply written")
            return result

        # Execute apply
        delta_path = self._execute_apply(plan)
        result.config_delta_path = str(delta_path)
        self._log(result, "apply_executed", "pass",
                  f"config delta written to {delta_path}")

        # Mutation counter increment
        now = datetime.now(timezone.utc).isoformat()
        result.mutation_counter_after = self._mutation_counter.increment(
            plan_sha=plan.candidate_sha,
            bot_id=plan.bot_id,
            timestamp=now,
        )
        self._log(result, "mutation_counter_incremented", "pass",
                  f"counter: {result.mutation_counter_before} → {result.mutation_counter_after}")

        # Generate rollback plan
        rollback_path = self._generate_rollback(plan, delta_path)
        result.rollback_path = str(rollback_path) if rollback_path else None
        self._log(result, "rollback_prepared", "pass",
                  f"rollback plan at {result.rollback_path}")

        # Record cooldown
        self._cooldown.record_apply(plan.candidate_sha)

        # Final shadow log
        self._logger.log(
            bot_id=plan.bot_id,
            candidate_sha=plan.candidate_sha,
            params={},
            outcome="apply_completed",
            phase=APPLY_PHASE,
            decision="pass",
            reason=(
                f"apply executed on {CANARY_BOT_ID}; "
                f"delta={result.config_delta_path}; "
                f"rollback={result.rollback_path}; "
                f"mutation_count={result.mutation_counter_after}"
            ),
        )

        result.status = ActuatorStatus.APPLIED
        return result

    # ------------------------------------------------------------------
    # Gate helpers
    # ------------------------------------------------------------------

    def _gate_eligibility(
        self, plan: DeploymentPlan, result: ActuatorResult
    ) -> bool:
        if plan.status != DeploymentStatus.READY_FOR_SHADOW.value:
            result.blocked_reason = (
                f"plan status is {plan.status!r}; "
                f"only 'ready_for_shadow' plans are eligible"
            )
            self._log(result, "eligibility_check", "block", result.blocked_reason)
            return False
        self._log(result, "eligibility_check", "pass",
                  f"plan status={plan.status!r} — eligible")
        return True

    def _gate_canary_only(
        self, plan: DeploymentPlan, result: ActuatorResult
    ) -> bool:
        if plan.bot_id != CANARY_BOT_ID:
            result.blocked_reason = (
                f"Phase 1 allows canary-only applies; "
                f"got bot_id={plan.bot_id!r}"
            )
            self._log(result, "canary_check", "block", result.blocked_reason)
            return False
        self._log(result, "canary_check", "pass", f"bot_id={plan.bot_id!r} — canary confirmed")
        return True

    def _gate_cooldown(self, result: ActuatorResult) -> bool:
        ok, reason = self._cooldown.is_cooled_down()
        if not ok:
            result.blocked_reason = f"cooldown active: {reason}"
            self._log(result, "cooldown_check", "block", result.blocked_reason)
            return False
        self._log(result, "cooldown_check", "pass", reason)
        return True

    def _gate_kill_switch(self, result: ActuatorResult) -> bool:
        state = self._kill_switch.get_state()
        if state != KillSwitchState.NORMAL:
            result.blocked_reason = f"kill-switch is {state.value} — apply blocked"
            self._log(result, "kill_switch_check", "block", result.blocked_reason)
            return False
        self._log(result, "kill_switch_check", "pass", f"kill-switch state={state.value}")
        return True

    def _gate_risk_guard(
        self, plan: DeploymentPlan, result: ActuatorResult
    ) -> bool:
        rg = self._risk_guard.evaluate(plan)
        if rg.verdict != RiskGuardVerdict.PASS:
            result.blocked_reason = f"RiskGuard {rg.verdict.value}: {rg.reason}"
            self._log(result, "risk_guard_check", "block", result.blocked_reason)
            return False
        self._log(result, "risk_guard_check", "pass", rg.reason)
        return True

    def _gate_shadow_log_apply_requested(
        self, plan: DeploymentPlan, result: ActuatorResult
    ) -> bool:
        """Write the mandatory apply_requested log entry.

        If the ShadowLogger raises, the apply is blocked — no log = no apply.
        """
        try:
            self._logger.log(
                bot_id=plan.bot_id,
                candidate_sha=plan.candidate_sha,
                params={},
                outcome="apply_requested",
                phase=APPLY_PHASE,
                decision="pending",
                reason="all pre-apply gates passed; awaiting human token",
            )
            self._log(result, "shadow_log_write", "pass",
                      "apply_requested logged to ShadowLogger")
            return True
        except Exception as exc:  # noqa: BLE001
            result.blocked_reason = f"ShadowLogger write failed — apply blocked: {exc}"
            self._log(result, "shadow_log_write", "block", result.blocked_reason)
            return False

    # ------------------------------------------------------------------
    # Core apply implementation
    # ------------------------------------------------------------------

    def _execute_apply(self, plan: DeploymentPlan) -> Path:
        """Write the config delta for the canary bot.

        Phase 1: writes a JSON delta file to the canary config directory.
        No Docker restart, no freqtrade process signal — config file only.
        The delta file is named by plan SHA + timestamp for traceability.

        Args:
            plan: The approved DeploymentPlan to apply.

        Returns:
            Path to the written config delta file.
        """
        self._canary_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        sha_short = plan.candidate_sha[:12] if plan.candidate_sha else "unknown"
        delta_file = self._canary_dir / f"delta_{sha_short}_{ts}.json"

        delta = {
            "schema_version": "1.0",
            "plan_sha": plan.candidate_sha,
            "bot_id": plan.bot_id,
            "applied_utc": datetime.now(timezone.utc).isoformat(),
            "phase": APPLY_PHASE,
            "steps": plan.steps,
            "shadow_start_utc": plan.shadow_start_utc,
            "shadow_end_utc": plan.shadow_end_utc,
            "status_at_apply": plan.status,
            "reason": plan.reason,
            "apply_type": "weight_parameter_only",  # Phase 1 constraint
            "requires_restart": False,               # Phase 1: no restart
        }
        delta_file.write_text(json.dumps(delta, indent=2))
        return delta_file

    # ------------------------------------------------------------------
    # Rollback helper
    # ------------------------------------------------------------------

    def _generate_rollback(
        self, plan: DeploymentPlan, delta_path: Path
    ) -> Path | None:
        """Persist a rollback descriptor next to the delta file.

        The rollback descriptor records which delta file to revert and
        how (Phase 1: simply delete / ignore the delta file).
        """
        try:
            rollback_file = delta_path.with_suffix(".rollback.json")
            rollback = {
                "schema_version": "1.0",
                "plan_sha": plan.candidate_sha,
                "bot_id": plan.bot_id,
                "created_utc": datetime.now(timezone.utc).isoformat(),
                "delta_file": str(delta_path),
                "revert_action": "disable_delta",
                "revert_instructions": (
                    f"Delete or rename {delta_path.name} and restart freqforge-canary "
                    "to revert to the baseline config."
                ),
                "max_revert_seconds": 60,
            }
            rollback_file.write_text(json.dumps(rollback, indent=2))
            return rollback_file
        except Exception:  # noqa: BLE001
            return None

    # ------------------------------------------------------------------
    # Internal log helper
    # ------------------------------------------------------------------

    def _log(
        self,
        result: ActuatorResult,
        gate: str,
        decision: str,
        reason: str,
    ) -> None:
        """Append a gate entry to result.gate_log."""
        result.gate_log.append(
            {
                "gate": gate,
                "decision": decision,
                "reason": reason,
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            }
        )
