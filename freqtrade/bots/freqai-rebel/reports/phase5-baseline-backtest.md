# Phase 5 — freqai-rebel Baseline Backtest

## Scope
Controlled baseline backtest. No optimization, no feature changes, no label changes.

## Config
- FreqAI model: RebelXGBoostClassifier
- Identifier: rebel-liquidation-v1-wrapper-n80-es20
- Exchange: Bitget futures, isolated margin
- dry_run: true
- Pairs: BTC/USDT:USDT, ETH/USDT:USDT
- n_estimators: 80
- early_stopping_rounds: 20
- DI_threshold: 0.9
- train_period_days: 30
- Timerange: 2026-04-14 to 2026-05-14 (30 days)

## Results

### Strategy Summary
```
Trades:           3 (0.1/day)
Winrate:          0% (0W / 0D / 3L)
Avg Profit:       -0.49%
Total Profit:     -0.693 USDT (-0.07%)
Profit Factor:    0.00 (no wins)
Max Drawdown:     0.693 USDT (0.07%)
Avg Duration:     17 min
Sharpe:           -3.66
Market Change:    +1.06%
```

### Pair Breakdown
```
BTC/USDT:USDT:  0 trades
ETH/USDT:USDT:  3 trades, -0.693 USDT (-0.07%)
```

### Exit Reasons
```
exit_signal:  3 trades (100%)
```

### Training Quality
```
BTC: Early stopping triggered, stopped early
ETH: ~26 rounds, logloss improved then plateaued
NaN drops: within acceptable range
```

## Interpretation

### The Good
- Pipeline works: training, prediction, signal gate all functional
- Early stopping works: no more 200-round overfitting
- Drawdown minimal: 0.07% (very conservative)
- No crashes, no KeyErrors

### The Bad
- **3 trades in 30 days** = extremely conservative
- **0% winrate** = all 3 trades lost
- **Profit factor 0.00** = no winning trades at all
- **Market +1.06%** but strategy -0.07% = missed the trend

### Root Cause
The label threshold `close.shift(-12) > close * 1.005` (+0.5% in 1h)
creates ~93:7 class imbalance. DI_threshold=0.9 further filters out
almost all signals. Combined result: nearly zero "up" predictions reach
the strategy, and the few that do are wrong.

## Conclusion
The infrastructure is solid but the signal quality is effectively zero.
The model almost never predicts "up", and when it does, it's incorrect.

This is NOT an infrastructure problem. It is a **label/target design problem**.

## Next Step
Phase 6: Target/Label Redesign
- Reduce threshold from 1.005 to 1.002 (0.2% instead of 0.5% in 1h)
- Or use percentile-based labeling (top 30% = "up")
- Or use continuous return target
- Requires approval to modify RebelLiquidation.py
