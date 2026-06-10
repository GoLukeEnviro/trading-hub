#!/usr/bin/env python3
"""
Shadowlock Indexer Queries

Convenience functions used by Forensics Agent and Self-Improvement Orchestrator.
"""

import sqlite3
from pathlib import Path

DB_PATH = Path("var/trading-shadowlock/state/shadowlock.db")


def get_bot_performance_summary(bot_name: str, days: int = 30):
    """Return simple performance stats for a bot from shadow events."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        SELECT 
            COUNT(*) as total_events,
            AVG(CAST(json_extract(performance_summary, '$.pf') AS REAL)) as avg_pf
        FROM shadow_events
        WHERE bot_name = ? 
          AND timestamp_utc > datetime('now', '-' || ? || ' days')
    ''', (bot_name, days))
    row = c.fetchone()
    conn.close()
    return {"total_events": row[0], "avg_pf": row[1]} if row else {}


def episode_exists(episode_id: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT 1 FROM shadow_events WHERE run_id = ? LIMIT 1", (episode_id,))
    exists = c.fetchone() is not None
    conn.close()
    return exists


def get_last_successful_episode(bot_name: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        SELECT run_id, timestamp_utc, performance_summary 
        FROM shadow_events 
        WHERE bot_name = ? AND event_type LIKE '%episode%' 
        ORDER BY timestamp_utc DESC LIMIT 1
    ''', (bot_name,))
    row = c.fetchone()
    conn.close()
    return row
