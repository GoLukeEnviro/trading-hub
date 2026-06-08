# Backtest Report — Regime-Hybrid R:R Fix — 2026-06-07

## 1. Run metadata
- **Focus topic:** Regime-Hybrid R:R exit geometry & entry filter refinement
- **Lookback / timerange:** 20260401-20260501
- **Container:** `trading-freqtrade-regime-hybrid-1`
- **Wallet:** 1000 USDT (dry-run)
- **Validity note:** 30-day window only. Preferred 90-180 day validation is still missing, so this is a comparative dry-run benchmark, not a deployment gate.
- **Raw artefacts:**
  - `freqtrade/bots/regime-hybrid/user_data/backtest_results/self_improvement/20260607-regime-hybrid-rr-fix/`
  - `var/trading-self-improvement/runs/20260607-regime-hybrid-rr-fix/`

## 2. Results table

| Variant | Strategy | Trades | Winrate | PF | Net Profit (USDT) | R:R | Max DD | Long | Short |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A | `RegimeSwitchingHybrid_v7_v04_Integration` | 71 | 42.25% | 0.4255 | -8.9997 | 0.58:1 | 0.9727% | 44 | 27 |
| B | `RegimeSwitchingHybrid_v8_1_RRR` | 162 | 60.49% | 0.9372 | -1.5352 | 0.61:1 | 0.4521% | 162 | 0 |
| C | `RegimeSwitchingHybrid_v8_2_RRR` | 162 | 60.49% | 0.9372 | -1.5352 | 0.61:1 | 0.4521% | 162 | 0 |
| D | `RegimeSwitchingHybrid_v8_3_Filter` | 105 | 59.05% | 0.9967 | -0.0523 | 0.69:1 | 0.2933% | 105 | 0 |

## 3. Interpretation
- Baseline **A** is clearly the weakest of the four: low PF, negative PnL, and the worst drawdown profile.
- Variants **B** and **C** are effectively identical on this window; widening the stop from 1% to 1.5% and nudging ROI from 2.0% to 2.5% did **not** produce a measurable edge change.
- Variant **D** is the best outcome: it has the highest PF, best R:R, lowest drawdown, and almost exactly break-even PnL.
- The gap between **B/C** and **D** says the bottleneck is **entry quality**, not stoploss width.
- None of the simplified variants crosses PF > 1.0, so the strategy is **improved but not solved**.

## 4. Exit / trade mix notes
- The current baseline is the only variant with short side + trailing/custom-stoploss behavior.
- The simplified v8 family is long-only and materially cleaner.
- Stop-loss hits drop from **56.34%** on the baseline to about **37%** on the simplified variants.
- The tight-entry variant **D** reduces stop-loss pressure further while also reducing drawdown.
- This is enough to justify a conservative follow-up branch, but **not** enough for automated promotion.

## 5. Proposals

### Proposal 1 — SI-20260607-regime-hybrid-rr-fix-1
- **Scope:** Regime-Hybrid exit geometry
- **Recommended change:** Use `RegimeSwitchingHybrid_v8_3_Filter` as the next proposal-only candidate branch and keep the long-only simplified geometry as the new baseline for follow-up validation.
- **Basis:** Baseline PF 0.4255 vs. best simplified PF 0.9967; variant D was the best balance of PF, R:R, drawdown, and trade count.
- **Expected effect:** Lower implementation complexity and materially better profitability profile than the current baseline; fewer moving parts should reduce exit-mode drift.
- **Risk:** Trade count is lower than the baseline, and PF is still just under 1.0. This still needs a longer validation window before any deployment discussion.

### Proposal 2 — SI-20260607-regime-hybrid-rr-fix-2
- **Scope:** Regime-Hybrid stoploss tuning
- **Recommended change:** Stop spending cycles on 1.0% vs. 1.5% stoploss widening for this branch; the evidence says stoploss width is not the dominant lever here.
- **Basis:** Variants B and C were numerically identical on all core metrics, so the stoploss/ROI widening did not move the needle.
- **Expected effect:** Saves iteration time and forces the next experiment to target entry quality / regime gating instead of exit geometry.
- **Risk:** If the market regime changes sharply, stoploss geometry may matter again; this proposal is for the current validated window only.

## 6. Approval note
**Do not auto-apply.** These are proposal-only findings and require explicit user/deployment-agent approval before any config or strategy change.