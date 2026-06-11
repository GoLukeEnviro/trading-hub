"""SQLite schema manager for the source_regime_stats derived cache.

Manages three tables:
- attribution_facts: raw fact records
- source_regime_stats: aggregated metrics per dimension group
- cache_metadata: build metadata
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_VERSION = "1.0"

CREATE_ATTRIBUTION_FACTS = """
CREATE TABLE IF NOT EXISTS attribution_facts (
    fact_id              TEXT PRIMARY KEY,
    trade_id             TEXT NOT NULL,
    source_id            TEXT NOT NULL,
    strategy_or_model_id TEXT,
    pair                 TEXT NOT NULL,
    timeframe            TEXT NOT NULL,
    regime               TEXT NOT NULL,
    confidence_bucket    TEXT NOT NULL,
    weighted_return      REAL NOT NULL,
    raw_trade_return     REAL NOT NULL,
    contribution_weight  REAL NOT NULL,
    outcome_classification TEXT NOT NULL,
    closed_at            TEXT NOT NULL,
    provenance_hash      TEXT NOT NULL,
    schema_version       TEXT NOT NULL
);
"""

CREATE_SOURCE_REGIME_STATS = """
CREATE TABLE IF NOT EXISTS source_regime_stats (
    source_id                TEXT NOT NULL,
    strategy_or_model_id     TEXT,
    pair                     TEXT NOT NULL,
    timeframe                TEXT NOT NULL,
    regime                   TEXT NOT NULL,
    confidence_bucket        TEXT NOT NULL,
    unique_trade_count       INTEGER NOT NULL DEFAULT 0,
    source_contribution_count INTEGER NOT NULL DEFAULT 0,
    win_count                INTEGER NOT NULL DEFAULT 0,
    loss_count               INTEGER NOT NULL DEFAULT 0,
    breakeven_count          INTEGER NOT NULL DEFAULT 0,
    win_rate                 REAL NOT NULL DEFAULT 0.0,
    average_raw_return       REAL NOT NULL DEFAULT 0.0,
    average_weighted_return  REAL NOT NULL DEFAULT 0.0,
    expectancy               REAL NOT NULL DEFAULT 0.0,
    cumulative_weighted_return REAL NOT NULL DEFAULT 0.0,
    drawdown_proxy           REAL NOT NULL DEFAULT 0.0,
    average_source_confidence REAL NOT NULL DEFAULT 0.0,
    average_regime_confidence  REAL NOT NULL DEFAULT 0.0,
    PRIMARY KEY (source_id, strategy_or_model_id, pair, timeframe, regime, confidence_bucket)
);
"""

CREATE_CACHE_METADATA = """
CREATE TABLE IF NOT EXISTS cache_metadata (
    schema_version      TEXT NOT NULL,
    source_fingerprint  TEXT NOT NULL DEFAULT '',
    last_rebuild_time   TEXT NOT NULL DEFAULT '',
    last_incremental_time TEXT NOT NULL DEFAULT '',
    build_mode          TEXT NOT NULL DEFAULT 'full'
);
"""


def create_schema(conn: sqlite3.Connection) -> None:
    """Create all three schema tables in the given connection."""
    conn.executescript(CREATE_ATTRIBUTION_FACTS)
    conn.executescript(CREATE_SOURCE_REGIME_STATS)
    conn.executescript(CREATE_CACHE_METADATA)
    conn.commit()


def integrity_check(conn: sqlite3.Connection) -> list[str]:
    """Run SQLite integrity_check and return any issues.

    Returns a list of problem strings. Empty list means clean.
    """
    cursor = conn.execute("PRAGMA integrity_check;")
    rows = [row[0] for row in cursor.fetchall()]
    return [r for r in rows if r != "ok"]


def open_db(path: str | Path) -> sqlite3.Connection:
    """Open a SQLite connection with standard settings."""
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn
