#!/usr/bin/env python3
"""Kill-Switch Proof/Verification — read-only, no mutation.

Verifies the integrity and consistency of the kill-switch state across
both the host (var/kill_switch.json) and container
(/freqtrade/shared/kill_switch.json) layers.

Exit codes:
  0 → GREEN   (all checks passed, consistent NORMAL)
  1 → YELLOW  (minor inconsistency, stale, or non-NORMAL mode)
  2 → RED     (fail-closed: missing, corrupt, or conflicting state)
  3 → Invalid arguments or configuration

Usage:
  python3 orchestrator/scripts/kill_switch_proof.py
  python3 orchestrator/scripts/kill_switch_proof.py --json
  python3 orchestrator/scripts/kill_switch_proof.py --stale-threshold-hours 48
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_MODES = {"NORMAL", "HALT_NEW", "EMERGENCY"}
DEFAULT_STALE_THRESHOLD_HOURS = 24

# Default paths
HOST_PATH = Path("var/kill_switch.json")
CONTAINER_PATH = Path("freqtrade/shared/kill_switch.json")

# ---------------------------------------------------------------------------
# Read helpers
# ---------------------------------------------------------------------------


def _read_state_file(path: Path) -> Optional[Dict[str, Any]]:
    """Read and parse a kill-switch JSON file.

    Returns None if the file is missing, unreadable, or contains
    invalid JSON.  Never raises.
    """
    try:
        raw = json.loads(path.read_text())
    except (FileNotFoundError, PermissionError, json.JSONDecodeError, OSError):
        return None
    if not isinstance(raw, dict):
        return None
    return raw


def _is_stale(
    state: Dict[str, Any],
    threshold_hours: float = DEFAULT_STALE_THRESHOLD_HOURS,
) -> bool:
    """Check whether the kill-switch state is stale.

    A state is stale when ``triggered_at`` is older than
    ``threshold_hours`` AND the mode is not NORMAL.
    NORMAL states are never stale (they are the default).
    """
    mode = state.get("mode", "NORMAL")
    if mode == "NORMAL":
        return False
    triggered_at = state.get("triggered_at", "")
    if not triggered_at:
        return True  # No timestamp → treat as stale
    try:
        ts = triggered_at if not triggered_at.endswith("Z") else triggered_at[:-1] + "+00:00"
        dt = datetime.fromisoformat(ts)
        age_hours = (datetime.now(tz=timezone.utc) - dt).total_seconds() / 3600
        return age_hours > threshold_hours
    except (ValueError, TypeError):
        return True  # Unparseable timestamp → treat as stale


def _is_auto_clear_expired(state: Dict[str, Any]) -> bool:
    """Check whether an auto_clear_at timestamp has passed.

    Returns True when auto_clear_at is set and the current time is
    past it.  This means the kill switch should have auto-cleared
    but the on-disk file was not updated.
    """
    auto_clear = state.get("auto_clear_at", "")
    if not auto_clear:
        return False
    try:
        ts = auto_clear if not auto_clear.endswith("Z") else auto_clear[:-1] + "+00:00"
        clear_dt = datetime.fromisoformat(ts)
        return datetime.now(tz=timezone.utc) >= clear_dt
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


def verify_kill_switch(
    host_path: Path = HOST_PATH,
    container_path: Path = CONTAINER_PATH,
    stale_threshold_hours: float = DEFAULT_STALE_THRESHOLD_HOURS,
) -> Dict[str, Any]:
    """Verify kill-switch integrity across host and container layers.

    Returns a dict with:
      - verdict: GREEN | YELLOW | RED
      - host: host state or None
      - container: container state or None
      - consistent: whether both layers agree
      - stale: whether the active non-NORMAL state is stale
      - auto_clear_expired: whether auto_clear_at has passed
      - errors: list of error strings
      - warnings: list of warning strings
    """
    errors: list[str] = []
    warnings: list[str] = []

    host_state = _read_state_file(host_path)
    container_state = _read_state_file(container_path)

    # --- Layer availability ---
    if host_state is None:
        errors.append(f"Host kill-switch file not readable: {host_path}")
    if container_state is None:
        errors.append(f"Container kill-switch file not readable: {container_path}")

    # --- Mode validation ---
    host_mode = (host_state or {}).get("mode", "UNKNOWN")
    container_mode = (container_state or {}).get("mode", "UNKNOWN")

    if host_mode not in VALID_MODES and host_mode != "UNKNOWN":
        errors.append(f"Host has invalid mode: {host_mode!r}")
    if container_mode not in VALID_MODES and container_mode != "UNKNOWN":
        errors.append(f"Container has invalid mode: {container_mode!r}")

    # --- Consistency check ---
    consistent = False
    if host_state is not None and container_state is not None:
        consistent = host_mode == container_mode
        if not consistent:
            warnings.append(
                f"Host/container mode mismatch: host={host_mode!r} vs container={container_mode!r}"
            )

    # --- Staleness check (only for non-NORMAL modes) ---
    stale = False
    for label, state in [("host", host_state), ("container", container_state)]:
        if state is None:
            continue
        if _is_stale(state, stale_threshold_hours):
            stale = True
            mode = state.get("mode", "?")
            triggered = state.get("triggered_at", "?")
            warnings.append(
                f"{label} kill switch is stale: mode={mode!r}, triggered_at={triggered!r}"
            )

    # --- Auto-clear check ---
    auto_clear_expired = False
    for label, state in [("host", host_state), ("container", container_state)]:
        if state is None:
            continue
        if _is_auto_clear_expired(state):
            auto_clear_expired = True
            warnings.append(
                f"{label} kill switch auto_clear_at has expired but state not updated"
            )

    # --- Verdict ---
    if errors:
        verdict = "RED"
    elif not consistent or stale or auto_clear_expired:
        verdict = "YELLOW"
    elif host_mode == "NORMAL" and container_mode == "NORMAL":
        verdict = "GREEN"
    else:
        verdict = "YELLOW"  # Non-NORMAL but consistent and fresh

    return {
        "verdict": verdict,
        "host": host_state,
        "container": container_state,
        "consistent": consistent,
        "stale": stale,
        "auto_clear_expired": auto_clear_expired,
        "errors": errors,
        "warnings": warnings,
        "host_mode": host_mode,
        "container_mode": container_mode,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Kill-Switch Proof/Verification — read-only, no mutation",
    )
    parser.add_argument(
        "--host-path",
        default=str(HOST_PATH),
        help=f"Host kill-switch path (default: {HOST_PATH})",
    )
    parser.add_argument(
        "--container-path",
        default=str(CONTAINER_PATH),
        help=f"Container kill-switch path (default: {CONTAINER_PATH})",
    )
    parser.add_argument(
        "--stale-threshold-hours",
        type=float,
        default=DEFAULT_STALE_THRESHOLD_HOURS,
        help=f"Staleness threshold in hours (default: {DEFAULT_STALE_THRESHOLD_HOURS})",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output JSON instead of human-readable text",
    )
    args = parser.parse_args()

    result = verify_kill_switch(
        host_path=Path(args.host_path),
        container_path=Path(args.container_path),
        stale_threshold_hours=args.stale_threshold_hours,
    )

    exit_code = 0 if result["verdict"] == "GREEN" else (1 if result["verdict"] == "YELLOW" else 2)

    if args.json:
        # Strip internal details for JSON output
        output = {
            "verdict": result["verdict"],
            "host_mode": result["host_mode"],
            "container_mode": result["container_mode"],
            "consistent": result["consistent"],
            "stale": result["stale"],
            "auto_clear_expired": result["auto_clear_expired"],
            "errors": result["errors"],
            "warnings": result["warnings"],
        }
        print(json.dumps(output, indent=2))
    else:
        print(f"Verdict          : {result['verdict']}")
        print(f"Host mode        : {result['host_mode']}")
        print(f"Container mode   : {result['container_mode']}")
        print(f"Consistent       : {result['consistent']}")
        print(f"Stale            : {result['stale']}")
        print(f"Auto-clear expired: {result['auto_clear_expired']}")
        if result["errors"]:
            print(f"Errors ({len(result['errors'])}):")
            for e in result["errors"]:
                print(f"  - {e}")
        if result["warnings"]:
            print(f"Warnings ({len(result['warnings'])}):")
            for w in result["warnings"]:
                print(f"  - {w}")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
