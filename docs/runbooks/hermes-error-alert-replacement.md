# Hermes Error Alert Replacement: cron_history_alert.py

## Decision: Option B

Replace the paused `hermes_error_alert.py` with `cron_history_alert.py`
that reads `cron_history.sqlite` and reports recent failures.

**Rationale:**
- `cron_history.sqlite` (Phase 2) already captures per-run execution data
including status, exit_code, and error_excerpt for every cron job
- No need for a separate error-detection mechanism scanning agent logs
- Bounded state is built into the history system (retention + capping)
- Dedup/cooldown is simpler: just track `last_alerted` per job_id

## Current State

| Item | Status |
|------|--------|
| `hermes_error_alert.py` | Paused since 2026-06-12 |
| `hermes_error_alert_state.json` | 341 KB, stale, no rotation |
| Cron history replacement | ✅ Implemented in Phase 2 |

## Proposed cron_history_alert.py Design

- **Mode:** no_agent script, every 15 minutes
- **Target:** deliver=origin (so alerts appear in Hermes chat)
- **DB source:** `/opt/data/profiles/orchestrator/state/cron_history.sqlite`
- **Bounded state:** `/opt/data/profiles/orchestrator/state/cron_history_alert_state.json`
  - Max 100 entries
  - Max age 7 days for alert history
  - Dedup by `(job_id, error_excerpt)` hash

### Alert Logic

1. Query cron_history.sqlite for rows with status='error' in last 15 min
2. Group by job_id, error_excerpt
3. For each unique error not already alerted in last 60 min → emit alert
4. Save last_alerted timestamp per error fingerprint

### State File Format

```json
{
  "last_cleanup": "2026-06-26T12:00:00",
  "alerted_errors": {
    "<fingerprint>": {
      "job_id": "job_xxx",
      "error_snippet": "...",
      "first_seen": "...",
      "last_alerted": "...",
      "alert_count": 3
    }
  }
}
```

### Rotation

- Remove entries with `last_alerted` older than 7 days
- Cap at 100 entries (remove oldest first)

## Migration Path

| Phase | Action |
|-------|--------|
| L2 (current) | Document replacement plan. Do NOT touch jobs.json. |
| L3 | If cron_history.sqlite has data after scheduler hook deploy, create `cron_history_alert.py`, test it, then unpause old error alert and replace. |
| L3 | Optionally archive `hermes_error_alert_state.json` to `state/archive/`. |

## Risk

- No alerting between L2 and L3 deployment (status quo — job was already paused)
- cron_history_alert.py depends on cron_history.sqlite existing and being populated
- Dependency requires the scheduler hook (Phase 4) to be applied first
