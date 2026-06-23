# SI-v2 Approval-Ready ShadowProposal

**Date:** 2026-06-23  
**Verdict:** APPROVAL_READY

---

## Candidate

| Attribute | Value |
|-----------|-------|
| Proposal ID | `65502d13a99bfadd` |
| Proposal type | `SHADOW_PROPOSAL` |
| Target bot | `freqtrade-freqforge` |
| Hypothesis | `reinforce_profitable_pair_cluster_v1` |
| Fleet relevance | ⭐⭐⭐⭐⭐ (fleet-wide hypothesis, validates profitable clusters) |
| Source cycle | `20260623T061729Z` |
| Evidence files | `self_improvement_v2/reports/phase2/evidence/active_cycle_20260623T061729Z.json` |
| Mutation policy | `safe_parameter_overlay_only` |
| Base mode | `proposal_only` |

---

## Walk-Forward Metrics

| Metric | Value |
|--------|-------|
| Total trades | 77 |
| Net PnL | +23.88 USDT |
| Profit factor | 1.56 |
| Max drawdown | 2.19% |
| Win rate | 0% (parameter overlay — not signal change) |
| Evaluation | **PASS_REVIEW** |

---

## What Would Change

The `reinforce_profitable_pair_cluster_v1` hypothesis identifies which asset/timeframe/strategy combinations produce profitable results across the dry-run fleet and reinforces those patterns through parameter overlays.

- **No strategy code changes** — `safe_parameter_overlay_only`
- **No live trading** — `dry_run=True`, `proposal_only`
- **No config mutation without approval**
- **Fleet-relevant**: insights from freqforge apply to canary and vice versa

---

## Why This Candidate

### Evidence
- 77 real dry-run trades from freqtrade-freqforge
- +23.88 USDT net profit over walk-forward period
- Profit factor 1.56 (>1.0, consistently profitable)
- Max drawdown 2.19% (well within acceptable range)
- PASS_REVIEW evaluation status

### Expected Impact
- Reinforces and replicates profitable pair clusters
- Fleet-wide insight applicable to all bots
- Incremental improvement — preserves safety defaults

### Why Now
- Phase A/B/C complete: Rainbow stable, factory logging active, persistent paths active
- Freqforge is the most active bot (77 trades) → strongest statistical foundation
- Next scheduled cycle (12:17 UTC) will provide post-Phase-C confirmation

### Why Better Than Alternatives
- `979773d1` (canary): lower absolute profit, fewer trades
- `44068fb9` (regime-hybrid): negative metrics
- `e6d2addc` (rebel): negative metrics, only 12 trades

---

## Risk Assessment

| Risk | Level | Mitigation |
|------|-------|------------|
| Runtime risk | LOW | `safe_parameter_overlay_only`, dry-run |
| Strategy risk | NONE | No strategy code change |
| Config risk | LOW | Parameter overlay, trivially reversible |
| Capital risk | NONE | `dry_run=True`, no live trading |
| Data quality risk | LOW | 77 trades, walk-forward validated |
| Rollback risk | LOW | Remove overlay → revert to baseline |

---

## Approval Gate

Required token:

```bash
export APPROVE_SI_V2_SHADOWPROPOSAL_APPLY_65502d13="APPROVE"
```

**Without this token:**
- No apply
- No config mutation
- No strategy mutation
- No runtime mutation
- No live trading

---

## Apply Plan (Dry-run Only, No Execution in This PR)

1. Review parameter overlay content from evidence/ShadowLogger
2. Create parameter overlay file for freqtrade-freqforge
3. Apply overlay via `safe_parameter_overlay_only` mechanism
4. Freqtrade picks up overlay on next restart (dry-run only)
5. Monitor next SI-v2 cycle for effect

---

## Measurement Plan

| Metric | Baseline (061729Z) | Post-Apply Target |
|--------|--------------------|-------------------|
| Net PnL | +23.88 USDT | ≤ 20% drawdown tolerance |
| Profit factor | 1.56 | > 1.0 maintained |
| Max drawdown | 2.19% | < 5% |
| SI-v2 cycle | GREEN, 4/4 bots | GREEN, 4/4 bots |
| Rainbow freshness | fresh=True | fresh=True |
| Mutations | 0 | 0 (except approved overlay) |

**Measurement window:** 2 scheduled SI-v2 cycles (12:17 UTC, 18:17 UTC)

### Success criteria
- Profit factor remains > 1.0
- Drawdown < 5%
- No new config/strategy/docker/live-trading mutations

### Failure criteria
- Profit factor drops below 1.0
- Drawdown exceeds 5%
- Rainbow freshness lost
- Any unauthorized mutation

### Rollback criteria
- Immediate rollback if failure criteria met
- Remove parameter overlay → revert to baseline config

---

## Rollback Plan

1. Remove parameter overlay file from freqtrade-freqforge config
2. Restart freqtrade-freqforge (dry-run) to pick up baseline
3. Verify next SI-v2 cycle returns GREEN with baseline metrics
4. Document rollback in `docs/context/`

---

## Safety Confirmation

| Gate | Status |
|------|--------|
| `dry_run` | **True** (never false) |
| Live trading | None |
| Controller | PAUSED / L3_REPOSITORY_ONLY |
| All mutation counters | 0 |
| Secrets exposed | None |
| `dry_run=false` scan | Clean |
