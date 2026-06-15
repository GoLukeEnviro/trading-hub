"""Kill-switch module — fleet-wide entry blocking and emergency position close.

Three modes:
    NORMAL      — No blocking. All gates pass to primo/risk logic.
    HALT_NEW    — Block all new entries fleet-wide. Open positions are kept.
    EMERGENCY   — Block entries AND signal strategies to close open positions.

State is persisted as JSON in var/kill_switch.json (host) or
/freqtrade/shared/kill_switch.json (container).  Path resolution uses
$KILL_SWITCH_FILE env var first, then the container path, then the host
project-root path.

Usage:
    from kill_switch import is_kill_active, is_emergency, get_kill_mode

    if is_kill_active():
        # Block new entries
    if is_emergency():
        # Close positions
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

# ── Mode constants ──────────────────────────────────────────────────────
MODE_NORMAL: str = "NORMAL"
MODE_HALT_NEW: str = "HALT_NEW"
MODE_EMERGENCY: str = "EMERGENCY"

_VALID_MODES: frozenset[str] = frozenset({MODE_NORMAL, MODE_HALT_NEW, MODE_EMERGENCY})

# ── Path resolution ─────────────────────────────────────────────────────

_PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Host state file (not tracked in git)
_HOST_STATE_PATH = _PROJECT_ROOT / "var" / "kill_switch.json"

# Container-mounted state file
_CONTAINER_STATE_PATH = Path("/freqtrade/shared/kill_switch.json")


def _resolve_state_path() -> Path:
    """Resolve the state file path with priority:
    1. $KILL_SWITCH_FILE env var override
    2. Container path (/freqtrade/shared/kill_switch.json)
    3. Host path (var/kill_switch.json relative to project root)
    """
    env_override = os.environ.get("KILL_SWITCH_FILE", "").strip()
    if env_override:
        return Path(env_override)

    if _CONTAINER_STATE_PATH.exists():
        return _CONTAINER_STATE_PATH

    return _HOST_STATE_PATH


# ── mtime cache ─────────────────────────────────────────────────────────

_cache: dict[str, Any] = {"mtime": 0, "state": {}}


def load_kill_state() -> dict[str, Any]:
    """Load the kill-switch state from the resolved state file.

    Uses mtime-based caching — no redundant I/O if the file hasn't changed.
    Returns a dict with at least ``mode``, ``reason``, ``triggered_at``,
    ``triggered_by``, ``auto_clear_at`` keys.
    """
    path = _resolve_state_path()

    try:
        mtime = path.stat().st_mtime
    except OSError:
        return {
            "mode": MODE_NORMAL,
            "reason": "state_file_not_found",
            "triggered_at": "",
            "triggered_by": "",
            "auto_clear_at": "",
        }

    if mtime == _cache["mtime"] and _cache["state"]:
        state = _cache["state"]
    else:
        try:
            raw = json.loads(path.read_text())
            state = raw if isinstance(raw, dict) else {}
        except (json.JSONDecodeError, OSError):
            state = {}
        _cache["mtime"] = mtime
        _cache["state"] = state

    # Normalise mode
    mode = str(state.get("mode", MODE_NORMAL)).strip().upper()
    if mode not in _VALID_MODES:
        mode = MODE_NORMAL

    # Auto-clear check
    auto_clear_at = str(state.get("auto_clear_at", "")).strip()
    if auto_clear_at and mode != MODE_NORMAL:
        try:
            if time.time() >= float(auto_clear_at):
                mode = MODE_NORMAL
                state = dict(state)
                state["mode"] = mode
                state["reason"] = "auto_cleared"
                _cache["state"] = state
        except (ValueError, TypeError):
            pass

    return {
        "mode": mode,
        "reason": str(state.get("reason", "")),
        "triggered_at": str(state.get("triggered_at", "")),
        "triggered_by": str(state.get("triggered_by", "")),
        "auto_clear_at": str(auto_clear_at),
    }


def get_kill_mode() -> str:
    """Return the current kill-switch mode: NORMAL, HALT_NEW, or EMERGENCY."""
    return str(load_kill_state().get("mode", MODE_NORMAL))


def is_kill_active() -> bool:
    """Return True when kill-switch is active (HALT_NEW or EMERGENCY)."""
    return get_kill_mode() != MODE_NORMAL


def is_emergency() -> bool:
    """Return True only when EMERGENCY mode is active."""
    return get_kill_mode() == MODE_EMERGENCY


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    """Atomically write JSON to a file using .tmp + os.replace()."""
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str))
    tmp.replace(path)


def set_kill_mode(
    mode: str,
    reason: str = "",
    triggered_by: str = "manual",
    auto_clear_minutes: int | None = None,
) -> dict[str, Any]:
    """Set the kill-switch to a specific mode.

    Args:
        mode: One of MODE_NORMAL, MODE_HALT_NEW, MODE_EMERGENCY.
        reason: Human-readable reason for the mode change.
        triggered_by: Identifier of who/what triggered the change.
        auto_clear_minutes: Optional — auto-revert to NORMAL after N minutes.

    Returns:
        The new state dict.
    """
    mode = str(mode).strip().upper()
    if mode not in _VALID_MODES:
        msg = f"Invalid kill-switch mode: {mode!r}. Must be one of {sorted(_VALID_MODES)}"
        raise ValueError(msg)

    now_iso = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())

    state: dict[str, Any] = {
        "mode": mode,
        "reason": reason,
        "triggered_at": now_iso,
        "triggered_by": triggered_by,
    }

    if auto_clear_minutes is not None and mode != MODE_NORMAL:
        state["auto_clear_at"] = str(time.time() + auto_clear_minutes * 60)
    else:
        state["auto_clear_at"] = ""

    path = _resolve_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_json(path, state)

    # Invalidate cache
    _cache["mtime"] = 0
    _cache["state"] = {}

    return load_kill_state()


def clear_kill_switch(reason: str = "", triggered_by: str = "manual") -> dict[str, Any]:
    """Revert the kill-switch to NORMAL mode.

    Shorthand for ``set_kill_mode(MODE_NORMAL, ...)``.
    """
    return set_kill_mode(MODE_NORMAL, reason=reason, triggered_by=triggered_by)


# ── CLI entry point ─────────────────────────────────────────────────────

def _cli() -> None:
    """Simple CLI for kill-switch management.

    Usage:
        python3 freqtrade/shared/kill_switch.py status
        python3 freqtrade/shared/kill_switch.py halt [reason]
        python3 freqtrade/shared/kill_switch.py emergency [reason]
        python3 freqtrade/shared/kill_switch.py clear [reason]
    """
    import sys

    args = sys.argv[1:]
    if not args:
        print("Usage: kill_switch.py <status|halt|emergency|clear> [reason]")
        sys.exit(1)

    command = args[0].lower()
    reason = " ".join(args[1:]) if len(args) > 1 else ""

    if command == "status":
        state = load_kill_state()
        print(f"Mode:         {state.get('mode', MODE_NORMAL)}")
        print(f"Reason:       {state.get('reason', '')}")
        print(f"Triggered at: {state.get('triggered_at', '')}")
        print(f"Triggered by: {state.get('triggered_by', '')}")
        print(f"Auto-clear:   {state.get('auto_clear_at', '')}")
    elif command == "halt":
        set_kill_mode(MODE_HALT_NEW, reason=reason, triggered_by="cli")
        print("Kill-switch set to HALT_NEW — all new entries blocked.")
    elif command == "emergency":
        set_kill_mode(MODE_EMERGENCY, reason=reason, triggered_by="cli")
        print("Kill-switch set to EMERGENCY — entries blocked, positions closing.")
    elif command == "clear":
        clear_kill_switch(reason=reason, triggered_by="cli")
        print("Kill-switch cleared — NORMAL mode restored.")
    else:
        print(f"Unknown command: {command!r}")
        sys.exit(1)


if __name__ == "__main__":
    _cli()
