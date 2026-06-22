# SI-v2 Active Cycle Proof — 4 Bot Runtime Evidence

**Date:** 2026-06-22  
**Cycle ID:** `20260622T204701Z`  
**Commit:** `84105c4` (`main`)  
**Controller:** PAUSED / L3_REPOSITORY_ONLY

---

## Verdict: GREEN

The SI-v2 Active Cycle successfully read real telemetry from all four Freqtrade dry-run bots, produced an evidence bundle, generated 4 ShadowProposals, and recorded zero mutations across all categories.

---

## Baseline

| Property | Value |
|----------|-------|
| Commit | `84105c4568f5281e80e507dfb243217c7ec0c9cb` |
| Branch | `main` (synced with origin) |
| P0 Security Sprint | ✅ Closed |
| Controller state | PAUSED / L3_REPOSITORY_ONLY |
| Merge policy | HUMAN_ONLY |
| Runtime policy | FORBIDDEN |

---

## Scope

Read-only active cycle proof. No apply. No runtime mutation. No container restart. No config change.

---

## Bot Readiness

| Bot | Container | Runtime Status | Ping | Telemetry | dry_run | Verdict |
|-----|-----------|---------------|------|-----------|---------|---------|
| FreqForge | trading-freqtrade-freqforge-1 | running | HTTP 200 ✅ | 78.9% WR, +21.64U, PF 1.51, 2 open | True | ✅ GREEN |
| Canary | trading-freqtrade-freqforge-canary-1 | running | HTTP 200 ✅ | 91.2% WR, +6.22U, PF 3.74, 2 open | True | ✅ GREEN |
| Regime-Hybrid | trading-freqtrade-regime-hybrid-1 | running | HTTP 200 ✅ | 67.3% WR, -7.25U, PF 0.58, 0 open | True | ✅ GREEN |
| FreqAI Rebel | trading-freqai-rebel-1 | running | HTTP 200 ✅ | 40.0% WR, -0.32U, PF 0.21, 0 open | True | ✅ GREEN (VISIBILITY_GAP noted) |

---

## Active Cycle Result

| Property | Value |
|----------|-------|
| Cycle ID | `20260622T204701Z` |
| Fleet Verdict | **GREEN** |
| Verdict Reason | all 4 bots authenticated and decisions generated |
| Bots pinged | 4/4 |
| Ping failed | 0 |
| Shadow Proposals | 4 (one per bot) |
| NO_PROPOSAL | 0 |
| Evidence window | runs_observed=5, freshness=fresh |
| Approval gate evaluations | 4 |
| Rainbow status | SUCCESS (read_only, 50 data points) |
| Rainbow freshness | False (producer stale: 24389s vs 900s max) |

### Evidence Artifacts Created

| Artifact | Path |
|----------|------|
| Cycle State | `self_improvement_v2/reports/phase2/cycle_state/active_cycle_20260622T204701Z.state.json` |
| Evidence Bundle | `self_improvement_v2/reports/phase2/evidence/active_cycle_20260622T204701Z.json` |
| Shadow Log (FreqForge) | `self_improvement_v2/reports/phase2/shadow_logs/shadow_freqtrade-freqforge.jsonl` |
| Shadow Log (Canary) | `self_improvement_v2/reports/phase2/shadow_logs/shadow_freqtrade-freqforge-canary.jsonl` |
| Shadow Log (Regime-Hybrid) | `self_improvement_v2/reports/phase2/shadow_logs/shadow_freqtrade-regime-hybrid.jsonl` |
| Shadow Log (Rebel) | `self_improvement_v2/reports/phase2/shadow_logs/shadow_freqai-rebel.jsonl` |
| Measurement Ledger | `self_improvement_v2/reports/phase2/measurement/measurement_ledger.jsonl` |
| Attribution Report | `self_improvement_v2/reports/phase2/measurement/attribution_report.md` |
| Cycle Runner Report | `self_improvement_v2/reports/phase2/active_cycle_runner_report.md` |
| Telemetry History | `self_improvement_v2/state/telemetry_history/telemetry_20260622.jsonl` |
| ShadowLock Audit | `var/trading-shadowlock/logs/2026/06/22.jsonl` |

---

## Mutation Safety

| Counter | Value | Status |
|---------|-------|--------|
| runtime_mutations | 0 | ✅ |
| config_mutations | 0 | ✅ |
| live_trading_mutations | 0 | ✅ |
| docker_mutations | 0 | ✅ |
| strategy_mutations | 0 | ✅ |
| **mutations_all_zero** | **True** | ✅ |
| secrets_found | False | ✅ |
| dry_run=false in bot configs | 0/4 (all True) | ✅ |
| git tracked changes after cycle | 0 (only untracked docs) | ✅ |

---

## Ledger Statistics

| Metric | Value | Previous (2026-06-16) | Trend |
|--------|-------|----------------------|-------|
| Cycles scanned | 47 | 27 | +20 |
| Bot measurement points | 188 | 108 | +80 |
| Proposal records | 89 | 24 | +65 |

---

## Findings

### 1. GREEN — Loop is functional
The SI-v2 observation loop reads all 4 bots via authenticated REST API, generates ShadowProposals, and appends to the measurement ledger. All mutation counters remain zero. The controller is correctly PAUSED.

### 2. Rainbow Freshness — Not yet scoring-eligible
Rainbow producer data is 24389 seconds old (6.8 hours) vs the 900-second freshness threshold. This means the scoring gate won't count this cycle toward the 10-cycle promotion threshold until the producer is running on schedule. This is a known operational gap, not a code defect.

### 3. FreqAI Rebel — VISIBILITY_GAP
Rebel shows 40% win rate, PF 0.21, 0 open trades. The Quality Hub flags this as VISIBILITY_GAP. This is a data-quality observation, not a runtime blocker.

### 4. Regime-Hybrid — Underperforming
Regime-Hybrid shows -7.25U PnL with PF 0.58. This may warrant a ShadowProposal for parameter review, but that decision is human-gated.

### 5. Kill Switch — HALT_NEW from host perspective
The kill switch shows HALT_NEW when read from the host (state file not at host path). This is expected fail-closed behavior from P0-1. Inside the Freqtrade containers, the kill switch file is available at `/freqtrade/shared/kill_switch.json`. This does not block read-only observation.

---

## Evidence Directory

```
/opt/data/reports/si-v2-active-cycle-proof-20260622T204640Z/
├── docker-ps.txt
├── freqtrade-monitor.json
├── git-head.txt
├── git-status-after.txt
├── git-status.txt
├── quality-hub.txt
├── si-v2-active-cycle.txt
└── new-artifacts.txt
```

---

## Next Step

The SI-v2 loop is proven functional and safe. The next priority is:

1. **Rainbow producer freshness fix** — get the producer running on schedule so cycles become scoring-eligible
2. **Continue scheduled 6h cycles** — each cycle adds to the ledger and moves toward the 10-cycle scoring gate
3. **Human review of accumulated ShadowProposals** — when enough scoring-eligible cycles exist

---

*Operation Level: L0 (read-only observation)*  
*No runtime mutation. No apply. No container restart. No config change.*
