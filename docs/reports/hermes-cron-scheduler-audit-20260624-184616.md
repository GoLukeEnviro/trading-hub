# Hermes / Trading Hub Cron & Scheduler Audit

- **Audit date:** 2026-06-24T18:46:16+02:00 (`20260624-184616`)
- **Operation level:** L0 / L1 read-only — no mutations
- **Auditor:** independent read-only verification (Claude Code), distinct from the
  earlier Hermes-generated audits at `…-1822` / `…-1844`
- **Safety:** no crontab edits, no timer enable/disable, no service/container restart,
  no apply-tokens, no `dry_run=false`, no schedule changes, no secrets printed.

## Verdict: 🟡 YELLOW

The SI-v2 6h active-cycle **is installed, scheduled, executing, and producing valid
4-bot evidence** today — the primary automation goal is met. It is **not GREEN** because
the watchdog/assurance layer (`trading-guardian`) is pointed at an **orphaned, stale
12-job snapshot that lacks the SI-v2 job**, and the host carries **two divergent cron
registries** at the same logical path (a silent-loss footgun). It is **not RED**: nothing
is broken now, and the real registry *is* persisted on disk via bind mount.

## Executive Summary

Three initial read-only sweeps disagreed on whether the SI-v2 cycle is automated at all
(claims: "Hermes job", "no such job in registry", "manual / no cron logs"). Resolving the
contradiction by inspecting the **live in-container registry directly** (rather than
trusting a doc-only claim) shows the automation is real and healthy:

- Live job `64866012641a` **"si-v2-active-cycle (6h, log-only)"** — enabled, `status=ok`,
  `last_run=2026-06-24T12:17:57Z`, `next_run=2026-06-24T18:17:00Z`, runner
  `si_v2_active_cycle_cron.sh` (exists on disk).
- Its cadence matches the newest evidence artifact (`active_cycle_20260624T121756Z.json`);
  4 consecutive GREEN cycles; 56+ artifacts since 2026-06-15; all 4 bots authenticated;
  0 mutations; controller PAUSED / L3_REPOSITORY_ONLY.

The real defect is **operational trust, not the loop itself**: `trading-guardian` mounts
the orphaned host path `/opt/data/profiles/orchestrator/cron` (12 stale jobs, no SI-v2,
empty `next_run`) instead of the real registry at
`/opt/hermes-green/config/profiles/orchestrator/cron` (58 jobs, fresh). The two trees are
**separate inodes** — not a bind mount — so the duplicate/divergent state is genuine.

## Safety Scope

Inspected (read-only): crontabs (user/root/`/etc/cron.d`/`/etc/crontab`/`/etc/cron.*`),
systemd timers & units, Docker containers + `docker inspect` mounts, container-internal
files via `docker exec … cat` (parsing safe fields only), `jobs.json` registries, repo
git state/history, generated artifacts, logs. **Not mutated:** anything. `restore_cron_jobs.sh`
was only `grep`ed, never executed.

## Repo State

| field | value |
|---|---|
| path | `/home/hermes/projects/trading` |
| branch | `main` |
| HEAD | `0cf5a4d30a8dc2a3d11e942b2f573e142d3acd71` |
| origin/main | `0cf5a4d30a8dc2a3d11e942b2f573e142d3acd71` (== HEAD ✅) |
| worktree | clean (untracked files only); remote `origin` = `GoLukeEnviro/trading-hub` |

## Scheduler Inventory

### Primary: Hermes orchestrator internal scheduler (in `hermes-green` container)
- **Live registry:** in-container `/opt/data/profiles/orchestrator/cron/jobs.json`, bind
  mount `/opt/hermes-green/config -> /opt/data` → host
  `/opt/hermes-green/config/profiles/orchestrator/cron/jobs.json`.
- **58 jobs total**, file fresh (mtime `2026-06-24 18:36 +02:00`, 75 862 B); 44 jobs with
  `next_run ≥ 2026-06-20`.

| id | name | schedule | enabled | status | last_run | next_run | SI-v2 / fleet |
|---|---|---|---|---|---|---|---|
| `64866012641a` | si-v2-active-cycle (6h, log-only) | every 6h | ✅ | ok | 2026-06-24T12:17:57Z | 2026-06-24T18:17:00Z | **core SI-v2, 4-bot** |
| `607f1890215d` | cron-guardian | `0 */6 * * *` | ✅ | — | — | — | runs `restore_cron_jobs.sh` (no_agent) |
| `e9ce544673b1` | Fleet Report | interval (4h) | ✅ | — | — | — | 4-bot (LLM agent) |
| (others) | watchdogs/backups/monitors | various | mostly ✅ | — | — | — | mixed |

### Secondary layers (all acceptable / non-blocking)
- **Root crontab:** 4 VPS-backup/healthcheck jobs (restic, backup-restore-test). Non-trading. GREEN.
- **`/etc/cron.d`:** `qdrant-backup`, `e2scrub_all`, `sysstat` (system); `delete-v2-collection`
  = **expired one-shot** (2026-06-12, script is date-guarded) — safe to remove.
- **systemd timers:** `trading-cron-guardian.timer` & `trading-permfix.timer` **disabled**
  (superseded by the container guardian); `si-v2-continuous.timer` = **inactive template**
  (the Hermes internal job above is the live path; template awaits an activation ceremony).
- **User crontab (hermes):** **frozen since 2026-06-11** (permission-autopilot commented
  out; superseded by guardian).
- **Docker:** `hermes-green` (orchestrator, Up 2d), `trading-guardian` (Up 12d), 4 freqtrade
  bots (Up/healthy), `trading-shadowlock-1`, `trading-ai-hedge-fund-1`, etc. s6 supervision
  active inside `hermes-green`.
- **SI-v2 cron planner** (`self_improvement_v2/cron_defs/jobs.yaml`): **dry-run only**
  (generates plans, forces `enabled=False` / `dry_run_only=True`).

## Active SI-v2 Automation Chain

```
Hermes internal scheduler (hermes-green)
  -> job 64866012641a "si-v2-active-cycle (6h, log-only)", no_agent
  -> runner si_v2_active_cycle_cron.sh
  -> active_cycle_runner.py  (self_improvement_v2/src/si_v2/loop/)
  -> freqtrade_rest_readonly.py (JWT, read-only) over 4 bots
  -> telemetry_normalizer -> fleet_analyzer
  -> ShadowProposal generation (non-applying)
  -> evidence artifacts (reports/phase2/evidence/) + cycle_state + telemetry_history
```

Stage colors: Scheduler GREEN · Command/runner GREEN · cwd/env GREEN · data readers GREEN ·
4-bot telemetry GREEN · fleet analyzer GREEN · proposal generation GREEN · evidence/state
GREEN · **notification/log YELLOW** (no proactive alerting observed) ·
**monitoring (guardian) YELLOW** (watching orphan). "Success" here = valid 4-bot evidence
produced — verified ✅.

## Execution Proof

- Job `last_run 12:17:57Z` ⟷ artifact `active_cycle_20260624T121756Z.json` (timestamps agree).
- 4 consecutive GREEN cycles: `20260624T121756Z`, `20260624T061755Z`, `20260624T002122Z`,
  `20260623T181740Z`. 56+ evidence files since 2026-06-15.
- Telemetry history fresh; 209 closed trades across fleet; data completeness "complete".
- No tracebacks/exceptions in recent evidence; **mutation counters = 0**; controller PAUSED.
- System cron logs (`journalctl -u cron/crond`) carry no SI-v2 entries — **expected**, since
  the loop runs via the in-container orchestrator scheduler, not host cron.

## Fleet Coverage ✅

All four bots authenticated and present in every artifact (telemetry, historical trades,
shadow proposals). IDs **explicitly configured** in
`self_improvement_v2/config/freqtrade_bots.readonly.json` (no dynamic discovery):

`freqtrade-freqforge-1`, `freqtrade-freqforge-canary-1`,
`trading-freqtrade-regime-hybrid-1`, `trading-freqai-rebel-1`.

No stale 6-bot references in live code (only a historical mention in `ORCHESTRATOR_CHARTER.md`).

## Creation Provenance — STRONG

`active_cycle_runner.py` + cron plumbing introduced via PRs **#36** (`abbc621`),
**#208** (`61fe380`), **#211** (`3b72438`), **#213** (`706e94b`), **#341** (`f14b286`),
**#343** (`0cf5a4d`). Guardian/restore scripts predate (commit `ee075a1`, 2026-05-21) with
later safety hardening.

## Broken / Stale / Risky Items (prioritized)

| # | item | risk | evidence |
|---|---|---|---|
| 1 | `trading-guardian` monitors orphan `/opt/data/.../cron` (12 jobs, **no SI-v2**, empty `next_run`) instead of real registry | MED (monitoring blind spot) | `docker inspect trading-guardian` mount + parsed both files |
| 2 | Two divergent `/opt/.../cron` trees (separate inodes; 58 vs 12 jobs) | MED (silent-loss footgun on restore) | `stat` both paths: inode 1079225 vs 129767 |
| 3 | `restore_cron_jobs.sh` does `cp "$BACKUP" "$JOBS_DB"`; `$BACKUP` contents/trigger **unverified** | MED→RED if `$BACKUP` lacks `64866012641a` | grep of script; registry currently intact |
| 4 | 1 job in error (`fleet correlation refresh`) | LOW (signal-quality, not loop-blocking) | prior audit note |
| 5 | `trading-guardian` container-name false positive (`ai-hedge-fund-crypto` vs `trading-ai-hedge-fund-1`) | COSMETIC | prior audit note |
| 6 | Expired one-shot `/etc/cron.d/delete-v2-collection`; disabled systemd timers | LOW (housekeeping) | `ls /etc/cron.d`; `systemctl` |

## Failure Tree

- **F-durability/MONITORING (YELLOW):** guardian watches orphan, not real registry. Strong evidence.
- **F-persistence/DUPLICATE (YELLOW):** two divergent `/opt/.../cron` trees. Strong evidence.
- **F-restore/BACKUP (YELLOW→RED):** `restore_cron_jobs.sh` `$BACKUP` + trigger unverified. Weak evidence — needs 1 read.
- **F-job/FAILING (LOW):** 1 job error (fleet correlation refresh). Not loop-blocking.
- **F-guardian/FALSEPOS (COSMETIC):** container-name mismatch.
- **F-stale/ONE-SHOT (LOW):** expired `delete-v2-collection`.

## Final Verdict: 🟡 YELLOW

Automation is installed, executing, and producing valid 4-bot evidence, **but** the
monitoring/assurance layer is blind to the real registry and the host has a duplicate
source-of-truth — so the loop's *trustworthiness as operated* is not yet GREEN. Not RED.

## Single Next Repair Step (recommendation — not executed in this read-only engagement)

**Reconcile the host cron path so `trading-guardian` monitors the real 58-job registry,
eliminating the duplicate source-of-truth** in one move. Concretely (back-up-before-mutate,
gated on explicit future approval):

1. Verify `$BACKUP` in `…/orchestrator/scripts/restore_cron_jobs.sh` includes `64866012641a`;
   if not, regenerate the backup from the live registry first.
2. Replace orphan host `/opt/data/profiles/orchestrator/cron` with a **symlink →
   `/opt/hermes-green/config/profiles/orchestrator/cron`** (recommended option), so the
   guardian's existing mount resolves to live data with no container/compose change.
   Alternatives: repoint the guardian mount, or copy real→orphan (needs periodic resync).
3. Confirm `trading-guardian` now reports 58 jobs incl. `64866012641a` (read-only re-check).

## Suggested Backlog Issues

- **Fix guardian cron-source drift.** Goal: `trading-guardian` monitors the real registry.
  AC: `/guardian/cron/jobs.json` shows 58 jobs incl. si-v2; `diff` of both trees identical.
  Effort: **S**. Deps: none. Relation: enables trustworthy SI-v2 loop monitoring.
- **Harden `restore_cron_jobs.sh` backup integrity.** Goal: restore never drops si-v2.
  AC: `$BACKUP` contains `64866012641a`; restore is idempotent/non-destructive; test covers it.
  Effort: **S**. Deps: above. Relation: prevents silent SI-v2 automation loss.
- **Cleanup pass.** Goal: remove expired one-shot cron + reconcile/disable or document the
  inactive `si-v2-continuous`/`trading-cron-guardian`/`trading-permfix` timers. AC: no orphaned
  schedulers remain. Effort: **S**. Deps: none. Relation: reduces audit surface.
- **Resolve failing `fleet correlation refresh` job + guardian container-name false positive.**
  Goal: clean guardian signal. AC: job `status=ok`; no false container-down alerts. Effort: **M**.
  Deps: none. Relation: SI-v2 signal quality.
