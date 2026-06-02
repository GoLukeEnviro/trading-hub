# P1: jobs.json Status Persistenz — Investigation 2026-06-01

**Status:** RESOLVED-AS-OBSERVABILITY_NOT_BUG
**Created:** 2026-06-01T16:11Z
**Originally flagged as:** "last_run_at=None, last_status=None" (stale)
**Actual finding:** Fields ARE updating correctly; "stale" appearance was a sampling artifact

---

## Background

During the post-lockdown audit, a brief check of `jobs.json` showed what appeared to be stale status fields:

```text
portfolio-rebalancer  last_run=2026-06-01T06:00:56  last_status=error
Fleet Report         last_run=2026-06-01T14:32:24  last_status=ok
72h Research Monitor last_run=2026-05-24T22:00:12  last_status=ok  (paused)
```

The `72h Research Fleet Monitor` looked stale (May 24 → June 1) but it is correctly marked `paused` in the job name itself.

## Investigation Result

Full scan of all 37 jobs:

| Field | Value |
|-------|-------|
| Total jobs | 37 |
| Null status (last_run+last_status both None) | **0** |
| Jobs with current errors | 5 (see below) |
| Jobs paused/completed (legitimately old) | ~3 |

The 5 currently-erroring jobs are **legitimate runtime errors**, not stale-state bugs:

| Job | Error | Root Cause |
|-----|-------|------------|
| portfolio-rebalancer | Exit code 1 | `datetime.utcnow()` DeprecationWarning (Python 3.12+) |
| ghostbuster | Exit code 1, Traceback line 403 | Permission drift repair now disabled (intentional — Phase 4) |
| signal-heartbeat | Exit code 23 | Signal age threshold check — may be flagging benign staleness |
| smart-heartbeat | Timeout after 120s | Network/API call hangs; needs investigation |
| daily-backup | Exit code 1, backup_rotation.py line 99 | Independent bug in backup rotation |

## Conclusion

The `jobs.json` status persistence is **working correctly**. Each of the 5 error jobs has a populated `last_error` field with full stderr. Reports and monitoring can trust this data.

The P1 follow-up is **not** about status persistence — it is about the **5 actual runtime errors** above. Each needs its own triage:

1. `portfolio-rebalancer` — replace `datetime.utcnow()` with `datetime.now(timezone.utc)` (trivial)
2. `ghostbuster` — exit 1 was always present; with permission repair disabled, the script may now report findings differently. Verify the new report-only behavior doesn't trigger an exit-1 on the always-failing path.
3. `signal-heartbeat` exit 23 — investigate threshold logic
4. `smart-heartbeat` timeout — add timeout/circuit-breaker to REST calls
5. `daily-backup` line 99 — independent bug, separate ticket

## Original P1 (now rejected)

~~P1: Hermes Scheduler / jobs.json status persistence klären.~~
~~Problem: last_run_at, last_status, last_error bleiben null/stale.~~
~~Ziel: Reports dürfen nicht "grün" oder "stale" aus falschen Statusfeldern ableiten.~~

**Status: REJECTED.** The status fields persist correctly. The original concern was based on a partial sample that included a paused job. The 5 error jobs above are real but separate issues.

## Action Items

| Priority | Item | Owner |
|----------|------|-------|
| P2 | Fix `datetime.utcnow()` in portfolio_rebalancer.py:69 | TBD |
| P2 | Verify ghostbuster.py exit 1 is acceptable (report-only, expected) | TBD |
| P2 | Investigate signal-heartbeat exit 23 | TBD |
| P2 | Add timeout to smart-heartbeat REST calls | TBD |
| P2 | Investigate backup_rotation.py:99 failure | TBD |
