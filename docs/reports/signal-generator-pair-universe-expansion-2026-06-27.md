# Signal Generator Pair Universe Expansion — 2026-06-27

## Executive Summary

Removed hardcoded 3-pair and 7-pair bottlenecks in the AI signal generation pipeline. The sentiment collector and portfolio management node now derive their pair universe from the reviewed RiskGuard pair-universe config (`orchestrator/config/riskguard-pair-universe.json`).

## Problem

PR #377 added a configurable pair universe for RiskGuard, but the upstream AI signal generator still bottlenecked to 3 pairs:

1. **`sentiment_collector.py`**: Hardcoded `SYMBOL_MAP` with 7 pairs, missing `TICKER_MAP` and `COINGECKO_SIMPLE_URL` (pre-existing bug — references to undefined names)
2. **`portfolio_management_node.py` line 236**: Hardcoded `["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"]` sentiment loop
3. **`config.yaml`**: 7 tickers not aligned with reviewed 10-pair active universe

## Solution

### `sentiment_collector.py` — Config-driven pair loading

- Added `_load_active_pairs_from_config()` that reads `riskguard-pair-universe.json` from multiple paths (host, Docker `/app/`, relative)
- `TICKER_MAP` (pair → CoinGecko ID), `SYMBOL_MAP` (pair → Bitget ticker), and `COINGECKO_SIMPLE_URL` are now built dynamically from `ACTIVE_PAIRS`
- Fallback to `["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"]` if config is missing/invalid
- Fixes pre-existing bug: `TICKER_MAP` and `COINGECKO_SIMPLE_URL` were referenced but never defined

### `portfolio_management_node.py` — Config-driven sentiment loop

- Replaced hardcoded `["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"]` with `list(composites.keys())`
- Iterates over whatever pairs the sentiment data actually contains
- Fallback to BTC/ETH/SOL if `composites` is empty

### `config.yaml` — Aligned tickers

- Updated from 7 tickers (BTC, ETH, SOL, AVAX, NEAR, ARB, OP) to 10 tickers matching RiskGuard active universe
- Removed: NEAR, ARB, OP
- Added: XRP, BNB, DOGE, ADA, TRX, LINK

### `pair_universe.py` — New helper functions

- `pair_to_base()` — Convert `BTC/USDT:USDT` → `BTC`
- `pair_to_bitget_ticker()` — Convert `BTC/USDT:USDT` → `BTCUSDT`
- `pair_to_coingecko_id()` — Convert `BTC/USDT:USDT` → `bitcoin`
- `get_active_tickers()` — List of base tickers from active universe
- `get_active_coingecko_ids()` — Dict of pair → CoinGecko ID
- `build_coingecko_url()` — Dynamic CoinGecko API URL
- `COINGECKO_ID_MAP` — 20 base tickers mapped to CoinGecko coin IDs

## Test Results

```
tests/test_pair_universe.py: 22 passed
tests/test_signal_pair_universe.py: 17 passed
Full test suite: 408 passed, 1 skipped, 0 failed
SI-v2 controlled apply tests: 181 passed
Compile check: ALL COMPILE OK
```

## Safety

- No live trading, no `dry_run=false`, no `execute_apply`
- No runtime config mutation (config.yaml is tracked source, not runtime bot config)
- No Docker changes, no cron changes
- Fallback to safe BTC/ETH/SOL baseline if config is missing
- No secrets exposed