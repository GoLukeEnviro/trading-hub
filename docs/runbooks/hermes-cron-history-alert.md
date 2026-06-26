# Hermes Cron History Alert — Operator Runbook

**Status:** L2 source-controlled tool. Not yet deployed to runtime.
**Replaces (eventually):** `hermes_error_alert.py` (paused since 2026-06-12, see deprecation timeline below).

This tool reads `/opt/data/profiles/orchestrator/state/cron_history.sqlite` (the DB populated by `cron_history_writer.py` since Sprint 1), classifies non-`ok` rows, deduplicates them, and applies a cooldown so a sustained failure does not produce alert spam.

## Why this exists

The previous alerting tool, `hermes_error_alert.py`, depended on volatile `jobs.json` fields:

- `last_status` / `last_error` (overwritten on every job run)
- `last_delivery_error` (transient, often empty)
- `agent.log` grep (unbounded text scraping)

After Sprint 1, `cron_history.sqlite` gives us a durable, append-only record of every cron execution with stable fields (`status`, `error_excerpt`, `duration_ms`, `exit_code`, `started_at`, `finished_at`). The DB is the correct source of truth.

## What it does

For each run:

1. Open the SQLite DB read-only via URI mode (`file:...?mode=ro`) — never blocks the writer.
2. Discover `cron_runs` schema via `PRAGMA table_info` (no hardcoded column list).
3. Fetch rows with `id > last_seen_id` from the state file.
4. For each row, classify:
   - `status='ok'` → no alert
   - `status ∈ {error, failed, timeout}` → ERROR alert
   - `status` is null/empty/unknown → WARNING alert
5. Compute a dedup key per row:
   - Primary: `job_id|status|sha1(error_excerpt)[:12]`
   - Fallback (no error_excerpt): `job_id|status|bucket:<5min>`
6. Drop alerts whose dedup key was emitted within `--cooldown-seconds`.
7. Collapse remaining alerts that share a dedup key into one (keep lowest row_id).
8. Cap to `--max-alerts`.
9. Optionally persist state to JSON (atomic write via `tempfile` + `os.replace`).

Telegram dispatch is **not** in this version. The tool prints alerts to stdout (text or JSON).

## CLI

```bash
python3 orchestrator/scripts/cron_history_alert.py \
  --db /opt/data/profiles/orchestrator/state/cron_history.sqlite \
  --state /opt/data/profiles/orchestrator/state/cron_history_alert_state.json \
  --lookback-minutes 60 \
  --cooldown-seconds 1800 \
  --max-alerts 5 \
  --dry-run
```

| Option | Default | Purpose |
| --- | --- | --- |
| `--db PATH` | `/opt/data/profiles/orchestrator/state/cron_history.sqlite` | SQLite path |
| `--state PATH` | `/opt/data/profiles/orchestrator/state/cron_history_alert_state.json` | Dedup/cooldown state JSON |
| `--lookback-minutes N` | 60 | Initial scan window when state is fresh |
| `--cooldown-seconds N` | 1800 | Per dedup-key cooldown |
| `--max-alerts N` | 5 | Hard cap per run |
| `--dry-run` | ON | Print to stdout, do not write state |
| `--commit-state` | OFF | Persist state changes (future runtime use) |
| `--format text\|json` | text | Output format |
| `--print-summary` | OFF | Always print one-line summary |

### Exit codes

| Code | Meaning |
| --- | --- |
| 0 | OK / no alerts / alerts rendered in dry-run |
| 2 | DB missing, schema invalid, or state file corrupted |
| 1 | Unexpected error |

## Operational patterns

### Live DB dry-run (manual check)

```bash
python3 orchestrator/scripts/cron_history_alert.py \
  --dry-run --print-summary
```

Expected output during a healthy run: `(no alerts)` plus a one-line summary to stderr:

```
summary: alerts=0 cooldown_suppressed=0 max_alerts_suppressed=0 rows_scanned=41 last_seen_id=41
```

### Manual replay (force a full re-scan without cooldown)

To re-read all rows from the beginning (useful after debugging a fix), reset the state file:

```bash
rm /opt/data/profiles/orchestrator/state/cron_history_alert_state.json
python3 orchestrator/scripts/cron_history_alert.py --dry-run --lookback-minutes 10080
```

The `--lookback-minutes 10080` (= 7 days) is a soft fallback; it does not actually constrain the read — the lookback is only used when state is fresh AND has no `last_seen_id` cursor. Since we removed the state file, the cursor is fresh.

### Inspecting a specific job's recent runs

Use the standard sqlite3 CLI (or any SQLite client). The tool does not currently expose a per-job query.

```bash
sqlite3 /opt/data/profiles/orchestrator/state/cron_history.sqlite \
  "SELECT id, status, started_at, error_excerpt FROM cron_runs WHERE job_id='a47e1c73e102' ORDER BY id DESC LIMIT 10"
```

### Validating after writer deploys

If you deploy a new `cron_history_writer.py` version, run the alert once with `--dry-run` and confirm:

- `rows_scanned` increases (writer is producing rows).
- No false alerts from schema changes.
- The `--format json` output is still valid JSON.

## State file format

`/opt/data/profiles/orchestrator/state/cron_history_alert_state.json`:

```json
{
  "last_seen_id": 41,
  "last_run_utc": "2026-06-26T14:04:48Z",
  "last_alerts": {
    "a47e1c73e102|error|c53d2f1a9a84": "2026-06-26T13:30:00+00:00"
  }
}
```

| Field | Purpose |
| --- | --- |
| `last_seen_id` | Cursor — `id > last_seen_id` rows are considered new |
| `last_run_utc` | ISO timestamp of the last successful run |
| `last_alerts` | dedup_key → ISO timestamp of last alert emitted (for cooldown) |

### Atomic writes

The state file is written via `tempfile.mkstemp` + `os.fsync` + `os.replace`. `os.replace` is atomic on POSIX, so a crash mid-write cannot produce a torn state file.

### Garbage collection

When state is persisted, the tool drops entries from `last_alerts` older than 7 days. This prevents the state file from growing unbounded if a job is broken for a long time.

## Deprecation of `hermes_error_alert.py`

The old script is NOT removed by this PR. It is still paused in `jobs.json` (`Hermes Error-Alert (5min)` — `enabled: false`, `state: paused`, paused at 2026-06-12T09:28:25 UTC, 133 completed runs before pause).

| Step | Status | Notes |
| --- | --- | --- |
| 1. Ship `cron_history_alert.py` + tests + runbook | ✅ this PR | L2 only |
| 2. Re-point paused job at new script | ⏸ separate PR | Requires runtime approval |
| 3. Observe at least one real alert in `cron_history.sqlite` end-to-end | ⏸ post-deploy | No manual trigger |
| 4. After one week of clean operation, archive old script | ⏸ future | Archive, do not delete |

The old script remains a fallback during this transition. **Do not delete `hermes_error_alert.py`** without separate explicit approval.

## Failure modes

| Symptom | Likely cause | Recovery |
| --- | --- | --- |
| Exit 2: "DB file missing" | Writer not deployed, or wrong path | Check `cron_history_writer.py` deployment |
| Exit 2: "required table missing" | DB is from a different writer version | Re-run writer, or migrate schema |
| Exit 2: "state file corrupted" | Disk full mid-write, or manual edit | Inspect JSON, fix or remove state file |
| Always exits 0 with `(no alerts)` despite known errors | Writer not running, or `status='ok'` filter is too permissive | Inspect DB directly |
| `suppressed_by_cooldown` keeps growing | Cooldown too long, or broken job in tight loop | Lower cooldown; investigate root cause |

## Tests

```bash
python3 -m pytest orchestrator/tests/test_cron_history_alert.py -v
```

51 unit tests covering:

- Status classification (ok, error, failed, timeout, unknown, empty)
- Dedup key (with and without error_excerpt)
- Schema discovery (column presence, missing table)
- Fetch after-id filtering
- State load/save (missing, valid, partial, corrupted)
- Cooldown filtering (within, expired, disabled)
- Max-alerts cap
- Intra-run dedup
- Render (text, JSON)
- End-to-end pipeline (empty DB, ok-only, mixed, commit-state)
- CLI main() (dry-run, JSON format, missing DB)

## See also

- `docs/reports/hermes-cron-history-alert-audit-20260626-140448.md` — design + audit report
- `docs/reports/hermes-cron-history-repair-campaign.md` — Sprint 1 (writer hook)
- `orchestrator/scripts/cron_history_writer.py` — Sprint 1 writer (populates this DB)
- `hermes-cron-runtime-contract` skill — runtime contract for `/opt/hermes` writes
