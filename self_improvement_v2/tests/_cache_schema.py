"""Canonical schema definitions for source_regime_stats cache tests.

This module provides the authoritative CREATE TABLE SQL for the
cache_metadata table and related fixtures used by source_regime_stats
caches. Tests should import from here rather than duplicating the
schema SQL inline.
"""

# Canonical cache_metadata table DDL matching source_regime_stats
CACHE_METADATA_SCHEMA_SQL = """
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

# Canonical source_regime_stats data table DDL
SOURCE_REGIME_STATS_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS source_regime_stats (
    stat_id                   TEXT PRIMARY KEY,
    source_id                 TEXT NOT NULL,
    regime                    TEXT NOT NULL,
    confidence_bucket         TEXT NOT NULL,
    unique_trade_count        INTEGER NOT NULL DEFAULT 0,
    win_count                 INTEGER NOT NULL DEFAULT 0,
    loss_count                INTEGER NOT NULL DEFAULT 0,
    breakeven_count           INTEGER NOT NULL DEFAULT 0,
    win_rate                  REAL NOT NULL DEFAULT 0.0,
    expectancy                REAL NOT NULL DEFAULT 0.0
);
"""

# Attribution facts table (used by source_regime_stats cache)
ATTRIBUTION_FACTS_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS attribution_facts (
    fact_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL
);
"""

# Canonical metadata row insert SQL
METADATA_INSERT_SQL = """
INSERT INTO cache_metadata (id, cache_schema_version, fact_schema_version,
    source_fingerprint, build_mode, last_evidence_time, operation_timestamp)
VALUES (1, '1.1', '1.0', 'test-fingerprint-abc123', 'full',
    '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')
"""
