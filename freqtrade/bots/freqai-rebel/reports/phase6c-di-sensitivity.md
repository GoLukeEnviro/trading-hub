# Phase 6C — DI Threshold Sensitivity

## Scope
Compare DI_threshold values with target 1.002. Timerange: 2026-04-14 to 2026-05-14.

## Results

| Metric         | DI=0.9 (Phase 6B) | DI=0.5 (Test A) | DI=0.0 (Test B) |
|----------------|:---:|:---:|:---:|
| Trades         | 4   | **0** | 4   |
| Winrate        | 25% | --    | 25% |
| Profit Factor  | 0.71| --    | 0.71|
| Total Profit   | -0.046 USDT | 0 USDT | -0.046 USDT |
| Max Drawdown   | 0.02% | 0.00% | 0.02% |
| Sharpe         | -0.37| --    | -0.37|

## Key Finding

DI_threshold is NOT the bottleneck.

- DI=0.5: 0 trades (blocks everything — model never confident enough)
- DI=0.0: identical 4 trades to DI=0.9 (no change)
- DI=0.9: 4 trades

The model predictions are so uniformly "down" that DI filtering has no effect.
The strategy entry/exit logic is the actual gate, not DI.

## Root Cause Analysis

The problem is upstream of DI:
1. Label imbalance (74:26) still causes model to predict mostly "down"
2. The strategy only enters on "up" predictions
3. With very few "up" predictions, DI is irrelevant
4. The few "up" signals that exist produce the same 4 trades regardless of DI

## Config Tested
- Target: 1.002 (+0.2% in 12 candles)
- n_estimators: 80, early_stopping: 20
- train_period: 30d
- Timerange: 2026-04-14 to 2026-05-14

## Decision
DI_threshold has no meaningful impact at current signal levels.
Keep DI=0.9 as the safe default — it provides protection without cost.

The real bottleneck is either:
1. Strategy entry logic (too restrictive)
2. Label quality (still too imbalanced)
3. Need for more training data or different features
