"""Central Kill Switch for the Trading Hub fleet (Phase 1D, Issue #598).

Schema v2 extends v1 with:
- Safety states: NORMAL | HALT_NEW | REDUCE_ONLY | EMERGENCY
- Requested actions: CANCEL_PENDING_ENTRIES | CANCEL_ALL_PENDING | REQUEST_CONTROLLED_UNWIND
- Action state tracking: requested/attempted/confirmed/failed
- Backward-compatible reading of v1 files

All existing callers (get_kill_mode, is_kill_active, set_kill_mode, etc.)
continue to work unchanged.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("kill_switch")

# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

_ENV_PATH = os.environ.get("KILL_SWITCH_FILE", "")
_CONTAINER_PATH = Path("/freqtrade/shared/kill_switch.json")
_HOST_PATH = Path(__file__).resolve().parent.parent.parent / "var" / "kill_switch.json"


def _resolve_path() -> Path:
    if _ENV_PATH:
        return Path(_ENV_PATH)
    if _CONTAINER_PATH.parent.exists():
        return _CONTAINER_PATH
    return _HOST_PATH


KILL_SWITCH_PATH: Path = _resolve_path()

# ---------------------------------------------------------------------------
# Safety states (v2)
# ---------------------------------------------------------------------------
SAFETY_NORMAL = "NORMAL"
SAFETY_HALT_NEW = "HALT_NEW"
SAFETY_REDUCE_ONLY = "REDUCE_ONLY"
SAFETY_EMERGENCY = "EMERGENCY"
VALID_SAFETY_STATES = frozenset(
    {SAFETY_NORMAL, SAFETY_HALT_NEW, SAFETY_REDUCE_ONLY, SAFETY_EMERGENCY}
)

# Backward-compat aliases
MODE_NORMAL = SAFETY_NORMAL
MODE_HALT_NEW = SAFETY_HALT_NEW
MODE_EMERGENCY = SAFETY_EMERGENCY
VALID_MODES = {MODE_NORMAL, MODE_HALT_NEW, MODE_EMERGENCY, SAFETY_REDUCE_ONLY}

# Precedence: most restrictive wins (higher = more restrictive)
_SAFETY_PRECEDENCE = {
    SAFETY_NORMAL: 0,
    SAFETY_REDUCE_ONLY: 1,
    SAFETY_HALT_NEW: 2,
    SAFETY_EMERGENCY: 3,
}

# ---------------------------------------------------------------------------
# Action types + states
# ---------------------------------------------------------------------------
ACTION_CANCEL_PENDING_ENTRIES = "CANCEL_PENDING_ENTRIES"
ACTION_CANCEL_ALL_PENDING = "CANCEL_ALL_PENDING"
ACTION_REQUEST_CONTROLLED_UNWIND = "REQUEST_CONTROLLED_UNWIND"
VALID_ACTIONS = frozenset(
    {ACTION_CANCEL_PENDING_ENTRIES, ACTION_CANCEL_ALL_PENDING, ACTION_REQUEST_CONTROLLED_UNWIND}
)

ACTION_STATE_REQUESTED = "requested"
ACTION_STATE_ATTEMPTED = "attempted"
ACTION_STATE_CONFIRMED = "confirmed"
ACTION_STATE_FAILED = "failed"
VALID_ACTION_STATES = frozenset(
    {ACTION_STATE_REQUESTED, ACTION_STATE_ATTEMPTED, ACTION_STATE_CONFIRMED, ACTION_STATE_FAILED}
)

# ---------------------------------------------------------------------------
# Default state (v2)
# ---------------------------------------------------------------------------
_DEFAULT_SAFETY_STATE = SAFETY_NORMAL
_DEFAULT_ACTIONS: Dict[str, Dict[str, str]] = {}

_DEFAULT_STATE: Dict[str, Any] = {
    "version": 2,
    "safety_state": _DEFAULT_SAFETY_STATE,
    "mode": MODE_NORMAL,  # backward compat
    "reason": "",
    "triggered_at": "",
    "triggered_by": "",
    "auto_clear_at": "",
    "actions": {},
}

_FAIL_CLOSED_STATE: Dict[str, Any] = {
    "version": 2,
    "safety_state": SAFETY_HALT_NEW,
    "mode": MODE_HALT_NEW,  # backward compat
    "reason": "fail-closed: unable to read kill switch state",
    "triggered_at": "",
    "triggered_by": "system",
    "auto_clear_at": "",
    "actions": {},
}


# ---------------------------------------------------------------------------
# V1→V2 migration
# ---------------------------------------------------------------------------


def _migrate_v1_to_v2(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a v1 state dict to v2, preserving existing fields."""
    mode = raw.get("mode", MODE_NORMAL)
    # Validate mode input — unknown falls back to HALT_NEW (fail-closed)
    if mode not in VALID_MODES:
        mode = SAFETY_HALT_NEW
    return {
        "version": 2,
        "safety_state": mode,
        "mode": mode,
        "reason": raw.get("reason", ""),
        "triggered_at": raw.get("triggered_at", ""),
        "triggered_by": raw.get("triggered_by", ""),
        "auto_clear_at": raw.get("auto_clear_at", ""),
        "actions": {},
    }


# ---------------------------------------------------------------------------
# Read helpers
# ---------------------------------------------------------------------------


def load_kill_state(
    path: Optional[Path] = None,
    *,
    _cache: Dict[str, Any] = {},  # noqa: B006
) -> Dict[str, Any]:
    """Load kill switch state from disk with mtime-based cache.

    Guaranteed to never raise. FAIL-CLOSED on any error.
    """
    p = path or KILL_SWITCH_PATH
    try:
        mtime = p.stat().st_mtime
    except FileNotFoundError:
        return dict(_FAIL_CLOSED_STATE)
    except Exception as exc:
        logger.warning("kill_switch: stat failed: %s", exc)
        return dict(_FAIL_CLOSED_STATE)

    cached = _cache.get(str(p))
    if cached and cached.get("_mtime") == mtime:
        return cached

    try:
        raw = json.loads(p.read_text())
    except Exception as exc:
        logger.warning("kill_switch: read/parse failed: %s", exc)
        return dict(_FAIL_CLOSED_STATE)

    if not isinstance(raw, dict):
        return dict(_FAIL_CLOSED_STATE)

    # Auto-clear check
    auto_clear = raw.get("auto_clear_at", "")
    if auto_clear:
        try:
            clear_dt = datetime.fromisoformat(auto_clear)
            if datetime.now(tz=timezone.utc) >= clear_dt:
                logger.info("kill_switch: auto_clear_at reached, reverting to NORMAL (in-memory)")
                raw["safety_state"] = SAFETY_NORMAL
                raw["mode"] = MODE_NORMAL
                raw["reason"] = "auto-cleared at " + auto_clear
                raw["auto_clear_at"] = ""
        except Exception:
            pass

    # Migration: v1 → v2
    version = raw.get("version", 1)
    if version < 2:
        raw = _migrate_v1_to_v2(raw)

    # Build canonical state dict
    state: Dict[str, Any] = dict(_DEFAULT_STATE)
    state.update({k: v for k, v in raw.items() if k in _DEFAULT_STATE})
    # Ensure "actions" is always a dict
    if not isinstance(state.get("actions"), dict):
        state["actions"] = {}
    state["_mtime"] = mtime
    _cache[str(p)] = state
    return state


def get_kill_mode(path: Optional[Path] = None) -> str:
    """Return current mode: NORMAL, HALT_NEW, REDUCE_ONLY, or EMERGENCY."""
    state = load_kill_state(path)
    return state.get("safety_state", state.get("mode", MODE_NORMAL))


def get_safety_state(path: Optional[Path] = None) -> str:
    """Return current safety state (v2 primary field)."""
    state = load_kill_state(path)
    return state.get("safety_state", state.get("mode", MODE_NORMAL))


def is_kill_active(path: Optional[Path] = None) -> bool:
    """Return True when entries should be blocked (any non-NORMAL state)."""
    mode = get_kill_mode(path)
    return mode != MODE_NORMAL


def is_emergency(path: Optional[Path] = None) -> bool:
    """Return True when EMERGENCY mode is active."""
    return get_kill_mode(path) == MODE_EMERGENCY


def is_reduce_only(path: Optional[Path] = None) -> bool:
    """Return True when REDUCE_ONLY mode is active."""
    return get_kill_mode(path) == SAFETY_REDUCE_ONLY


def get_effective_safety_state(*states: str) -> str:
    """Return the most restrictive safety state from multiple sources.

    Used when combining fleet kill switch with per-bot states.
    """
    best = SAFETY_NORMAL
    best_prec = 0
    for s in states:
        prec = _SAFETY_PRECEDENCE.get(s, 2)  # unknown → HALT_NEW level
        if prec > best_prec:
            best = s
            best_prec = prec
    return best


# ---------------------------------------------------------------------------
# Action tracking
# ---------------------------------------------------------------------------


def get_actions(path: Optional[Path] = None) -> Dict[str, Dict[str, str]]:
    """Return the current actions dict from the kill switch state."""
    state = load_kill_state(path)
    actions = state.get("actions", {})
    return dict(actions) if isinstance(actions, dict) else {}


def record_action(
    action: str,
    action_state: str,
    *,
    triggered_by: str = "operator",
    reason: str = "",
    path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Record an action transition without changing the safety state.

    Idempotent: recording the same state twice is a no-op for "confirmed".
    """
    if action not in VALID_ACTIONS:
        raise ValueError(f"Invalid action: {action!r}. Must be one of {VALID_ACTIONS}")
    if action_state not in VALID_ACTION_STATES:
        raise ValueError(
            f"Invalid action state: {action_state!r}. Must be one of {VALID_ACTION_STATES}"
        )

    p = path or KILL_SWITCH_PATH
    state = load_kill_state(p)
    actions: Dict[str, Dict[str, str]] = dict(state.get("actions", {}))
    now = datetime.now(tz=timezone.utc).isoformat()

    entry = dict(actions.get(action, {}))
    if action_state == ACTION_STATE_REQUESTED:
        entry["state"] = ACTION_STATE_REQUESTED
        entry["requested_at"] = now
        entry["requested_by"] = triggered_by
        entry["reason"] = reason
    elif action_state == ACTION_STATE_ATTEMPTED:
        entry["state"] = ACTION_STATE_ATTEMPTED
        entry["attempted_at"] = now
    elif action_state == ACTION_STATE_CONFIRMED:
        entry["state"] = ACTION_STATE_CONFIRMED
        entry["confirmed_at"] = now
    elif action_state == ACTION_STATE_FAILED:
        entry["state"] = ACTION_STATE_FAILED
        entry["failed_at"] = now
        entry["reason"] = reason or entry.get("reason", "")

    actions[action] = entry
    state["actions"] = actions
    _atomic_write(state, p)
    logger.info("kill_switch: action %s → %s by %s", action, action_state, triggered_by)
    return state


def is_action_attempted(action: str, path: Optional[Path] = None) -> bool:
    """Return True if an action has been at least attempted."""
    actions = get_actions(path)
    entry = actions.get(action, {})
    return entry.get("state", "") in {
        ACTION_STATE_ATTEMPTED,
        ACTION_STATE_CONFIRMED,
    }


def is_action_confirmed(action: str, path: Optional[Path] = None) -> bool:
    """Return True if an action has been confirmed as executed.

    An exit intent (REQUEST_CONTROLLED_UNWIND requested) is NOT confirmed
    closure — only the 'confirmed' state represents actual execution evidence.
    """
    actions = get_actions(path)
    entry = actions.get(action, {})
    return entry.get("state", "") == ACTION_STATE_CONFIRMED


# ---------------------------------------------------------------------------
# Write helpers
# ---------------------------------------------------------------------------


def _atomic_write(state: Dict[str, Any], path: Path) -> None:
    """Write state atomically via .tmp + os.replace()."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    os.replace(tmp, path)
    _refresh_cache(path, state)


def _refresh_cache(path: Path, state: Dict[str, Any]) -> None:
    kwdefaults = load_kill_state.__kwdefaults__ or {}
    cache = kwdefaults.get("_cache")
    if not isinstance(cache, dict):
        return
    try:
        cached = dict(state)
        cached["_mtime"] = path.stat().st_mtime
        cache[str(path)] = cached
    except OSError:
        cache.pop(str(path), None)


def set_kill_mode(
    mode: str,
    reason: str = "",
    triggered_by: str = "operator",
    auto_clear_minutes: Optional[float] = None,
    path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Activate or deactivate the kill switch (backward-compat).

    Now accepts REDUCE_ONLY in addition to NORMAL/HALT_NEW/EMERGENCY.
    """
    if mode not in VALID_MODES:
        raise ValueError(f"Invalid kill switch mode: {mode!r}. Must be one of {VALID_MODES}")

    p = path or KILL_SWITCH_PATH
    now = datetime.now(tz=timezone.utc)

    auto_clear_at = ""
    if auto_clear_minutes is not None and mode != MODE_NORMAL:
        from datetime import timedelta
        auto_clear_at = (now + timedelta(minutes=auto_clear_minutes)).isoformat()

    # Preserve existing actions
    existing = load_kill_state(p)
    actions = existing.get("actions", {})

    state = {
        "version": 2,
        "safety_state": mode,
        "mode": mode,  # backward compat
        "reason": reason,
        "triggered_at": now.isoformat(),
        "triggered_by": triggered_by,
        "auto_clear_at": auto_clear_at,
        "actions": dict(actions) if isinstance(actions, dict) else {},
    }
    _atomic_write(state, p)
    logger.warning(
        "kill_switch: mode set to %s by %s | reason: %s",
        mode, triggered_by, reason or "(none)",
    )
    return state


def clear_kill_switch(
    triggered_by: str = "operator",
    path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Convenience: set safety state back to NORMAL, preserve actions."""
    return set_kill_mode(
        MODE_NORMAL,
        reason="manually cleared",
        triggered_by=triggered_by,
        path=path,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    reason = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else ""

    if cmd == "status":
        s = load_kill_state()
        print(json.dumps({k: v for k, v in s.items() if not k.startswith("_")}, indent=2))

    elif cmd == "halt":
        s = set_kill_mode(MODE_HALT_NEW, reason=reason or "manual halt", triggered_by="cli")
        print(f"[KILL SWITCH] Mode: {s['safety_state']} — {s['reason']}")

    elif cmd == "emergency":
        s = set_kill_mode(MODE_EMERGENCY, reason=reason or "manual emergency", triggered_by="cli")
        print(f"[KILL SWITCH] EMERGENCY — {s['reason']}")

    elif cmd == "clear":
        s = clear_kill_switch(triggered_by="cli")
        print(f"[KILL SWITCH] Cleared — mode: {s.get('safety_state', s.get('mode'))}")

    else:
        print(f"Usage: {sys.argv[0]} [status|halt|emergency|clear] [reason]")
        sys.exit(1)
