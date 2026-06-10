#!/usr/bin/env python3
"""
Shadowlock Indexer v1.0

Creates and maintains a fast SQLite read-cache over the append-only JSONL shadow logs.
This allows the Forensics Agent and Orchestrator to run fast analytical queries
without scanning thousands of JSONL lines.

The JSONL remains the source of truth (append-only, git-ignorable).
The SQLite DB can be rebuilt at any time.

Author: Consolidated Self-Improvement architecture
"""

import sqlite3
import json
import os
from pathlib import Path
from datetime import datetime

DB_PATH = Path("var/trading-shadowlock/state/shadowlock.db")
LOGS_DIR = Path("var/trading-shadowlock/logs")


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS shadow_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp_utc TEXT,
            run_id TEXT,
            bot_name TEXT,
            role TEXT,
            mode TEXT,
            event_type TEXT,
            strategy_version TEXT,
            config_summary TEXT,
            git_commit_hash TEXT,
            performance_summary TEXT,
            signal_summary TEXT,
            noteworthy_events TEXT,
            data_gaps TEXT,
            schema_version TEXT,
            raw_json TEXT
        )
    ''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_bot_time ON shadow_events(bot_name, timestamp_utc)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_event_type ON shadow_events(event_type)')
    conn.commit()
    conn.close()


def index_jsonl_file(jsonl_path: Path):
    """Index a single daily JSONL file into SQLite."""
    if not jsonl_path.exists():
        return 0

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    inserted = 0

    with open(jsonl_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            c.execute('''
                INSERT OR IGNORE INTO shadow_events
                (timestamp_utc, run_id, bot_name, role, mode, event_type,
                 strategy_version, config_summary, git_commit_hash,
                 performance_summary, signal_summary, noteworthy_events,
                 data_gaps, schema_version, raw_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                event.get("timestamp_utc"),
                event.get("run_id"),
                event.get("bot_name"),
                event.get("role"),
                event.get("mode"),
                event.get("event_type"),
                event.get("strategy_version"),
                json.dumps(event.get("config_summary", {})),
                event.get("git_commit_hash"),
                json.dumps(event.get("performance_summary", {})),
                json.dumps(event.get("signal_summary", {})),
                json.dumps(event.get("noteworthy_events", [])),
                json.dumps(event.get("data_gaps", [])),
                event.get("schema_version", "1.0"),
                line
            ))
            inserted += 1

    conn.commit()
    conn.close()
    return inserted


def rebuild_index():
    """Rebuild the entire SQLite index from all JSONL files."""
    init_db()
    total = 0
    for year_dir in sorted(LOGS_DIR.glob("*")):
        for month_dir in sorted(year_dir.glob("*")):
            for jsonl_file in sorted(month_dir.glob("*.jsonl")):
                total += index_jsonl_file(jsonl_file)
    print(f"Indexed {total} events into {DB_PATH}")
    return total


def get_recent_events(bot_name: str = None, limit: int = 100):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if bot_name:
        c.execute("SELECT * FROM shadow_events WHERE bot_name = ? ORDER BY timestamp_utc DESC LIMIT ?", (bot_name, limit))
    else:
        c.execute("SELECT * FROM shadow_events ORDER BY timestamp_utc DESC LIMIT ?", (limit,))
    rows = c.fetchall()
    conn.close()
    return rows


if __name__ == "__main__":
    rebuild_index()
