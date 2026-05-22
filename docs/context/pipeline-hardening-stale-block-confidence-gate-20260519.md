# Pipeline Hardening — Stale Block + Confidence Gate

**Date:** 2026-05-19
**Scope:** `orchestrator/scripts/trading_pipeline.py`
**Mode:** dry-run trading system; no live trading enabled.

## Summary

Implemented the final critical safety hardening for the signal pipeline:

1. Hard stale-signal block before RiskGuard evaluation.
2. Confidence hard gate raised from 0.60 to 0.65.
3. `SIGNAL_OVERRIDE` support for deterministic stale/low-confidence tests.
4. ShadowLogger records `PIPELINE_BLOCKED` events and low-confidence `REJECTED` decisions.
5. `smart_heartbeat.py` deployed as a defensive freshness watchdog.

## Behaviour

### Stale Block

If the source signal is missing, timestamp is invalid, or age exceeds `MAX_AGE_MINUTES = 25.0`, the pipeline now:

- Writes stale state to all `primo_signal_state.json` targets.
- Uses `fresh=false`, `stale=true`, `block_reason=<reason>`, `pairs={}`.
- Appends a `PIPELINE_BLOCKED` event to `shadow_decisions.jsonl`.
- Exits cleanly with code 0.

This prevents bots from trading on old signals.

### Confidence Gate

`CONFIDENCE_THRESHOLD = 0.65` is now enforced in code. Signals below this are converted to HOLD/WATCH_ONLY in bot state and logged to ShadowLogger with `decision="REJECTED"`.

## Tests Performed

- Syntax check: `python3 -m py_compile trading_pipeline.py` → OK.
- Simulated stale signal via `SIGNAL_OVERRIDE=/tmp/test_stale_signal.json` → `PIPELINE_BLOCKED`, stale state written, shadow event appended.
- Simulated low-confidence signal (`confidence=0.64`) → 0 accepted, 3 rejected shadow decisions.
- Fresh restore via `ai_hedge_signal_heartbeat.sh` + `trading_pipeline.py` → state fresh, 3 active SHORT signals.

## Cron / Persistence

Added:

- `smart-heartbeat` cron: `*/10 * * * *`, no-agent, local delivery.
- `cron_jobs_backup.json` updated to 10 jobs.
- `restore_cron_jobs.sh` guard threshold updated from 8 to 10 jobs.

## Files Changed

- `/home/hermes/projects/trading/orchestrator/scripts/trading_pipeline.py`
- `/home/hermes/projects/trading/orchestrator/scripts/smart_heartbeat.py`
- `/home/hermes/projects/trading/orchestrator/scripts/restore_cron_jobs.sh`
- `/home/hermes/projects/trading/orchestrator/config/cron_jobs_backup.json`
- `/opt/data/profiles/orchestrator/scripts/trading_pipeline.py`
- `/opt/data/profiles/orchestrator/scripts/smart_heartbeat.py`
- `/opt/data/profiles/orchestrator/scripts/restore_cron_jobs.sh`

## Backup

Pre-change backup:

`/home/hermes/projects/trading/orchestrator/backups/20260519-142350-pipeline-hardening/trading_pipeline.py.bak`
