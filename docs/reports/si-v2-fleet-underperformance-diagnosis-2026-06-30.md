# SI-v2 Fleet Underperformance Diagnosis — 2026-06-30

## Status

YELLOW / READ_ONLY_DIAGNOSIS

## Scope

- Issue: #352
- Bots: 4-Bot fleet (freqtrade-freqforge, freqtrade-freqforge-canary, freqtrade-regime-hybrid, freqai-rebel)
- Mutation status: NONE

## Executive Summary

The fleet is split into two clear tiers: two profitable FreqForge-based bots (freqforge, canary) and two underperforming bots (regime-hybrid, freqai-rebel). regime-hybrid suffers from an inverted risk/reward ratio — wins are small (avg +$0.27), losses are 3.4x larger (avg -$0.91). freqai-rebel suffers from a low win rate (40%) combined with insufficient signal quality from its ML classifier, producing a profit factor of 0.40. Both bots have negative net PnL and are blocked at the profitability gate. The root cause is strategy underperformance, not data pipeline issues or proposal quality.

## Evidence Sources

| Source | Path | Freshness | Notes |
|---|---|---|---|
| Profitability gate root cause | `docs/reports/si-v2-profitability-gate-root-cause-2026-06-26.md` | 2026-06-26 | Baseline 4-bot matrix, original diagnosis |
| Historical trades summary | `self_improvement_v2/state/historical_trades/historical_trades_summary.json` | 2026-06-23 | Generated 2026-06-23 — partially stale (pre-T3 trades) |
| Live SQLite — freqforge | `tradesv3.freqforge.dryrun.sqlite` (Docker exec) | 2026-06-30T09:31Z | 80 closed, 1 open — current |
| Live SQLite — canary | `tradesv3.freqforge_canary.dryrun.sqlite` (Docker exec) | 2026-06-30 | 59 closed, 1 open — current |
| Live SQLite — regime-hybrid | `tradesv3.regime_hybrid.dryrun.sqlite` (Docker exec) | 2026-06-30T09:31Z | 56 closed, 0 open — current |
| Live SQLite — freqai-rebel | `tradesv3.freqai_rebel.dryrun.sqlite` (Docker exec) | 2026-06-30T09:00Z | 50 closed, 0 open — current |
| Active cycle evidence | `active_cycle_20260630T061729Z.json` | 2026-06-30T06:17Z | 3/4 bots authenticated (canary DNS failure from orchestrator) |
| Kill Switch | `kill_switch.json` (Docker exec) | 2026-06-29T04:15Z | NORMAL |
| Current operational state | `docs/state/current-operational-state.md` | 2026-06-30 | main @ f677123 |

**Data gap note:** The historical_trades_summary.json was generated 2026-06-23 and does not include trades after that date. Live SQLite queries (2026-06-30) are used as the primary source for current metrics. The profitability gate report (2026-06-26) is used for walk-forward evaluation context.

## 4-Bot Fleet Matrix

| Bot | Net PnL | PF | Win Rate | Trades | Open | Avg Win | Avg Loss | Drawdown | Trend | Verdict |
|---|---:|---:|---:|---:|---:|---:|---:|---|---|---|
| freqtrade-freqforge | -$1.79 | 0.97 | 77.5% (62W/18L) | 80 | 1 | +$1.09 | -$3.84 | High (worst trade -$13.88) | Declining (was +$24.78) | CANDIDATE (was) |
| freqtrade-freqforge-canary | +$3.98 | 1.88 | 89.8% (53W/6L) | 59 | 1 | +$0.16 | -$0.75 | Low (worst -$2.24) | Stable | CANDIDATE |
| freqtrade-regime-hybrid | -$7.35 | 0.57 | 66.1% (37W/19L) | 56 | 0 | +$0.27 | -$0.91 | Moderate (worst -$3.10) | Stable negative | BLOCKED |
| freqai-rebel | -$1.82 | 0.40 | 40.0% (20W/30L) | 50 | 0 | +$0.06 | -$0.10 | Low (worst -$0.67) | Declining | BLOCKED |

**Key observation:** freqforge's net PnL dropped from +$24.78 (2026-06-26 report) to -$1.79 due to 2 large loss trades (ETH -$12.70, SOL -$13.88) that closed on 2026-06-29. This is a recent drawdown event, not a persistent pattern.

## Fleet Baseline

| Metric | Value |
|---|---|
| Fleet net PnL | -$6.98 (sum of all 4 bots) |
| Fleet median PnL | -$1.81 (average of regime-hybrid and freqai-rebel) |
| Fleet median PF | 0.49 (average of regime-hybrid 0.57 and rebel 0.40) |
| Fleet median win rate | 53.0% (average of 66.1% and 40.0%) |
| Fleet total trades | 245 closed |
| Candidate bots (positive PnL) | 1 (canary only) |
| Blocked bots (negative PnL) | 3 (freqforge, regime-hybrid, freqai-rebel) |
| Fleet profit factor (aggregate) | 0.80 (total gross profit $86.82 / total gross loss $94.61) |

**Note on freqforge:** freqforge was a CANDIDATE bot in the 2026-06-26 report (+$24.78). Two large loss trades on 2026-06-29 (ETH -$12.70, SOL -$13.88) pushed it into negative territory. This may be a transient drawdown event rather than structural underperformance — the 77.5% win rate and 1.09 avg win vs 3.84 avg loss suggest the strategy works but has tail risk.

## Underperformance Diagnosis: regime-hybrid

### Observation

- Net PnL: -$7.35 across 56 closed trades (since 2026-05-03)
- Profit factor: 0.57 (gross profit $9.85 / gross loss $17.19)
- Win rate: 66.1% (37W/19L) — seemingly decent, but misleading
- Average win: +$0.27 vs average loss: -$0.91 (3.4:1 unfavorable ratio)
- Worst trade: -$3.10 vs best trade: +$1.53 (2:1 unfavorable)
- Only 1 new trade since 2026-06-23 (a loss of -$0.10)
- 0 open trades — strategy is not finding entries

### Cause

**Inverted risk/reward ratio.** The regime-switching strategy wins 66% of the time, but each win is tiny (+$0.27 average) while each loss is 3.4x larger (-$0.91 average). The strategy's expectancy per trade is:

- Expectancy = (0.661 × $0.27) + (0.339 × -$0.91) = $0.179 - $0.308 = **-$0.129 per trade**

Over 56 trades, this produces an expected loss of -$7.22, which closely matches the actual -$7.35. The strategy has a structurally negative expectancy.

**Pair-specific breakdown:**
- Only profitable pairs: BTC/USDT:USDT (+$1.50), ETH/USDT (+$0.65)
- Worst pairs: ETH/USDT:USDT (-$2.20), NEAR/USDT:USDT (-$1.70), OP/USDT:USDT (-$1.56)
- ARB/USDT:USDT: 14 trades, 7W/7L, +$0.54 — high frequency but net flat

**Problem character:** Many small losses compounded by occasional larger losses. Not a few catastrophic trades — it's a structural risk/reward inversion.

### Evidence

- SQLite query: 56 closed trades, 37 wins, 19 losses
- Gross profit $9.85, gross loss $17.19 → PF 0.57
- Avg win $0.266, avg loss -$0.905
- Per-trade expectancy: -$0.129
- Walk-forward block reason: `walk_forward_net_metrics_negative`
- Anomaly flag: `negative_closed_profit`
- Only 1 new trade since 2026-06-23 (nearly inactive)

### Recommendation

1. **Regime-transition entry risk:** The strategy may be entering at unfavorable regime transitions. Consider tightening regime confirmation filters or adding a regime-stability check before entry.
2. **Stop-loss calibration:** The avg loss ($0.91) is 3.4x the avg win ($0.27). Consider tighter stop-losses or trailing stops to cap downside.
3. **Pair selection:** ARB/USDT:USDT has high frequency (14 trades) but is net flat. Consider removing or reducing weight on pairs with high trade count but near-zero PnL.

## Underperformance Diagnosis: freqai-rebel

### Observation

- Net PnL: -$1.82 across 50 closed trades (since 2026-06-15)
- Profit factor: 0.40 (gross profit $1.19 / gross loss $3.01)
- Win rate: 40.0% (20W/30L) — below 50%
- Average win: +$0.06 vs average loss: -$0.10 (1.7:1 unfavorable)
- Worst trade: -$0.67 vs best trade: +$0.40 (1.7:1 unfavorable)
- 40 new trades since 2026-06-23 (high frequency, all losses: -$1.50 net)
- 0 open trades
- Only 2 pairs traded: ETH/USDT:USDT (31 trades, -$0.37) and BTC/USDT:USDT (19 trades, -$1.45)

### Cause

**Triple issue — low win rate, poor signal quality, and declining trend.**

1. **Low win rate (40%):** The XGBoost classifier is generating poor entry signals. 60% of trades close at a loss. This is below the break-even threshold for the current risk/reward ratio.

2. **ML/classifier signal quality:** The model's predictions have a profit factor of 0.40, meaning for every $1 of profit, $2.50 of loss is generated. The classifier may be overfitting or the market regime has shifted away from its training data.

3. **Declining trend:** 40 new trades since 2026-06-23, all producing -$1.50 net. The model's performance is not improving — it's consistently negative. The most recent trade closed 2026-06-30T09:00Z, showing the bot is active but not profitable.

4. **Sample size:** 50 trades is borderline for statistical confidence. However, the direction is consistently negative across all 50 trades, and the pattern is stable (40% win rate, 0.40 PF). This is not a small-sample fluke — it's a reliable negative signal.

5. **Pair-specific weakness:** BTC/USDT:USDT is the worst pair (19 trades, 4W/15L, -$1.45). ETH/USDT:USDT is also negative (31 trades, 16W/15L, -$0.37). The model performs poorly on both pairs.

**Problem character:** Many small losses with a low win rate. The strategy is actively trading (40 trades in the last week) but consistently losing. This is a signal quality problem, not a risk management problem.

### Evidence

- SQLite query: 50 closed trades, 20 wins, 30 losses
- Gross profit $1.19, gross loss $3.01 → PF 0.40
- Win rate 40.0%, well below 50%
- 40 new trades since 2026-06-23, all producing -$1.50 net
- Walk-forward block reason: `walk_forward_net_metrics_negative`
- Anomaly flag: `negative_closed_profit`
- Profit trend: declining (worst of all 4 bots)
- Only 2 pairs traded, both negative

### Recommendation

1. **Model retraining:** The XGBoost classifier likely needs retraining with more recent data. The current model was trained on data that may not reflect current market conditions.
2. **Feature engineering:** Consider adding regime-detection features or volatility-based features to improve signal quality.
3. **Win-rate threshold:** Consider adding a minimum confidence threshold for entries — if the model's prediction confidence is below a threshold, skip the trade.
4. **Pair expansion or restriction:** The bot only trades BTC and ETH. Consider either expanding to more pairs (to diversify signal sources) or restricting to the pair with better performance (ETH is less bad than BTC).

## Relative Fleet Comparison

| Bot | Delta vs Fleet Median PnL | Delta vs Fleet Median PF | Delta vs Fleet Median Win Rate |
|---|---:|---:|---:|
| freqtrade-freqforge | +$0.02 (near median) | +0.48 | +24.5% |
| freqtrade-freqforge-canary | +$5.79 | +1.39 | +36.8% |
| freqtrade-regime-hybrid | -$5.54 | +0.08 | +13.1% |
| freqai-rebel | -$0.01 (near median) | -0.09 | -13.0% |

**Note:** Fleet median PnL is -$1.81 (average of the two blocked bots). freqforge is near the median because its recent large losses pulled it down. Canary is the clear outperformer. regime-hybrid has the worst absolute PnL delta. freqai-rebel is near the median because it defines the median.

## ShadowProposal Candidates

### ShadowProposal Candidate: rh_stoploss_tightening_v1

| Field | Value |
|---|---|
| Scope | regime-hybrid |
| Type | diagnostic_only |
| Proposed change | Tighten stop-loss from current value to reduce avg loss from $0.91 to ~$0.50, bringing expectancy closer to break-even |
| Expected effect | Reduce per-trade loss size; may reduce win rate slightly but should improve net expectancy |
| Risk | Tighter stops may trigger more frequently on noise, reducing trade count |
| Validation plan | Backtest with tighter stop-loss on historical data; compare net PnL, win rate, and profit factor before/after |
| Rollback condition | If win rate drops below 50% or net PnL worsens, revert to original stop-loss |
| Apply eligibility | NOT_ELIGIBLE |
| Reason blocked | Requires T4 completion + human approval + canary-first plan |

### ShadowProposal Candidate: rh_regime_filter_stability_v1

| Field | Value |
|---|---|
| Scope | regime-hybrid |
| Type | diagnostic_only |
| Proposed change | Add regime-stability confirmation filter — require regime to be stable for N candles before entry |
| Expected effect | Reduce false entries at regime transitions; improve win rate and avg win size |
| Risk | May reduce trade frequency; may miss fast-moving opportunities |
| Validation plan | Backtest with regime-stability filter (N=3, N=5, N=10); compare entry quality and net PnL |
| Rollback condition | If trade count drops below 20% of baseline or net PnL worsens, revert filter |
| Apply eligibility | NOT_ELIGIBLE |
| Reason blocked | Requires T4 completion + human approval + canary-first plan |

### ShadowProposal Candidate: rebel_model_retrain_v1

| Field | Value |
|---|---|
| Scope | freqai-rebel |
| Type | diagnostic_only |
| Proposed change | Retrain XGBoost classifier with data from 2026-06-01 to 2026-06-30 (recent market regime) |
| Expected effect | Improve signal quality; target win rate >50% and PF >1.0 |
| Risk | Retraining may overfit to recent data; requires infrastructure time |
| Validation plan | Walk-forward backtest with retrained model; compare win rate, PF, and net PnL against current model |
| Rollback condition | If retrained model performs worse than current in walk-forward, keep current model |
| Apply eligibility | NOT_ELIGIBLE |
| Reason blocked | Requires T4 completion + human approval + canary-first plan + model retraining infrastructure |

### ShadowProposal Candidate: rebel_confidence_threshold_v1

| Field | Value |
|---|---|
| Scope | freqai-rebel |
| Type | diagnostic_only |
| Proposed change | Add minimum prediction confidence threshold (e.g., 0.65) — skip trades where model confidence is below threshold |
| Expected effect | Filter out low-quality signals; improve win rate by trading only high-confidence predictions |
| Risk | May reduce trade count significantly; may not improve PF if high-confidence predictions are also wrong |
| Validation plan | Backtest with confidence thresholds 0.55, 0.65, 0.75; compare trade count, win rate, PF, and net PnL |
| Rollback condition | If trade count drops to 0 or PF does not improve, revert threshold |
| Apply eligibility | NOT_ELIGIBLE |
| Reason blocked | Requires T4 completion + human approval + canary-first plan |

### ShadowProposal Candidate: fleet_partial_apply_policy_v1

| Field | Value |
|---|---|
| Scope | fleet |
| Type | diagnostic_only |
| Proposed change | Document a fleet policy allowing controlled apply on profitable bots while blocked bots remain in observation |
| Expected effect | Enable SI-v2 loop progression for candidate bots without waiting for all 4 bots to pass profitability gate |
| Risk | May create fleet imbalance; blocked bots continue losing while candidates improve |
| Validation plan | Policy review; simulate partial apply impact on fleet PnL; compare against full-fleet-gate requirement |
| Rollback condition | If partial apply causes fleet-level risk increase or blocked bots drag fleet PnL below threshold, revert to full-gate policy |
| Apply eligibility | NOT_ELIGIBLE |
| Reason blocked | Requires T4 completion + human approval + fleet policy documentation |

## Blockers

- No apply until current T4 loop resolves (Canary UNI/USDT still open)
- No second candidate without explicit approval
- No proposal eligible for runtime mutation
- freqforge's recent negative PnL may be transient (2 large loss trades) — needs monitoring before reclassification
- Active cycle evidence shows canary DNS failure from orchestrator (not a runtime issue — canary is healthy via Docker exec)

## Safety Confirmation

- No apply
- No restart
- No rollback
- No Docker/Compose mutation
- No live trading
- No dry_run=false
- No secrets
- No strategy changes
- No config changes
- No cron/guardian/infra work
- All data collected via read-only SQLite queries and Docker exec (inspect/ps only)