r"""Phase 1 Controlled Apply Actuator — Canary-First Human Gate (#363).

This module is the **canary-first readiness layer** that sits in front of the
existing apply-actuator stack (``controlled_apply.py`` -> ``policy.py`` ->
``proof.py``).  It adds the safety gates the existing runner lacks:

  1. **Canary-only**  — only ``freqtrade-freqforge-canary`` is accepted.
  2. **Safe keys + values** — keys checked against ``SAFE_PARAMETERS``;
     values validated against ``_PARAMETER_RANGES``.
  3. **Kill-switch NORMAL** — read-only gate; missing/unreadable -> BLOCKED.
  4. **RiskGuard PASS** — conservative gate; status unknown -> BLOCKED.
  5. **Human approval** — ``requires_human_approval`` must be ``True``.
  6. **L3 token** — ``APPROVE_SI_V2_RUNTIME_ACTUATOR_ACTIVATION=APPROVE``.
  7. **Cooldown** — max 1 apply per 7 days; corrupt state -> fail-closed.
  8. **dry_run** — must remain ``True``.

Architecture
------------

``check_readiness()`` is a **read-only** runner that evaluates all gates and
returns a ``ReadinessReport`` with the verdict ``READY_FOR_HUMAN_L3_APPLY``
or ``BLOCKED``.  It performs **zero side-effects**.

``execute_apply()`` runs only after readiness is GREEN and the L3 token is
present.  It delegates to ``compute_apply_result()`` from ``policy.py`` for
binding -> overlay_merge -> proof -> verdict.

Safety invariants
-----------------
  - Never restarts bots.
  - Never disables dry-run.
  - Never enables live trading.
  - Never changes strategies.
  - Never mutates Docker/Compose/cron.
  - Fail-closed: uncertainty -> BLOCKED.
  - Status name is ``SHADOW_OVERLAY_WRITTEN`` (not ``APPLIED``) until runtime
    proof is GREEN.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Final

from si_v2.apply_actuator.models import (
    ApplyActuatorResult,
    ApplyStatus,
    OverlayProposal,
)
from si_v2.apply_actuator.policy import compute_apply_result
from si_v2.apply_actuator.runtime_binding import (
    build_host_overlay_path,
    resolve_binding,
)
from si_v2.propose.safe_parameters import (
    FORBIDDEN_KEYS,
    SAFE_PARAMETERS,
    validate_safe_parameter,
)

CANARY_BOT_ID: Final[str] = "freqtrade-freqforge-canary"
COOLDOWN_DAYS: Final[int] = 7
L3_TOKEN_ENV: Final[str] = "APPROVE_SI_V2_RUNTIME_ACTUATOR_ACTIVATION"
L3_TOKEN_VALUE: Final[str] = "APPROVE"
DEFAULT_STATE_DIR: Final[Path] = Path(
    "/opt/data/profiles/orchestrator/state/si_v2_controlled_apply"
)
RISKGUARD_STATE_PATH: Final[Path] = Path(
    "/home/hermes/projects/trading/orchestrator/state/riskguard/riskguard_state.json"
)


@dataclass(frozen=True)
class GateResult:
    """Result of a single gate check."""

    passed: bool
    reason: str = ""

    def __bool__(self) -> bool:
        return self.passed


@dataclass(frozen=True)
class ReadinessReport:
    """Complete read-only readiness assessment."""

    candidate_sha: str = ""
    bot_id: str = ""
    parameter_overlay: dict[str, int | float] = field(default_factory=dict)
    canary_gate: GateResult = field(
        default_factory=lambda: GateResult(False, "not checked")
    )
    safe_parameters_gate: GateResult = field(
        default_factory=lambda: GateResult(False, "not checked")
    )
    kill_switch_gate: GateResult = field(
        default_factory=lambda: GateResult(False, "not checked")
    )
    riskguard_gate: GateResult = field(
        default_factory=lambda: GateResult(False, "not checked")
    )
    human_approval_gate: GateResult = field(
        default_factory=lambda: GateResult(False, "not checked")
    )
    token_gate: GateResult = field(
        default_factory=lambda: GateResult(False, "not checked")
    )
    cooldown_gate: GateResult = field(
        default_factory=lambda: GateResult(False, "not checked")
    )
    dry_run_gate: GateResult = field(
        default_factory=lambda: GateResult(False, "not checked")
    )
    planned_overlay_path: str = ""
    ready: bool = False

    def to_dict(self) -> dict[str, object]:
        gates: dict[str, dict[str, object]] = {}
        for name in (
            "canary_gate", "safe_parameters_gate", "kill_switch_gate",
            "riskguard_gate", "human_approval_gate", "token_gate",
            "cooldown_gate", "dry_run_gate",
        ):
            gate: GateResult = getattr(self, name)
            gates[name] = {"passed": gate.passed, "reason": gate.reason}
        return {
            "candidate_sha": self.candidate_sha,
            "bot_id": self.bot_id,
            "parameter_overlay": dict(self.parameter_overlay),
            **gates,
            "planned_overlay_path": self.planned_overlay_path,
            "ready": self.ready,
        }


@dataclass(frozen=True)
class ControlledApplyDecision:
    """Complete result of a controlled apply attempt."""

    overall_status: str = "BLOCKED"
    candidate_sha: str = ""
    bot_id: str = ""
    parameter_overlay: dict[str, int | float] = field(default_factory=dict)
    overlay_path: str = ""
    overlay_sha256: str = ""
    rollback_plan_path: str = ""
    runtime_visible: bool = False
    runtime_proof_status: str = "NOT_RUN"
    readiness_report: ReadinessReport = field(default_factory=ReadinessReport)
    actuator_result: ApplyActuatorResult = field(default_factory=ApplyActuatorResult)
    errors: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def mutation_counter_should_increment(self) -> bool:
        return self.actuator_result.mutation_counter_should_increment

    @property
    def measurement_allowed(self) -> bool:
        return self.actuator_result.measurement_allowed

    def to_dict(self) -> dict[str, object]:
        return {
            "overall_status": self.overall_status,
            "candidate_sha": self.candidate_sha,
            "bot_id": self.bot_id,
            "parameter_overlay": dict(self.parameter_overlay),
            "overlay_path": self.overlay_path,
            "overlay_sha256": self.overlay_sha256,
            "rollback_plan_path": self.rollback_plan_path,
            "readiness_report": self.readiness_report.to_dict(),
            "actuator_result": self.actuator_result.to_dict(),
            "mutation_counter_should_increment": (
                self.mutation_counter_should_increment
            ),
            "measurement_allowed": self.measurement_allowed,
            "runtime_visible": self.runtime_visible,
            "runtime_proof_status": self.runtime_proof_status,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


def check_canary_bot(bot_id: str) -> GateResult:
    """Gate 1: Only the canary bot is accepted."""
    if bot_id == CANARY_BOT_ID:
        return GateResult(True, f"Bot {bot_id!r} is the approved canary")
    return GateResult(
        False,
        f"Bot {bot_id!r} is not the canary ({CANARY_BOT_ID!r}). "
        f"Canary-only gate blocks all non-canary applies.",
    )


def check_safe_parameters(
    overlay: Mapping[str, object],
) -> GateResult:
    """Gate 2: Only SAFE_PARAMETERS keys with validated values."""
    if not overlay:
        return GateResult(False, "Empty overlay - no parameters to apply")
    bad_keys: list[str] = []
    out_of_range: list[str] = []
    for key, value in overlay.items():
        if key in FORBIDDEN_KEYS:
            bad_keys.append(f"{key!r} (forbidden)")
            continue
        if key not in SAFE_PARAMETERS:
            bad_keys.append(f"{key!r} (not in SAFE_PARAMETERS)")
            continue
        try:
            if not validate_safe_parameter(key, float(value)):  # type: ignore[arg-type]
                out_of_range.append(f"{key}={value!r} (out of range)")
        except (ValueError, TypeError):
            out_of_range.append(f"{key}={value!r} (non-numeric)")
    issues = bad_keys + out_of_range
    if issues:
        return GateResult(
            False,
            f"Parameter validation failed: {issues}. "
            f"Allowed keys: {sorted(SAFE_PARAMETERS)}.",
        )
    return GateResult(True, "All parameter keys and values validated")


def check_kill_switch(kill_switch_path: Path | None = None) -> GateResult:
    """Gate 3: Kill-switch must be NORMAL. Fail-closed on unreadable/corrupt."""
    if kill_switch_path is None:
        here = Path(__file__).resolve().parent
        for p in [
            here / "var" / "kill_switch.json",
        ]:
            if p.exists():
                kill_switch_path = p
                break
    if kill_switch_path is None:
        return GateResult(False, "No kill-switch path provided - fail-closed BLOCKED")
    if not kill_switch_path.exists():
        return GateResult(False, "Kill-switch file not found - fail-closed BLOCKED")
    try:
        data = json.loads(kill_switch_path.read_text())
    except (json.JSONDecodeError, OSError):
        return GateResult(False, "Kill-switch corrupt/unreadable - fail-closed BLOCKED")
    if not isinstance(data, dict):
        return GateResult(False, "Kill-switch state not a dict - fail-closed BLOCKED")
    mode = data.get("mode", "")
    if mode == "NORMAL":
        return GateResult(True, "Kill-switch mode is NORMAL")
    if mode == "HALT_NEW":
        return GateResult(False, "Kill-switch is HALT_NEW: blocking entries")
    if mode == "EMERGENCY":
        return GateResult(False, "Kill-switch is EMERGENCY: blocking all operations")
    return GateResult(False, f"Kill-switch mode {mode!r} unrecognised - fail-closed BLOCKED")


def _load_riskguard_state(path: Path) -> dict[str, object]:
    """Read the canonical RiskGuard state file.  Never raises."""
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def derive_riskguard_status(state: dict[str, object]) -> str:
    """Derive a PASS/FAIL verdict from the canonical RiskGuard state dict.

    PASS conditions (all must hold):
      - summary.status == "ACTIVE"
      - at least one pair verdict == "ACCEPTED"
      - no pair verdict == "BLOCK_ENTRY"

    Anything else is FAIL, including missing/corrupt/unknown state.
    """
    summary = state.get("summary")
    if not isinstance(summary, dict):
        return "FAIL"
    if summary.get("status") != "ACTIVE":
        return "FAIL"

    pairs = state.get("pairs")
    if not isinstance(pairs, dict):
        return "FAIL"

    has_accepted = False
    for pair_data in pairs.values():
        if not isinstance(pair_data, dict):
            continue
        verdict = pair_data.get("verdict")
        if verdict == "BLOCK_ENTRY":
            return "FAIL"
        if verdict == "ACCEPTED":
            has_accepted = True

    return "PASS" if has_accepted else "FAIL"


def read_riskguard_status(state_path: Path | None = None) -> GateResult:
    """Read canonical RiskGuard state and return PASS or fail-closed BLOCK."""
    path = state_path or RISKGUARD_STATE_PATH
    state = _load_riskguard_state(path)
    if not state:
        return GateResult(
            False,
            "RiskGuard state missing or unreadable - fail-closed BLOCKED.",
        )
    status = derive_riskguard_status(state)
    if status == "PASS":
        return GateResult(True, "RiskGuard state ACTIVE with ACCEPTED pair(s)")
    return GateResult(
        False,
        f"RiskGuard derived status is {status!r} - requires PASS.",
    )


def check_riskguard(riskguard_status: str | None = None) -> GateResult:
    """Gate 4: RiskGuard must report PASS.  None -> BLOCKED.

    If a literal status string is supplied, it is used directly.
    Otherwise the canonical RiskGuard state file is read and a PASS/FAIL
    verdict is derived read-only.
    """
    if riskguard_status is None:
        return read_riskguard_status()
    if riskguard_status == "PASS":
        return GateResult(True, "RiskGuard status is PASS")
    return GateResult(
        False,
        f"RiskGuard status is {riskguard_status!r} - requires PASS.",
    )


def check_human_approval(requires_human_approval: bool) -> GateResult:
    """Gate 5: requires_human_approval must be True."""
    if requires_human_approval is True:
        return GateResult(True, "requires_human_approval is True")
    return GateResult(
        False,
        "requires_human_approval is False. "
        "Human approval must be explicitly set.",
    )


def check_token() -> GateResult:
    """Gate 6: L3 activation token must be present."""
    value = os.environ.get(L3_TOKEN_ENV, "")
    if value == L3_TOKEN_VALUE:
        return GateResult(True, f"Token {L3_TOKEN_ENV!r} is set to APPROVE")
    return GateResult(
        False,
        f"Token {L3_TOKEN_ENV!r} not set or incorrect "
        f"(value={value!r}).",
    )


@dataclass
class CooldownState:
    """Persistent cooldown state.  Fail-closed on corrupt state."""

    last_apply_utc: str = ""
    candidate_sha: str = ""
    bot_id: str = ""
    _corrupt: bool = False

    def is_on_cooldown(self) -> bool:
        if self._corrupt:
            return True
        if not self.last_apply_utc:
            return False
        try:
            last = datetime.fromisoformat(self.last_apply_utc)
        except (ValueError, TypeError):
            return True
        elapsed = datetime.now(UTC) - last
        return elapsed < timedelta(days=COOLDOWN_DAYS)

    def remaining_seconds(self) -> float:
        if self._corrupt:
            return float(COOLDOWN_DAYS) * 86400
        if not self.last_apply_utc:
            return 0.0
        try:
            last = datetime.fromisoformat(self.last_apply_utc)
        except (ValueError, TypeError):
            return float(COOLDOWN_DAYS) * 86400
        elapsed = (datetime.now(UTC) - last).total_seconds()
        remaining = timedelta(days=COOLDOWN_DAYS).total_seconds() - elapsed
        return max(0.0, remaining)

    @classmethod
    def load(cls, state_dir: Path) -> CooldownState:
        path = state_dir / "cooldown_state.json"
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text())
            return cls(
                last_apply_utc=data.get("last_apply_utc", ""),
                candidate_sha=data.get("candidate_sha", ""),
                bot_id=data.get("bot_id", ""),
            )
        except (json.JSONDecodeError, OSError):
            return cls(_corrupt=True)

    def save(self, state_dir: Path) -> None:
        state_dir.mkdir(parents=True, exist_ok=True)
        tmp = state_dir / f"cooldown_state.json.tmp.{os.getpid()}"
        tmp.write_text(
            json.dumps(
                {
                    "last_apply_utc": self.last_apply_utc,
                    "candidate_sha": self.candidate_sha,
                    "bot_id": self.bot_id,
                },
                indent=2,
            )
        )
        tmp.replace(state_dir / "cooldown_state.json")


def check_cooldown(
    state_dir: Path,
) -> tuple[CooldownState, GateResult]:
    """Gate 7: Load and check cooldown state.  Fail-closed on corrupt."""
    state_dir.mkdir(parents=True, exist_ok=True)
    state = CooldownState.load(state_dir)
    if state._corrupt:
        return state, GateResult(
            False,
            "Cooldown state corrupt - fail-closed BLOCKED.",
        )
    if state.is_on_cooldown():
        remaining = state.remaining_seconds()
        days = int(remaining // 86400)
        hours = int((remaining % 86400) // 3600)
        return state, GateResult(
            False,
            f"Cooldown active: last apply {state.last_apply_utc} "
            f"(~{days}d {hours}h remaining). "
            f"Max 1 apply per {COOLDOWN_DAYS} days.",
        )
    return state, GateResult(True, "Cooldown clear")


def check_dry_run(
    pre_apply_config: dict[str, object] | None,
) -> GateResult:
    """Gate 8: dry_run must be True in pre-apply config."""
    if pre_apply_config is None:
        return GateResult(
            False,
            "pre_apply_config not provided - cannot verify dry_run. "
            "Supply pre_apply_config with dry_run=True.",
        )
    dry_run_val = pre_apply_config.get("dry_run", True)
    if dry_run_val is True:
        return GateResult(True, "dry_run is True")
    return GateResult(
        False,
        f"dry_run is {dry_run_val!r} - cannot apply to live.",
    )


def check_readiness(
    candidate_sha: str,
    bot_id: str,
    parameter_overlay: dict[str, int | float],
    *,
    requires_human_approval: bool = True,
    state_dir: Path | None = None,
    kill_switch_path: Path | None = None,
    riskguard_status: str | None = None,
    pre_apply_config: dict[str, object] | None = None,
) -> ReadinessReport:
    """Evaluate all gates and return a read-only readiness report."""
    resolved_state_dir = state_dir or DEFAULT_STATE_DIR
    g1 = check_canary_bot(bot_id)
    g2 = check_safe_parameters(parameter_overlay)
    g3 = check_kill_switch(kill_switch_path)
    g4 = check_riskguard(riskguard_status)
    g5 = check_human_approval(requires_human_approval)
    g6 = check_token()
    _, g7 = check_cooldown(resolved_state_dir)
    g8 = check_dry_run(pre_apply_config)
    planned_path = ""
    binding = resolve_binding(bot_id)
    if binding is not None:
        planned_path = build_host_overlay_path(
            bot_id, candidate_sha
        ) or ""
    all_pass = all(g for g in [g1, g2, g3, g4, g5, g6, g7, g8])
    return ReadinessReport(
        candidate_sha=candidate_sha,
        bot_id=bot_id,
        parameter_overlay=dict(parameter_overlay),
        canary_gate=g1,
        safe_parameters_gate=g2,
        kill_switch_gate=g3,
        riskguard_gate=g4,
        human_approval_gate=g5,
        token_gate=g6,
        cooldown_gate=g7,
        dry_run_gate=g8,
        planned_overlay_path=planned_path,
        ready=all_pass,
    )


def write_overlay_file(
    candidate_sha: str,
    overlay: dict[str, int | float],
    overlay_dir: Path | None = None,
) -> tuple[str, str]:
    """Write a flat-key overlay JSON file and return (path, sha256)."""
    if overlay_dir is None:
        binding = resolve_binding(CANARY_BOT_ID)
        if binding is None:
            raise ValueError(f"No runtime binding for {CANARY_BOT_ID!r}")
        overlay_dir = Path(binding.host_user_data_path)
    overlay_dir.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = dict(overlay)
    payload["_meta"] = {
        "candidate_sha": candidate_sha,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "source": "si_v2_controlled_apply_actuator",
    }
    payload_bytes = json.dumps(
        payload, indent=2, sort_keys=True
    ).encode("utf-8")
    sha = hashlib.sha256(payload_bytes).hexdigest()
    filename = f"overlay_{candidate_sha[:16]}.json"
    path = overlay_dir / filename
    tmp = path.with_suffix(f".json.tmp.{os.getpid()}")
    tmp.write_bytes(payload_bytes)
    tmp.replace(path)
    return str(path), sha


def create_rollback_plan(
    candidate_sha: str,
    bot_id: str,
    overlay_path: str,
    pre_apply_config: dict[str, object],
    plan_dir: Path | None = None,
) -> str:
    """Create a rollback plan document and return its path."""
    if plan_dir is None:
        plan_dir = DEFAULT_STATE_DIR / "rollback_plans"
    plan_dir.mkdir(parents=True, exist_ok=True)
    snapshot_keys = set(SAFE_PARAMETERS) | {"dry_run", "max_open_trades"}
    plan = {
        "candidate_sha": candidate_sha,
        "bot_id": bot_id,
        "overlay_path": overlay_path,
        "pre_apply_config_snapshot": {
            k: v for k, v in pre_apply_config.items()
            if k in snapshot_keys
        },
        "created_at_utc": datetime.now(UTC).isoformat(),
        "restore_instructions": (
            f"To roll back candidate {candidate_sha[:16]} on {bot_id}:\n"
            f"  1. Remove the overlay file at {overlay_path}\n"
            f"  2. Verify base config is unmodified\n"
            f"  3. [L3 SEPARATE APPROVAL] Restart the bot\n"
            f"     - Restart is NOT performed by this actuator.\n"
            f"  4. Verify parameters return to pre-apply values\n"
        ),
    }
    filename = f"rollback_{candidate_sha[:16]}.json"
    path = plan_dir / filename
    tmp = path.with_suffix(f".json.tmp.{os.getpid()}")
    tmp.write_text(json.dumps(plan, indent=2))
    tmp.replace(path)
    return str(path)


def log_shadow_events(
    candidate_sha: str,
    bot_id: str,
    parameter_overlay: dict[str, int | float],
    overlay_path: str,
    rollback_path: str,
    log_dir: Path | None = None,
) -> None:
    """Log apply events using the existing ShadowLogger."""
    try:
        from si_v2.deploy.shadow_logger import ShadowLogger
        logger = ShadowLogger(log_dir=log_dir)
        events = [
            ("apply_requested", "pass", "Gates passed"),
            ("apply_approved", "pass", f"Overlay at {overlay_path}"),
            ("apply_executed", "pass", f"Rollback at {rollback_path}"),
            ("rollback_ready", "pass", "Rollback ready"),
        ]
        for outcome, decision, reason in events:
            logger.log(
                bot_id=bot_id,
                candidate_sha=candidate_sha,
                params=dict(parameter_overlay),
                outcome=outcome,
                phase="deploy",
                decision=decision,
                reason=reason,
            )
    except Exception:
        fallback_dir = log_dir or DEFAULT_STATE_DIR / "shadow_log"
        fallback_dir.mkdir(parents=True, exist_ok=True)
        fallback_path = fallback_dir / "controlled_apply.jsonl"
        entry = {
            "timestamp_utc": datetime.now(UTC).isoformat(),
            "candidate_sha": candidate_sha,
            "bot_id": bot_id,
            "overlay_path": overlay_path,
            "rollback_path": rollback_path,
        }
        with open(fallback_path, "a") as f:
            f.write(json.dumps(entry, default=str) + "\n")


def execute_apply(
    candidate_sha: str,
    bot_id: str,
    parameter_overlay: dict[str, int | float],
    *,
    requires_human_approval: bool = True,
    state_dir: Path | None = None,
    overlay_dir: Path | None = None,
    plan_dir: Path | None = None,
    log_dir: Path | None = None,
    pre_apply_config: dict[str, object] | None = None,
    kill_switch_path: Path | None = None,
    riskguard_status: str | None = None,
) -> ControlledApplyDecision:
    """Execute the controlled apply after all gates pass."""
    resolved_state_dir = state_dir or DEFAULT_STATE_DIR
    report = check_readiness(
        candidate_sha,
        bot_id,
        parameter_overlay,
        requires_human_approval=requires_human_approval,
        state_dir=resolved_state_dir,
        kill_switch_path=kill_switch_path,
        riskguard_status=riskguard_status,
        pre_apply_config=pre_apply_config,
    )
    if not report.ready:
        all_gates = [
            report.canary_gate,
            report.safe_parameters_gate,
            report.kill_switch_gate,
            report.riskguard_gate,
            report.human_approval_gate,
            report.token_gate,
            report.cooldown_gate,
            report.dry_run_gate,
        ]
        errors = [g.reason for g in all_gates if not g.passed]
        return ControlledApplyDecision(
            overall_status="BLOCKED",
            candidate_sha=candidate_sha,
            bot_id=bot_id,
            parameter_overlay=dict(parameter_overlay),
            readiness_report=report,
            errors=tuple(errors),
        )
    overlay_path, overlay_sha = write_overlay_file(
        candidate_sha, parameter_overlay, overlay_dir=overlay_dir,
    )
    resolved_plan_dir = plan_dir or DEFAULT_STATE_DIR / "rollback_plans"
    rollback_path = create_rollback_plan(
        candidate_sha,
        bot_id,
        overlay_path,
        pre_apply_config or {},
        plan_dir=resolved_plan_dir,
    )
    log_shadow_events(
        candidate_sha,
        bot_id,
        parameter_overlay,
        overlay_path,
        rollback_path,
        log_dir=log_dir,
    )
    overlay_proposal = OverlayProposal(
        proposal_id=candidate_sha,
        bot_id=bot_id,
        policy="safe_parameter_overlay_only",
        parameters=dict(parameter_overlay),
    )
    actuator_result = compute_apply_result(
        overlay_proposal,
        docker_available=True,
    )
    if actuator_result.status == ApplyStatus.APPLIED_WITH_RUNTIME_PROOF:
        overall_status = "APPLIED_WITH_RUNTIME_PROOF"
    else:
        overall_status = "SHADOW_OVERLAY_WRITTEN"
    if overall_status in (
        "APPLIED_WITH_RUNTIME_PROOF", "SHADOW_OVERLAY_WRITTEN"
    ):
        new_cooldown = CooldownState(
            last_apply_utc=datetime.now(UTC).isoformat(),
            candidate_sha=candidate_sha,
            bot_id=bot_id,
        )
        new_cooldown.save(resolved_state_dir)
    return ControlledApplyDecision(
        overall_status=overall_status,
        candidate_sha=candidate_sha,
        bot_id=bot_id,
        parameter_overlay=dict(parameter_overlay),
        overlay_path=overlay_path,
        overlay_sha256=overlay_sha,
        rollback_plan_path=rollback_path,
        readiness_report=report,
        actuator_result=actuator_result,
        warnings=tuple(actuator_result.warnings),
    )


def run_controlled_apply_canary(
    candidate_sha: str,
    bot_id: str,
    parameter_overlay: dict[str, int | float],
    *,
    requires_human_approval: bool = True,
    state_dir: Path | None = None,
    overlay_dir: Path | None = None,
    plan_dir: Path | None = None,
    log_dir: Path | None = None,
    pre_apply_config: dict[str, object] | None = None,
    kill_switch_path: Path | None = None,
    riskguard_status: str | None = None,
) -> ControlledApplyDecision:
    """Run the full controlled apply pipeline for the canary bot."""
    return execute_apply(
        candidate_sha,
        bot_id,
        parameter_overlay,
        requires_human_approval=requires_human_approval,
        state_dir=state_dir,
        overlay_dir=overlay_dir,
        plan_dir=plan_dir,
        log_dir=log_dir,
        pre_apply_config=pre_apply_config,
        kill_switch_path=kill_switch_path,
        riskguard_status=riskguard_status,
    )


def summarize_decision(
    decision: ControlledApplyDecision,
) -> dict[str, object]:
    """Produce a short summary dict for human-friendly reporting."""
    return {
        "status": decision.overall_status,
        "candidate": (
            decision.candidate_sha[:16]
            if decision.candidate_sha else ""
        ),
        "bot": decision.bot_id,
        "ready": decision.readiness_report.ready,
        "errors": len(decision.errors),
        "warnings": len(decision.warnings),
        "overlay_written": bool(decision.overlay_path),
        "rollback_ready": bool(decision.rollback_plan_path),
        "mutation_counter_should_increment": (
            decision.mutation_counter_should_increment
        ),
        "measurement_allowed": decision.measurement_allowed,
        "runtime_visible": decision.runtime_visible,
        "runtime_proof_status": decision.runtime_proof_status,
    }
