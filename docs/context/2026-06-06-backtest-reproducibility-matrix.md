# Backtest Reproducibility Matrix — 2026-06-06

## Bot/Strategy Mapping

| Bot | Container | Config Path | Strategy | Exchange | Timeframe | Pairs | Data Files | Data Ready |
|-----|-----------|-------------|----------|----------|-----------|-------|------------|------------|
| **FreqForge** | trading-freqtrade-freqforge-1 | freqforge/user_data/config.json | FreqForge_Override | bitget | 15m + 1h inf | BTC, ETH, SOL | 49 | ✅ |
| **Canary** | trading-freqtrade-freqforge-canary-1 | freqforge-canary/user_data/config.json | FreqForge_Override | bitget | 15m + 1h inf | BTC, ETH, SOL, LINK, DOT, ATOM, UNI, AAVE | **0** | ❌ |
| **Regime-Hybrid** | trading-freqtrade-regime-hybrid-1 | freqtrade/bots/regime-hybrid/user_data/config.json | RegimeSwitchingHybrid_v7_v04_Integration | bitget | 15m + 1h inf | BTC, SOL, AVAX, NEAR, ARB | 132 | ✅ |
| **FreqAI-Rebel** | trading-freqai-rebel-1 | freqtrade/bots/freqai-rebel/user_data/config.json | RebelLiquidation (+XGBoost) | bitget | 5m + 15m/1h inf | BTC, ETH | 10 | ✅ |

## Data Availability Detail

### FreqForge: ✅ Backtest-ready
- BTC/USDT:USDT 15m + 1h ✅ (1074KB)
- ETH/USDT:USDT 15m + 1h ✅
- SOL/USDT:USDT 15m + 1h ✅
- All files: May 12 2026 (modified)

### Regime-Hybrid: ✅ Backtest-ready (15m data)
- BTC 15m ✅ (2163KB), SOL ✅, AVAX ✅, NEAR ✅, ARB ✅
- All 5 pairs have 15m + 1h data
- 132 total feather files (includes extra pairs like ADA, AAVE, DOGE, DOT, LINK, XRP, OP, ATOM, APT, ETH)

### FreqAI-Rebel: ⚠️ Limited data (10 files, but sufficient)
- BTC 5m futures ✅ (1183KB)
- ETH 5m futures ✅
- Both have 15m + 1h + funding rate + mark price data
- train_period_days=60, backtest_period_days=7 — needs ~67 days of data

### Canary: ❌ NO DATA — download required before backtesting
- `freqforge-canary/user_data/data/` is EMPTY (0 files)
- 8 pairs, none have data
- Download command would be needed first

## Backtest Commands

### 1. FreqForge Smoke (Main Bot)
```bash
docker run --rm \
  -v /home/hermes/projects/trading/freqforge/user_data:/freqtrade/user_data \
  freqtradeorg/freqtrade:stable \
  backtesting -c /freqtrade/user_data/config.json \
  --strategy FreqForge_Override \
  --timerange 20260501-20260601 \
  --export trades \
  --export-filename /freqtrade/user_data/backtest_results/bt-smoke-freqforge-$(date +%Y%m%d_%H%M%S)
```

### 2. Regime-Hybrid Smoke
```bash
docker run --rm \
  -v /home/hermes/projects/trading/freqtrade/bots/regime-hybrid/user_data:/freqtrade/user_data \
  freqtradeorg/freqtrade:stable \
  backtesting -c /freqtrade/user_data/config.json \
  --strategy RegimeSwitchingHybrid_v7_v04_Integration \
  --timerange 20260501-20260601 \
  --export trades \
  --export-filename /freqtrade/user_data/backtest_results/bt-smoke-regime-$(date +%Y%m%d_%H%M%S)
```

### 3. FreqAI-Rebel Smoke (Custom Image)
```bash
docker run --rm \
  -v /home/hermes/projects/trading/freqtrade/bots/freqai-rebel/user_data:/freqtrade/user_data \
  freqtrade-freqai-rebel:custom \
  backtesting -c /freqtrade/user_data/config.json \
  --strategy RebelLiquidation \
  --timerange 20260401-20260601 \
  --export trades
```

## Pass/Fail Criteria
- ✅ Exit code = 0
- ✅ Backtest completes within 30 minutes
- ✅ Results file written to backtest_results/
- ✅ No "Data not found" errors for configured pairs
- ✅ No strategy import errors
- ❌ Fail if: missing data, import error, timerange error

## Risks & Mitigation
- **Canary**: Skip entirely (no data). Requires explicit approval for data download.
- **Rebel**: Custom image with FreqAI — could take longer due to model training.
- **Regime-Hybrid**: 5 pairs on 15m → 1 month = ~2880 candles/pair → manageable.
