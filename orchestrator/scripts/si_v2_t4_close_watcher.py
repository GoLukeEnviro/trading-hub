#!/usr/bin/env python3
"""SI-v2 T4 Close Watcher — read-only Canary/Control trade close detector.

Reads the Canary and Control Freqtrade SQLite databases (host bind-mount)
and checks whether at least one new trade has closed since the T3 measurement
point.  Outputs a single-line verdict suitable for cron/no_agent delivery.

Verdicts
--------
STILL_WAITING              — Canary has 0 new closed trades since T3.
T4_READY                   — Canary has >=1 and Control has >=1 new closed trade.
STILL_WAITING_CONTROL_MISSING — Canary has >=1 but Control has 0 new closed trades.
UNKNOWN                    — DB not found, unreadable, or query error.

Safety
------
- Read-only (SQLite mode=ro, PRAGMA query_only=ON).
- No file writes, no config changes, no Docker/Compose mutation.
- No auto-apply, no auto-restart, no auto-rollback.
- No live trading, no dry_run=false.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

# Default T3 measurement timestamp (UTC)
DEFAULT_T3_UTC = "2026-06-28T18:27:00Z"

# Default host bind-mount DB paths (from source-of-truth audit, PR #399)
DEFAULT_CANARY_DB = (
    "/home/hermes/projects/trading/freqforge-canary/user_data"
    "/tradesv3.freqforge_canary.dryrun.sqlite"
)
DEFAULT_CONTROL_DB = (
    "/home/hermes/projects/trading/freqforge/user_data"
    "/tradesv3.freqforge.dryrun.sqlite"
)

# Verdict constants
STILL_WAITING = "STILL_WAITING"
T4_READY = "T4_READY"
STILL_WAITING_CONTROL_MISSING = "STILL_WAITING_CONTROL_MISSING"
UNKNOWN = "UNKNOWN"


def _parse_t3(t3_str: str) -> str:
    """Normalise a T3 timestamp to ISO-8601 format accepted by SQLite.

    Accepts ``2026-06-28T18:27:00Z`` or ``2026-06-28 18:27:00``.
    Returns a string suitable for SQLite comparison.
    """
    t3_str = t3_str.strip().replace("T", " ").rstrip("Z")
    # Validate by round-tripping
    try:
        dt = datetime.strptime(t3_str, "%Y-%m-%d %H:%M:%S")
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        raise ValueError(f"Invalid T3 timestamp: {t3_str!r}")


def _connect_ro(path: Path) -> sqlite3.Connection:
    """Open a SQLite connection in strict read-only mode."""
    uri = f"file:{path.resolve()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.execute("PRAGMA query_only = ON")
    return conn


def _count_closed_since(conn: sqlite3.Connection, since: str) -> int:
    """Return the number of closed trades with close_date > ``since``."""
    cur = conn.execute(
        "SELECT COUNT(*) FROM trades "
        "WHERE is_open = 0 AND close_date IS NOT NULL AND close_date > ?",
        (since,),
    )
    return cur.fetchone()[0]


def check_t4_readiness(
    canary_db: Path,
    control_db: Path,
    t3_timestamp: str = DEFAULT_T3_UTC,
) -> tuple[str, dict[str, object]]:
    """Check whether the Canary and Control bots have new closed trades since T3.

    Returns
    -------
    (verdict, details)
        verdict is one of the module-level constants.
        details contains per-bot counts and the T3 timestamp used.
    """
    since = _parse_t3(t3_timestamp)
    errors: list[str] = []
    details: dict[str, object] = {
        "t3_timestamp": t3_timestamp,
        "since_normalised": since,
        "canary_db": str(canary_db),
        "control_db": str(control_db),
        "canary_new_closed": None,
        "control_new_closed": None,
        "errors": errors,
    }

    canary_count: int | None = None
    control_count: int | None = None

    # Canary
    if not canary_db.exists():
        details["errors"].append(f"canary_db_not_found: {canary_db}")
    else:
        try:
            conn = _connect_ro(canary_db)
            canary_count = _count_closed_since(conn, since)
            conn.close()
            details["canary_new_closed"] = canary_count
        except (sqlite3.DatabaseError, sqlite3.OperationalError) as e:
            details["errors"].append(f"canary_db_error: {e}")

    # Control
    if not control_db.exists():
        details["errors"].append(f"control_db_not_found: {control_db}")
    else:
        try:
            conn = _connect_ro(control_db)
            control_count = _count_closed_since(conn, since)
            conn.close()
            details["control_new_closed"] = control_count
        except (sqlite3.DatabaseError, sqlite3.OperationalError) as e:
            details["errors"].append(f"control_db_error: {e}")

    # Determine verdict
    if details["errors"] and canary_count is None and control_count is None:
        return UNKNOWN, details

    if canary_count is None or control_count is None:
        return UNKNOWN, details

    if canary_count >= 1 and control_count >= 1:
        return T4_READY, details
    elif canary_count >= 1:
        return STILL_WAITING_CONTROL_MISSING, details
    else:
        return STILL_WAITING, details


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--canary-db",
        type=Path,
        default=Path(DEFAULT_CANARY_DB),
        help="Path to the Canary bot's SQLite trade database.",
    )
    p.add_argument(
        "--control-db",
        type=Path,
        default=Path(DEFAULT_CONTROL_DB),
        help="Path to the Control bot's SQLite trade database.",
    )
    p.add_argument(
        "--t3-timestamp",
        type=str,
        default=DEFAULT_T3_UTC,
        help="T3 measurement timestamp (UTC). Default: %(default)s",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="Output verdict and details as JSON (default: plain text).",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    verdict, details = check_t4_readiness(
        canary_db=args.canary_db,
        control_db=args.control_db,
        t3_timestamp=args.t3_timestamp,
    )

    if args.json:
        import json
        details["verdict"] = verdict
        print(json.dumps(details, indent=2, default=str))
    else:
        print(verdict)

    if verdict == UNKNOWN:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
