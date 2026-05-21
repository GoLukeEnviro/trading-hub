# FreqForge Diff and Repo Hygiene Review — 2026-05-21

## Current State After Recovery Commit b6530c3

Recovery commit b6530c3 fixed core safety gates, removed the hardcoded Anthropic
token from the working tree, enabled always-on ShadowLogger, and removed runtime
state JSON files from git tracking. The branch is 1 ahead of origin.

## FreqForge Diff Classification

Both `freqforge` and `freqforge-canary` FreqForge_Override.py were modified
with significant behavior changes. Classification:

### REMOVE_NOW (done in this session)
- `_inject_ai_signal_override`: Forced SELL/SHORT on confidence >= 0.80,
  bypassing canonical RiskGuard gate. **Replaced with no-op.**
- `signal_override_short`: Forced short entries on confidence >= 0.80
  regardless of TA. **Disabled, commented out.**

### SAFE_KEEP (no bypasses, positive changes)
- `from fleet_risk_manager import FleetRiskManager` — enables risk integration
- `FleetRiskManager()` init + `_fleet_source` in __init__
- `bot_loop_start` — syncs trade state to FleetRiskManager
- FleetRisk `check_entry_allowed` checks in populate_entry_trend
- `confirm_trade_entry` returns False on risk/primo gate block
- FleetRisk cluster stats enrichment in confirm_trade_entry log

### NEEDS_SEPARATE_REVIEW (behavior changes, not committed yet)
| Change | freqforge | canary | Notes |
|--------|-----------|--------|-------|
| can_short = True | YES | YES | Enables shorts — needs backtest |
| minimal_roi changed | YES | NO | Different profit targets |
| stoploss -0.09 -> -0.045 | YES | NO | Tighter stop |
| use_custom_stoploss = True | YES | NO | New custom logic |
| trailing_stop + params | YES | NO | New trailing behavior |
| custom_stoploss function | YES | NO | Time-based tightening |
| Short entry logic (trend/range) | YES | YES | New short entries |
| JSONL "\\\\n" double-escape | YES | YES | Likely a bug |

## What Was Removed/Disabled

- `_inject_ai_signal_override` function body replaced with no-op + explanation
- `signal_override_short` logic commented out in populate_entry_trend
- Native short entries (trend_short, range_short) preserved — they are
  NEEDS_SEPARATE_REVIEW but not dangerous in isolation

## What Remains Uncommitted and Why

The FreqForge files still contain NEEDS_SEPARATE_REVIEW changes (can_short,
stoploss, trailing, ROI, short entries, JSONL bug). These are:
1. Behavior-heavy changes that need backtest validation
2. Not safety-critical now that the 0.80 override is disabled
3. Best committed as a separate review with backtest evidence

## Tracked .bak Files

| File | Recommendation |
|------|---------------|
| RegimeSwitchingHybrid_v2.py.bak_20260503_022741 | `git rm --cached` |
| RegimeSwitchingHybrid_v6_1_Fett.py.bak_v04_integration | `git rm --cached` |
| RegimeSwitchingHybrid_v6_Stable.json.bak-shadow-fix-phase25b2 | `git rm --cached` |

Future cleanup: `git rm --cached` each, add `*.bak*` to .gitignore.

## Untracked File Summary

| Category | Count | Risk |
|----------|-------|------|
| docs_history | 38 | LOW — historical context notes |
| operational_scripts | 17 | MEDIUM — actively used by cron/containers |
| research_artifacts | 12 | LOW — sideaware research + signal tools |
| freqtrade_shared_ops | 4 | MEDIUM — fleet watcher, equity updater |
| runtime_artifacts | 2 | LOW — already ignored, untracked |

## Secret-History Status

- Current working tree: **CLEAN** — no hardcoded tokens
- Git history: **CONTAINS TOKEN** in optimize_loop.py (commit 801ff86 forward)
- **Token must be rotated at z.ai/Anthropic provider immediately**
- `git filter-repo` requires separate explicit approval (history rewrite + force-push)
- Do NOT run `git filter-repo` without coordination

## Exact Next Action Recommendation

1. **Immediate**: Rotate the Anthropic token at the provider
2. **Next commit**: Review and commit the remaining FreqForge changes
   (can_short, stoploss, trailing, short entries) with backtest evidence
3. **Cleanup**: `git rm --cached` the 3 tracked .bak files + add to .gitignore
4. **History purge**: `git filter-repo --invert-paths --path freqtrade/bots/momentum/user_data/strategies/optimize_loop.py --blob-callback` (after token rotation)
5. **Push**: After cleanup is complete and history is clean

**Date:** 2026-05-21
**Branch:** chore/final-docs-and-worktree-cleanup
**Recovery commit:** b6530c3
