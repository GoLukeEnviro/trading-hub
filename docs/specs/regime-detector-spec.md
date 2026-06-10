# Regime Detector Specification v1.0

**Status:** Production-ready core component  
**Owner:** Self-Improvement Intelligence Layer  
**Last updated:** 2026-06-10

## Purpose

Provides regime-aware context to the Rainbow Intelligence Engine and the Self-Improvement Meta-Learner.

Without regime detection, signal weights are static and perform poorly across different market conditions (trending vs ranging vs choppy).

## Supported Regimes

| Regime              | Description                          | Typical Behavior                  | Recommended Weight Multiplier |
|---------------------|--------------------------------------|-----------------------------------|-------------------------------|
| `strong_trend_up`   | Clear bullish trend (ADX > 25)      | Trend-following works well       | 1.15                         |
| `strong_trend_down` | Clear bearish trend                 | Short bias or reduced exposure   | 0.85                         |
| `weak_trend_up`     | Mild bullish movement               | Cautious long bias               | 1.05                         |
| `weak_trend_down`   | Mild bearish movement               | Cautious short / flat            | 0.95                         |
| `ranging`           | Sideways market (low ADX)           | Mean-reversion / tight filters   | 0.80                         |
| `high_volatility`   | High ATR, unclear direction         | Reduce position size             | 0.70                         |
| `choppy`            | High vol + low ADX (whipsaw)        | Very conservative or pause       | 0.60                         |

## Implementation

- File: `intelligence/regime_detector.py`
- Core function: `detect_regime(df)`
- Inputs: OHLCV DataFrame (15m or 1h recommended)
- Outputs: regime label + confidence + metrics (ADX, ATR%, EMA slope)

## Integration Points

1. **RainbowScorer** (ai4trade-bot)
   - Attach regime to every `CryptoSignal`
   - Use regime-specific weights in Rainbow Engine

2. **Meta-Learner** (trading-hub)
   - Performance attribution per regime
   - Weight updates become regime-aware

3. **Shadowlock** 
   - Log regime at signal generation and trade entry/exit

## Next Evolution (v2)

- Add HMM or simple ML classifier for smoother regime transitions
- Multi-timeframe regime consensus
- Regime change detection + cooldown

## Safety

- Always fall back to `ranging` if confidence < 0.5
- Never use regime to increase leverage — only to modulate existing risk parameters
