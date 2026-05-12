# Phase 42 — Fleet Rescue Operation (May 11, 2026)

## Background

Luke demanded: "Alle Freqtrade-Instanzen müssen profitabel laufen. Fixe alles systematisch."

## Fleet Discovery (6 containers, 5 traders)

| # | Container | Strategy | Port | Uptime |
|---|-----------|----------|------|--------|
| 1 | freqtrade-rsi | RSIMeanReversionV11 | 8081→8080 | 20h |
| 2 | freqtrade-momentum | MomentumBG15_v1 | 8084→8082 | 2d |
| 3 | freqtrade-regime-hybrid | RegimeSwitchingHybrid_v7_v04_Integration | 8085 | 27h |
| 4 | freqtrade-freqforge | FreqForge_Override | 8086 | 17h |
| 5 | freqtrade-sve | SessionVolExpansion | - | Just started |
| 6 | freqtrade-webserver | (utility) | - | 20h |

## Pre-Fix Trade Statistics

| Bot | Trades | PnL% | WR% | Exit Breakdown |
|-----|--------|------|-----|----------------|
| RSI | **0** | 0% | N/A | Silent Failure (20h) |
| Momentum | 9 | -0.09% | 55.6% | ROI +5.45 / SL -14.49 (8 shorts, 1 long) |
| Regime-Hybrid | 33 | -0.015% | 78.8% | ROI +4.72 / Trailing -3.73 / ExitSig -2.49 |
| FreqForge | 7 | **+0.087%** | 100% | ROI only (7/7) |
| SVE | 0 | 0% | N/A | Just started |

## Root Cause Analysis

### 1. RSI — Silent Failure (0 Trades)
- **Root Cause:** `use_ema_trend_filter = True` with EMA197 period
- Entry required ALL: `close > EMA197` + `close <= BB_Lower` + `RSI < 35` + `Stoch_K < 25` + crossover
- In sideways market, the EMA197 guard blocks EVERY entry even when oversold conditions fire
- Joint probability effectively 0 on 15m timeframe

### 2. Momentum — RR Death Spiral
- **Root Cause:** SL -3% vs ROI 1% → R:R = 1:3 → needs 75% WR → actual 55.6%
- SL exits total -14.49 USDT destroys ROI gains +5.45 USDT → net -9.04 USDT
- 8/9 trades were shorts in a neutral market
- V2 refactor already existed (SL -1.8%, ROI 2.5%→1.5%→0.8%) but was not deployed

### 3. Regime-Hybrid — Trailing Profit Killer
- **Root Cause:** `trailing_stop = True` + `use_custom_stoploss = True`
- 8 trailing exits avg -0.47% ate all 20 ROI wins avg +0.24%
- FreqForge uses IDENTICAL ROI/stoploss table but with `trailing_stop = False` → 100% WR
- ATR-based custom stoploss was prematurely exiting with losses

### 4. FreqForge — The Reference
- Clean Baseline from Phase 41: stoploss -9%, ROI 8.5%→4.5%→2%→0%
- Key difference from Regime-Hybrid: `trailing_stop = False`, `use_custom_stoploss = False`, `can_short = False`
- Proves the ROI/SL table works — trailing was the sole destroyer

## Fixes Applied

### RSI (Line ~77)
```
use_ema_trend_filter = BooleanParameter(default=True, ...)
→ use_ema_trend_filter = BooleanParameter(default=False, ...)
```
Result: Entry gate open. Verified: `use_ema_trend_filter = False` in logs.

### Momentum (Full file overwrite)
```
momentum_bg15_v1.py ← MomentumBG15_v2_RRRefactor.py content
Class name kept: MomentumBG15_v1 (matches --strategy CLI arg)
stoploss: -0.03 → -0.018
minimal_roi: {'0': 0.01, '30': 0.005} → {'0': 0.025, '45': 0.015, '120': 0.008, '240': 0}
```
Result: R:R 1:1.8, verified in logs.

### Regime-Hybrid (Lines 66, 65, 61)
```
trailing_stop = True → trailing_stop = False
use_custom_stoploss = True → use_custom_stoploss = False
can_short = True → can_short = False
```
Result: Matches FreqForge config pattern. Verified in logs.

## Post-Fix Verification

All 3 bots confirmed RUNNING with correct parameters loaded from strategy files. No startup errors.

## Next Steps

1. **24h Observation Period** — Monitor trade generation and profitability
2. **If RSI still 0 trades after 24h** → Widen RSI threshold to 40, check pair whitelist
3. **Deploy FreqForge strategy as fleet standard** if its profitability holds over 30+ trades
4. **LLM Exit Layer** only after baseline profitability is confirmed

## Fleet Priority Matrix

| Priority | Bot | Action | ETA |
|----------|-----|--------|-----|
| 🔴 P0 | RSI → Trades or not | 24h observe | May 12 |
| 🟡 P1 | Momentum v2 → Profitable? | 24h observe | May 12 |
| 🟡 P1 | Regime-Hybrid → Profitable? | 24h observe | May 12 |
| 🟢 P2 | FreqForge → Scale | Keep running | Ongoing |
| ⚪ P3 | SVE → Evaluate | Wait for trades | May 13 |
