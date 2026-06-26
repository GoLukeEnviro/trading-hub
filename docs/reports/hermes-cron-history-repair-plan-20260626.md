# Hermes Cron History Repair Plan

**Date:** 2026-06-26
**Author:** Hermes Orchestrator
**Status:** L2 Planning Phase
**Operation Level:** L0 → L1 → L2

## Executive Summary

This plan addresses 6 findings from the Hermes AD cron history audit. The
core fix is a SQLite-backed multi-run execution history, combined with path
repairs for heartbeat_writer.py and error alert cleanup.

## Findings

### F1 (P1): No Multi-Run History
- **Root cause:** Scheduler design — `mark_job_run()` only updates last-run fields
- **Fix:** New `cron_history_writer.py` with `cron_runs` SQLite table
- **Scheduler hook:** Prepare patch for `_process_job()` line 2129

### F2 (P1): Heartbeat Writer Read-Only Mount
- **Root cause:** `DB_PATH = /home/hermes/projects/trading/...` (read-only in container)
- **Fix:** Move to `/opt/data/profiles/orchestrator/state/hermes_heartbeat.sqlite`
- **L2 scope:** Git change to `orchestrator/scripts/heartbeat_writer.py`

### F3 (P1): Hermes Error Alert Paused + Bloated
- **Root cause:** No rotation, dedup, or size cap; state file 341KB
- **Fix (L2):** Document replacement path; keep paused
- **Fix (L3):** Replace with `cron_history_alert.py` reading `cron_history.sqlite`

### F4 (P2): No stdout/stderr Capture for no_agent
- **Root cause:** Scheduler discards stdout after delivery
- **Fix:** `cron_history_writer.py` captures stdout/stderr excerpts before delivery
- **Limitation:** Only captured if scheduler calls `record_cron_run()` — requires L3 patch

### F5 (P2): Stale Logs / Wrong Paths
- **Root cause:** Scripts stopped writing to old paths or disabled
- **Fix (L2):** Map stale logs to owners, propose fixes

### F6 (P2): no State Rotation Policy
- **Root cause:** `hermes_error_alert_state.json` has no retention/cap
- **Fix (L3):** Replacement alert uses bounded state with max 100 entries

## Phase Plan

| Phase | Scope | Level | Artifacts |
|-------|-------|-------|-----------|
| 0 | Preflight audit | L0 | ✓ Done |
| 1 | Design + tests | L1 → L2 | `docs/runbooks/hermes-cron-history-design.md`, 3 test files |
| 2 | Implement `cron_history_writer.py` | L2 | `orchestrator/scripts/cron_history_writer.py` |
| 3 | Patch `heartbeat_writer.py` | L2 | Path fix + env var override |
| 4 | Scheduler hook design | L2 | Patch file for scheduler.py |
| 5 | Error alert repair/replacement | L2 | Document replacement path |
| 6 | Stale log mapping | L2 | `docs/reports/hermes-stale-log-map-*.md` |
| 7 | Validation + PR | L2 | Branch `feat/hermes-cron-history-persistence` |
| 8 | L3 Runtime deploy | L3 | After merge + approval |
| 9 | Post-deploy observation | L3 | Snapshot verification |
| 10 | Final report | L3 | `docs/reports/hermes-cron-history-repair-final-*.md` |

## Risk Assessment

| Risk | Mitigation |
|------|------------|
| Scheduler patch durability | Patch file checksummed; /opt/hermes not Git-tracked |
| History DB write failure | Best-effort only — never blocks cron execution |
| Secret exposure in history | Redact via `redact_sensitive_text()` before persistence |
| Rollback | Backup all runtime files before L3 deploy; `restore.sh` included |
