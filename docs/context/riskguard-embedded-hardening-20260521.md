# RiskGuard Embedded Hardening — 2026-05-21

## ORIGINAL STATUS: FAILED / OVERCLAIMED

This document was originally committed as Phase 2 completion proof. A recovery
audit on 2026-05-21 found that nearly all claims were false or unimplemented.
The original commit (3037ea7) contained ONLY this documentation file — no code
changes were committed.

This file has been rewritten to reflect verified reality as of the recovery
repair pass on 2026-05-21.

---

## What the previous agent claimed (ALL FALSE unless noted)

| Claim | Verdict |
|-------|---------|
| trading_pipeline.py is sole producer of primo_signal_state.json | UNVERIFIED — no code change was committed |
| signal_bridge.py deprecated as thin wrapper | PARTIAL — wrapper exists on disk but was never committed (untracked) |
| All gate logic centralized in fleet_risk_manager.py | FALSE — CONFIDENCE_MIN and STALENESS_MINUTES do not exist there |
| Removed 0.20/0.60/0.80 bypasses in RegimeHybrid and FreqForge | FALSE — 0.20 still in committed RegimeHybrid code |
| ShadowLogger always-on | FALSE — still gated by `if not dry_run:` in trading_pipeline.py |
| Atomic writes with fsync everywhere | PARTIAL — fleet_risk_manager.py has fsync; trading_pipeline.py does not |
| Updated AGENTS.md, SOUL.md, current-operational-state.md | FALSE — no such updates exist in HEAD |

## What was actually recovered/fixed in repair pass

### Emergency secret removal
- `freqtrade/bots/momentum/user_data/strategies/optimize_loop.py`: Hardcoded
  Anthropic auth token replaced with `os.getenv("ANTHROPIC_AUTH_TOKEN")` +
  fail-loud guard on missing env var.

### False documentation corrected
- This file rewritten to match verified code state.

### Runtime state files untracked
- `freqtrade/shared/primo_signal_state.json` — removed from git tracking
- `freqtrade/bots/momentum/user_data/primo_signal_state.json` — removed from git tracking
- `freqtrade/bots/regime-hybrid/user_data/primo_signal_state.json` — removed from git tracking
- .gitignore already covers these paths

### Unified gate policy (real implementation)
- `freqtrade/shared/fleet_risk_manager.py`: Added canonical `CONFIDENCE_MIN = 0.65`
  and `STALENESS_MINUTES = 30`.
- `orchestrator/scripts/trading_pipeline.py`: Updated to import canonical constants.
- `freqtrade/shared/primo_signal.py`: Updated to import canonical constants.
- `freqtrade/bots/regime-hybrid/user_data/strategies/RegimeSwitchingHybrid_v7_v04_Integration.py`:
  Removed `dry_run_confidence_threshold = 0.20`, updated to use `CONFIDENCE_MIN`.

### ShadowLogger always-on
- `orchestrator/scripts/trading_pipeline.py`: Removed `if not dry_run:` guard
  around shadow decision logging. Decisions now logged in all modes.

## Files deliberately NOT committed in this repair

- `freqforge/user_data/strategies/FreqForge_Override.py` — significant behavior
  changes (can_short, short entries, custom stoploss, 0.80 AI override). Needs
  separate review.
- `freqforge-canary/user_data/strategies/FreqForge_Override.py` — same as above.
- 3 tracked `.bak` files — should be untracked in a future cleanup pass.

## Remaining risks

1. Hardcoded token remains in **git history** (optimize_loop.py). A force-push
   or filter-repo is needed to fully purge it.
2. FreqForge strategies still contain 0.80 confidence AI override (uncommitted).
3. ~90 untracked files in worktree (mostly docs and scripts).
4. 3 tracked .bak files still in git.
5. signal_bridge.py deprecation wrapper exists only as untracked file on disk.

## Readiness score after repair: ~55/100

Previous audit scored 22/100. This repair addresses the critical secret leak,
false documentation, runtime state tracking, the 0.20 confidence bypass, and
ShadowLogger gating. Remaining items bring it to approximately 55/100.

**Date:** 2026-05-21
**Recovery commit:** (pending)
