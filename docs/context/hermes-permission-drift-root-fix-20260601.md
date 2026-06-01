# Permission Drift Root Fix — 2026-06-01

**Created:** 2026-06-01T14:22Z
**Status:** APPLIED, PENDING GIT COMMIT
**Scope:** Script source-of-truth, ownership contract, deploy pipeline, permission repair consolidation

---

## Root Cause

Recurring permission drift was NOT a VPS bug. It was caused by three structural problems:

1. **No single source of truth for scripts.** Scripts existed in two locations:
   - `/home/hermes/projects/trading/orchestrator/scripts/` (Git-tracked, 1337:1337)
   - `/opt/data/profiles/orchestrator/scripts/` (runtime, mixed ownership)
   
   Scripts were edited in the runtime dir without syncing back to Git. 6 scripts existed ONLY in the runtime dir (CRON_ONLY — not in Git).

2. **Competing permission repair.** Two independent components silently modified file ownership:
   - `ghostbuster.py` (Hermes cron, every 15 min): `find -chgrp -chmod` on root:root files
   - `trading-guardian` container (every 5 min): scoped per-file permission repair
   
   Both changed ownership of the same files, creating race conditions and hidden state changes.

3. **No deployment pipeline.** Script changes were applied ad-hoc via `cp` without ownership normalization or verification. The deploy script did not exist.

## Why VPS Reinstall Would NOT Fix This

A reinstall would reproduce the exact same problem because:
- The Hermes gateway process runs as root and writes `jobs.json` as root:root
- The cron scheduler runs as UID 10000 and needs readable permissions
- Without a single source of truth and deploy pipeline, scripts would again diverge
- Without an ownership contract, repair loops would again compete

## What Was Changed

### Phase 3: Script Sync (7 CRON_ONLY + 4 RUNTIME_WINS + 2 MERGE + 4 PROJECT_WINS deployed)

| Action | Scripts | Count |
|--------|---------|-------|
| CRON_ONLY copied to Git | config_diff_detector.py, critical_event_watchdog.py, fleet_risk_auto_params.py, hermes_standby_monitor.py, log_rotation.py, morning_brief.py, riskguard_service.py | 7 |
| RUNTIME_WINS synced to Git | fleet_auto_repair.py, fleet_correlation_refresh.sh, heartbeat_writer.py, memory_backfill.py | 4 |
| MERGE (cron fix + project paths) | ghostbuster.py (Honcho cleanup), system_optimizer.py (cursor fix) | 2 |
| PROJECT_WINS deployed to runtime | daily_heartbeat.py, mem0_watchdog.py, smart_heartbeat.py, restore_cron_jobs.sh | 4 |

### Phase 4: Permission Repair Consolidation

| Change | What | Effect |
|--------|------|--------|
| ghostbuster.py | `check_permission_drift()` changed from AUTO-FIX to REPORT-ONLY | No more competing ownership writes |
| external_cron_guardian.sh (cron dir) | Synced to project tree version (repair disabled) | Cron dir copy no longer runs repair |

**Single repair source: trading-guardian container only** (baked-in, scoped to explicit files).

### Phase 6: Ownership Normalization

All 30 runtime scripts set to hermes:hermes (10000:10000) mode 711.
Previous state: mix of root:root, root:hermes, 1337:1337, hermes:hermes with various modes.

### Phase 7: Deploy Script Created

`orchestrator/scripts/deploy_cron_scripts.sh` — single deploy command that:
- Fails if CRON_ONLY scripts exist (enforces Git-tracking discipline)
- Only overwrites existing files (never creates)
- Sets correct ownership (10000:10000 711)
- Verifies zero drift after deploy

## What Must NEVER Be Edited Directly Again

| Path | Rule |
|------|------|
| `/opt/data/profiles/orchestrator/scripts/*` | NEVER edit directly. Deploy from Git via `deploy_cron_scripts.sh`. |
| `/opt/data/profiles/orchestrator/cron/jobs.json` | NEVER edit manually. Use `cronjob()` tool only. |
| `/home/hermes/projects/trading/orchestrator/scripts/*` | Edit here (Git), then deploy. |
| State files in `orchestrator/state/` | Only via their canonical writer scripts. |

## How Deployment Works

```
1. Edit script in /home/hermes/projects/trading/orchestrator/scripts/
2. Test: python3 -c "import ast; ast.parse(open('script.py').read())"
3. Deploy: bash orchestrator/scripts/deploy_cron_scripts.sh
4. Verify: bash orchestrator/scripts/deploy_cron_scripts.sh --check
```

## Ownership Matrix

| Location | Owner | Group | Mode | Writer |
|----------|-------|-------|------|--------|
| Project scripts (Git) | 1337 | 1337 | 775 | Git/agent |
| Runtime scripts (cron) | 10000 | 10000 | 711 | deploy script only |
| jobs.json | root | 10000 | 0640 | Hermes gateway (root writes, guardian fixes) |
| State files | 1337 or root | 1337 or 10000 | 664 | Writer scripts |
| Logs | mixed | hermes (10000) | 664 | All cron scripts |

Full contract: `docs/context/hermes-runtime-ownership-contract-20260601.md`

## Validation Evidence

| Check | Result |
|-------|--------|
| Python syntax (all .py in cron dir) | 0 errors |
| Bash syntax (all .sh in cron dir) | 0 errors |
| All 29 active scripts in Git | PASS |
| All 29 active scripts in runtime | PASS |
| Zero drift after deploy | PASS |
| drawdown_guard writes state | EXIT 0 |
| container_watchdog persists | EXIT 0 |
| signal-heartbeat reads correct source | EXIT 0 |
| smart-heartbeat reads correct source | EXIT 0 |
| All 4 trading bots dry_run=True | PASS |
| No secrets printed | PASS |

## Rollback Plan

1. `cd /home/hermes/projects/trading`
2. `git checkout -- orchestrator/scripts/` (restores pre-fix versions)
3. `bash orchestrator/scripts/deploy_cron_scripts.sh` (re-deploys to runtime)
4. All scripts return to their Git-committed state

## Suggested Git Commit

```
chore(hermes): establish runtime script source-of-truth and ownership contract

- Sync 7 CRON_ONLY scripts from runtime to Git tracking
- Merge 4 runtime-improved scripts (heartbeat_writer, memory_backfill, etc.)
- Merge ghostbuster Honcho cleanup + system_optimizer cursor fix
- Deploy corrected green-* container names to all runtime scripts
- Disable ghostbuster.py permission repair (REPORT-ONLY, guardian handles)
- Normalize all runtime scripts to hermes:hermes 711
- Add deploy_cron_scripts.sh as single deploy pipeline
- Add runtime ownership contract documentation
```

Files to stage:
- `orchestrator/scripts/config_diff_detector.py` (new)
- `orchestrator/scripts/critical_event_watchdog.py` (new)
- `orchestrator/scripts/deploy_cron_scripts.sh` (new)
- `orchestrator/scripts/fleet_risk_auto_params.py` (new)
- `orchestrator/scripts/hermes_standby_monitor.py` (new)
- `orchestrator/scripts/log_rotation.py` (new)
- `orchestrator/scripts/morning_brief.py` (new)
- `orchestrator/scripts/riskguard_service.py` (new)
- `orchestrator/scripts/daily_heartbeat.py` (modified)
- `orchestrator/scripts/drawdown_guard.py` (modified)
- `orchestrator/scripts/fleet_auto_repair.py` (modified)
- `orchestrator/scripts/fleet_correlation_refresh.sh` (modified)
- `orchestrator/scripts/ghostbuster.py` (modified)
- `orchestrator/scripts/heartbeat_writer.py` (modified)
- `orchestrator/scripts/mem0_watchdog.py` (modified)
- `orchestrator/scripts/memory_backfill.py` (modified)
- `orchestrator/scripts/system_optimizer.py` (modified)
- `orchestrator/guardian/scripts/external_cron_guardian.sh` (modified)
- `docs/context/hermes-runtime-ownership-contract-20260601.md` (new)
- `docs/context/hermes-permission-drift-root-fix-20260601.md` (new)
