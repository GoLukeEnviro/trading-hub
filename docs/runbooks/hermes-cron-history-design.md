# Hermes Cron History Design

## Problem

The Hermes cron scheduler stores only **last-run metadata** in `jobs.json`:
`last_run_at`, `last_status`, `last_error`, `last_delivery_error`. There is no
multi-run execution history, no stdout/stderr capture for `no_agent` jobs,
and no way to audit past failures or trends.

## Architecture Decision

### Core Mechanism: SQLite Execution History

Create a standalone `cron_history_writer.py` module that persists one row per
cron execution to `/opt/data/profiles/orchestrator/state/cron_history.sqlite`.

### Integration Strategy (Scheduler Hook)

Since `/opt/hermes` is not a Git repository and the scheduler at
`/opt/hermes/cron/scheduler.py` cannot be safely patched in L2, we use a
**wrapper/instrumentation layer**:

1. The `cron_history_writer.py` module can be called as a CLI wrapper around
   existing scripts, or imported and called from the scheduler's
   `_process_job()` function after `mark_job_run()`.
2. A scheduler patch exporting the exact changes to `scheduler.py` and
   `jobs.py` is prepared as a patch file for L3 deployment.
3. The scheduler patch adds a single call to `record_cron_run(...)` after
   `mark_job_run()` in `_process_job()` (line 2129 of scheduler.py).

### Data Flow

```
cron tick → _process_job(job)
  → run_job(job)           # executes script or LLM
  → save_job_output(...)   # persists to file
  → deliver_result(...)    # sends to target
  → mark_job_run(...)      # updates jobs.json last_*
  → record_cron_run(...)   # NEW: appends to cron_history.sqlite
```

### Schema

```sql
CREATE TABLE IF NOT EXISTS cron_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id          TEXT NOT NULL,
    job_name        TEXT,
    no_agent        INTEGER,
    script_path     TEXT,
    delivery_mode   TEXT,
    started_at      TEXT NOT NULL,
    finished_at     TEXT,
    duration_ms     INTEGER,
    status          TEXT NOT NULL,
    exit_code       INTEGER,
    timeout         INTEGER,
    stdout_excerpt  TEXT,
    stderr_excerpt  TEXT,
    error_excerpt   TEXT,
    created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_cron_runs_job_time ON cron_runs(job_id, started_at);
CREATE INDEX IF NOT EXISTS idx_cron_runs_status_time ON cron_runs(status, started_at);
```

### Security

- **Secret redaction:** All stdout/stderr/error excerpts are passed through
  `agent.redact.redact_sensitive_text()` (same function used by the scheduler)
  before persistence.
- **Size capping:** stdout/stderr/excerpts capped at 4096 chars each.
- **No raw env dumps:** Only specified fields are stored.
- **Narrow permissions:** DB file created with mode 0o640.

### Retention Policy

- Keep last 90 days of history.
- Keep max 10,000 rows per job_id (newest wins).
- Retention enforced on every write: old rows are purged after insert.

### File Location

- Module: `orchestrator/scripts/cron_history_writer.py`
- DB: `/opt/data/profiles/orchestrator/state/cron_history.sqlite`
- Self-test mode: writes to a temp directory unless `--db-path` is given

## Heartbeat Writer Fix

Change `heartbeat_writer.py` DB_PATH from:
```python
DB_PATH = Path("/home/hermes/projects/trading/orchestrator/state/hermes_heartbeat.sqlite")
```
To:
```python
DB_PATH = Path("/opt/data/profiles/orchestrator/state/hermes_heartbeat.sqlite")
```

With environment variable override:
```python
DB_PATH = Path(os.environ.get(
    "HERMES_HEARTBEAT_DB_PATH",
    "/opt/data/profiles/orchestrator/state/hermes_heartbeat.sqlite"
))
```

## Error Alert Strategy

**Decision:** Option B — Replace with `cron_history.sqlite`-based alerting.

The paused `hermes_error_alert.py` (runtime-only, not in Git) is replaced by a
new `cron_history_alert.py` (L3) that reads `cron_history.sqlite` and reports
recent failures with bounded state and dedup cooldown.

During L2: keep paused, document replacement path.

## Affected Paths

| Current Path | New Path | Component |
|---|---|---|
| `/home/hermes/projects/trading/orchestrator/state/hermes_heartbeat.sqlite` | `/opt/data/profiles/orchestrator/state/hermes_heartbeat.sqlite` | heartbeat_writer.py |
| `/home/hermes/projects/trading/HERMES_CHANGELOG.md` | `/opt/data/profiles/orchestrator/logs/hermes_changelog.md` | hermes_error_alert.py (replacement) |
| `/home/hermes/projects/trading/HERMES_METRICS.json` | `/opt/data/profiles/orchestrator/state/hermes_metrics.json` | hermes_error_alert.py (replacement) |
| *(new)* `/opt/data/profiles/orchestrator/state/cron_history.sqlite` | — | cron_history_writer.py |
