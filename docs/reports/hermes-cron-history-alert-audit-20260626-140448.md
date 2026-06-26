# Sprint 2 Audit — Hermes Cron History Alerting

**Date (UTC):** 2026-06-26 14:04:48
**Auditor:** Hermes (orchestrator profile)
**Operation Level:** L0 (read-only)
**Final Status:** **GREEN for design, ready to implement**

This is the Sprint 2 audit before implementing `cron_history_alert.py`. Sprint 1 closed GREEN: `cron_history.sqlite` now receives real scheduler-driven rows. Sprint 2 must replace the volatile `jobs.json`-based `hermes_error_alert.py` approach with a DB-backed reader.

---

## Executive Verdict

**GREEN for design — proceed to L2 implementation.**

The path is clear, but two findings shape the design:

1. **`hermes_error_alert.py` already exists at `/opt/data/profiles/orchestrator/scripts/`** but is NOT in the Git repo (CRON_ONLY). The corresponding `Hermes Error-Alert (5min)` job in `jobs.json` is **disabled and paused since 2026-06-12T09:28:25 UTC** (133 completed runs before pause). It currently emits zero alerts and is safe to leave running or to supersede.

2. **`cron_history.sqlite` has 16 columns**, including the dedup-relevant `error_excerpt`. The schema is stable enough to depend on for alerting, but the tool must use `PRAGMA table_info(cron_runs)` to discover columns at startup rather than hard-coding (defensive against future schema migrations).

3. **Live DB state is GREEN**: 41 rows, 23 unique job_ids, all `status='ok'`. A first dry-run against the live DB will produce `no alerts`. This is the right time to ship the tool — no test data needed to demonstrate "happy path" behaviour.

---

## Existing Alert Architecture (Phase 0 read-only audit)

### `hermes_error_alert.py` (current, paused)

| Property | Value |
| --- | --- |
| Path | `/opt/data/profiles/orchestrator/scripts/hermes_error_alert.py` |
| In Git repo? | **No** — CRON_ONLY runtime script |
| Size | 148 lines |
| Last modified | 2026-06-12 (approximate; paused the same day) |
| Triggered by | `Hermes Error-Alert (5min)` job, every 5 minutes |
| Job status in `jobs.json` | `enabled: false`, `state: paused`, paused at 2026-06-12T09:28:25 UTC |
| Repeat count | 133 completed runs before pause |
| Sources it reads | `jobs.json` (`last_status`, `last_error`, `last_delivery_error`) + `/opt/data/profiles/orchestrator/logs/agent.log` (grep) |
| Outputs it writes | `HERMES_CHANGELOG.md`, `HERMES_METRICS.json`, Telegram via legacy ``deliver=telegram:<chat_id>`` config |
| State file | `/opt/data/profiles/orchestrator/state/hermes_error_alert_state.json` |

### Why it needs replacing

The current tool depends on `jobs.json` fields that are scheduler-managed and **volatile**:

- `last_status` / `last_error` get overwritten on every job run
- `last_delivery_error` is a transient post-mortem string, often empty
- `agent.log` grep is unbounded text scraping

After Sprint 1, `cron_history.sqlite` gives us a durable, append-only record of every cron execution with stable fields (`status`, `error_excerpt`, `duration_ms`, `exit_code`, `started_at`, `finished_at`). The DB is the correct source of truth.

### Telegram dispatch path

Two known dispatchers exist:

| Path | Use case |
| --- | --- |
| `self_improvement_v2/src/si_v2/adapters/telegram_adapter.py` | SI-v2 internal Telegram adapter (parameterized by bot/channel) |
| `hermes_error_alert.py` direct `deliver=telegram:<chat_id>` | Legacy error alert (legacy chat_id redacted from this report) |

Sprint 2 should **not** introduce a third Telegram dispatch path. The new alert tool will print alerts to stdout and (in a future runtime-deploy phase) call into a configured adapter. For now: `--dry-run` and `--log-only` only — no Telegram dispatch in this PR.

---

## `cron_history.sqlite` Live Schema (from `PRAGMA table_info`)

| Column | Type | Constraints | Use for alerting |
| --- | --- | --- | --- |
| `id` | INTEGER | PK, auto-increment | Cursor (`last_seen_id`) |
| `job_id` | TEXT | NOT NULL | Dedup key |
| `job_name` | TEXT | | Alert title |
| `no_agent` | INTEGER | 0/1 | Optional: distinguish script vs. agent jobs |
| `script_path` | TEXT | | Optional: source attribution |
| `delivery_mode` | TEXT | | Optional: alert destination hint |
| `started_at` | TEXT | NOT NULL, ISO 8601 UTC | Alert context |
| `finished_at` | TEXT | ISO 8601 UTC | Alert context |
| `duration_ms` | INTEGER | nullable | Optional: slow-run warning |
| `status` | TEXT | NOT NULL | **Primary alert trigger** |
| `exit_code` | INTEGER | nullable | Optional: classified detail |
| `timeout` | INTEGER | 0/1 flag | Optional: timeout-specific alert |
| `stdout_excerpt` | TEXT | redacted, truncated | Optional: alert body |
| `stderr_excerpt` | TEXT | redacted, truncated | Optional: alert body |
| `error_excerpt` | TEXT | redacted, truncated | **Dedup fingerprint** |
| `created_at` | TEXT | NOT NULL, ISO 8601 UTC | Alert ordering |

Indexes (already in place):

- `idx_cron_runs_job_time` on `(job_id, started_at)`
- `idx_cron_runs_status_time` on `(status, started_at)`

The second index is exactly what the alert reader will use to find non-`ok` rows quickly.

### Live DB snapshot at audit time

| Metric | Value |
| --- | --- |
| DB size | 57344 bytes |
| Total rows | 41 |
| Status distribution | `ok: 41` (no errors yet) |
| Unique `job_id` values | 23 |
| Oldest scheduler-written row | 2026-06-26T13:45:08 UTC (`heartbeat-writer`) |
| Latest row | 2026-06-26T14:02:53 UTC (`Hermes Session Metrics (5min)`) |

The DB has grown from 9 rows at Sprint 1 close to 41 rows now — Sprint 1 hook is actively writing.

---

## Implementation Plan

### New files

| Path | Purpose |
| --- | --- |
| `orchestrator/scripts/cron_history_alert.py` | Standalone reader + classifier + dedup + render |
| `orchestrator/tests/test_cron_history_alert.py` | Unit tests with `tmp_path` SQLite fixtures |
| `docs/runbooks/hermes-cron-history-alert.md` | Operator runbook (deploy, dry-run, manual replay) |

### Module structure (pure functions for testability)

```
cron_history_alert.py
  ├── open_db(path) -> sqlite3.Connection (read-only, URI mode)
  ├── discover_columns(conn, table='cron_runs') -> dict[name -> type]
  ├── fetch_new_rows(conn, after_id, status_filter) -> list[dict]
  ├── classify_row(row, known_statuses) -> "ok" | "error" | "warning" | "unknown"
  ├── build_dedup_key(row) -> str    (job_id + status + normalized error_excerpt hash)
  ├── load_state(path) -> dict
  ├── save_state(path, state) -> None   (atomic temp → rename)
  ├── filter_by_cooldown(alerts, state, cooldown_seconds) -> list[alert]
  ├── render_text(alerts) -> str
  └── render_json(alerts) -> str
main() — argparse, --dry-run default, exit codes 0/2
```

### CLI design

```bash
python3 orchestrator/scripts/cron_history_alert.py \
  --db /opt/data/profiles/orchestrator/state/cron_history.sqlite \
  --state /opt/data/profiles/orchestrator/state/cron_history_alert_state.json \
  --lookback-minutes 60 \
  --cooldown-seconds 1800 \
  --max-alerts 5 \
  --dry-run
```

| Option | Purpose | Default |
| --- | --- | --- |
| `--db PATH` | SQLite file | `/opt/data/profiles/orchestrator/state/cron_history.sqlite` |
| `--state PATH` | Dedup state file | `/opt/data/profiles/orchestrator/state/cron_history_alert_state.json` |
| `--lookback-minutes N` | Initial scan window when state is fresh | 60 |
| `--cooldown-seconds N` | Per dedup-key cooldown | 1800 (30 min) |
| `--max-alerts N` | Hard cap per run | 5 |
| `--dry-run` | Print alerts to stdout, no state write | default ON for safety |
| `--format json\|text` | Output format | text |
| `--commit-state` | Persist new state even outside dry-run | (off; future runtime) |

### Exit codes

| Code | Meaning |
| --- | --- |
| `0` | OK — no alerts, or alerts rendered in dry-run |
| `2` | DB unavailable, schema invalid, or state file corrupted |

### Status classification

- `status = 'ok'` → no alert
- `status = 'error'` → alert (severity: error)
- `status = 'failed'` → alert (severity: error)
- `status = 'timeout'` → alert (severity: error)
- `status` is null or empty → alert (severity: warning, "unknown status")
- any other unknown status → alert (severity: warning, "unknown status")

### Dedup key

```python
import hashlib
def build_dedup_key(row):
    fingerprint_material = (row.get("error_excerpt") or "").strip()
    h = hashlib.sha1(fingerprint_material.encode()).hexdigest()[:12]
    return f"{row['job_id']}|{row['status']}|{h}"
```

If `error_excerpt` is missing or empty: fall back to `f"{job_id}|{status}|{created_at_bucket_5min}"` so repeated identical failures still get one alert per bucket, not one alert per second.

### State file format

```json
{
  "last_seen_id": 41,
  "last_run_utc": "2026-06-26T14:04:48Z",
  "last_alerts": {
    "a47e1c73e102|error|abc123def456": "2026-06-26T13:30:00Z"
  }
}
```

Atomic write: write to `*.tmp` in the same directory, then `os.replace()` (POSIX atomic rename).

### Test cases (must all pass before PR)

| Test | Expected |
| --- | --- |
| Empty DB | no alerts, no crash |
| DB with only `ok` rows | no alerts |
| DB with one `error` row | exactly one alert |
| Same error row twice within cooldown | one alert (dedup) |
| Same error row after cooldown expiry | new alert |
| `--max-alerts=3` with 5 errors | only 3 alerts emitted |
| Missing optional `error_excerpt` column | no crash, falls back to timestamp bucket |
| DB file missing | exit 2, clean message |
| State file missing | initializes fresh state, no crash |
| State file corrupted | exit 2 with clear error |
| Concurrent DB writer | read-only SQLite (no lock contention) |

### Files NOT in this PR

- No runtime deploy (`/opt/data/profiles/orchestrator/scripts/cron_history_alert.py`)
- No `jobs.json` edits
- No Telegram dispatch
- No deletion of `hermes_error_alert.py` (separate explicit approval required)
- No restart

---

## Old `hermes_error_alert.py` — Deprecation Plan

The new tool supersedes the old one logically, but the runtime copy stays untouched in this PR. Two-step deprecation:

1. **Step 1 (this PR — L2 only)**: ship `cron_history_alert.py` + tests + runbook. Document `hermes_error_alert.py` as legacy in the runbook. Job stays paused.
2. **Step 2 (separate, after live dry-run proves it)**: in a dedicated runtime-deploy PR (with explicit approval), point the paused `Hermes Error-Alert (5min)` job at the new script. Old script is archived, not deleted. Only after at least one week of clean operation is the old script removed.

No code change in this PR touches the old script. The runbook documents the deprecation timeline.

---

## Acceptance Criteria for Sprint 2 PR

- [ ] `cron_history_alert.py` compiles, all unit tests pass.
- [ ] Live DB dry-run produces zero alerts (sanity: all `ok`).
- [ ] Cooldown and dedup logic tested with deterministic fixtures.
- [ ] `--max-alerts` cap enforced.
- [ ] No Telegram dispatch in this PR.
- [ ] No `jobs.json` edits.
- [ ] No runtime deploy, no restart, no secrets in diff.
- [ ] Runbook explains old-vs-new tool clearly.

---

## Risks

| Risk | Mitigation |
| --- | --- |
| Schema changes in future writer versions | `PRAGMA table_info` discovery, fail-soft on missing columns |
| SQLite locked by writer | read-only URI mode, no write lock contention |
| State file corrupted | exit 2 with clear message, do not silently reset (operator decides) |
| Telegram spam | not enabled in this PR; will require separate approval |
| Clock skew in dedup timestamps | use `started_at` not `created_at` for cooldown bucket |

---

## Next

After this PR is merged GREEN, Sprint 2 follow-ups:

1. Runtime deploy of `cron_history_alert.py` to `/opt/data/profiles/orchestrator/scripts/` (separate explicit approval).
2. Re-point the paused `Hermes Error-Alert (5min)` job at the new script (separate explicit approval).
3. Observe at least one real error alert in `cron_history.sqlite` end-to-end.
4. After one week of clean operation: archive `hermes_error_alert.py`.

None of these are in scope for this L2 PR.
