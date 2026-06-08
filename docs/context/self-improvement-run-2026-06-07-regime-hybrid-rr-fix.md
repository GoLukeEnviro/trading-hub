# Self-Improvement Run — 2026-06-07 — Regime-Hybrid R:R Fix

## 1. Run metadata
- **Run-ID:** 20260607-regime-hybrid-rr-fix
- **Date:** 2026-06-07
- **Focus:** Regime-Hybrid R:R exit geometry & entry filter refinement
- **Timerange:** 20260401-20260501
- **Lookback:** 30 days
- **Bots / strategies:**
  - A: `RegimeSwitchingHybrid_v7_v04_Integration`
  - B: `RegimeSwitchingHybrid_v8_1_RRR`
  - C: `RegimeSwitchingHybrid_v8_2_RRR`
  - D: `RegimeSwitchingHybrid_v8_3_Filter`
- **Data note:** 30-day April 2026 slice; this is below the preferred 90-180 day validation standard, so confidence remains moderate.

## 2. Baseline snapshot used for the run
- Current v7 baseline on this window: **71 trades**, **42.25% WR**, **PF 0.4255**, **-8.9997 USDT net**, **R:R 0.58:1**, **0.9727% max DD**.
- Stop-loss pressure is high: **56.34%** of trades exited via stop loss.
- The baseline is still long/short and carries trailing/custom-stoploss logic; the simplified variants are long-only.

## 3. Hypotheses & test plan
1. **H1:** Removing ATR / custom stoploss / trailing and simplifying the exit geometry will improve PF and lower drawdown.
2. **H2:** A slightly wider hard stoploss may reduce premature stopouts and improve net PnL relative to the tighter 1% stop.
3. **H3:** Tighter entry gating (ADX 25 / RSI 48) should cut low-quality trades and improve PF / R:R even if trade count falls.
4. **H4:** If none of the simplified variants beat the baseline on PF, the issue is structural and should shift to a deeper entry redesign.

## 4. What was executed
- Four dry-run-only backtests on the same timerange and pair universe.
- All runs were isolated to the regime-hybrid container and used the repo strategies without touching live configs.
- Raw artefacts were written under:
  - `freqtrade/bots/regime-hybrid/user_data/backtest_results/self_improvement/20260607-regime-hybrid-rr-fix/`
  - `var/trading-self-improvement/runs/20260607-regime-hybrid-rr-fix/`

## 5. Next question
Which simplified geometry is the least-bad candidate for deeper validation, and does tighter entry filtering outperform exit tinkering?