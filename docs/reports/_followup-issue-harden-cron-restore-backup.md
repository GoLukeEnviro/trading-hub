# Follow-up Issue — Harden Hermes cron restore backup and restore guard

**Severity:** P1 (P0 if the live registry ever shows instability / job_count drop)
**Status:** Prepared (not auto-opened on GitHub — await Luke's go-ahead)
**Origin:** `docs/reports/guardian-cron-registry-source-of-truth-fix-20260624-224841.md`

## Problem

The Hermes cron scheduler registry (`/opt/hermes-green/config/profiles/orchestrator/cron/jobs.json`,
58 jobs, including SI-v2 `64866012641a`) can be overwritten by a **stale restore path**:

- Scheduled job **`607f1890215d`** ("cron-guardian", `0 */6 * * *`) runs `restore_cron_jobs.sh`.
- `restore_cron_jobs.sh` writes to `JOBS_DB=/opt/data/profiles/orchestrator/cron/jobs.json`, which
  **inside hermes-green** resolves to the **live canonical registry** (bind `/opt/hermes-green/config`→`/opt/data`).
- Its only guard is `if CURRENT_COUNT >= 10: skip`. When the live registry has ≥10 jobs it is a no-op
  (currently dormant: 58 ≥ 10).
- If the live registry ever drops below 10 jobs (corruption, partial write, race, manual edit), the
  guard passes and the script does `cp <backup> <live>` with the **stale 11-job backup**
  (`orchestrator/config/cron_jobs_backup.json`, **no SI-v2**, mtime 2026-06-05).

**Impact:** live registry reduced 58 → 11, **SI-v2 job `64866012641a` deleted**, scheduler loses the
SI-v2 active cycle until manually restored.

Note: the Guardian `:ro` fix (PR `fix/guardian-cron-registry-source-of-truth`) does **not** mitigate
this — `restore_cron_jobs.sh` writes through hermes-green's own filesystem, not the Guardian mount.

## Acceptance criteria

- [ ] Backup is regenerated from the current canonical registry (or replaced) **without committing secrets**.
- [ ] Restore is **non-destructive / merge-safe** — it must never `cp`-overwrite the whole registry wholesale.
- [ ] Restore **cannot remove SI-v2 job `64866012641a`** (presence asserted pre/post).
- [ ] Restore **cannot reduce the canonical registry from 58 to stale 11/12 jobs**.
- [ ] A validation/dry-run proves SI-v2 survives a restore preflight (e.g., assert canonical job set
      is a superset of backup, or block restore when it would remove an enabled job).
- [ ] The `CURRENT_COUNT >= 10` heuristic is replaced with a content-aware guard.

## Suggested approach (for the follow-up PR)

1. Make `restore_cron_jobs.sh` **merge-safe**: only add jobs missing from the live registry; never
   delete or shrink it. Assert SI-v2 present before and after.
2. Regenerate `cron_jobs_backup.json` from the canonical 58-job registry (sanity-check no secrets).
3. Add a unit test simulating a `<10 job` live registry and proving restore does not drop SI-v2.
4. Re-evaluate whether the "cron-guardian" scheduled restore job is still needed at all.

## Out of scope for this follow-up

- Container-name false positive (`ai-hedge-fund-crypto` vs `trading-ai-hedge-fund-1`) — separate PR.
