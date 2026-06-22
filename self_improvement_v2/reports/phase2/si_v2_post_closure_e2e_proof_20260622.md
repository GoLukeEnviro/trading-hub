# SI v2 Post-Closure End-to-End Proof Report

**Date:** 2026-06-22  
**Base Chain:** `1613eb4` (includes #279 → #284 → #288 → #276 → #277 → #278 → #280)

---

## Verdict

**GREEN** — All artifact-only loop stages completed successfully.

| Stage | Status |
|---|---|
| Active Cycle (evidence) | ✅ |
| Multi-Cycle Evidence | ✅ |
| Apply-Plan Creation | ✅ |
| Impact Measurement | ✅ (INSUFFICIENT_POST_APPLY_DATA for fixture — expected) |
| Safety (mutations, controller) | ✅ |

---

## 1. Active Cycle — Cycle ID `20260622T053349Z`

**Evidence artifact:** `self_improvement_v2/reports/phase2/evidence/active_cycle_20260622T053349Z.json`

| Bot | Decision | Hypothesis | Approval |
|---|---|---|---|
| freqtrade-freqforge | SHADOW_PROPOSAL | telemetry_reachability_baseline_established | PENDING_HUMAN, eligible=False |
| freqtrade-regime-hybrid | SHADOW_PROPOSAL | telemetry_reachability_baseline_established | PENDING_HUMAN, eligible=False |
| freqtrade-freqforge-canary | SHADOW_PROPOSAL | telemetry_reachability_baseline_established | PENDING_HUMAN, eligible=False |
| freqai-rebel | SHADOW_PROPOSAL | telemetry_reachability_baseline_established | PENDING_HUMAN, eligible=False |

**Safety:** Runtime mutations=0, Config mutations=0, Docker=0, Strategy=0  
**Controller:** `PAUSED / L3_REPOSITORY_ONLY`  
**Profitability Gate:** `blocked` (no real metrics available — env-limited)

---

## 2. Multi-Cycle Evidence — 8-window aggregation

| Bot | Cycles | Real Metrics | Net PnL Avg | PF Avg | Classification |
|---|---|---|---|---|---|
| freqtrade-freqforge | 8 | 2 | 0.0000 | 0.0000 | blocked |
| freqtrade-regime-hybrid | 8 | 7 | -6.2126 | 0.4937 | blocked |
| freqtrade-freqforge-canary | 8 | 1 | 0.0000 | 0.0000 | blocked |
| freqai-rebel | 8 | 7 | -0.2738 | 0.1763 | blocked |

**Fleet recommendation:** none — no bot has sufficient positive real metrics for pilot candidacy.

---

## 3. Apply-Plan Smoke

**Fixture:** `self_improvement_v2/fixtures/approved_proposal_smoke.json`  
**Artifact:** `self_improvement_v2/reports/phase2/apply_plans/apply_plan_076230d3.json`

| Field | Value |
|---|---|
| `bot_id` | freqtrade-freqforge |
| `hypothesis` | reinforce_profitable_pair_cluster_v1 |
| `mutation_performed` | false |
| `safety_verdict` | APPLY_PLAN_CREATED |
| `parameter_overlay` | {} |

---

## 4. Impact Measurement

**Artifact:** `self_improvement_v2/reports/phase2/impact/impact_report_20260622T053406Z.md`

| Field | Value |
|---|---|
| Apply Plan | `076230d3` |
| Verdict | **INSUFFICIENT_POST_APPLY_DATA** |
| Reason | insufficient_post_apply_data |

Note: INSUFFICIENT_DATA is expected here because the fixture proposal references a non-existent pre-cycle. When a real approved proposal exists with matching evidence, the impact will produce IMPROVED/DEGRADED/UNCHANGED.

---

## 5. Validation

| Command | Result |
|---|---|
| `pytest test_no_forbidden_patterns.py -q` | 49 passed |
| `pytest test_multi_bot_fleet_analyzer.py -q` | 26 passed |
| `pytest test_dry_run_apply_path.py -q` | 21 passed |
| `pytest test_post_apply_impact.py -q` | 13 passed |
| `ruff check src/si_v2` | All checks passed |

---

## Safety Confirmation

- ✅ No live trading
- ✅ No `dry_run=false`
- ✅ No Docker/Compose/Cron mutation
- ✅ No Freqtrade config/strategy writes
- ✅ No credentials printed
- ✅ All mutation counters = 0
- ✅ Controller remains `PAUSED / L3_REPOSITORY_ONLY`

---

## Environment Note

The full positive-profit chain (#288 → SHADOW_PROPOSAL with `reinforce_profitable_pair_cluster_v1`) requires JWT-authenticated access to all four Freqtrade containers. In the orchestrator shell, only `freqtrade-freqforge` was reachable, and no SI v2 JWT env vars were set. The cron-based 6h cycle has the full network + credentials and will produce richer proposals.

---

## Next Steps

1. **#256 Compose Split** — infra cleanup, not loop-blocking
2. **Runtime Safety Review** — structured review of cron, credentials, rollback
3. **Live-Pilot Prep** — only after runtime review
