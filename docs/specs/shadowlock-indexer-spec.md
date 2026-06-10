# Shadowlock Indexer Specification

**Component:** Shadowlock Indexer  
**Purpose:** Fast analytical read layer over the append-only JSONL audit trail  
**Status:** v1.0 — ready for integration

## Why it exists

The Shadowlock Writer produces high-volume append-only JSONL logs.
Forensics Agent and Orchestrator need fast queries ("show me all episodes for regime-hybrid in last 90 days", "has this parameter set already been tested?")

Scanning JSONL every time is slow and fragile. The Indexer solves this.

## Architecture

- **Source of truth**: JSONL files in `var/trading-shadowlock/logs/YYYY/MM/`
- **Read cache**: SQLite DB at `var/trading-shadowlock/state/shadowlock.db`
- **Rebuildable**: Can be dropped and rebuilt at any time from the JSONL

## Files

- `shadowlock/shadowlock_indexer.py` — core indexing logic
- `shadowlock/shadowlock_indexer_queries.py` — helper queries for agents
- `shadowlock/Dockerfile.indexer` — optional sidecar container

## Integration

- Triggered automatically by `shadowlock_writer.py` after every write (non-blocking)
- Used by:
  - Profitability Forensics Agent
  - Self-Improvement Orchestrator (to avoid re-testing same parameters)
  - Dashboard / reporting

## Future

- Incremental update mode (watch new JSONL lines)
- Automatic vacuum + optimization
- Export to Parquet for heavier analytics
