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
4. **On a fresh state** (`last_seen_id == 0`), apply a time-window filter using `--lookback-minutes`:
   rows whose `created_at` (preferred) or `started_at` (fallback) is older than `now_utc - lookback_minutes` are skipped. This protects the first-ever run from alerting on historical failures from days/weeks ago.
5. For each remaining row, classify:
   - `status='ok'` → no alert
   - `status ∈ {error, failed, timeout}` → ERROR alert
   - `status` is null/empty/unknown → WARNING alert
6. Compute a dedup key per row:
   - Primary: `job_id|status|sha1(error_excerpt)[:12]`
   - Fallback (no error_excerpt): `job_id|status|bucket:<5min>`
7. Drop alerts whose dedup key was emitted within `--cooldown-seconds`.
8. Collapse remaining alerts that share a dedup key into one (keep lowest row_id).
9. Cap to `--max-alerts`.
10. Optionally persist state to JSON (atomic write via `tempfile` + `os.replace`).

Telegram dispatch is **not** in this version. The tool prints alerts to stdout (and optionally JSON).

### Lookback semantics — important

The lookback window is **only** applied when the state file is fresh (no cursor yet). Once the tool has a `last_seen_id`, it only considers rows with `id > last_seen_id`, which by construction are recent — no time filter is applied. This prevents accidental suppression of legitimate late writes.

If both `created_at` and `started_at` fail to parse (malformed timestamp), the row is **included** conservatively. We never silently drop an alert because of bad writer data; the operator must investigate the writer.

If you want a manual "force fresh scan" (e.g. after debugging a fix), remove the state file and run with the desired `--lookback-minutes` value. The state cursor will be re-created on the next commit.

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
| `--lookback-minutes N` | 60 | Time-window filter for fresh-state runs. `0` disables the filter (legacy behaviour). |
| `--cooldown-seconds N` | 1800 | Per dedup-key cooldown |
| `--max-alerts N` | 5 | Hard cap per run |
| `--dry-run` | OFF | Alias for omitting `--commit-state`. State is never written. **Mutually exclusive with `--commit-state`.** |
| `--commit-state` | OFF | Persist state changes after this run. **Mutually exclusive with `--dry-run`.** |
| `--now-utc ISO` | system time | Override `now_utc` for deterministic runs (tests, replay). |
| `--format text\|json` | text | Output format |
| `--print-summary` | OFF | Always print one-line summary |

### `--dry-run` vs `--commit-state` — important

The tool's safety model is: **state is written ONLY when `--commit-state` is explicitly set.** Without `--commit-state`, no file is touched. The `--dry-run` flag is an explicit no-write marker; combined with `--commit-state` it is rejected with exit code 2 and a clear error message.

Use cases:

- Manual inspection: `--dry-run --print-summary`
- Scheduled cron: `--commit-state` (no `--dry-run`)
- Reproducible historical replay: `--commit-state --now-utc 2026-06-25T14:00:00+00:00` (be careful — this overwrites the cursor)

### Exit codes

| Code | Meaning |
| --- | --- |
| 0 | OK / no alerts / alerts rendered in dry-run |
| 2 | DB missing, schema invalid, state file corrupted, or `--dry-run --commit-state` |
| 1 | Unexpected error |

## Operational patterns

### Live DB dry-run (manual check)

```bash
python3 orchestrator/scripts/cron_history_alert.py \
  --dry-run --print-summary
```

Expected output during a healthy run: `(no alerts)` plus a one-line summary to stderr:

```
summary: alerts=0 cooldown_suppressed=0 max_alerts_suppressed=0 rows_scanned=N rows_filtered_by_lookback=0 last_seen_id=N
```

Note `rows_filtered_by_lookback` will be `0` once the state file has a cursor — it only fires on fresh-state first runs.

### Manual replay (force a full re-scan without cooldown)

To re-read all rows from the beginning (useful after debugging a fix), reset the state file:

```bash
rm /opt/data/profiles/orchestrator/state/cron_history_alert_state.json
python3 orchestrator/scripts/cron_history_alert.py --dry-run
```

The default `--lookback-minutes 60` then limits the re-scan to the last hour. If you genuinely want a longer window (debug only — this would also alert on old rows), pass `--lookback-minutes 1440` (24h) explicitly. **Never use this in production cron — it's a manual operator action.**

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
