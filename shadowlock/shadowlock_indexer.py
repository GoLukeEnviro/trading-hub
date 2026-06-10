#!/usr/bin/env python3
"""
Shadowlock Indexer v2.0

Creates and maintains a fast SQLite read-cache over the append-only JSONL shadow logs.
Supports full rebuild, incremental update, and watch modes.

The JSONL remains the source of truth (append-only).
The SQLite DB can be dropped and rebuilt at any time.

Usage:
    python shadowlock_indexer.py --rebuild       # Full rebuild
    python shadowlock_indexer.py --update        # Incremental update
    python shadowlock_indexer.py --watch --interval 60  # Continuous sidecar
"""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
import time
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("shadowlock-indexer")

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "var" / "trading-shadowlock" / "state" / "shadowlock.db"
LOGS_DIR = BASE_DIR / "var" / "trading-shadowlock" / "logs"
STATE_PATH = BASE_DIR / "var" / "trading-shadowlock" / "state" / "indexer.state"

# Schema version for tracking DB format
SCHEMA_VERSION = "2.0"


# ── Schema ──────────────────────────────────────────────────────────────────


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS episodes (
    episode_id          TEXT PRIMARY KEY,
    target_bot          TEXT NOT NULL,
    outcome             TEXT,
    PF                  REAL,
    actual_delta_PF     REAL,
    confidence          TEXT,
    outcome_margin      REAL,
    trade_count         INTEGER,
    next_action_label   TEXT,
    trigger             TEXT,
    source_forensics_run_id TEXT,
    timestamp_utc       TEXT NOT NULL,
    episode_window_start TEXT,
    episode_window_end   TEXT,
    artifacts_invalidated INTEGER DEFAULT 0,
    raw_entry           TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS forensics_runs (
    run_id              TEXT PRIMARY KEY,
    timestamp_utc       TEXT NOT NULL,
    bots_analyzed       TEXT,
    candidates_found    INTEGER,
    top_candidate_bot   TEXT,
    top_candidate_priority_score REAL,
    artifacts           TEXT,
    raw_entry           TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS shadowlock_events (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    sequence_number     INTEGER,
    episode_id          TEXT,
    event_type          TEXT NOT NULL,
    bot_name            TEXT,
    target_bot          TEXT,
    timestamp_utc       TEXT NOT NULL,
    schema_version      TEXT,
    entry_sha256        TEXT,
    raw_entry           TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_episodes_bot       ON episodes(target_bot);
CREATE INDEX IF NOT EXISTS idx_episodes_outcome   ON episodes(outcome);
CREATE INDEX IF NOT EXISTS idx_episodes_timestamp ON episodes(timestamp_utc);
CREATE INDEX IF NOT EXISTS idx_events_type        ON shadowlock_events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_bot         ON shadowlock_events(bot_name);
CREATE INDEX IF NOT EXISTS idx_events_timestamp   ON shadowlock_events(timestamp_utc);
CREATE INDEX IF NOT EXISTS idx_forensics_timestamp ON forensics_runs(timestamp_utc);
"""


# ── Database ─────────────────────────────────────────────────────────────────


def _get_conn() -> sqlite3.Connection:
    """Open a connection with row factory."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    """Create tables and indexes if they don't exist."""
    conn = _get_conn()
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    conn.close()
    logger.info("Database initialised at %s", DB_PATH)


# ── State tracking for incremental updates ──────────────────────────────────


def _read_state() -> dict:
    """Read the last processed state file.

    Returns:
        dict with 'file' (last processed JSONL path) and 'line' (line number).
    """
    if not STATE_PATH.exists():
        return {}
    try:
        raw = STATE_PATH.read_text().strip()
        parts = raw.split(":", 1)
        if len(parts) == 2:
            return {"file": parts[0], "line": int(parts[1])}
    except (ValueError, OSError):
        pass
    return {}


def _write_state(file_path: str, line_number: int) -> None:
    """Write processing state so incremental updates know where to resume."""
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(f"{file_path}:{line_number}")


# ── JSONL Processing ────────────────────────────────────────────────────────


def _route_event(conn: sqlite3.Connection, line: str, line_num: int) -> None:
    """Parse a JSONL line and route it to the correct table."""
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        logger.warning("Skipping corrupt JSONL line %d: %s", line_num, line[:80])
        return

    event_type = event.get("event_type", "")
    ts = event.get("timestamp_utc", "")

    # Always insert into shadowlock_events
    conn.execute(
        """INSERT OR IGNORE INTO shadowlock_events
           (sequence_number, episode_id, event_type, bot_name, target_bot,
            timestamp_utc, schema_version, entry_sha256, raw_entry)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            event.get("sequence_number"),
            event.get("episode_id"),
            event_type,
            event.get("bot_name"),
            event.get("target_bot"),
            ts,
            event.get("schema_version", SCHEMA_VERSION),
            event.get("entry_sha256"),
            line,
        ),
    )

    # Route to specialized tables
    if event_type == "self_improvement_episode":
        conn.execute(
            """INSERT OR IGNORE INTO episodes
               (episode_id, target_bot, outcome, PF, actual_delta_PF,
                confidence, outcome_margin, trade_count, next_action_label,
                trigger, source_forensics_run_id, timestamp_utc,
                episode_window_start, episode_window_end,
                artifacts_invalidated, raw_entry)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event.get("episode_id"),
                event.get("target_bot"),
                event.get("outcome"),
                event.get("PF"),
                event.get("actual_delta_PF"),
                event.get("confidence"),
                event.get("outcome_margin"),
                event.get("trade_count"),
                event.get("next_action_label"),
                event.get("trigger"),
                event.get("source_forensics_run_id"),
                ts,
                event.get("episode_window_start"),
                event.get("episode_window_end"),
                1 if event.get("artifacts_invalidated") else 0,
                line,
            ),
        )

    elif event_type == "forensics_run_complete":
        conn.execute(
            """INSERT OR IGNORE INTO forensics_runs
               (run_id, timestamp_utc, bots_analyzed, candidates_found,
                top_candidate_bot, top_candidate_priority_score,
                artifacts, raw_entry)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event.get("run_id"),
                ts,
                json.dumps(event.get("bots_analyzed", [])),
                event.get("candidates_found"),
                event.get("top_candidate_bot"),
                event.get("top_candidate_priority_score"),
                json.dumps(event.get("artifacts", {})),
                line,
            ),
        )


def index_jsonl_file(
    conn: sqlite3.Connection,
    jsonl_path: Path,
    skip_lines: int = 0,
) -> int:
    """Index a single JSONL file, optionally skipping N lines.

    Args:
        conn: Open database connection.
        jsonl_path: Path to JSONL file.
        skip_lines: Number of lines to skip (for incremental updates).

    Returns:
        Number of lines indexed.
    """
    if not jsonl_path.exists():
        return 0

    inserted = 0
    with open(jsonl_path) as f:
        for line_num, line in enumerate(f, start=1):
            if line_num <= skip_lines:
                continue
            line = line.strip()
            if not line:
                continue
            _route_event(conn, line, line_num)
            inserted += 1

    conn.commit()
    return inserted


# ── Modes ────────────────────────────────────────────────────────────────────


def rebuild_index() -> int:
    """Full rebuild: drop and recreate all tables, re-index all JSONL files."""
    logger.info("Starting full rebuild...")
    conn = _get_conn()
    # Drop and recreate
    conn.executescript("""
        DROP TABLE IF EXISTS episodes;
        DROP TABLE IF EXISTS forensics_runs;
        DROP TABLE IF EXISTS shadowlock_events;
    """)
    conn.executescript(SCHEMA_SQL)
    conn.commit()

    total = 0
    files_processed = 0
    for year_dir in sorted(LOGS_DIR.glob("*")):
        if not year_dir.is_dir():
            continue
        for month_dir in sorted(year_dir.glob("*")):
            if not month_dir.is_dir():
                continue
            for jsonl_file in sorted(month_dir.glob("*.jsonl")):
                indexed = index_jsonl_file(conn, jsonl_file, skip_lines=0)
                total += indexed
                files_processed += 1
                if indexed:
                    logger.info("  %s: %d events", jsonl_file.name, indexed)

    conn.close()
    # Reset state to trigger a fresh incremental scan next time
    _write_state("", 0)
    logger.info(
        "Rebuild complete: %d events from %d files into %s",
        total, files_processed, DB_PATH,
    )
    return total


def update_index() -> int:
    """Incremental update: only process new entries since last run.

    Returns:
        Number of newly indexed events.
    """
    state = _read_state()
    last_file = state.get("file", "")
    last_line = state.get("line", 0)

    conn = _get_conn()
    init_db()

    total = 0
    found_last = last_file == ""
    for year_dir in sorted(LOGS_DIR.glob("*")):
        if not year_dir.is_dir():
            continue
        for month_dir in sorted(year_dir.glob("*")):
            if not month_dir.is_dir():
                continue
            for jsonl_file in sorted(month_dir.glob("*.jsonl")):
                fpath = str(jsonl_file)
                if not found_last:
                    if fpath == last_file:
                        found_last = True
                        indexed = index_jsonl_file(conn, jsonl_file, skip_lines=last_line)
                    else:
                        continue
                else:
                    indexed = index_jsonl_file(conn, jsonl_file, skip_lines=0)

                total += indexed
                if indexed:
                    # Update state to this file's last line
                    _write_state(fpath, _count_lines(jsonl_file))

    conn.close()
    if total:
        logger.info("Incremental update: %d new events indexed", total)
    return total


def _count_lines(path: Path) -> int:
    """Count total lines in a file efficiently."""
    try:
        with open(path) as f:
            return sum(1 for _ in f)
    except OSError:
        return 0


def watch_mode(interval: int = 60) -> None:
    """Run as a continuous sidecar, polling for new JSONL entries."""
    logger.info("Starting watch mode (interval=%ds)", interval)
    init_db()
    while True:
        try:
            count = update_index()
            if count:
                logger.info("Watch: %d new events indexed", count)
        except Exception as exc:
            logger.error("Watch cycle failed: %s", exc)
        time.sleep(interval)


# ── CLI ──────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Shadowlock Indexer — SQLite read-cache for JSONL ledger"
    )
    parser.add_argument(
        "--rebuild", action="store_true", help="Full rebuild from all JSONL files"
    )
    parser.add_argument(
        "--update", action="store_true", help="Incremental update since last run"
    )
    parser.add_argument(
        "--watch", action="store_true", help="Run as continuous sidecar"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Poll interval in seconds (default: 60, used with --watch)",
    )

    args = parser.parse_args()

    if args.rebuild:
        rebuild_index()
    elif args.update:
        update_index()
    elif args.watch:
        watch_mode(interval=args.interval)
    else:
        # Default: init and update
        init_db()
        count = update_index()
        if count == 0:
            logger.info("No new events to index (run --rebuild for full rebuild)")


if __name__ == "__main__":
    main()
