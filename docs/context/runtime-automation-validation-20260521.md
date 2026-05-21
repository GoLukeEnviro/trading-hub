# Runtime Automation Validation — 2026-05-21

## Context

Follows commits b6530c3, d451819, b6411d4 on branch
`chore/final-docs-and-worktree-cleanup`.

## 1. Static Validation

All 6 core Python files parse without errors:

| File | Result |
|------|--------|
| fleet_risk_manager.py | PASS |
| primo_signal.py | PASS |
| trading_pipeline.py | PASS |
| RegimeHybrid v7 v04 Integration | PASS |
| FreqForge_Override.py | PASS |
| FreqForge-Canary FreqForge_Override.py | PASS |

## 2. Gate Policy Validation

Canonical values confirmed active:

| Source | CONFIDENCE_MIN | STALENESS_MINUTES | Method |
|--------|---------------|-------------------|--------|
| fleet_risk_manager.py (line 30-31) | 0.65 | 30.0 | CANONICAL |
| primo_signal.py (line 21-23) | imports | imports | import + fallback 30.0 |
| trading_pipeline.py (line 46-52) | imports | imports | import + fallback 0.65/30.0 |
| RegimeHybrid (line 105-108) | imports | — | import + fallback 0.65 |

Bypass status:
- 0.20 dry_run bypass: REMOVED (RegimeHybrid now imports canonical)
- 0.60 threshold: NOT PRESENT in any active code
- 0.80 force-entry: NEUTRALIZED (FreqForge _inject_ai_signal_override is no-op)

ShadowLogger evidence confirms gate works:
- 15:01 BTC conf=0.55 → REJECTED (below 0.65)
- 15:10 ETH/SOL conf=0.60 → REJECTED (below 0.65)
- 15:20+ all conf=0.85 → ACCEPTED

## 3. Pipeline Dry-Run Result

```
python3 orchestrator/scripts/trading_pipeline.py --dry-run
```

Result: PASS
- Read signal from hermes_signal.json (age 20.5 min)
- 3 pairs processed: BTC/USDT, ETH/USDT, SOL/USDT
- All ACCEPTED (conf=0.85)
- State files NOT written (dry-run mode)
- No errors, no exceptions

## 4. ShadowLogger Dry-Run Append Result

PASS. ShadowLogger appended entry at 2026-05-21T15:41:10Z even in dry-run mode.
The entry has `state_writes: {}` (empty — correct for dry-run).
Previous real-run entries show state_writes with "OK" status.

Historical entries at 15:01 and 15:10 used max_age_minutes=25.0 (pre-fix).
Latest entry uses max_age_minutes=30.0 (post-fix confirmed active).

## 5. Cron/Scheduler Wiring

17 Hermes cron jobs active. Key trading automation:

| Job | Schedule | Status |
|-----|----------|--------|
| trading-pipeline | */10 min | Active — calls trading_pipeline.py |
| signal-heartbeat | */20 min | Active — monitors pipeline |
| drawdown-guard | */30 min | Active |
| container-watchdog | */5 min | Active |
| FleetRisk equity updater | */5 min | Active |

No cron job calls deprecated signal_bridge.py directly.
smart_heartbeat.py mentions trading_pipeline.py in a comment only (not importing).

## 6. Container Status (Read-Only)

| Container | Status | Uptime |
|-----------|--------|--------|
| freqtrade-momentum | Up | 22h |
| freqtrade-regime-hybrid | Up | 16h |
| freqtrade-freqforge | Up | 16h |
| freqtrade-freqforge-canary | Up | 16h |
| freqai-rebel | Up | 2d |
| freqtrade-webserver | Up | 2d |
| trading-guardian | Up | 5h |

All healthy. No restarting or unhealthy containers.

## 7. Git Cleanliness After Runtime

Modified tracked files: 0
Staged files: 0
All state files properly ignored (except RSI — see below).

## Findings Requiring Follow-Up

### MEDIUM: Tracked runtime state in RSI bot
`freqtrade/bots/rsi/user_data/primo_signal_state.json` is tracked in git
but is a runtime state file. Not ignored by .gitignore. Needs `git rm --cached`
in next cleanup pass.

### MEDIUM: ShadowLogger max_age_minutes transition
Pre-fix entries (15:01, 15:10) show max_age_minutes=25.0, post-fix shows 30.0.
This is expected — the fix is confirmed active. But if any other process
caches the old value, it could cause stale-threshold drift. Monitor.

### LOW: ~72 untracked files
Untracked clutter is harmless but should be triaged for git add or .gitignore
in a future cleanup pass.

## Summary

| Check | Result |
|-------|--------|
| Static parse | PASS (6/6) |
| Gate policy unified | PASS (0.65/30.0 canonical) |
| Pipeline dry-run | PASS |
| ShadowLogger dry-run | PASS (always-on confirmed) |
| Cron wiring | PASS (no deprecated refs) |
| Containers | PASS (all healthy) |
| Git cleanliness | PASS (0 modified tracked) |
| Secrets in tree | PASS (clean) |
| RSI tracked state | MEDIUM (needs untracking) |

**Date:** 2026-05-21
**Branch:** chore/final-docs-and-worktree-cleanup
**Commits:** b6530c3, d451819, b6411d4
