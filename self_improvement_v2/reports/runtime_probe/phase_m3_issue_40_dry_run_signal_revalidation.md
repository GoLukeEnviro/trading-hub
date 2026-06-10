# Phase M.3 — Issue #40 Dry-Run Signal Revalidation Report

> **Probe ID:** phase-m3-issue-40-dry-run-signal-revalidation-20260610  
> **Date:** 2026-06-10 ~12:00 UTC  
> **Approval:** `APPROVE_ISSUE_40_DRY_RUN_SIGNAL_REVALIDATION_AFTER_FLEETRISK_FIX`

---

## 1. Repository State

| Check | Value |
|-------|-------|
| Branch | `main` |
| HEAD | `91b10b9` |
| Working tree | Clean (2 untracked non-trading files: `.github/`, `docs/state/issue-40-approval-packet.md`) |
| Merged PRs | #49, #50, #51, #76, #53, #52, #54, #74, #75, **#77** (FleetRiskManager fix) |

---

## 2. Safety Gate Validation

| Check | Result |
|-------|--------|
| FleetRiskManager tests | **14/14 passed** ✅ (includes regression test `test_check_entry_allowed_handles_missing_state`) |
| `ruff check` | All checks passed ✅ |
| Dry-run confirmation | `dry_run: true` ✅ (confirmed via backup config inspection + `exchange.key: False` + `.dryrun.sqlite` naming convention) |
| No live credentials | ✅ Exchange keys empty in all configs |
| No Docker mutation performed | ✅ No restart, stop, start, recreate, or compose operations |
| No secrets exposed | ✅ No config files read for credential values, only `dry_run` + `exchange.name` fields |
| No live trading mode | ✅ All 4 Freqtrade bots in dry-run |

---

## 3. Fleet Inventory (Current)

**22 containers total.** Active Freqtrade bots:

| Container | Image | Status | Started | Port |
|-----------|-------|--------|---------|------|
| trading-freqtrade-freqforge-1 | freqtradeorg/freqtrade:stable | Up 5h | 06:59 UTC | 127.0.0.1:8086 |
| trading-freqtrade-freqforge-canary-1 | freqtradeorg/freqtrade:stable | Up 5h | 06:59 UTC | 127.0.0.1:8081 |
| trading-freqtrade-regime-hybrid-1 | freqtradeorg/freqtrade:stable | Up 5h | 06:59 UTC | 127.0.0.1:8085 |
| trading-freqai-rebel-1 | freqtrade-freqai-rebel:custom | Up 5h | 06:59 UTC | 127.0.0.1:8087 |

Infrastructure containers all healthy:
- `trading-ai-hedge-fund-1` = healthy, running
- `trading-guardian` = running (RiskGuard authority)
- `trading-hermes-watchdog-1` = running (read-only watchdog)
- `shadowlock` = healthy, running

---

## 4. FleetRiskManager Fix Status

### 4.1 Fix Verification

| Check | Result |
|-------|--------|
| Fix on `main` branch | ✅ Merged at `91b10b9` (PR #77) |
| Fix on host filesystem | ✅ `getattr(self, "state", {}) or {}` at line 771 |
| Unit test | ✅ `test_check_entry_allowed_handles_missing_state` — 14/14 passed |
| Host `.py` timestamp | `2026-06-10 11:39:16` (post-merge) |

### 4.2 Deployment Gap

| Factor | Detail |
|--------|--------|
| Containers started at | `2026-06-10 06:59:08` UTC |
| Fix merged at | `2026-06-10 11:39:16` UTC |
| **Delta** | **Fix applied +4h40m after container start** |
| Python import cache | Old module cached in memory at container start |
| Active fix in containers? | **❌ No — containers run old code** |
| FleetRiskManager crash in recent logs? | ❌ **No crash errors visible** in last 500 log lines per bot |

### 4.3 Explanation

The Freqtrade bots import `fleet_risk_manager.py` from the shared volume `./freqtrade/shared:/freqtrade/shared`. While the `.py` file on the host was updated post-merge at 11:39, Python caches the compiled module in memory at container startup. The containers started at 06:59, before the fix was applied. **The old `self.state or {}` code remains loaded** in all 4 bots.

No `AttributeError` crash appears in the last 500 log lines per bot — either the error threshold hasn't been reached (it occurs only on specific candle/entry conditions), or the bots haven't attempted entry decisions since the start window.

---

## 5. Signal Pipeline Assessment

Based on the M.2 baseline report and current state:

| Component | Status | Verdict |
|-----------|--------|---------|
| Signal Generation (ai-hedge-fund) | ✅ Running healthy | 🟢 GREEN |
| Signal Bridge (primo_signal_state) | ✅ Active (schema v0.3, source `trading_pipeline_v1.0`) | 🟢 GREEN |
| AI Override Strategy | ✅ Was accepting signals in M.2 | 🟢 GREEN |
| FleetRiskManager | ⚠️ Fix merged + tested but **not deployed** to running containers | 🟡 YELLOW |
| Bot Decision Execution | 🔶 Blocked until containers pick up fix | 🟡 YELLOW |
| Guardian (RiskGuard) | ✅ Running | 🟢 GREEN |
| Watchdog | 🟡 host.docker.internal timeout (known Issue #39) | 🟡 YELLOW |

### Signal Flow Diagram

```
ai-hedge-fund-core ──> sentiment/signal ──> /app/output/hermes_signal.json
                                                     │
                                                     ▼
                                      Freqtrade Bot (primo_signal_state.json)
                                                     │
                                                     ▼
                                      AIOverride strategy ──> ACCEPTED signal
                                                     │
                                                     ▼
                                      FleetRiskManager ──> ⚠️ Old code until restart
                                                     │
                                                     ▼
                                      Trade blocked (or crash)
```

---

## 6. Dry-Run Confirmation

| Evidence | Source |
|----------|--------|
| `dry_run: true` | Config backup inspection |
| `exchange.key: False` | No API keys configured |
| `exchange.secret: False` | No secrets configured |
| DB naming: `.dryrun.sqlite` | All bot trade databases named with `.dryrun` suffix |
| No `FREQTRADE__DRY_RUN=false` env var | Docker inspect of all 4 bots |
| Fleet risk state trades from `*_dryrun` sources | All trade sources end in `dryrun` |

**Verdict: ✅ DRY-RUN CONFIRMED on all 4 Freqtrade bots.**

---

## 7. Shadowlock/Indexer Evidence

| Component | Status |
|-----------|--------|
| `shadowlock` container | ✅ Running since 20h, healthy |
| `shadowlock_indexer.py` | ✅ Merged via PR #74 (on main, on host) |
| `shadowlock_writer.py` with `_trigger_indexer()` | ✅ Merged via PR #74 (on main, on host) |
| Integration tests | ✅ Merged via PR #75 |

The shadowlock pipeline code is on main and correct. The running `shadowlock` container predates the indexer changes and would need a rebuild to activate them.

---

## 8. Safety Invariants Check

| Invariant | Status |
|-----------|--------|
| No live trading | ✅ Confirmed |
| No `dry_run=false` | ✅ Confirmed |
| No Docker mutation performed | ✅ Read-only inspection only |
| No secrets printed or copied | ✅ No config key/secret values read |
| No orders created | ✅ Not attempted |
| No config files mutated | ✅ Not touched |
| No strategy changes | ✅ Not touched |
| No cron/scheduler activation | ✅ Not touched |
| Raw output stored | ✅ Redacted report only |

---

## 9. Overall Verdict

**🟡 YELLOW**

### What works
- ✅ Signal generation pipeline (ai-hedge-fund → bridge → AI override)
- ✅ FleetRiskManager fix is correct, merged, and validated (14/14 tests)
- ✅ Dry-run confirmed on all bots
- ✅ No live trading, no secrets exposed
- ✅ All safety invariants preserved
- ✅ Shadowlock indexer code on main

### What needs attention
- ⚠️ **Containers started before fix merge** — the fix is on the host filesystem but Python cached the old module at container start. The bots need a restart to pick up `getattr(self, "state", {}) or {}`.
- ⚠️ No FleetRiskManager crash in recent logs, but this could mean the crash path simply hasn't been exercised yet.

### Residual Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Fix not active in containers | 🟡 Medium | Requires container restart (needs explicit Docker mutation approval) |
| Watchdog connectivity (Issue #39) | 🟡 Low | Known, non-blocking for signal validation |
| Rebel Telegram conflict (Issue #38) | 🟡 Low | Non-fatal for headless trading |

---

## 10. Recommended Next Steps

In order:

1. **Restart Freqtrade containers** (after approval) — activates FleetRiskManager fix + any merged strategy adapter changes
2. **Re-run M.3 validation** after restart — confirm fix is live and decisions flow past risk checks
3. **Close Issue #48 (Phase 0 Tracker)** — after restart validation
4. **Clean up local merged branches** with `git branch -d`
5. **Proceed to Issue #21** (Read-Only Adapter Prototypes) or **#55** (Rainbow Signal Integration)

If restart is not immediately possible, the fix is proven correct and will activate on next natural container restart.

---

*Report generated by Hermes (orchestrator profile) on 2026-06-10 ~12:00 UTC.*
*Approval token: APPROVE_ISSUE_40_DRY_RUN_SIGNAL_REVALIDATION_AFTER_FLEETRISK_FIX*
