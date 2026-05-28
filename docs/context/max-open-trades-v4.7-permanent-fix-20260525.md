# max_open_trades-Block v4.7 Permanent Fix — 2026-05-25

## Scope

Structural hardening of the dry-run safety release path so an expired pause or stale historical loss window cannot reapply `max_open_trades=0` to the active fleet.

## Exact root cause

The recurring block was a state-precedence bug inside `orchestrator/scripts/system_optimizer.py`:

1. `check_consecutive_loss_protection()` evaluated historical closes again after expiry.
2. Recovery did not run first; new rule evaluation could happen before a forced restore.
3. Host-side config/state writes were not consistently atomic+backed up.
4. The per-strategy quarantine path still allowed old history to matter longer than the recent operating window.

## Structural fix implemented

### 1. Recovery-first execution order
- Added `recovery_preflight()` and moved it to the top of the optimizer run.
- It now checks expiry state before any new quarantine path runs.
- If a bot is blocked but the recent 24h window is green (or empty/insufficient), the baseline limit is force-restored immediately.
- Permanent quarantine still overrides recovery for Rebel.

### 2. Recent-window enforcement
- Consecutive-loss analysis now uses a strict recent floor: `max(last cursor, now-24h)`.
- Old history outside the last 24h no longer participates in a fresh block decision.
- Per-strategy max-loss quarantine now evaluates recent 24h realized loss instead of all-time historical PnL.
- Performance quarantine remains recent-window based (`24h`, minimum `8` trades).

### 3. Safer writes + backups
- Added `_atomic_write_json()` with timestamped backups under `orchestrator/backups/system-optimizer-state/`.
- Added `_atomic_write_text()` with timestamped backups under `orchestrator/backups/system-optimizer-config/`.
- `quarantine_log.json`, `consec_loss_state.json`, `signal_confidence_adjust.json`, and host config writes now use atomic replace flow.
- Container config writes now create an in-container `.bak-<timestamp>` before replace.

### 4. Cursor protection remains mandatory
- `consec_loss_state.json` keeps:
  - `analysis_cursor`
  - `last_checked_close_date`
  - `last_processed_close_date`
- Expired state cleanup preserves the cursor instead of wiping the analysis boundary.

## Backups created before change

Session backup root:
- `/home/hermes/projects/trading/orchestrator/backups/max-open-v47-20260525T093943Z`

## Files changed

- `/home/hermes/projects/trading/orchestrator/scripts/system_optimizer.py`
- `/opt/data/profiles/orchestrator/scripts/system_optimizer.py`

## Verification executed

### Syntax
- `python3 -m py_compile orchestrator/scripts/system_optimizer.py`
- `python3 -m py_compile /opt/data/profiles/orchestrator/scripts/system_optimizer.py`

### Safe runtime verification
- Restarted dry-run bots:
  - `freqtrade-freqforge`
  - `freqtrade-regime-hybrid`
  - `freqtrade-freqforge-canary`
  - `freqai-rebel`
- Ran `python3 orchestrator/scripts/trading_pipeline.py`
- Ran `python3 orchestrator/scripts/system_optimizer.py`
- Ran `python3 orchestrator/scripts/quality_hub_monitor.py`
- Triggered cron jobs:
  - `trading-hub-deep-dive-validation`
  - `Fleet Report (alle 4h)`

## Verified state after fix

### max_open_trades
- FreqForge = `5`
- Canary = `3`
- Regime-Hybrid = `5`
- Rebel = `0` (intentional permanent quarantine)

### Signal / pipeline
- Fresh signal age during validation: ~1 minute
- RiskGuard result: `ACCEPTED=3`, `WATCH_ONLY=4`
- Accepted pairs: `BTC`, `ETH`, `SOL` short
- Signal bridge writes: `4/4` active target files written successfully during manual pipeline run
- ShadowLogger append succeeded

### Safety status during validation
- `dry_run=True` on all four bots
- Fleet drawdown: `0.09%`
- Daily loss: `0.00%`
- Consecutive-loss recovery path cleaned expired guard state and preserved cursor
- No immediate re-block occurred after restart + pipeline + optimizer rerun

### Trading capability evidence
- Canary remained active with `2` open trades during validation
- FreqForge / Regime-Hybrid are not blocked (`max_open_trades > 0`) and can accept new entries when their strategy filters allow

## Operational conclusion

The v4.7 change hardens the release path structurally:
- recovery happens first,
- stale history older than 24h cannot re-trigger the block,
- state/config writes are backed up and atomic,
- the consecutive-loss cursor survives cleanup,
- Rebel remains the only intentional `max_open_trades=0` bot.
