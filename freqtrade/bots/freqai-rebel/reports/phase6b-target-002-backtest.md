# Phase 6B — freqai-rebel Target 1.002 Backtest

## Scope
Controlled backtest after minimal target redesign. Timerange: 2026-04-14 to 2026-05-14 (30 days).

## Comparison Against Phase 5

| Metric         | Phase 5 (1.005) | Phase 6B (1.002) | Delta        |
|----------------|:---:|:---:|:---:|
| Trades         | 3   | 4   | +1 (+33%) |
| Winrate        | 0%  | 25% | +25pp |
| Profit Factor  | 0.00| 0.71 | +0.71 |
| Total Profit   | -0.693 USDT (-0.07%) | -0.046 USDT (-0.00%) | +93% better |
| Max Drawdown   | 0.07% | 0.02% | 3.5x lower |
| Sharpe         | -3.66| -0.37 | +3.29 |
| Avg Duration   | 17 min | 6 min | -65% faster |
| Market Change  | +1.06%| +1.06%| same |

## Pair Breakdown

| Pair           | Trades | Avg Profit | Tot Profit | Winrate |
|----------------|:---:|:---:|:---:|:---:|
| BTC/USDT:USDT  | 2     | +0.12% | +0.106 USDT | 50% (1W/1L) |
| ETH/USDT:USDT  | 2     | -0.16% | -0.152 USDT | 0% (0W/2L) |

## Config
- Target: 1.002 (+0.2% in 12 candles)
- Identifier: rebel-liquidation-v1-wrapper-n80-es20-t002
- n_estimators: 80, early_stopping_rounds: 20
- DI_threshold: 0.9, train_period: 30d
- Bitget futures, isolated, dry_run

## Interpretation

### Improvement
- Profit factor 0.00 → 0.71 (no longer zero)
- Winrate 0% → 25% (at least 1 win now)
- Drawdown reduced from 0.07% to 0.02%
- BTC pair is net positive (+0.106 USDT)
- Sharpe improved from -3.66 to -0.37

### Remaining Issues
- Still only 4 trades in 30 days (0.13/day) — very low
- ETH still unprofitable (0% winrate)
- Profit factor 0.71 < 1.0 — still net negative
- Trade count barely moved (3 → 4)
- DI_threshold=0.9 still filtering most signals

### Root Cause
The target 1.002 improved label distribution but DI_threshold=0.9 is still
blocking most predictions. The model produces very few signals that pass
the DI gate. Combined with still-imbalanced labels (74:26), the classifier
remains conservative.

## Next Step
Consider DI_threshold reduction (0.9 → 0.5 or 0.0) to test if signal
volume increases without quality degradation. This is a config-only change,
no strategy modification needed.
