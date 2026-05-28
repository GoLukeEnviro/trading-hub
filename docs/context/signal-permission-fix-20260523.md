# Signal Permission Fix — 2026-05-23

## What changed

- Repaired ownership and permissions for the live signal state files:
  - `freqforge/user_data/primo_signal_state.json`
  - `freqforge-canary/user_data/primo_signal_state.json`
  - `freqtrade/bots/regime-hybrid/user_data/primo_signal_state.json`
  - `freqtrade/shared/primo_signal_state.json`
- Also fixed the writable `user_data/` directories for FreqForge, Canary, and Regime-Hybrid so the cron pipeline can continue using atomic temp-file writes.
- Verified `trading_pipeline.py` writes the expected 5 targets:
  - shared
  - momentum
  - regime-hybrid
  - freqforge
  - freqforge-canary

## Verification

- Restarted FreqForge, Canary, and Regime-Hybrid containers.
- Ran the signal pipeline successfully.
- Confirmed all 5 signal files are JSON-readable and fresh (mtime ~2 minutes after the pipeline run).

## Note

The previously documented cleanup of stale `freqforge/bots/freqforge*` paths was already reflected in the current pipeline state; the remaining issue was directory ownership drift on the writable `user_data/` paths.
