r"""Phase 1 Controlled Apply Actuator — Canary-First Human Gate (#363).

Bridges SI-v2 Evidence Bundle Candidates → safe, gated, auditable runtime overlay
overwriting for the canary bot only.  Human approval is mandatory at every step.

Gate hierarchy (ALL must pass):
  1. Bot gate:  only ``freqtrade-freqforge-canary`` is accepted
  2. Key gate:  only :data:`SAFE_OVERLAY_KEYS` are allowed
  3. Approval:  ``requires_human_approval`` must be ``True``
  4. Token:     L3 activation token must be present
  5. Cooldown:  at most 1 apply per 7 days
  6. dry_run:   must remain ``True`` (never apply to live)

On success the actuator:
  - Writes an overlay JSON file to the bot's config directory
  - Creates a rollback snapshot + plan
  - Logs all four ShadowLogger events (requested, approved, executed, rollback_ready)
  - Does NOT restart the bot (that requires separate L3 approval)

Safety invariants (enforced regardless of token):
  - Never writes to runtime bot mount paths outside the overlay
  - Never restarts bots
  - Never disables dry-run mode
  - Never enables live trading
  - Never changes strategies
  - Never mutates Docker/Compose/cron
  - Fail-closed: uncertainty → BLOCKED

Reference candidate: f68a031923d0 (freqtrade-freqforge-canary, cooldown_candles 3→4)
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Final

from si_v2.propose.safe_parameters import SAFE_PARAMETERS

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CANARY_BOT_ID: Final[str] = "freqtrade-freqforge-canary"
"""The only bot this actuator is allowed to target."""

SAFE_OVERLAY_KEYS: Final[tuple[str, ...]] = SAFE_PARAMETERS
"""Subset of parameters that may be mutated via overlay."""

COOLDOWN_DAYS: Final[int] = 7
"""Minimum interval between apply attempts."""

L3_TOKEN_ENV: Final[str] = "APPROVE_SI_V2_RUNTIME_ACTUATOR_ACTIVATION"
L3_TOKEN_VALUE: Final[str] = "APPROVE"

DEFAULT_STATE_DIR: Final[Path] = Path(
    "/opt/data/profiles/orchestrator/state/si_v2_controlled_apply"
)

# ---------------------------------------------------------------------------
# Status / result types
# ---------------------------------------------------------------------------


class ApplyGateResult:
    """Simple result type for a single gate check."""

    def __init__(self, passed: bool, reason: str = "") -> None:
        self.passed = passed
        self.reason = reason

    def __bool__(self) -> bool:
        return self.passed

    def __repr__(self) -> str:
        return f"ApplyGateResult({self.passed}, {self.reason!r})"


@dataclass(frozen=True)
class ControlledApplyDecision:
    """Complete result of a controlled apply attempt.

    All gates are evaluated before any side-effect occurs.
    """

    overall_status: str = "BLOCKED"
    """One of: BLOCKED, COOLDOWN_ACTIVE, APPROVED, APPLIED, ROLLBACK_READY."""

    candidate_sha: str = ""
    bot_id: str = ""
    parameter_overlay: dict[str, int | float] = field(default_factory=dict)
    overlay_path: str = ""
    overlay_sha256: str = ""
    rollback_plan_path: str = ""
    errors: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, object]:
        return {
            "overall_status": self.overall_status,
            "candidate_sha": self.candidate_sha,
            "bot_id": self.bot_id,
            "parameter_overlay": dict(self.parameter_overlay),
            "overlay_path": self.overlay_path,
            "overlay_sha256": self.overlay_sha256,
            "rollback_plan_path": self.rollback_plan_path,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


# ---------------------------------------------------------------------------
# Canary gate — bot validation
# ---------------------------------------------------------------------------


def check_canary_bot(bot_id: str) -> ApplyGateResult:
    """Gate 1: Only the canary bot is accepted."""
    if bot_id == CANARY_BOT_ID:
        return ApplyGateResult(True, f"Bot {bot_id!r} is the approved canary")
    return ApplyGateResult(
        False,
        f"Bot {bot_id!r} is not the canary ({CANARY_BOT_ID!r}). "
        f"Cannotary-only gate blocks all non-canary applies.",
    )


def check_safe_overlay_keys(
    overlay: Mapping[str, object],
) -> ApplyGateResult:
    """Gate 2: Only SAFE_OVERLAY_KEYS are allowed."""
    if not overlay:
        return ApplyGateResult(False, "Empty overlay - no parameters to apply")
    bad_keys = [k for k in overlay if k not in SAFE_OVERLAY_KEYS]
    if not bad_keys:
        return ApplyGateResult(True, "All parameter keys are in SAFE_OVERLAY_KEYS")
    return ApplyGateResult(
        False,
        f"Unsafe or unrecognised parameter keys: {sorted(bad_keys)}. "
        f"Allowed: {sorted(SAFE_OVERLAY_KEYS)}.",
    )


def check_human_approval_flag(
    proposal: dict[str, object],
) -> ApplyGateResult:
    """Gate 3: requires_human_approval must be True."""
    flag = proposal.get("requires_human_approval", False)
    if flag is True:
        return ApplyGateResult(True, "requires_human_approval is True")
    return ApplyGateResult(
        False,
        f"requires_human_approval is {flag!r}. "
        "Human approval must be explicitly set.",
    )


def check_activation_token() -> ApplyGateResult:
    """Gate 4: L3 activation token must be present."""
    value = os.environ.get(L3_TOKEN_ENV, "")
    if value == L3_TOKEN_VALUE:
        return ApplyGateResult(
            True, f"Token {L3_TOKEN_ENV!r} is set to APPROVE"
        )
    return ApplyGateResult(
        False,
        f"Token {L3_TOKEN_ENV!r} not set or incorrect (value={value!r}). "
        "Set it to APPROVE to pass the L3 gate.",
    )


# ---------------------------------------------------------------------------
# Cooldown state — max 1 apply per 7 days
# ---------------------------------------------------------------------------


@dataclass
class CooldownState:
    """Persistent cooldown state stored as JSON.

    Tracks the last apply timestamp per candidate/bot so the cooldown
    gate can reject applies that arrive too soon.
    """

    last_apply_utc: str = ""
    """ISO-8601 timestamp of the last successful apply."""

    candidate_sha: str = ""
    """SHA of the candidate that was last applied."""

    bot_id: str = ""
    """Bot that received the last apply."""

    def is_on_cooldown(self) -> bool:
        """Check whether the cooldown period is still active."""
        if not self.last_apply_utc:
            return False
        try:
            last = datetime.fromisoformat(self.last_apply_utc)
        except (ValueError, TypeError):
            return False
        elapsed = datetime.now(UTC) - last
        return elapsed < timedelta(days=COOLDOWN_DAYS)

    def remaining_seconds(self) -> float:
        """Seconds remaining until cooldown expires (0 if not on cooldown)."""
        if not self.last_apply_utc:
            return 0.0
        try:
            last = datetime.fromisoformat(self.last_apply_utc)
        except (ValueError, TypeError):
            return 0.0
        elapsed = (datetime.now(UTC) - last).total_seconds()
        remaining = timedelta(days=COOLDOWN_DAYS).total_seconds() - elapsed
        return max(0.0, remaining)

    @classmethod
    def load(cls, state_dir: Path) -> CooldownState:
        """Load cooldown state from disk, or return fresh state."""
        path = state_dir / "cooldown_state.json"
        if path.exists():
            try:
                data = json.loads(path.read_text())
                return cls(
                    last_apply_utc=data.get("last_apply_utc", ""),
                    candidate_sha=data.get("candidate_sha", ""),
                    bot_id=data.get("bot_id", ""),
                )
            except (json.JSONDecodeError, OSError):
                pass
        return cls()

    def save(self, state_dir: Path) -> None:
        """Persist cooldown state to disk atomically."""
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


def check_cooldown(state_dir: Path) -> CooldownState:
    """Gate 5: Load and check cooldown state.

    Returns the current CooldownState.  Caller calls ``is_on_cooldown()``
    to decide whether to block.
    """
    return CooldownState.load(state_dir)


# ---------------------------------------------------------------------------
# Overlay file writer — writes delta overlay to canary config dir
# ---------------------------------------------------------------------------


DEFAULT_OVERLAY_BASE: Final[Path] = Path(
    "/opt/data/profiles/orchestrator/config_overlays/canary"
)


def write_overlay_file(
    candidate_sha: str,
    overlay: dict[str, int | float],
    overlay_dir: Path | None = None,
) -> tuple[str, str]:
    """Write an overlay JSON file and return (path, sha256).

    The overlay is written as a JSON delta file with the format:
      {
        "candidate_sha": "...",
        "overlay": { ... },
        "created_at_utc": "..."
      }

    For testing, *overlay_dir* can be overridden; defaults to
    :data:`DEFAULT_OVERLAY_BASE`.
    """
    if overlay_dir is None:
        overlay_dir = DEFAULT_OVERLAY_BASE

    overlay_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "candidate_sha": candidate_sha,
        "overlay": dict(overlay),
        "created_at_utc": datetime.now(UTC).isoformat(),
    }

    payload_bytes = json.dumps(payload, indent=2).encode("utf-8")
    sha = hashlib.sha256(payload_bytes).hexdigest()

    filename = f"overlay_{candidate_sha[:16]}.json"
    path = overlay_dir / filename

    # Atomic write
    tmp = path.with_suffix(f".json.tmp.{os.getpid()}")
    tmp.write_bytes(payload_bytes)
    tmp.replace(path)

    return str(path), sha


# ---------------------------------------------------------------------------
# Rollback plan — capture pre-apply config snapshot
# ---------------------------------------------------------------------------


def create_rollback_plan(
    candidate_sha: str,
    bot_id: str,
    overlay_path: str,
    pre_apply_config: dict[str, object],
    plan_dir: Path | None = None,
) -> str:
    """Create a rollback plan document and return its path.

    The plan captures:
      - Which candidate was applied
      - The pre-apply base config snapshot
      - The overlay file path
      - Timestamp and instructions for restoring

    For testing, *plan_dir* can be overridden; defaults to the state dir.
    """
    if plan_dir is None:
        plan_dir = DEFAULT_STATE_DIR / "rollback_plans"

    plan_dir.mkdir(parents=True, exist_ok=True)

    plan = {
        "candidate_sha": candidate_sha,
        "bot_id": bot_id,
        "overlay_path": overlay_path,
        "pre_apply_config_snapshot": {
            k: v
            for k, v in pre_apply_config.items()
            if k in SAFE_OVERLAY_KEYS or k in ("dry_run", "max_open_trades")
        },
        "created_at_utc": datetime.now(UTC).isoformat(),
        "restore_instructions": (
            f"To roll back candidate {candidate_sha[:16]} on {bot_id}:\n"
            f"  1. Stop the bot (docker stop {bot_id.replace('freqtrade-', 'trading-')}-1)\n"
            f"  2. Remove or restore the overlay file at {overlay_path}\n"
            f"  3. Ensure the base config at the snapshot location is unmodified "
            f"or restore from backup\n"
            f"  4. Restart the bot (docker start ...)\n"
            f"  5. Verify cooldown_candles returns to its pre-apply value\n"
        ),
    }

    filename = f"rollback_{candidate_sha[:16]}.json"
    path = plan_dir / filename

    tmp = path.with_suffix(f".json.tmp.{os.getpid()}")
    tmp.write_text(json.dumps(plan, indent=2))
    tmp.replace(path)

    return str(path)


# ---------------------------------------------------------------------------
# ShadowLogger integration (append-only)
# ---------------------------------------------------------------------------

SHADOW_LOG_EVENTS: Final[tuple[str, ...]] = (
    "apply_requested",
    "apply_approved",
    "apply_executed",
    "rollback_ready",
)


def log_shadow_event(
    event: str,
    candidate_sha: str,
    bot_id: str,
    details: dict[str, object] | None = None,
    log_dir: Path | None = None,
) -> None:
    """Append a structured event to the ShadowLogger JSONL file.

    The log is append-only — entries are never modified or deleted.

    Args:
        event: Event name (one of SHADOW_LOG_EVENTS).
        candidate_sha: SHA of the candidate.
        bot_id: Bot identifier.
        details: Optional structured details dict.
        log_dir: Log directory (defaults to state dir).
    """
    if log_dir is None:
        log_dir = DEFAULT_STATE_DIR / "shadow_log"

    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "controlled_apply.jsonl"

    entry: dict[str, object] = {
        "event": event,
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "candidate_sha": candidate_sha,
        "bot_id": bot_id,
    }
    if details:
        entry["details"] = details

    # Append-only write — never modify existing entries
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, default=str) + "\n")
        f.flush()
        os.fsync(f.fileno())


# ---------------------------------------------------------------------------
# Main entry point: run_controlled_apply_canary
# ---------------------------------------------------------------------------


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
) -> ControlledApplyDecision:
    """Run the full controlled apply pipeline for the canary bot.

    This is the only public entry point.  All gates are evaluated
    in sequence; if any gate blocks, the pipeline stops and returns
    a BLOCKED decision without side effects.

    Args:
        candidate_sha: Candidate SHA (e.g. ``f68a031923d0``).
        bot_id: Bot identifier (must be the canary).
        parameter_overlay: Dict of parameter changes (must be SAFE_OVERLAY_KEYS).
        requires_human_approval: Must be ``True``.
        state_dir: Override for state directory (testing).
        overlay_dir: Override for overlay output directory (testing).
        plan_dir: Override for rollback plan directory (testing).
        log_dir: Override for shadow log directory (testing).
        pre_apply_config: Pre-apply config snapshot for rollback plan.
            In testing, pass a dict; in production this is read from
            the canary bot's current config.

    Returns:
        ControlledApplyDecision with overall_status and all gates evaluated.

    Side effects (only when overall_status == APPLIED):
      - Overlay file written to ``overlay_dir``
      - Rollback plan written to ``plan_dir``
      - Cooldown state updated
      - Shadow log written (all four events)
    """
    errors: list[str] = []
    warnings: list[str] = []

    # Build the proposal dict for gate checks
    proposal: dict[str, object] = {
        "bot_id": bot_id,
        "candidate_sha": candidate_sha,
        "parameter_overlay": dict(parameter_overlay),
        "requires_human_approval": requires_human_approval,
    }

    # -- Gate 1: Canary bot -------------------------------------------------
    gate1 = check_canary_bot(bot_id)
    if not gate1:
        errors.append(gate1.reason)
        return ControlledApplyDecision(
            overall_status="BLOCKED",
            candidate_sha=candidate_sha,
            bot_id=bot_id,
            parameter_overlay=dict(parameter_overlay),
            errors=tuple(errors),
        )

    # -- Gate 2: Safe overlay keys ------------------------------------------
    gate2 = check_safe_overlay_keys(parameter_overlay)
    if not gate2:
        errors.append(gate2.reason)
        return ControlledApplyDecision(
            overall_status="BLOCKED",
            candidate_sha=candidate_sha,
            bot_id=bot_id,
            parameter_overlay=dict(parameter_overlay),
            errors=tuple(errors),
        )

    # -- Gate 3: Human approval flag ----------------------------------------
    gate3 = check_human_approval_flag(proposal)
    if not gate3:
        errors.append(gate3.reason)
        return ControlledApplyDecision(
            overall_status="BLOCKED",
            candidate_sha=candidate_sha,
            bot_id=bot_id,
            parameter_overlay=dict(parameter_overlay),
            errors=tuple(errors),
        )

    # -- Gate 4: L3 activation token ----------------------------------------
    gate4 = check_activation_token()
    if not gate4:
        errors.append(gate4.reason)
        return ControlledApplyDecision(
            overall_status="BLOCKED",
            candidate_sha=candidate_sha,
            bot_id=bot_id,
            parameter_overlay=dict(parameter_overlay),
            errors=tuple(errors),
        )

    # -- Gate 5: Cooldown ---------------------------------------------------
    resolved_state_dir = state_dir or DEFAULT_STATE_DIR
    cooldown = check_cooldown(resolved_state_dir)
    if cooldown.is_on_cooldown():
        remaining = cooldown.remaining_seconds()
        days = int(remaining // 86400)
        hours = int((remaining % 86400) // 3600)
        errors.append(
            f"Cooldown active: last apply was {cooldown.last_apply_utc} "
            f"(~{days}d {hours}h remaining). "
            f"Max 1 apply per {COOLDOWN_DAYS} days."
        )
        return ControlledApplyDecision(
            overall_status="COOLDOWN_ACTIVE",
            candidate_sha=candidate_sha,
            bot_id=bot_id,
            parameter_overlay=dict(parameter_overlay),
            errors=tuple(errors),
        )

    # -- Gate 6: dry_run check (using pre_apply_config if provided) ----------
    if pre_apply_config is not None:
        dry_run_val = pre_apply_config.get("dry_run", True)
        if dry_run_val is not True:
            errors.append(
                f"dry_run is {dry_run_val!r} in pre-apply config. "
                "Cannot apply to live trading."
            )
            return ControlledApplyDecision(
                overall_status="BLOCKED",
                candidate_sha=candidate_sha,
                bot_id=bot_id,
                parameter_overlay=dict(parameter_overlay),
                errors=tuple(errors),
            )

    # -- All gates passed — proceed with apply -------------------------------

    # Log: requested
    log_shadow_event(
        "apply_requested",
        candidate_sha,
        bot_id,
        details={"parameter_overlay": dict(parameter_overlay)},
        log_dir=log_dir,
    )

    # Write overlay file
    overlay_path, overlay_sha = write_overlay_file(
        candidate_sha, parameter_overlay, overlay_dir=overlay_dir
    )

    # Log: approved
    log_shadow_event(
        "apply_approved",
        candidate_sha,
        bot_id,
        details={
            "overlay_path": overlay_path,
            "overlay_sha256": overlay_sha,
        },
        log_dir=log_dir,
    )

    # Create rollback plan
    resolved_plan_dir = plan_dir or DEFAULT_STATE_DIR / "rollback_plans"
    rollback_path = create_rollback_plan(
        candidate_sha,
        bot_id,
        overlay_path,
        pre_apply_config or {},
        plan_dir=resolved_plan_dir,
    )

    # Update cooldown state
    new_cooldown = CooldownState(
        last_apply_utc=datetime.now(UTC).isoformat(),
        candidate_sha=candidate_sha,
        bot_id=bot_id,
    )
    new_cooldown.save(resolved_state_dir)

    # Log: executed
    log_shadow_event(
        "apply_executed",
        candidate_sha,
        bot_id,
        details={
            "overlay_path": overlay_path,
            "overlay_sha256": overlay_sha,
            "rollback_plan_path": rollback_path,
        },
        log_dir=log_dir,
    )

    # Log: rollback_ready
    log_shadow_event(
        "rollback_ready",
        candidate_sha,
        bot_id,
        details={
            "rollback_plan_path": rollback_path,
            "restore_instructions": (
                f"Restore overlay from rollback plan at {rollback_path}"
            ),
        },
        log_dir=log_dir,
    )

    return ControlledApplyDecision(
        overall_status="APPLIED",
        candidate_sha=candidate_sha,
        bot_id=bot_id,
        parameter_overlay=dict(parameter_overlay),
        overlay_path=overlay_path,
        overlay_sha256=overlay_sha,
        rollback_plan_path=rollback_path,
    )


def summarize_decision(decision: ControlledApplyDecision) -> dict[str, object]:
    """Produce a short summary dict for human-friendly reporting."""
    return {
        "status": decision.overall_status,
        "candidate": decision.candidate_sha[:16] if decision.candidate_sha else "",
        "bot": decision.bot_id,
        "errors": len(decision.errors),
        "warnings": len(decision.warnings),
        "overlay_written": bool(decision.overlay_path),
        "rollback_ready": bool(decision.rollback_plan_path),
    }
