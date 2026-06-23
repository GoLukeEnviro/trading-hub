# SI-v2 ShadowProposal Inventory After Rainbow Phase C

**Date:** 2026-06-23  
**Source Cycle:** 20260623T061729Z (scheduled, pre-Phase-C, Rainbow ENABLED)  
**Verdict:** GREEN — 2 approval-eligible candidates

---

## Source Cycle

| Metric | Value |
|--------|-------|
| Cycle ID | `20260623T061729Z` |
| Type | scheduled |
| Evidence | `self_improvement_v2/reports/phase2/evidence/active_cycle_20260623T061729Z.json` |
| Rainbow | SUCCESS, fresh=True, 50 signals, 34s age |
| Bots read | 4/4 |
| Fleet verdict | GREEN |

---

## Proposal Inventory

| Rank | Proposal | Bot | Hypothesis | Eligible | Net PnL | Profit Factor | Drawdown | Trades | Evaluation |
|------|----------|-----|-----------|----------|---------|---------------|----------|--------|------------|
| 🥇 | `65502d13` | freqforge | `reinforce_profitable_pair_cluster_v1` | ✅ | +23.88 | 1.56 | 2.19% | 77 | PASS_REVIEW |
| 🥈 | `979773d1` | freqforge-canary | `reinforce_profitable_pair_cluster_v1` | ✅ | +6.22 | 3.74 | 0.46% | 57 | PASS_REVIEW |
| — | `44068fb9` | regime-hybrid | `observe_underperforming_pair_cluster_v1` | ❌ | -0.07 | 0.53 | 4.59% | 41 | NEGATIVE |
| — | `e6d2addc` | freqai-rebel | `observe_underperforming_pair_cluster_v1` | ❌ | -0.33 | 0.20 | 3.94% | 12 | NEGATIVE |

---

## Rejected / Deferred Proposals

| Proposal | Reason |
|----------|--------|
| `44068fb9` (regime-hybrid) | Negative net metrics, profit factor < 1.0 |
| `e6d2addc` (freqai-rebel) | Negative net metrics, profit factor 0.20, only 12 trades |

---

## Best Candidate: `65502d13` — freqtrade-freqforge

### Why This Candidate

- **Fleet-level evidence**: `reinforce_profitable_pair_cluster_v1` is a fleet-wide hypothesis — validates what works across bots
- **Strongest absolute evidence**: 77 trades, +23.88 USDT net profit — most trades, most profit
- **Walk-forward PASS_REVIEW**: independently validated
- **Safe mutation policy**: `safe_parameter_overlay_only` — no strategy code changes
- **Low risk**: 2.19% max drawdown, dry-run only
- **Base mode**: `proposal_only` — requires human approval before any apply

### Why Not freqforge-canary (🥈)

- Lower absolute profit (+6.22 vs +23.88)
- Fewer trades (57 vs 77) → less statistical evidence
- Same hypothesis, less data to support it
- Would be a strong second candidate after freqforge validation

### Fleet Relevance

The `reinforce_profitable_pair_cluster_v1` hypothesis is inherently fleet-relevant — it analyzes which assets/strategies produce profits across the dry-run fleet and reinforces those patterns. It's not a single-bot tweak.

---

## Safety

| Gate | Status |
|------|--------|
| Apply performed | ❌ No |
| Mutations | 0 (all counters) |
| Controller | PAUSED / L3_REPOSITORY_ONLY |
| dry_run | True |
| Live trading | None |
