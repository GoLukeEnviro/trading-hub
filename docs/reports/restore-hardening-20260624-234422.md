# Harden Hermes cron restore backup and restore guard (Issue #345)

**Date (UTC):** 2026-06-24T23:44:22Z  •  **Operation Level:** L2  •  **Author:** Claude Code (Claudio)
**Branch:** `fix/harden-cron-restore-345`  •  **Issue:** [#345](https://github.com/GoLukeEnviro/trading-hub/issues/345)

## Verdict

- **PR objective (restore hardening): GREEN** — the scheduled `restore_cron_jobs.sh` can no longer
  shrink the live registry or delete SI-v2; a stale backup without SI-v2 is refused.
- **Overall scheduler/restore safety: GREEN** (was YELLOW after PR #344) — the last open P1/P0 vector
  is eliminated with proof. Guardian already read-only (#344).

## Summary

The scheduled job `607f1890215d` ("cron-guardian", `0 */6 * * *`) ran `restore_cron_jobs.sh` every 6 h.
Its old logic did a wholesale `cp backup -> live` whenever `CURRENT_COUNT < 10`. With a **stale 11-job
backup lacking SI-v2**, any live-registry dip below 10 jobs would have overwritten the live 58-job
registry, deleting SI-v2 (`64866012641a`) — a 58→11 destruction. `cron_restore.log` proved it ran
actively (8 runs 23.–24.06., always „Skip" while count ≥ 10).

This change replaces the wholesale `cp` with a **merge-safe, content-aware** restore and a
**backup-validity gate**, and regenerates the backup from the canonical registry. The vector is now
impossible by construction.

## What changed

| File | Change |
|---|---|
| `orchestrator/scripts/restore_cron_jobs.py` (new) | Self-contained merge-safe restore: `plan_merge()` with backup-validity gate (refuse without `64866012641a`), add-only merge, no-shrink guard, SI-v2 invariant; `main()` with env-overridable paths + `--dry-run` + atomic write + post-write re-assert. |
| `orchestrator/scripts/restore_cron_jobs.sh` | Rewritten to a thin wrapper (`exec python3 …/restore_cron_jobs.py "$@"`). Scheduler job reference unchanged → **no cron-registry mutation**. |
| `orchestrator/tests/test_restore_cron_jobs.py` (new) | 12 unit + integration tests covering all mandatory cases via `tmp_path`/env overrides (no live paths). |
| `orchestrator/config/cron_jobs_backup.json` (runtime, **gitignored**) | Regenerated from the canonical 58-job registry; old 11-job backup kept as `.bak-20260624T234224Z`. **Not committed.** |

Runtime deploy (restart-free): `restore_cron_jobs.py` + `.sh` copied to
`/opt/hermes-green/config/profiles/orchestrator/scripts/` (where the scheduler reads them inside
hermes-green). Verified content-identical to repo, owner `hermes:hermes`, mode 755.

## Safety (no-go list respected)

- No `hermes-green` restart, no Freqtrade bot restart, no image rebuild, no SI-v2 schedule change.
- No live restore run (validated via `--dry-run` + temp copies only).
- No apply-token, no `dry_run=false`, no strategy/config mutation.
- No `git add .`; the backup (gitignored) and its `.bak` were **not** committed.

## Proof — the seven required points

1. **Old backup was stale/invalid:** 11 jobs, `64866012641a` absent (`.bak-20260624T234224Z` preserved).
2. **New backup is current + SI-v2-safe:** 58 jobs, contains `64866012641a` and `si-v2-active-cycle`,
   valid JSON, byte-for-byte job set equal to the canonical registry; secret-scan: no real secret keys,
   no token-like values.
3. **No secrets committed:** backup is gitignored (`.gitignore:80`); diff secret-scan clean; only the
   `.py`, `.sh`, test and this report are committed.
4. **Restore refuses backups without `64866012641a`:** unit tests `test_plan_refuses_backup_without_protected_id`,
   `test_invalid_backup_does_not_add_stale_jobs`, `test_invalid_backup_broken_live_refuses`,
   `test_both_missing_si_v2_refuses`, `test_main_no_write_on_invalid_backup` all PASS; runtime evidence
   against the real old backup → `REFUSE: invalid backup (no protected job); no write`, live unchanged.
5. **Restore cannot shrink the live registry:** add-only merge + `NO_SHRINK_VIOLATION` guard;
   `test_valid_backup_broken_live_merges_no_shrink` PASS; `len(planned) >= len(live)` always.
6. **Restore adds no stale backup-only jobs from the old 11-job backup:** the backup-validity gate refuses
   the whole stale backup before any add; runtime test #2 → 0 stale jobs added, live stayed 58 + SI-v2.
7. **58→11 impossible:** by construction (no wholesale overwrite; add-only; validity gate; no-shrink).

## Test results

`orchestrator/tests/test_restore_cron_jobs.py` — **12 passed** (pytest 9.1.1, py3.12). Cases:
invalid-backup refuse (healthy + broken live), no stale-job add, valid-backup merge no-shrink,
SI-v2 restore-when-missing, both-missing refuse, dry-run never writes, healthy no-op, plus `main()`
integration tests via env/tmp_path.

(`bash -n restore_cron_jobs.sh` OK; module `ast` parse OK; diff secret-scan clean.)

## Runtime evidence (deployed script, no live mutation)

```
(1) Real-state dry-run (live 58 + regenerated backup 58):
    "OK: already complete (58 jobs); skip"   -> live copy unchanged (58)
(2) Deployed script vs. live + OLD stale 11-job backup:
    "REFUSE: invalid backup (no protected job); no write"
    -> live copy unchanged: 58 jobs, si_v2_present=True, 0 stale jobs added
(3) Canonical LIVE registry structurally unchanged after deploy+regen:
    valid_json=True job_count=58 si_v2_id=True si_v2_name=True (owner hermes:hermes mode 600)
```

## Deploy order followed (regen BEFORE script deploy)

Implement → unit tests (pass) → secret-scan → `.bak` old backup → regenerate from canonical →
**verify** (58 + SI-v2 + name + secret-free; STOP-on-fail gate) → deploy `.py`+`.sh` to canonical
scripts dir → verify content/perms → dry-run/runtime evidence. No step failed.

## Rollback

Revert the three repo files; copy the pre-change `restore_cron_jobs.sh` (or revert the wrapper) back
to `/opt/hermes-green/config/profiles/orchestrator/scripts/`; restore the old backup from
`cron_jobs_backup.json.bak-20260624T234224Z`. No container restart required (scheduler reads the
script fresh each run).

## Remaining (out of scope here)

- Container-name false positive (`ai-hedge-fund-crypto` vs `trading-ai-hedge-fund-1`) — separate PR + image rebuild.
- The stale orphan host dirs (`/opt/data/profiles/orchestrator/{cron,scripts}`) are not read by the
  scheduler (it reads the canonical path via the `/opt/data` bind inside hermes-green) — separate cleanup.

## Next step

Independent review of this PR (you/Grok, as for #344) → merge → close #345.
