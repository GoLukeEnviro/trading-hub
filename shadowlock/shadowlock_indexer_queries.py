#!/usr/bin/env python3
"""
Shadowlock Indexer Queries v2.0

Convenience query functions for Forensics Agent and Self-Improvement Orchestrator.
Each function opens a read-only connection, queries, and closes.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "var" / "trading-shadowlock" / "state" / "shadowlock.db"


def _query(sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    """Run a read-only query and return results."""
    if not DB_PATH.exists():
        return []
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(sql, params)
        rows = cur.fetchall()
        return rows
    finally:
        conn.close()


def _query_one(sql: str, params: tuple = ()) -> sqlite3.Row | None:
    """Run a read-only query and return the first row or None."""
    rows = _query(sql, params)
    return rows[0] if rows else None


# ── Episode Queries ──────────────────────────────────────────────────────


def get_recent_episodes(bot: str, days: int = 365) -> list[dict]:
    """Get recent episodes for a bot within the given day window.

    Args:
        bot: Bot identifier.
        days: Lookback window in days.

    Returns:
        List of episode dicts.
    """
    rows = _query(
        """SELECT * FROM episodes
           WHERE target_bot = ?
             AND timestamp_utc > datetime('now', '-' || ? || ' days')
           ORDER BY timestamp_utc DESC""",
        (bot, str(days)),
    )
    return [dict(r) for r in rows]


def get_episodes_by_outcome(bot: str, outcome: str) -> list[dict]:
    """Get episodes for a bot filtered by outcome.

    Args:
        bot: Bot identifier.
        outcome: Outcome value (pass, fail, partial, etc.).

    Returns:
        List of episode dicts.
    """
    rows = _query(
        """SELECT * FROM episodes
           WHERE target_bot = ? AND outcome = ?
           ORDER BY timestamp_utc DESC""",
        (bot, outcome),
    )
    return [dict(r) for r in rows]


def get_hard_stop_episodes(bot: str, within_days: int = 30) -> list[dict]:
    """Get episodes that resulted in automated hard-stop within N days.

    Args:
        bot: Bot identifier.
        within_days: Lookback window in days.

    Returns:
        List of episode dicts with artifacts_invalidated=1 or severe outcomes.
    """
    rows = _query(
        """SELECT * FROM episodes
           WHERE target_bot = ?
             AND (artifacts_invalidated = 1 OR outcome IN ('fail', 'error'))
             AND timestamp_utc > datetime('now', '-' || ? || ' days')
           ORDER BY timestamp_utc DESC""",
        (bot, str(within_days)),
    )
    return [dict(r) for r in rows]


# ── Performance / Baseline Queries ────────────────────────────────────────


def get_baseline_PF(bot: str) -> float | None:
    """Get the baseline performance factor for a bot.

    Uses the median PF from the last 20 episodes.

    Args:
        bot: Bot identifier.

    Returns:
        Median PF value, or None if insufficient data.
    """
    rows = _query(
        """SELECT PF FROM episodes
           WHERE target_bot = ? AND PF IS NOT NULL
           ORDER BY timestamp_utc DESC LIMIT 20""",
        (bot,),
    )
    if not rows:
        return None
    pfs = sorted([r["PF"] for r in rows if r["PF"] is not None])
    if not pfs:
        return None
    n = len(pfs)
    return float(pfs[n // 2])


# ── Forensics Run Queries ─────────────────────────────────────────────────


def get_forensics_runs(limit: int = 10) -> list[dict]:
    """Get the most recent forensics runs.

    Args:
        limit: Maximum number of runs to return.

    Returns:
        List of forensics run dicts.
    """
    rows = _query(
        """SELECT * FROM forensics_runs
           ORDER BY timestamp_utc DESC LIMIT ?""",
        (limit,),
    )
    return [dict(r) for r in rows]


# ── Existence / Dedup Queries ─────────────────────────────────────────────


def episode_id_exists(episode_id: str) -> bool:
    """Check whether an episode ID already exists in the index.

    Args:
        episode_id: Episode identifier to check.

    Returns:
        True if the episode exists.
    """
    row = _query_one(
        "SELECT 1 FROM episodes WHERE episode_id = ? LIMIT 1",
        (episode_id,),
    )
    return row is not None


def get_recent_events(bot_name: str | None = None, limit: int = 100) -> list[dict]:
    """Get recent shadowlock events, optionally filtered by bot.

    Args:
        bot_name: Optional bot filter.
        limit: Maximum number of events.

    Returns:
        List of event dicts.
    """
    if bot_name:
        rows = _query(
            """SELECT * FROM shadowlock_events
               WHERE bot_name = ?
               ORDER BY timestamp_utc DESC LIMIT ?""",
            (bot_name, limit),
        )
    else:
        rows = _query(
            "SELECT * FROM shadowlock_events ORDER BY timestamp_utc DESC LIMIT ?",
            (limit,),
        )
    return [dict(r) for r in rows]
