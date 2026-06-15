# SI v2 — Dry-Run Readiness Checklist

**Date:** 2026-06-15
**Branch:** main
**Commit:** eb64e5c

## Phase 0 Gates

| Gate | Status | Detail |
|------|--------|--------|
| #199 — Freqtrade healthchecks | ✅ PASS | Deterministic HEALTHCHECK for 4-bot fleet |
| #200 — Compose ownership | ✅ PASS | All containers mapped, drift documented |
| #201 — Non-root evaluation | ✅ PASS | Assessed — hermes-green accepted risk, qdrant quick-win documented |
| #176 — Controller isolation | ✅ PASS | OS isolation proof + one-shot proof completed |
| #202 — Scoped auth one-shot | ✅ PASS | Read-only JWT auth proof across fleet |

## CI Status

| Check | Status | Detail |
|-------|--------|--------|
| main-gate | ✅ PASS | Always-reporting workflow on all PRs |
| offline-smoke | ✅ PASS | SI v2 test suite (1177+ tests) |
| Branch protection ruleset | ✅ ACTIVE | main branch protected |

## Kill-Switch

| Check | Status | Detail |
|-------|--------|--------|
| kill_switch.py module | ✅ DEPLOYED | NORMAL/HALT_NEW/EMERGENCY |
| primo_signal.py integration | ✅ DEPLOYED | Entry blocking via primo_gate_allows() |
| Trigger script | ✅ DEPLOYED | CLI + drawdown auto-check skeleton |
| Runbook | ✅ DEPLOYED | docs/runbooks/kill-switch.md |
| Test coverage | ⏳ PENDING | #229 — new issue |
| Pipeline wiring | ⏳ PENDING | #230 — new issue |
| Drawdown auto-check + cron | ⏳ PENDING | #231 — new issue |

## Safety Invariants

| Invariant | Verified |
|-----------|----------|
| All bots dry_run=true | ✅ Confirmed |
| No exchange credentials on main | ✅ Confirmed |
| No live trading enablement | ✅ Confirmed |
| Controller PAUSED | ✅ Confirmed |
| Scheduler FORBIDDEN | ✅ Confirmed |

## Infrastructure

| Component | Status |
|-----------|--------|
| Docker compose | ✅ 11 managed containers |
| Docker healthchecks | ✅ 4 Freqtrade bots + ai-hedge-fund + shadowlock |
| Container networking | ✅ Internal DNS names resolving |
| Volume persistence | ✅ tradesv3.*.dryrun.sqlite per bot |
| Hermes agent | ✅ orchestrator profile active |

## Next Steps for Dry-Run Readiness

1. Resolve Kill-Switch follow-ups: #229 → #230 → #231
2. Proceed with Phase 2 feature implementation (#89, #90, #92)
3. Begin Market Data adapter work (#177) when resources available
