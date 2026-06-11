"""SQLite schema manager for the source_regime_stats derived cache.

Manages three tables:
- attribution_facts: raw fact records with CHECK constraints
- source_regime_stats: aggregated metrics per dimension group
- cache_metadata: single-row build metadata
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_VERSION = "1.1"

# ---------------------------------------------------------------------------
# Attribution facts — strict schema matching the #57 AttributionFact model
# ---------------------------------------------------------------------------
CREATE_ATTRIBUTION_FACTS = """
CREATE TABLE IF NOT EXISTS attribution_facts (
    fact_id              TEXT PRIMARY KEY,
    trade_id             TEXT NOT NULL,
    source_id            TEXT NOT NULL,
    strategy_or_model_id TEXT,
    pair                 TEXT NOT NULL,
    timeframe            TEXT NOT NULL,
    regime               TEXT NOT NULL CHECK (regime IN ('bullish','bearish','neutral','unknown')),
    confidence_bucket    TEXT NOT NULL,
    weighted_return      REAL NOT NULL,
    raw_trade_return     REAL NOT NULL,
    contribution_weight  REAL NOT NULL CHECK (contribution_weight > 0 AND contribution_weight <= 1.0),
    outcome_classification TEXT NOT NULL CHECK (outcome_classification IN ('WIN','LOSS','BREAKEVEN')),
    closed_at            TEXT NOT NULL,
    provenance_hash      TEXT NOT NULL,
    schema_version       TEXT NOT NULL,
    CHECK (length(trade_id) > 0),
    CHECK (length(source_id) > 0),
    CHECK (length(pair) > 0),
    CHECK (length(timeframe) > 0),
    CHECK (length(provenance_hash) > 0)
);
"""

# ---------------------------------------------------------------------------
# Source regime stats — aggregated metrics per dimension group
# ---------------------------------------------------------------------------
CREATE_SOURCE_REGIME_STATS = """
CREATE TABLE IF NOT EXISTS source_regime_stats (
    source_id                TEXT NOT NULL,
    strategy_or_model_id     TEXT,
    pair                     TEXT NOT NULL,
    timeframe                TEXT NOT NULL,
    regime                   TEXT NOT NULL CHECK (regime IN ('bullish','bearish','neutral','unknown')),
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
    average_source_confidence REAL,
    average_regime_confidence  REAL,
    evidence_max_closed_at   TEXT,
    input_fingerprint        TEXT NOT NULL DEFAULT '',
    last_updated             TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (source_id, strategy_or_model_id, pair, timeframe, regime, confidence_bucket)
);
"""

# ---------------------------------------------------------------------------
# Cache metadata — single-row pattern
# ---------------------------------------------------------------------------
CREATE_CACHE_METADATA = """
CREATE TABLE IF NOT EXISTS cache_metadata (
    id                 INTEGER PRIMARY KEY CHECK (id = 1),
    cache_schema_version TEXT NOT NULL,
    fact_schema_version  TEXT NOT NULL DEFAULT '',
    source_fingerprint   TEXT NOT NULL DEFAULT '',
    build_mode           TEXT NOT NULL DEFAULT 'full',
    last_evidence_time   TEXT NOT NULL DEFAULT '',
    operation_timestamp  TEXT NOT NULL DEFAULT ''
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


def foreign_key_check(conn: sqlite3.Connection) -> list[str]:
    """Run SQLite foreign_key_check and return any issues.

    Returns a list of 'table:rowid:parent:seq' problem strings.
    Empty list means all foreign keys are satisfied.
    """
    cursor = conn.execute("PRAGMA foreign_key_check;")
    issues: list[str] = []
    for row in cursor.fetchall():
        issues.append(f"{row[0]}:{row[1]}:{row[2]}:{row[3]}")
    return issues


def open_db(path: str | Path) -> sqlite3.Connection:
    """Open a SQLite connection with standard settings."""
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn
