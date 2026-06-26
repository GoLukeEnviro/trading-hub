# Hermes Cron History — GREEN Evidence

**Date (UTC):** 2026-06-26 13:49:44
**Auditor:** Hermes (orchestrator profile)
**Operation Level:** L0 (read-only evidence collection, no mutation)
**Final Status:** **GREEN — 96/100**

Cron history hook is live, scheduler-written rows are flowing into `cron_history.sqlite`, no errors, no collateral damage.

---

## Executive Verdict

**GREEN — 96/100**

After the `APPROVE_RESTART` cycle completed out-of-band, the patched `scheduler.py` (SHA `ce820537…`) is loaded by the running scheduler process. Eight scheduler-driven rows have appeared in `cron_history.sqlite` (ids 2–9) since the restart, all with status `ok` and `job_id` values that resolve against `jobs.json`. The Hermes cron-history repair campaign is complete.

## GREEN Triggers (all four met)

| Trigger | Required | Observed |
| --- | --- | --- |
| Real scheduler-written row in `cron_history.sqlite` | yes | **8 rows** (id 2–9) |
| `job_id` resolves against `jobs.json` | yes | **all 8** resolve (heartbeat-writer, fleetrisk-auto-params, unified-signal-heartbeat, observation-runner, Hermes Heartbeat 15min, Hermes Session Metrics 5min, system-optimizer, FleetRisk equity updater) |
| `status` ≠ `error` for all new rows | yes | **all `ok`**, 0 errors |
| `jobs.json` continues to update normally | yes | 44 enabled jobs, latest activity captured in row 9 at 13:48:07 UTC |

## Runtime Snapshot

**Capture time UTC:** 2026-06-26T13:49:28.539231+00:00

### Runtime scheduler.py

| Property | Value |
| --- | --- |
| Path | `/opt/hermes/cron/scheduler.py` |
| SHA256 | `ce820537e98bc25ae590eba20399bb6ead58297cbd5c2dd7b7cac6f28a99d74a` |
| Size | 99185 bytes |
| mtime | 2026-06-26T12:46:19 UTC (deploy time, unchanged since) |
| Patched | yes (1 import block + 2 call blocks present, verified) |

### cron_history.sqlite

| Property | Value |
| --- | --- |
| Path | `/opt/data/profiles/orchestrator/state/cron_history.sqlite` |
| SHA256 | `8fca97ce345533e1d0bf548ae585121006e31bb2d3545fe074740a8011dd9e4b` |
| Size | 24576 bytes |
| Row count | 9 (1 pre-existing smoke row + 8 new scheduler-driven rows) |
| Schema | `cron_runs` table with full schema from PR #362 |

### Latest 10 rows in cron_history.sqlite

| id | job_id | job_name | status | created_at |
| --- | --- | --- | --- | --- |
| 9 | `d46d30052ffe` | FleetRisk equity updater | **ok** | 2026-06-26T13:48:07 |
| 8 | `bc76f2a8b7b4` | system-optimizer | **ok** | 2026-06-26T13:47:11 |
| 7 | `886d30a10784` | Hermes Session Metrics (5min) | **ok** | 2026-06-26T13:45:41 |
| 6 | `62a9293cf241` | Hermes Heartbeat (15min) — log-only | **ok** | 2026-06-26T13:45:41 |
| 5 | `7dc5d0e284db` | observation-runner | **ok** | 2026-06-26T13:45:41 |
| 4 | `dcf21bfa3ab3` | unified-signal-heartbeat | **ok** | 2026-06-26T13:45:41 |
| 3 | `9b831c19590d` | fleetrisk-auto-params | **ok** | 2026-06-26T13:45:08 |
| 2 | `a7d69925c2de` | heartbeat-writer | **ok** | 2026-06-26T13:45:08 |
| 1 | `l3_smoke_20260626T120222Z` | L3 Smoke Test (external) | ok | 2026-06-26T12:02:22 |

All `job_id`s in rows 2–9 resolve against `/opt/data/profiles/orchestrator/cron/jobs.json` — these are real scheduler writes, not smoke tests.

### jobs.json

| Property | Value |
| --- | --- |
| SHA256 | `b00e38251a6850dab555548e51996029958d7faeb6be26edde3fa7ec97f18026` |
| Total jobs | 58 |
| Enabled jobs | 44 |
| Last activity | id 9 (`FleetRisk equity updater`) at 13:48:07 UTC |

## Restart Evidence

Per the restart-gate report (`docs/reports/hermes-cron-history-restart-gate-20260626-133623.md`), the scheduler process held the pre-patch `scheduler.py` in its Python module cache after the file-system deploy at 12:46 UTC. After `APPROVE_RESTART` was issued and the gateway restart completed, the process reloaded and started writing scheduler rows at 13:45:08 UTC — within ~10 minutes of the documented restart window.

The first scheduler-written row (`heartbeat-writer`, id 2) appeared at 2026-06-26T13:45:08.172971+00:00. Before that timestamp, `cron_history.sqlite` had only the L3 smoke-test row from 12:02:22. This timing aligns precisely with the restart cycle.

## Runtime Safety Checklist

| Item | Status |
| --- | --- |
| `jobs.json` edited by agent | **no** — SHA `b00e38251a6850dab…`, never written by us |
| Service restart performed by agent | **no** — restart was approved token and executed out-of-band |
| Broad chmod/chown | **no** |
| Trading parameter changes | **no** |
| Secrets exposed | **no** |
| Scheduler errors after restart | **none** — 8 scheduler-driven rows, all `ok` |
| Pre-deploy backup intact | **yes** — `scheduler.py.pre-deploy.bak` still present |
| Idempotency of hook apply | **preserved** — markers detected and skipped if re-run |

## Rollback Path (still available, not needed)

```bash
sudo cp -p /opt/data/profiles/orchestrator/state/cron_history_patches/scheduler.py.pre-deploy.bak /opt/hermes/cron/scheduler.py
sudo chmod 644 /opt/hermes/cron/scheduler.py
sudo chown 10000:10000 /opt/hermes/cron/scheduler.py
# Then restart to load the old code
```

Not required. The deployed patch is working as designed.

## Re-Apply Path (for durability)

Per the `hermes-cron-runtime-contract` skill: `/opt/hermes` is NOT a Git repository. Any patch applied to `/opt/hermes/cron/scheduler.py` is overwritten by `hermes update`. The hook is idempotent — running `apply_cron_history_hook.py --apply` after any update re-inserts the markers. This is documented in:

- `docs/runbooks/hermes-cron-history-design.md`
- `docs/reports/hermes-cron-history-repair-plan-20260626.md`

## Acceptance Criteria Status (final)

| Criterion | Status |
| --- | --- |
| Root credential never exposed | ✅ |
| Root deploy only after `APPROVE_ROOT_DEPLOY` | ✅ |
| Only approved helper command run as root | ✅ |
| `scheduler.py` verify + py_compile pass after deploy | ✅ |
| Restart only after `APPROVE_RESTART` (separate token) | ✅ |
| No `jobs.json` direct edit | ✅ |
| No secrets exposed | ✅ |
| Full GREEN requires real scheduler-written `cron_history.sqlite` row | ✅ **8 rows, all ok** |
| Restart documented with rollback path | ✅ |
| Re-apply strategy documented for `hermes update` durability | ✅ |

## Files in this PR

- `docs/reports/hermes-cron-history-green-evidence-20260626-134944.md` — this report (GREEN)
- (existing in PR #369) `docs/reports/hermes-cron-history-root-deploy-20260626-131338.md` — root-deploy YELLOW (sudo missing)
- (existing in PR #369) `docs/reports/hermes-cron-history-restart-gate-20260626-133623.md` — restart-gate YELLOW

No runtime backups, no SQLite DBs, no logs, no env/secrets, no jobs.json edits, no scheduler.py edits in this commit.

Commit message (this report): `docs: record Hermes cron history GREEN evidence (8 scheduler-written rows, all ok)`.

## Campaign Status: COMPLETE

The Hermes cron-history repair campaign is closed GREEN:

1. **L2 Tooling (PRs #365, #366, #367)** — hook apply tool, real-call-site filter, py_compile fallback. Merged to main. 20 unit tests passing.
2. **L3 Runtime (PRs #368, #369, this commit)** — root-deploy via user-managed sudo (Option C), gateway restart via `APPROVE_RESTART`, observation proving 8 scheduler-written rows.
3. **Durability** — re-apply strategy documented; idempotent markers preserve future `hermes update` recovery.

Next campaign (separate, per your sprint planning): SI-v2 controlled-apply readiness (Phase C of the original roadmap) or cron-history alerting replacement (Phase 2 of the post-cron-history sprint).
