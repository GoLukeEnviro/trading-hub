"""Central Kill Switch for the Trading Hub fleet.

This module provides a single, atomic file-based kill switch that is read by:
- freqtrade/shared/primo_signal.py (blocks FT strategy entries)
- trading_pipeline / bridge (forces WATCH_ONLY mode)
- orchestrator scripts (drawdown_guard integration)

Kill switch modes
-----------------
NORMAL      Normal operation. All gates pass through to primo/risk logic.
HALT_NEW    Block all new entries across the fleet. Open positions kept.
            Use for: elevated risk, manual pause, operator override.
EMERGENCY   Block all entries AND signal strategies to exit all open positions.
            Use for: drawdown breach, exchange outage, operator emergency.

File location
-------------
The state file lives at VAR_DIR/kill_switch.json.
Inside FT containers:  /freqtrade/shared/kill_switch.json
On host (pipeline):    var/kill_switch.json (relative to project root)
Override:              set env KILL_SWITCH_FILE=/path/to/kill_switch.json

Atomic writes
-------------
All writes use a .tmp + os.replace() pattern to prevent half-written reads.

Usage (in a FT strategy)
-------------------------
    from kill_switch import is_kill_active, get_kill_mode

    # In populate_entry_trend:
    if is_kill_active():
        df["enter_long"] = 0
        df["enter_short"] = 0
        return df

    # In custom_exit (for EMERGENCY mode):
    if get_kill_mode() == "EMERGENCY":
        return "kill_switch_emergency"

Usage (in trading_pipeline / bridge)
--------------------------------------
    from kill_switch import is_kill_active, get_kill_state

    if is_kill_active():
        # Force verdict to WATCH_ONLY, skip all ACCEPTED processing
        ...
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
# Valid modes
# ---------------------------------------------------------------------------
MODE_NORMAL = "NORMAL"
MODE_HALT_NEW = "HALT_NEW"
MODE_EMERGENCY = "EMERGENCY"
VALID_MODES = {MODE_NORMAL, MODE_HALT_NEW, MODE_EMERGENCY}

# --------------------------------------------------------------------------- #
# Default state
# --------------------------------------------------------------------------- #
_DEFAULT_STATE: Dict[str, Any] = {
    "mode": MODE_NORMAL,
    "reason": "",
    "triggered_at": "",
    "triggered_by": "",
    "auto_clear_at": "",
}

# Fail-closed state — returned when the kill switch state cannot be reliably
# read (missing file, corrupt JSON, permission error, etc.).
# SAFETY INVARIANT: when safety status is unknown, block entries.
_FAIL_CLOSED_STATE: Dict[str, Any] = {
    "mode": MODE_HALT_NEW,
    "reason": "fail-closed: unable to read kill switch state",
    "triggered_at": "",
    "triggered_by": "system",
    "auto_clear_at": "",
}


# ---------------------------------------------------------------------------
# Read helpers
# ---------------------------------------------------------------------------

def load_kill_state(
    path: Optional[Path] = None,
    *,
    _cache: Dict[str, Any] = {},  # noqa: B006  intentional mtime cache
) -> Dict[str, Any]:
    """Load kill switch state from disk with mtime-based cache.

    Guaranteed to never raise.

    FAIL-CLOSED: returns HALT_NEW state on any error (missing file,
    corrupt JSON, permission denied, etc.).  When safety status is
    unknown, entries are blocked.
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

    # Auto-clear check — READ-ONLY (no disk write).
    #
    # Previous versions wrote NORMAL back to disk inside this read function,
    # creating a TOCTOU race: a concurrent reader could overwrite an
    # EMERGENCY state set by another process.  We now compute the expired
    # state in memory only.  The on-disk file is updated lazily by the next
    # set_kill_mode() / clear_kill_switch() call or by a cron cleanup job.
    auto_clear = raw.get("auto_clear_at", "")
    if auto_clear:
        try:
            clear_dt = datetime.fromisoformat(auto_clear)
            if datetime.now(tz=timezone.utc) >= clear_dt:
                logger.info("kill_switch: auto_clear_at reached, reverting to NORMAL (in-memory)")
                raw["mode"] = MODE_NORMAL
                raw["reason"] = "auto-cleared at " + auto_clear
                raw["auto_clear_at"] = ""
        except Exception:
            pass

    state = dict(_DEFAULT_STATE)
    state.update({k: v for k, v in raw.items() if k in _DEFAULT_STATE})
    state["_mtime"] = mtime
    _cache[str(p)] = state
    return state


def get_kill_mode(path: Optional[Path] = None) -> str:
    """Return current mode: NORMAL, HALT_NEW, or EMERGENCY."""
    return load_kill_state(path).get("mode", MODE_NORMAL)


def is_kill_active(path: Optional[Path] = None) -> bool:
    """Return True when entries should be blocked (HALT_NEW or EMERGENCY)."""
    return get_kill_mode(path) != MODE_NORMAL


def is_emergency(path: Optional[Path] = None) -> bool:
    """Return True when EMERGENCY mode is active (open positions should close)."""
    return get_kill_mode(path) == MODE_EMERGENCY


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
    """Keep the mtime cache coherent after same-tick writes."""
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
    """Activate or deactivate the kill switch.

    Parameters
    ----------
    mode:               NORMAL, HALT_NEW, or EMERGENCY
    reason:             Human-readable reason stored in the state file.
    triggered_by:       Source of the trigger (e.g. 'drawdown_guard', 'operator', 'cli').
    auto_clear_minutes: If set, revert to NORMAL automatically after N minutes.
    path:               Override state file path.

    Returns the new state dict.
    """
    if mode not in VALID_MODES:
        raise ValueError(f"Invalid kill switch mode: {mode!r}. Must be one of {VALID_MODES}")

    p = path or KILL_SWITCH_PATH
    now = datetime.now(tz=timezone.utc)

    auto_clear_at = ""
    if auto_clear_minutes is not None and mode != MODE_NORMAL:
        from datetime import timedelta
        auto_clear_at = (now + timedelta(minutes=auto_clear_minutes)).isoformat()

    state = {
        "mode": mode,
        "reason": reason,
        "triggered_at": now.isoformat(),
        "triggered_by": triggered_by,
        "auto_clear_at": auto_clear_at,
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
    """Convenience: set mode back to NORMAL."""
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
        print(f"[KILL SWITCH] Mode: {s['mode']} — {s['reason']}")

    elif cmd == "emergency":
        s = set_kill_mode(MODE_EMERGENCY, reason=reason or "manual emergency", triggered_by="cli")
        print(f"[KILL SWITCH] EMERGENCY — {s['reason']}")

    elif cmd == "clear":
        s = clear_kill_switch(triggered_by="cli")
        print(f"[KILL SWITCH] Cleared — mode: {s['mode']}")

    else:
        print(f"Usage: {sys.argv[0]} [status|halt|emergency|clear] [reason]")
        sys.exit(1)
