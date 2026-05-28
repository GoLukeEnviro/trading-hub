# Cron Crash Fix — 2026-05-23

## Summary

Two cron issues were repaired:

1. `trading_pipeline.py` now prefers the canonical signal source first:
   - `ai-hedge-fund-crypto/output/hermes_signal.json`
   - then `ai-hedge-fund-crypto/output/latest/hermes_signal.json`
   - then the legacy shared fallback
2. `system_optimizer.py` no longer raises on fleet report delivery when the primary alert directory is unwritable.
   - It now writes to the normal alert queue when possible
   - otherwise falls back to `/tmp/hermes-system-optimizer-alerts`
   - and never propagates a traceback from `_send_fleet_report()`

## Verification

- Ran `trading_pipeline.py` successfully as `hermes` after a fresh heartbeat.
- Ran `system_optimizer.py` successfully as `hermes` after the fix.
- Confirmed the fleet report alert was queued and the script exited 0.

## Notes

- `equity_history.json` still emits a non-fatal permission warning in the equity protection section; this does not crash the cron job.
- The no-agent cron scripts were synced to `/opt/data/profiles/orchestrator/scripts/` after patching.
