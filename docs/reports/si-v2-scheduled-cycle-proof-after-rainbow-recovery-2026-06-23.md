# SI-v2 Scheduled Cycle Proof — Post-Rainbow-Recovery

**Date:** 2026-06-23
**Branch:** `main`
**Commit:** `2afaa80`
**Classification:** GREEN

---

## 1. Purpose

Prove that the SI-v2 Active Cycle Runner can produce a full GREEN cycle after Rainbow Producer recovery, including the automatic scheduled run at 06:17 UTC. No manual intervention was required for the scheduled cycle.

---

## 2. Manual Cycle: 20260623T055529Z (Post-Recovery)

| Metric | Value |
|--------|-------|
| Bots read | 4/4 |
| Fleet verdict | `GREEN` |
| Rainbow status | `SUCCESS` |
| Rainbow fresh | `true` |
| Freshness | 43s |
| Fresh signals | 9/50 |
| Source | `read_only` |
| Errors | 0 |
| Future signals | 0 |
| Invalid timestamps | 0 |
| Controller | `PAUSED / L3_REPOSITORY_ONLY` |
| Config mutations | 0 |
| Docker mutations | 0 |
| Strategy mutations | 0 |
| Runtime mutations | 0 |
| Live trading mutations | 0 |
| ShadowProposals | 4 |

### Per-Bot

| Bot | Decision | Hypothesis | Approval |
|-----|----------|------------|----------|
| freqforge | `SHADOW_PROPOSAL` | reinforce_profitable_pair_cluster_v1 | PENDING_HUMAN |
| regime-hybrid | `SHADOW_PROPOSAL` | observe_underperforming_pair_cluster_v1 | PENDING_HUMAN ⚠️ negative metrics |
| freqforge-canary | `SHADOW_PROPOSAL` | reinforce_profitable_pair_cluster_v1 | PENDING_HUMAN |
| freqai-rebel | `SHADOW_PROPOSAL` | observe_underperforming_pair_cluster_v1 | PENDING_HUMAN ⚠️ negative metrics |

---

## 3. Scheduled Cycle: 20260623T061729Z (Automatic)

| Metric | Value |
|--------|-------|
| Bots read | 4/4 |
| Fleet verdict | `GREEN` |
| Rainbow status | `SUCCESS` |
| Rainbow fresh | `true` |
| Freshness | 34s |
| Fresh signals | 24/50 |
| Source | `read_only` |
| Errors | 0 |
| Future signals | 0 |
| Invalid timestamps | 0 |
| Controller | `PAUSED / L3_REPOSITORY_ONLY` |
| Config mutations | 0 |
| Docker mutations | 0 |
| Strategy mutations | 0 |
| Runtime mutations | 0 |
| Live trading mutations | 0 |
| ShadowProposals | 4 |

### Per-Bot

| Bot | Decision | Hypothesis | Approval |
|-----|----------|------------|----------|
| freqforge | `SHADOW_PROPOSAL` | reinforce_profitable_pair_cluster_v1 | PENDING_HUMAN |
| regime-hybrid | `SHADOW_PROPOSAL` | observe_underperforming_pair_cluster_v1 | PENDING_HUMAN ⚠️ negative metrics |
| freqforge-canary | `SHADOW_PROPOSAL` | reinforce_profitable_pair_cluster_v1 | PENDING_HUMAN |
| freqai-rebel | `SHADOW_PROPOSAL` | observe_underperforming_pair_cluster_v1 | PENDING_HUMAN ⚠️ negative metrics |

---

## 4. Acceptance Test Confirmation

The existing acceptance test (`self_improvement_v2/tests/test_rainbow_readiness.py`) validates:

- ✅ `/health` — HTTP 200, `status: "healthy"`
- ✅ `/signals/latest` — 50 signals returned
- ✅ Freshness gate — freshest signal < 900s
- ✅ Scoring eligibility — `source: read_only`, `count>=1`, `errors==0`
- ✅ `can_execute=False` — hardcoded in `si_v2/rainbow/client.py:485`
- ✅ `dry_run_only=True` — hardcoded in `si_v2/rainbow/client.py:486`
- ✅ Symbol normalization — `BTCUSDT` → `BTC/USDT:USDT`

---

## 5. Safety Gate Summary

| Gate | Status |
|------|--------|
| Kill Switch | `NORMAL` (no blocking) |
| History gate | `insufficient_history=False` (not blocking) |
| Scoring gate | 4/10 (eligible but not executing) |
| Mutation gate | All counters = 0 |
| Controller | `PAUSED / L3_REPOSITORY_ONLY` |
| dry_run=false scan | clean |
| Approval gate | `PENDING_HUMAN` (all 4 proposals) |

---

## 6. Evidence References

| Artifact | Path |
|----------|------|
| Manual cycle evidence | `self_improvement_v2/reports/phase2/evidence/active_cycle_20260623T055529Z.json` |
| Manual cycle state | `self_improvement_v2/reports/phase2/cycle_state/active_cycle_20260623T055529Z.state.json` |
| Scheduled cycle evidence | `self_improvement_v2/reports/phase2/evidence/active_cycle_20260623T061729Z.json` |
| Scheduled cycle state | `self_improvement_v2/reports/phase2/cycle_state/active_cycle_20260623T061729Z.state.json` |
| Scheduled proof snapshot | `/opt/data/reports/si-v2-scheduled-cycle-proof-after-rainbow-recovery-20260623T060256Z/` |
| Measurement ledger | `self_improvement_v2/reports/phase2/measurement/measurement_ledger.jsonl` (250 lines) |
| Shadow decisions | `orchestrator/logs/shadow_decisions.jsonl` |
| Rainbow adapter | `self_improvement_v2/src/si_v2/rainbow/client.py` |
