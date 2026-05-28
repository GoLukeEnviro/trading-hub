# max_open_trades-Block Root Cause & Fix — 2026-05-25

## Summary

The recurring fleet block was caused by `orchestrator/scripts/system_optimizer.py` re-applying `max_open_trades=0` from the consecutive-loss protection path after the pause window had already expired.

## Root Cause

1. `check_consecutive_loss_protection()` evaluated the last 20 closed trades without limiting them to trades closed after the pause window.
2. When the pause expired, old loss trades were still present in the sample, so the script re-triggered the 4-loss pause instead of releasing the fleet.
3. `cleanup_expired_guard_state()` only deleted `consec_loss_state.json` and `signal_confidence_adjust.json`; it did not restore bot limits.
4. Performance quarantine was also too sticky because it relied on all-time stats instead of a recent window.

## Structural Fix

- Added baseline restore logic for FreqForge, Canary, and Regime-Hybrid.
- Made performance quarantine use a recent 24h window with a minimum recent-trade threshold.
- Made consecutive-loss evaluation look only at trades closed after `resume_after` once a pause has expired.
- Added automatic fleet-limit restoration when an expired pause is cleared.
- Synced the updated `system_optimizer.py` into both script locations:
  - `/home/hermes/projects/trading/orchestrator/scripts/system_optimizer.py`
  - `/opt/data/profiles/orchestrator/scripts/system_optimizer.py`

## Verification

- FreqForge restored to `max_open_trades=5`
- Canary restored to `max_open_trades=3`
- Regime-Hybrid restored to `max_open_trades=5`
- Rebel remains at `max_open_trades=0` due to permanent quarantine
- `trading_pipeline.py` rerun successfully and refreshed the shared Primo state
- All active trading containers are running again after restart

## Notes

This fix prevents stale historical losses from pinning the fleet in a permanent pause loop. The remaining `consec_loss_state.json` will expire naturally; after expiry, the optimizer now lifts the temporary block cleanly instead of re-triggering it from old data.
