# max_open_trades v4.8 — Single Source of Truth

Date: 2026-05-25 UTC

## Scope
- Enforce single-writer discipline for `max_open_trades`
- Fix false recent-window matches in safety checks
- Add simple floor watchdog
- Verify stable values across repeated optimizer runs

## Root cause
The structural bug was not only competing jobs. The decisive re-lock cause was a broken SQLite recent-window predicate inside `system_optimizer.py`.

Old logic compared `strftime('%s', close_date)` as text against `strftime('%s', 'now') - 86400`. SQLite treated that comparison truthily for stale rows, so trades from previous days/weeks were incorrectly counted as "recent". That false 24h sample re-triggered performance quarantine and pushed `Regime-Hybrid` back to `max_open_trades=0`.

## Audit — all max_open_trades touchpoints

### Actual write paths
1. `orchestrator/scripts/system_optimizer.py`
   - `_set_max_open_trades(...)` — new single internal write path
   - `quarantine_bot(...)` -> writes `max_open_trades=0`
   - `restore_bot_limit(...)` -> writes baseline restore values
   - `recovery_preflight()` / `restore_fleet_limits()` call restore path only
   - drawdown/daily-loss/per-strategy/consecutive-loss protections now all route through the same writer helpers

### Read/report-only paths
2. `/opt/data/profiles/orchestrator/cron/jobs.json`
   - `Fleet Report (alle 4h)` prompt updated to explicit read-only / never write `max_open_trades`
   - `System Health Check (alle 8h)` prompt updated to explicit read-only / never write `max_open_trades`
3. `orchestrator/scripts/trading_pipeline.py`
   - writes only `primo_signal_state.json` state targets
   - does not read or write bot config `max_open_trades`
4. `orchestrator/scripts/drawdown_guard.py`
   - reads `dry_run` / `max_open_trades` for reporting only
5. `orchestrator/trading_autopilot.py`
   - reads `max_open_trades` for monitoring only
6. Active bot config files
   - `freqforge/config/config_freqforge_dryrun.json`
   - `freqforge-canary/config/config_canary_dryrun.json`
   - `freqtrade/bots/regime-hybrid/config/config_regime_hybrid_dryrun.json`
   - `freqai-rebel:/freqtrade/user_data/config.json`
   - values only; not autonomous writers

## Changes applied
1. `system_optimizer.py` bumped to v4.8.
2. Introduced `_set_max_open_trades(...)` as the internal single write primitive.
3. Refactored quarantine/restore paths to use the same writer.
4. Consecutive-loss pause no longer writes configs inline; it now calls `quarantine_bot(...)`.
5. Added hard `SAFETY_MAX_AGE_SECONDS = 86400`.
6. Fixed recent-window SQL with integer casting:
   - `CAST(strftime('%s', close_date) AS INTEGER) >= CAST(strftime('%s', 'now') AS INTEGER) - 86400`
7. Applied the 86400-second filter to:
   - `get_bot_recent_stats(...)`
   - `get_bot_24h_pnl(...)`
   - `get_fleet_recent_trades(...)`
8. Added `orchestrator/scripts/mot_floor_watchdog.py`
   - simple floor check only
   - no direct config writes
   - delegates restores through `system_optimizer.restore_bot_limit(...)`
9. Created optional manual lock file:
   - `orchestrator/state/manual_max_open_trades_locks.json`
10. Synced updated scripts to cron runtime directory:
   - `/opt/data/profiles/orchestrator/scripts/`
11. Added cron job:
   - `mot-floor-watchdog` (`ca4933892906`)
   - schedule `*/10 * * * *`
   - `no_agent=true`

## Backups
- Backup bucket: `/home/hermes/projects/trading/orchestrator/backups/max-open-trades-v4.8-20260525T103719Z`
- Automatic system-optimizer config/state backups also created during writes.

## Verification
### Immediate restore state
- FreqForge = 5
- Canary = 3
- Regime-Hybrid = 5
- Rebel = 0
- All four remain `dry_run=true`

### Triple optimizer run
Verification log:
- `/home/hermes/projects/trading/orchestrator/logs/max_open_trades_v48_verify.log`

Observed after the final fix:
- Run 1: `FreqForge=5`, `Canary=3`, `Regime-Hybrid=5`, `Rebel=0`
- Run 2: unchanged
- Run 3: unchanged

Safety checks now report `0t in 24h` for stale bots instead of falsely reusing old historical trades.

### Floor watchdog
Manual run output:
- `OK FreqForge=5, Regime-Hybrid=5, Canary=3, Rebel=0`

## Residual notes
- `ghostbuster` cron remains in error; unrelated to this fix.
- Fleet performance totals still show lifetime stats in the summary section; only safety/quarantine logic was narrowed to strict 24h windows.
