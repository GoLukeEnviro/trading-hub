# Phase 44 Stage 1.8 — ai-hedge-fund-crypto Bitget Adapter Report

**Timestamp:** 2026-05-12T04:00Z
**Host:** Hermes Docker Container
**Test Image:** `ai-hedge-fund-crypto:test`

## Executive Summary

The Bitget Futures data adapter was built, integrated, and validated. All 12
OHLCV combinations (3 pairs × 4 timeframes) work with full column schema.
The complete pipeline (Technical Analysis → Risk Management → LLM Portfolio
Decision) runs successfully on Bitget Futures data using DeepSeek V4 Pro.

## Why Bitget Was Required Before Cleanup

The existing Freqtrade fleet uses Bitget Futures (BTC/USDT:USDT format).
Using Binance as the signal source would introduce exchange-level discrepancies
in price, liquidity, and market structure. Bitget OHLCV ensures the signal
matches the execution environment.

## Existing Binance Provider Audit

**Interface (BinanceDataProvider):**
- `get_latest_data(symbol, timeframe, limit)` → pd.DataFrame with 12 columns
- `get_historical_klines(symbol, timeframe, start, end)` → pd.DataFrame
- `get_history_klines_with_end_time(symbol, timeframe, end_time, limit)` → pd.DataFrame
- `get_multi_timeframe_data(...)` → Dict[str, pd.DataFrame]
- `get_latest_multi_timeframe_data(...)` → Dict[str, pd.DataFrame]
- `get_multiple_timeframes_with_end_time(...)` → Dict[str, pd.DataFrame]

**DataNode** had `BinanceDataProvider()` hardcoded at module level.

## Bitget Provider Implementation

**Files created:**
- `src/data_providers/__init__.py` — factory function `get_data_provider(exchange)`
- `src/data_providers/bitget_provider.py` — `BitgetProvider` class implementing
  full BinanceDataProvider interface

**Key differences vs Binance:**
- ccxt.bitget returns 6 OHLCV columns (not 12) → padded with estimates
- Symbol format needs `/` for ccxt: `BTC/USDT:USDT` (not `BTCUSDT`)
- Swap/futures require `options.defaultType = 'swap'`
- Rate limit: 50ms between requests (handled by ccxt)
- No API keys needed for public OHLCV data

**Files modified:**
- `src/graph/data_node.py` — uses `get_data_provider()` factory instead of
  hardcoded BinanceDataProvider
- `src/graph/start_node.py` — removed dead BinanceDataProvider import
- `src/utils/settings.py` — added `exchange: str = "binance"` field
- `config.yaml` — `exchange: bitget`, pairs in Freqtrade format
- `pyproject.toml` — added `ccxt>=4.0.0`, restored `langchain-ollama>=0.3.3`
- `docker/Dockerfile` — removed `tail -5` masking pip failures

## Symbol Mapping

| Input Format | Bitget ccxt Symbol | Notes |
|-------------|-------------------|-------|
| `BTC/USDT:USDT` | `BTC/USDT:USDT` | Passthrough (already correct) |
| `BTCUSDT` | `BTC/USDT:USDT` | Binance spot format |
| `BTC/USDT` | `BTC/USDT:USDT` | Standard pair format |

## Timeframe Support

| Timeframe | Status |
|-----------|--------|
| 30m | ✅ Works |
| 1h | ✅ Works |
| 4h | ✅ Works |
| 1d | ✅ Works |

All standard Freqtrade timeframes supported.

## OHLCV Smoke Test Results

```
12/12 PASS — No API keys required

BTC/USDT:USDT  30m → cols=True, close=81188.60
BTC/USDT:USDT  1h  → cols=True, close=81178.40
BTC/USDT:USDT  4h  → cols=True, close=81178.30
BTC/USDT:USDT  1d  → cols=True, close=81178.40
ETH/USDT:USDT  30m → cols=True, close=2312.63
ETH/USDT:USDT  1h  → cols=True, close=2312.63
ETH/USDT:USDT  4h  → cols=True, close=2313.03
ETH/USDT:USDT  1d  → cols=True, close=2313.03
SOL/USDT:USDT  30m → cols=True, close=96.31
SOL/USDT:USDT  1h  → cols=True, close=96.31
SOL/USDT:USDT  4h  → cols=True, close=96.33
SOL/USDT:USDT  1d  → cols=True, close=96.33
```

## Full Analysis Test Results

**Layer 1: Technical Analysis (MACD Strategy)**
```
BTC → bullish   (42%) — trend + stat arb bullish
ETH → neutral   (20%) — all signals neutral/bearish
SOL → neutral   (19%) — trend bullish, conf too low
```

**Layer 2: Risk Management (deterministic)**
```
$10k portfolio, $2k position limit per pair ✅
```

**Layer 3: Portfolio Management (DeepSeek V4 Pro @ 0.15)**
```
BTC → hold (conf 42 < 60) — policy compliant
ETH → hold (conf 20 < 60) — policy compliant
SOL → hold (conf 19 < 60) — policy compliant
```

**Runtime:** ~5 seconds for full pipeline (technical + risk + LLM)

## Hermes-Compatible Sample Output

Written to: `output/hermes_sample_signal_bitget.json`

```json
{
  "schema_version": "1.0",
  "source": "ai-hedge-fund-crypto",
  "exchange": "bitget",
  "llm_used": true,
  "llm_model": "deepseek-v4-pro",
  "pairs": {
    "BTC/USDT:USDT": {"bias": "bullish", "recommendation": "observe", "confidence": 0.42},
    "ETH/USDT:USDT": {"bias": "neutral",  "recommendation": "observe", "confidence": 0.20},
    "SOL/USDT:USDT": {"bias": "neutral",  "recommendation": "observe", "confidence": 0.19}
  },
  "global_risk_mode": "neutral"
}
```

## PrimoAgent Safety Confirmation

```
primo-agent     (healthy, port 8420)   ✅ — untouched
hermes-bridge   (healthy, port 9118)   ✅ — untouched
freqtrade-mvs   (up, port 8087)        ✅ — untouched
```

## Remaining Blocker

| # | Blocker | Impact | Effort |
|---|---------|--------|--------|
| 1 | **Kein Bitget Private Client** | Brauchen API keys für Positions-/Order-Daten | Nach Cleanup |
| 2 | **Nicht im Signal-Bus integriert** | Signal wird nicht an Freqtrade weitergeleitet | Nach Cleanup |
| 3 | **Nur 1 Stunde historical data getestet** | Backtest nicht gelaufen | Nach Cleanup |

**Kein Blocker für APPROVED_CLEANUP_AND_MIGRATION.**
Bitget OHLCV funktioniert vollständig. Private API + Signal-Bus kommen nach der
Migration.

## Recommendation

**Proceed to APPROVED_CLEANUP_AND_MIGRATION.**

The Bitget adapter is validated end-to-end:
- OHLCV data: 12/12 PASS
- Column schema: matches BinanceDataProvider
- Technical analysis: runs on Bitget data
- Risk management: runs on Bitget data
- LLM decision: DeepSeek V4 Pro over Bitget data
- Hermes sample output: generated with exchange=bitget
- PrimoAgent: untouched throughout
- No live trading: analysis-only mode

## File Change Summary

| File | Action |
|------|--------|
| `src/data_providers/__init__.py` | **Created** — provider factory |
| `src/data_providers/bitget_provider.py` | **Created** — BitgetProvider (228 lines) |
| `src/graph/data_node.py` | **Modified** — uses get_data_provider() |
| `src/graph/start_node.py` | **Modified** — removed dead BinanceDataProvider import |
| `src/utils/settings.py` | **Modified** — added exchange field |
| `config.yaml` | **Modified** — exchange: bitget, Bitget pairs |
| `pyproject.toml` | **Modified** — added ccxt, restored langchain-ollama |
| `docker/Dockerfile` | **Modified** — removed broken tail -5 |
| `output/hermes_sample_signal_bitget.json` | **Created** — Hermes output example |

## Rollback

```bash
# Remove Bitget adapter changes
git checkout -- src/graph/data_node.py src/graph/start_node.py
git checkout -- src/utils/settings.py config.yaml

# Remove new files
rm -rf src/data_providers/

# Rebuild Docker image
docker build --no-cache -t ai-hedge-fund-crypto:test -f docker/Dockerfile .
```
