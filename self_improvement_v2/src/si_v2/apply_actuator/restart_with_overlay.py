r"""Canary restart-with-overlay planner — read-only, safety-gated, audit-ready.

This module provides the **planning layer** between ``execute_apply()`` (which
writes the overlay file) and a future L3-gated runtime restart (which would
recreate the container with the overlay).

Architecture
------------
::

    execute_apply()
        → writes overlay_<sha>.json to canary user_data
        → writes apply/audit event
        → writes snapshot/rollback metadata
        → NO restart, NO Docker, NO compose

    plan_canary_restart_with_overlay()   ← THIS MODULE
        → read-only
        → builds RestartPlan
        → validates canary, overlay, SHA, forbidden keys, dry_run, command
        → NO runtime mutation

    execute_canary_restart_with_overlay()  ← HARD-BLOCKED in Phase 3B-A
        → returns NOT_IMPLEMENTED
        → requires separate L3 token in a future sprint

Safety invariants
-----------------
- Canary-only: ``bot_id`` must be ``freqtrade-freqforge-canary``.
- Overlay path must exist and be under the canary ``user_data`` directory.
- Overlay must be valid JSON and contain no forbidden keys.
- ``dry_run`` must be ``True`` in the pre-apply config.
- Current command must contain a base ``--config`` argument.
- Proposed command appends exactly one additional ``--config`` for the overlay.
- Rollback command is the current command without any overlay ``--config``.
- No subprocess, no Docker, no filesystem writes in the planner.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Literal

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CANARY_BOT_ID: Final[str] = "freqtrade-freqforge-canary"
"""The only bot ID accepted by the restart planner."""

CANARY_CONTAINER_NAME: Final[str] = "trading-freqtrade-freqforge-canary-1"
"""Expected Docker container name for the canary."""

CANARY_SERVICE_NAME: Final[str] = "freqtrade-freqforge-canary"
"""Docker Compose service name for the canary."""

CANARY_USER_DATA_RELATIVE: Final[Path] = Path("freqforge-canary/user_data")
"""Relative path from repo root to the canary's user_data directory."""

RESTART_FORBIDDEN_KEYS: Final[frozenset[str]] = frozenset({
    "dry_run",
    "strategy",
    "pair_whitelist",
    "exchange",
    "api_server",
    "db_url",
    "user_data_dir",
    "telegram",
    "external_message_consumer",
})
"""Keys that must NEVER appear in an overlay intended for restart.

Extends the overlay_merge.py ``SAFETY_FORBIDDEN_KEYS`` with additional
runtime-critical keys that must not be mutated via overlay.
"""

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RestartPlan:
    """A deterministic, read-only plan for restarting the canary with an overlay.

    All fields are populated at plan-creation time. The plan is immutable and
    JSON-serialisable via ``to_dict()``.
    """

    plan_id: str
    """Unique plan identifier (candidate SHA prefix)."""

    bot_id: str
    """Target bot ID — must be ``freqtrade-freqforge-canary``."""

    container_name: str
    """Docker container name for the target bot."""

    service_name: str | None
    """Docker Compose service name, if applicable."""

    host_overlay_path: str
    """Absolute host path to the overlay JSON file."""

    container_overlay_path: str
    """Container-side path where the overlay is visible."""

    overlay_sha256: str
    """SHA-256 of the overlay file content."""

    base_config_container_path: str
    """Container-side path to the base ``config.json``."""

    current_command: tuple[str, ...]
    """The current Freqtrade process command as a tuple of args."""

    proposed_command: tuple[str, ...]
    """The proposed command with the overlay ``--config`` appended."""

    rollback_command: tuple[str, ...]
    """The command that restores the base config (current without overlay)."""

    expected_parameter: str
    """The parameter name being changed (e.g. ``max_open_trades``)."""

    expected_value: object
    """The expected value after restart (e.g. ``2``)."""

    safety_checks: dict[str, bool]
    """Mapping of check name → passed (True) or failed (False)."""

    blocked_reasons: tuple[str, ...]
    """Reasons the plan is blocked (empty if ready)."""

    created_at_utc: str
    """ISO 8601 timestamp of plan creation."""

    def to_dict(self) -> dict[str, object]:
        """Serialise to a JSON-compatible dict."""
        return {
            "plan_id": self.plan_id,
            "bot_id": self.bot_id,
            "container_name": self.container_name,
            "service_name": self.service_name,
            "host_overlay_path": self.host_overlay_path,
            "container_overlay_path": self.container_overlay_path,
            "overlay_sha256": self.overlay_sha256,
            "base_config_container_path": self.base_config_container_path,
            "current_command": list(self.current_command),
            "proposed_command": list(self.proposed_command),
            "rollback_command": list(self.rollback_command),
            "expected_parameter": self.expected_parameter,
            "expected_value": self.expected_value,
            "safety_checks": dict(self.safety_checks),
            "blocked_reasons": list(self.blocked_reasons),
            "created_at_utc": self.created_at_utc,
        }


@dataclass(frozen=True)
class RestartPlanResult:
    """Result of a restart plan attempt.

    If ``ready`` is ``True``, ``plan`` is populated and ``blocked_reasons`` is
    empty. If ``ready`` is ``False``, ``plan`` is ``None`` and ``blocked_reasons``
    contains the reasons.
    """

    ready: bool
    plan: RestartPlan | None
    blocked_reasons: tuple[str, ...]


@dataclass(frozen=True)
class RestartExecutionResult:
    """Result of a restart execution attempt.

    In Phase 3B-A this is always ``NOT_IMPLEMENTED``. A future sprint may
    implement ``EXECUTED`` or ``BLOCKED`` outcomes.
    """

    status: Literal["BLOCKED", "NOT_IMPLEMENTED", "EXECUTED"]
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
    """Normalise a command sequence to a tuple of strings."""
    return tuple(str(arg) for arg in command)


def _find_config_args(command: tuple[str, ...]) -> list[int]:
    """Return indices of ``--config`` arguments in the command tuple."""
    return [i for i, arg in enumerate(command) if arg == "--config"]


def _build_proposed_command(
    current_command: tuple[str, ...],
    container_overlay_path: str,
) -> tuple[str, ...]:
    """Append a ``--config <overlay_path>`` after the last ``--config`` arg.

    If the overlay path is already present in the command, the command is
    returned unchanged (no duplicate).
    """
    if container_overlay_path in current_command:
        return current_command

    config_indices = _find_config_args(current_command)
    if not config_indices:
        # No --config found; append at the end
        return (*current_command, "--config", container_overlay_path)

    # Insert after the last --config <value> pair
    last_config_idx = config_indices[-1]
    # The value follows the --config flag
    insert_after = last_config_idx + 1
    return (
        *current_command[: insert_after + 1],
        "--config",
        container_overlay_path,
        *current_command[insert_after + 1 :],
    )


def _build_rollback_command(
    current_command: tuple[str, ...],
) -> tuple[str, ...]:
    """Remove all ``--config`` arguments that point to overlay files.

    An overlay ``--config`` is identified as any ``--config`` whose value
    contains ``overlay_``. The first ``--config`` (the base config) is
    always preserved.
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
                # Skip this --config and its value
                skip_next = True
                continue
        result.append(arg)
    return tuple(result)


# ---------------------------------------------------------------------------
# Safety validators
# ---------------------------------------------------------------------------


def _check_canary_only(bot_id: str) -> tuple[bool, str]:
    """Block any bot that is not the approved canary."""
    if bot_id == CANARY_BOT_ID:
        return True, ""
    return False, f"not_canary: bot_id={bot_id!r} is not {CANARY_BOT_ID!r}"


def _check_overlay_path(
    overlay_path: Path,
    canary_user_data: Path,
) -> tuple[bool, str]:
    """Block overlays outside the canary user_data directory."""
    if not overlay_path.exists():
        return False, f"overlay_file_missing: {overlay_path} does not exist"
    try:
        resolved = overlay_path.resolve()
        canary_resolved = canary_user_data.resolve()
        if not str(resolved).startswith(str(canary_resolved)):
            return (
                False,
                f"overlay_outside_canary: {resolved} is not under {canary_resolved}",
            )
    except (OSError, ValueError) as e:
        return False, f"overlay_path_resolution_error: {e}"
    return True, ""


def _check_overlay_content(
    overlay_path: Path,
) -> tuple[dict[str, object] | None, list[str]]:
    """Parse overlay JSON and check for forbidden keys."""
    try:
        raw = overlay_path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (json.JSONDecodeError, OSError) as e:
        return None, [f"overlay_parse_error: {e}"]

    if not isinstance(data, dict):
        return None, ["overlay_not_a_dict"]

    blocked: list[str] = []
    for key in data:
        if key in RESTART_FORBIDDEN_KEYS:
            blocked.append(f"forbidden_key_in_overlay: {key!r}")

    return data, blocked


def _check_dry_run(pre_apply_config: Mapping[str, object]) -> tuple[bool, str]:
    """Block if dry_run is not True in the pre-apply config."""
    dry_run_val = pre_apply_config.get("dry_run")
    if dry_run_val is True:
        return True, ""
    if dry_run_val is None:
        return False, "dry_run_not_found: key 'dry_run' missing from pre_apply_config"
    return False, f"dry_run_not_true: dry_run={dry_run_val!r}"


def _check_current_command(
    current_command: tuple[str, ...],
) -> tuple[bool, str]:
    """Block if the current command has no ``--config`` argument."""
    config_indices = _find_config_args(current_command)
    if not config_indices:
        return False, "current_command_no_config: no --config argument found"
    return True, ""


# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------


def plan_canary_restart_with_overlay(
    *,
    bot_id: str,
    overlay_path: Path,
    current_command: Sequence[str],
    expected_parameter: str,
    expected_value: object,
    pre_apply_config: Mapping[str, object],
    canary_user_data: Path | None = None,
) -> RestartPlanResult:
    """Build a read-only restart plan for the canary bot.

    This function performs **zero** side effects:
    - No subprocess calls
    - No Docker interaction
    - No filesystem writes
    - No config mutations

    Args:
        bot_id: Target bot ID (must be ``freqtrade-freqforge-canary``).
        overlay_path: Host path to the overlay JSON file.
        current_command: The current Freqtrade process command as a sequence.
        expected_parameter: The parameter being changed (e.g. ``max_open_trades``).
        expected_value: The expected value after restart (e.g. ``2``).
        pre_apply_config: The pre-apply config dict (must contain ``dry_run``).
        canary_user_data: Override for the canary user_data path. Defaults to
            ``<repo_root>/freqforge-canary/user_data``.

    Returns:
        A ``RestartPlanResult`` with ``ready=True`` and a populated ``RestartPlan``
        if all safety checks pass, or ``ready=False`` with blocked reasons.
    """
    blocked: list[str] = []
    safety_checks: dict[str, bool] = {}

    # 1. Canary-only check
    canary_ok, canary_reason = _check_canary_only(bot_id)
    safety_checks["canary_only"] = canary_ok
    if not canary_ok:
        blocked.append(canary_reason)

    # 2. Resolve canary user_data path
    if canary_user_data is None:
        # Default: assume repo root is two levels up from this file
        # self_improvement_v2/src/si_v2/apply_actuator/restart_with_overlay.py
        repo_root = Path(__file__).resolve().parent.parent.parent.parent.parent
        canary_user_data = repo_root / "freqforge-canary" / "user_data"

    # 3. Overlay path check
    path_ok, path_reason = _check_overlay_path(overlay_path, canary_user_data)
    safety_checks["overlay_path_valid"] = path_ok
    if not path_ok:
        blocked.append(path_reason)

    # 4. Overlay content check
    overlay_data: dict[str, object] | None = None
    content_blocked: list[str] = []
    if path_ok:
        overlay_data, content_blocked = _check_overlay_content(overlay_path)
    safety_checks["overlay_content_valid"] = len(content_blocked) == 0
    blocked.extend(content_blocked)

    # 5. Forbidden keys in overlay
    forbidden_ok = not any(
        key in RESTART_FORBIDDEN_KEYS
        for key in (overlay_data or {})
    )
    safety_checks["no_forbidden_keys"] = forbidden_ok
    # (already covered by content_blocked, but tracked separately for clarity)

    # 6. dry_run check
    dry_run_ok, dry_run_reason = _check_dry_run(pre_apply_config)
    safety_checks["dry_run_true"] = dry_run_ok
    if not dry_run_ok:
        blocked.append(dry_run_reason)

    # 7. Current command check
    cmd = _parse_command(current_command)
    cmd_ok, cmd_reason = _check_current_command(cmd)
    safety_checks["current_command_has_config"] = cmd_ok
    if not cmd_ok:
        blocked.append(cmd_reason)

    # 8. Build proposed and rollback commands (only if current command is valid)
    proposed_command: tuple[str, ...] = ()
    rollback_command: tuple[str, ...] = ()
    container_overlay_path = ""

    if cmd_ok:
        # Derive container overlay path from the host path
        # The container sees /freqtrade/user_data/<filename>
        container_overlay_path = (
            f"/freqtrade/user_data/{overlay_path.name}"
        )
        proposed_command = _build_proposed_command(cmd, container_overlay_path)
        rollback_command = _build_rollback_command(cmd)

        # Verify proposed command doesn't duplicate overlay
        overlay_count = sum(
            1 for i, arg in enumerate(proposed_command)
            if arg == "--config" and i + 1 < len(proposed_command)
            and "overlay_" in proposed_command[i + 1]
        )
        safety_checks["no_duplicate_overlay"] = overlay_count <= 1
        if overlay_count > 1:
            blocked.append("duplicate_overlay_in_proposed_command")

        # Verify rollback has no overlay
        rollback_overlay_count = sum(
            1 for i, arg in enumerate(rollback_command)
            if arg == "--config" and i + 1 < len(rollback_command)
            and "overlay_" in rollback_command[i + 1]
        )
        safety_checks["rollback_has_no_overlay"] = rollback_overlay_count == 0
        if rollback_overlay_count > 0:
            blocked.append("rollback_command_still_has_overlay")

    # 9. Compute overlay SHA256
    overlay_sha256 = ""
    if path_ok and overlay_path.exists():
        overlay_sha256 = hashlib.sha256(
            overlay_path.read_bytes()
        ).hexdigest()

    # 10. Plan ID
    plan_id = f"restart_{overlay_path.stem}" if overlay_path.stem else "restart_unknown"

    # 11. Timestamp
    now_utc = datetime.now(UTC).isoformat()

    if blocked:
        return RestartPlanResult(
            ready=False,
            plan=None,
            blocked_reasons=tuple(blocked),
        )

    # Build the plan
    plan = RestartPlan(
        plan_id=plan_id,
        bot_id=bot_id,
        container_name=CANARY_CONTAINER_NAME,
        service_name=CANARY_SERVICE_NAME,
        host_overlay_path=str(overlay_path.resolve()),
        container_overlay_path=container_overlay_path,
        overlay_sha256=overlay_sha256,
        base_config_container_path="/freqtrade/user_data/config.json",
        current_command=cmd,
        proposed_command=proposed_command,
        rollback_command=rollback_command,
        expected_parameter=expected_parameter,
        expected_value=expected_value,
        safety_checks=safety_checks,
        blocked_reasons=(),
        created_at_utc=now_utc,
    )

    return RestartPlanResult(
        ready=True,
        plan=plan,
        blocked_reasons=(),
    )


# ---------------------------------------------------------------------------
# Execute — hard-blocked in Phase 3B-A
# ---------------------------------------------------------------------------


def execute_canary_restart_with_overlay(
    plan: RestartPlan,
    *,
    token: str | None = None,
) -> RestartExecutionResult:
    """Execute a restart plan — **intentionally hard-blocked in Phase 3B-A**.

    This function exists as a **safety stub** that proves no runtime restart
    can occur through this module in the current sprint. It always returns
    ``NOT_IMPLEMENTED``.

    A future sprint may implement the actual restart path, which must:
    - Require a separate L3 token (``APPROVE_SI_V2_CANARY_RESTART_WITH_OVERLAY``)
    - Use ``docker compose -f docker-compose.yml -f override.yml up -d``
    - Verify the container is the correct canary
    - Verify ``dry_run=true`` before and after restart
    - Verify the overlay file exists and SHA matches
    - Run ``RuntimeEffectProof`` after restart
    - Only then allow ``measurement_allowed=true`` and ``mutation_counter++``

    Args:
        plan: A validated ``RestartPlan`` (must be ``ready=True``).
        token: Future L3 activation token (ignored in this sprint).

    Returns:
        ``RestartExecutionResult(status="NOT_IMPLEMENTED", ...)``.
    """
    _ = token  # Explicitly unused — safety measure
    return RestartExecutionResult(
        status="NOT_IMPLEMENTED",
        reason=(
            "Runtime restart execution is intentionally not implemented "
            "in Phase 3B-A. Requires separate L3 approval and a runtime "
            "executor sprint. See ADR-2026-06-27-si-v2-restart-with-overlay."
        ),
        plan_id=plan.plan_id,
    )
