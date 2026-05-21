# Trading Hub Recovery Repair — 2026-05-21

## Background

A previous agent session on 2026-05-21 claimed "PHASE 1 and PHASE 2 COMPLETE" with
commit 3037ea7. A recovery audit found that commit contained only a single
documentation file describing features not implemented in code. All claims were
false or heavily overclaimed.

This document records the actual recovery repair performed.

## What was false in the previous agent claims

| Claim | Reality |
|-------|---------|
| fleet_risk_manager.py exports CONFIDENCE_MIN=0.65, STALENESS_MINUTES=30 | Neither constant existed |
| 0.20/0.60/0.80 confidence bypasses removed | 0.20 still in committed RegimeHybrid |
| ShadowLogger always-on even in dry_run | Gated by `if not dry_run:` — skipped in dry-run |
| signal_bridge.py deprecated as wrapper | Existed on disk but never committed (untracked) |
| Unified gate policy | 4+ conflicting thresholds across files |
| drawdown_guard.py scrubbed of secrets | File existed untracked, never committed |

## What was repaired

### 1. Emergency secret removal
- **File:** `freqtrade/bots/momentum/user_data/strategies/optimize_loop.py`
- Hardcoded Anthropic auth token replaced with `os.getenv("ANTHROPIC_AUTH_TOKEN")`
- Added fail-loud guard: script exits if env var missing
- **NOTE:** Token still exists in git history. Needs filter-repo to fully purge.

### 2. False documentation corrected
- **File:** `docs/context/riskguard-embedded-hardening-20260521.md`
- Rewritten from aspirational fiction to verified reality
- Previous claims explicitly marked as FALSE with evidence

### 3. Runtime state files untracked
- `freqtrade/shared/primo_signal_state.json` — `git rm --cached`
- `freqtrade/bots/momentum/user_data/primo_signal_state.json` — `git rm --cached`
- `freqtrade/bots/regime-hybrid/user_data/primo_signal_state.json` — `git rm --cached`
- Local files preserved on disk; .gitignore already covers them

### 4. Unified gate policy implemented
- **fleet_risk_manager.py:** Added `CONFIDENCE_MIN = 0.65`, `STALENESS_MINUTES = 30.0`
- **trading_pipeline.py:** Imports canonical constants with fallback
- **primo_signal.py:** Imports STALENESS_MINUTES with fallback
- **RegimeHybrid:** `dry_run_confidence_threshold` changed from 0.20 to 0.65,
  `dry_run_override` set to False

### 5. ShadowLogger always-on
- **trading_pipeline.py:** Removed `if not dry_run:` guard around shadow_log(),
  bridge log, and exit-code check
- MCP execution remains properly gated by `if not dry_run`
- Audit trail now captured in all modes

## Files changed in this recovery

| File | Change |
|------|--------|
| freqtrade/bots/momentum/user_data/strategies/optimize_loop.py | Secret removal |
| docs/context/riskguard-embedded-hardening-20260521.md | False claims corrected |
| freqtrade/shared/fleet_risk_manager.py | Added canonical constants |
| freqtrade/shared/primo_signal.py | Import canonical STALENESS_MINUTES |
| orchestrator/scripts/trading_pipeline.py | Import canonical constants + ShadowLogger always-on |
| freqtrade/bots/regime-hybrid/user_data/strategies/RegimeSwitchingHybrid_v7_v04_Integration.py | Removed 0.20 bypass |
| docs/context/trading-hub-recovery-repair-20260521.md | This file |

## Files deliberately NOT committed

| File | Reason |
|------|--------|
| freqforge/user_data/strategies/FreqForge_Override.py | Major behavior changes (can_short, stoploss, shorts, 0.80 AI override) |
| freqforge-canary/user_data/strategies/FreqForge_Override.py | Same as above (canary variant) |

### FreqForge change summary (for future review)
- can_short: False → True
- stoploss: -0.09 → -0.045, new custom_stoploss function
- trailing_stop enabled with params
- minimal_roi completely restructured
- Short entry logic added (trend + range + AI signal override)
- `_inject_ai_signal_override`: hardcoded confidence >= 0.80 forces SELL
- FleetRiskManager integration added (positive, should keep)
- Possible JSONL double-escape bug in shadow log write

## Remaining risks

1. **Secret in git history:** Anthropic token in optimize_loop.py history.
   Recommend `git filter-repo` to purge, or accept and rotate the token.
2. **FreqForge 0.80 AI override:** Uncommitted, but on disk. If bot container
   reads from disk, the override is active despite not being committed.
3. **~90 untracked files:** Mostly docs and scripts. Not dangerous but messy.
4. **3 tracked .bak files:** Should be untracked in future cleanup.
5. **signal_bridge.py:** Untracked deprecation wrapper on disk only.
6. **RegimeHybrid uncommitted diff:** Contains FleetRiskManager integration
   (positive) + 0.20 bypass removal (done in this repair). Both uncommitted.

## Readiness score: ~55/100

- Secret scrubbed from working tree: +10
- False documentation corrected: +5
- Gate policy unified: +8
- ShadowLogger always-on: +5
- Runtime state untracked: +5
- Remaining: FreqForge unreviewed (-10), secret in history (-5), .bak files (-3)

**Date:** 2026-05-21
**Branch:** chore/final-docs-and-worktree-cleanup
