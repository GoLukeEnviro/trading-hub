# Strategy Optimization Notes
## Starting Point: momentum_bg15_v3_1
- v3.1: 93t | 52.7% WR | -$50.00 | SL -3.0% | EMA200 trend filter
- Known profitable pairs: NEAR, AAVE, ETH, ATOM
- Known losing pairs: SOL, AVAX, ARB, OP, BTC, APT
- Problem: 6/10 pairs eat all profits from 4/10 profitable pairs
- ROI exits are 100% profitable, stoploss exits are 100% losing

## Iteration 2: Aggressive Entry Filtering (Changes 10-14)

**Diagnosis**: v3.1 had changes 6-9 (ADX>20, volume>SMA, EMA alignment, tighter ROI) but still lost -$50 across 93 trades. The filters were not aggressive enough — 52.7% WR means nearly half of entries still hit SL. The math is brutal: with 3% SL and max ~2% ROI wins, WR needs to be ~60%+ to be profitable.

**Strategy**: Since ROI exits are the ONLY profitable exits, dramatically increase entry selectivity. Accept fewer trades but much higher quality. Every bad entry filtered out is pure P&L improvement.

### CHANGE 10: Bollinger Band expansion filter
- Compute BB(20, 2.0) bandwidth = (upper - lower) / middle
- Only enter when BB width is expanding vs previous candle
- Why: Losing pairs generate signals during BB contraction/chop. Expansion confirms a genuine volatility breakout with momentum behind it. Choppy pairs (SOL, AVAX, ARB) rarely sustain expansion.

### CHANGE 11: Stronger ADX threshold (20 → 25)
- ADX ≥ 25 instead of > 20
- Why: The 20-25 ADX zone is a dead zone — signals here often false-breakout on choppy pairs. Genuine trends on profitable pairs (NEAR, AAVE) consistently show ADX ≥ 25. This single threshold bump should eliminate many losing entries.

### CHANGE 12: Volume surge (1x → 1.5x SMA)
- Volume must be ≥ 1.5x the 20-period SMA, not just above it
- Why: Volume barely above average isn't confirmation — it's noise. A 1.5x threshold ensures institutional participation and momentum conviction. Losing entries often trigger on average-volume candles with no real buying/selling pressure.

### CHANGE 13: EMA spread minimum (0.15%)
- ema_fast must be at least 0.15% above ema_slow for longs (and vice versa)
- Why: Marginal EMA alignment (fast barely above slow) produces false signals that immediately reverse. The 0.15% spread ensures the short-term momentum is actually meaningful. Losers often trigger on barely-positive spreads that flip within 1-2 candles.

### CHANGE 14: Tighter ROI table
- 0: 1.8% → 20m: 1.0% → 75m: 0.4% → 180m: 0
- Why: ROI exits are 100% profitable. Faster ROI targets mean more trades exit via ROI before they can reverse into SL. Still allows 1.8% for strong moves but provides escape hatches at tighter intervals.

### Expected impact
- Significantly fewer trades (maybe 30-50 vs 93)
- Higher WR (targeting 60%+)
- Lower total loss from SL exits
- Risk: may over-filter and miss some profitable entries on winning pairs

## Iteration 2 Results: 0 TRADES — TOTAL OVER-FILTERING

**Result**: All 10 pairs produced zero trades. The entry signal intersection was empty.

**Root cause**: RSI < 50 for longs (mean-reversion) contradicts all momentum filters (ADX≥25, BB expanding, volume 1.5x, EMA spread 0.15%, MACD rising, close>EMA200). When a strong uptrend fires all momentum signals, RSI is almost always > 50. The conditions were mutually exclusive — demanding both "strong uptrend" AND "RSI showing weakness" simultaneously.

**Secondary causes**: ADX ≥ 25, volume 1.5x, and EMA spread 0.15% were each defensible alone but together compressed the signal space to nothing.

## Iteration 3: Fix Over-Filtered Entry (Changes 15-19)

**Diagnosis**: Iteration 2's filters were individually reasonable but collectively contradictory. The RSI logic was the fatal flaw — it was a mean-reversion signal in a momentum strategy.

**Strategy**: Flip RSI to momentum confirmation, relax the three most aggressive filters back to reasonable levels, widen ROI slightly for winners.

### CHANGE 15: Flip RSI to momentum confirmation
- LONG: RSI > 50 AND RSI < 75 (was RSI < 50)
- SHORT: RSI < 50 AND RSI > 25 (was RSI > 50)
- Why: A momentum strategy needs RSI confirming the trend direction, not opposing it. RSI < 50 for longs meant "enter uptrend only during pullback" — but the other 6 filters all required the trend to be actively pushing forward. The upper bound (75 for longs, 25 for shorts) prevents entering at exhausted extremes where reversal is imminent.

### CHANGE 16: Relax ADX back to 20 (was 25)
- ADX ≥ 20 instead of ≥ 25
- Why: ADX 25 + BB expansion + volume surge + EMA spread was too many simultaneous trend-strength filters. BB expansion alone already confirms genuine volatility breakout. ADX ≥ 20 with the other filters provides sufficient trend quality.

### CHANGE 17: Relax volume to 1.2x SMA (was 1.5x)
- Volume > 1.2x SMA instead of 1.5x
- Why: 1.5x was too strict combined with BB expansion and ADX. 1.2x still confirms above-average participation without being as restrictive.

### CHANGE 18: Reduce EMA spread to 0.05% (was 0.15%)
- EMA spread ≥ 0.05% instead of 0.15%
- Why: 0.15% spread between 8 and 21 EMA on 15m crypto is a large gap that rarely occurs. 0.05% still filters marginal crossovers (flat EMAs) but allows genuine momentum alignment.

### CHANGE 19: Wider ROI table for winning trades
- 0: 2.2% → 25m: 1.2% → 75m: 0.5% → 180m: 0
- Why: v3.1 showed ROI exits are 100% profitable. Giving winners more room (2.2% vs 1.8% cap) captures larger moves. Still fast to lock profits at lower tiers.

### Expected impact
- Trades should flow again (estimate 40-70 trades)
- RSI now confirms rather than contradicts momentum
- WR should improve with coherent signal alignment
- Risk: if WR still below 55%, next iteration should add trailing stop to protect gains

## Iteration 3 Results: 62t | 53.2% WR | -$50.39 | SL avg -3.56%

**Result**: Trades flowed again (62 vs 0 in iteration 2). WR improved slightly (52.7% → 53.2%) but P&L barely changed (-$50.00 → -$50.39). Still FAIL.

**Per-pair**:
- Winners: AVAX (+$2.85), APT (+$2.70), ATOM (+$2.15)
- Losers: OP (-$10.71, 0% WR), NEAR (-$10.78, 37.5% WR), ETH (-$10.48), BTC (-$9.09, 60% WR), ARB (-$6.86), SOL (-$5.13), AAVE (-$5.04)

**Exit breakdown**: ROI: 11t avg +1.47% (+$16.06) | SL: 15t avg -3.56% (-$52.80). 36 other exits (RSI signal or force-exit). Long/Short: 25/37.

**Root cause — R:R imbalance, not WR**:
- Risk/Reward ratio = 0.41 (avg win 1.47% / avg loss 3.56%)
- Even 60% WR loses money with this R:R (BTC: 60% WR, -$9.09)
- Breakeven WR at current R:R = 71% — unrealistic target
- The ATR-based custom_stoploss was WRITTEN but DISABLED (use_custom_stoploss=False)
- Trailing stop parameters existed but trailing_stop=False
- RSI exit at 72 was killing winners before they could reach ROI tiers

## Iteration 4: Fix R:R Imbalance (Changes 20-23)

**Diagnosis**: The core problem isn't entry quality (53.2% WR is close to target) — it's that wins are too small (~1.5%) and losses too big (~3.5%). The ATR-based custom stoploss and trailing stop were already implemented but disabled. RSI exit at 72 was prematurely closing winners.

**Strategy**: Fix the exit mechanics — tighten SL via custom stoploss, let winners run wider, stop killing them with RSI exits.

### CHANGE 20: Enable custom stoploss
- use_custom_stoploss = True (was False — ATR SL code was dead!)
- Static stoploss: -2.5% (was -3.0%, fallback only)
- Existing custom_stoploss uses ATR × 1.5, capped at 2.5%
- Tightens to -0.8% when profit > 2.5%, -1.2% when > 1.5%
- Why: The ATR SL adapts to actual pair volatility instead of a blanket 3%. Low-vol pairs get tighter SL, reducing avg loss.

### CHANGE 21: Candle body confirmation
- LONG: close > open (bullish candle body)
- SHORT: close < open (bearish candle body)
- Why: Prevents entering on doji or counter-trend candles within a trend. The entry candle itself must show directional conviction. Cheap filter — no new indicators needed.

### CHANGE 22: Wider ROI + enable trailing stop
- ROI: 0: 3.5% → 60m: 2.0% → 180m: 0.8% → 360m: 0
- Was: 0: 2.2% → 25m: 1.2% → 75m: 0.5% → 180m: 0
- Trailing: 1.2% trail after 2.5% profit offset (was disabled)
- Why: The previous ROI was too aggressive — most ROI exits happened at 1.2% or 0.5%, not the 2.2% cap. Wider initial ROI (3.5%) lets strong moves develop. Trailing protects gains above 2.5%.

### CHANGE 23: Widen RSI exit bands
- Exit long: RSI > 80 (was 72)
- Exit short: RSI < 20 (was 28)
- Why: 36/62 trades exited via non-ROI/non-SL. Many were likely RSI exits at ~1-1.5% profit. RSI 72 in a momentum strategy is "starting to get strong", not "overbought". Raising to 80 lets winners reach ROI/trailing levels.

### Expected impact
- Avg SL loss should drop from -3.56% to ~-2.0% (ATR-based SL)
- Avg ROI win should rise from +1.47% to ~2.0-2.5% (wider ROI + trailing)
- New R:R ~1.0-1.25 (was 0.41) — breakeven WR drops to ~50%
- Fewer trades (candle filter) but each trade has better R:R
- Risk: if ATR is very low on some pairs, SL could be too tight → stopped out by noise

## Iteration 4 Results: 40t | 5.0% WR | -$49.79 | SL avg -1.69%

**Result**: WR collapsed from 53.2% to 5.0%. Only 2/40 trades were profitable. R:R improved to 2.07 (avg win +3.50%, avg loss -1.69%) but WR is catastrophically below the 33% breakeven.

**Exit breakdown**: ROI: 2t avg +3.50% (+$6.90) | SL: 16t avg -1.69% (-$26.82) | TrailingSL: 4t avg -1.04% (-$4.11) | Other: 18t (all losses). Long/Short: 18/22.

**Root cause — Over-tight stoploss, not entry quality**:
- ATR × 1.5 produces SL of ~1 ATR — a single 15m candle can stop you out
- For BTC (ATR ~0.5% on 15m): SL = 0.75%, less than one candle's range
- The +1.5% profit tightening tier: SL snaps to -1.2% from current, noise kills it
- The 3.5% ROI cap was unreachable with the tight SL — trades died first
- R:R math is perfect but useless when WR is 5%
- 18 unaccounted exits likely from protections triggering after consecutive SLs

## Iteration 5: Fix Over-Tight Stoploss (Changes 24-27)

**Diagnosis**: The iteration 4 changes correctly identified the R:R problem but overcorrected. The SL went from too wide (-3.0%) to too tight (ATR × 1.5 ≈ 0.75-1.0% for most pairs). The profit-based tightening at +1.5% made it worse. The wider ROI (3.5%) required trades to survive longer, but the tighter SL killed them sooner. Classic case of solving one problem (R:R) by creating a worse one (WR).

**Strategy**: Find the middle ground — wider SL than iteration 4 but tighter than iteration 3, and tighten ROI to match.

### CHANGE 24: Widen ATR-based stoploss
- ATR multiplier: 1.5 → 2.5 (trades get 2.5 ATR of noise room)
- Cap: 2.5% → 3.5% (allow wider SL for volatile pairs)
- Static fallback: -3.5% (was -2.5%)
- Why: 1 ATR SL is noise — a single 15m candle exceeds it. 2.5 ATR gives ~2× noise tolerance. For BTC: SL ~1.25%. For ALTs: SL ~2.5%. This is between iteration 3's -3.0% and iteration 4's ~-1.0%.

### CHANGE 25: Relax profit-based SL tightening
- Remove the +1.5% profit tier entirely (was -1.2% from current)
- +2.5% tier: -1.2% from current (was -0.8%, too aggressive)
- New +4.0% tier: -0.8% from current (only for large gains)
- Why: The +1.5% tier was the silent killer — trades touching +1.5% got their SL snapped to within noise range of the current price. Without this tier, trades at +1.5% keep the ATR-based SL and have room to develop toward ROI.

### CHANGE 26: Tighter ROI table
- 0: 2.5% → 30m: 1.5% → 90m: 0.6% → 240m: 0
- Was: 0: 3.5% → 60m: 2.0% → 180m: 0.8% → 360m: 0
- Why: The 3.5% ROI cap was unreachable with even a 2.5 ATR SL. More trades should reach 2.5% than 3.5%. Faster time decay (30m/90m vs 60m/180m) forces exits before positions degrade. Expected: more ROI exits, each at ~1.5-2.5%.

### CHANGE 27: Adjust trailing stop
- Offset: 2.5% → 1.8% (activate trailing sooner)
- Trail: 1.2% → 0.8% (tighter trail to lock gains)
- Why: With ROI cap at 2.5%, the old 2.5% trailing offset never activated before ROI. At 1.8%, trades reaching +1.8% get a trailing floor at +1.0% — guaranteed profit lock-in even if ROI isn't reached.

### Expected impact
- Avg SL loss: ~-2.0 to -2.5% (was -1.69%, iteration 3 was -3.56%)
- Avg ROI win: ~1.5-2.5% (was +3.50% with fewer ROI exits, iteration 3 was +1.47%)
- R:R: ~1.0 (balanced — neither side dominates)
- Breakeven WR: ~50% (achievable with good entry signals)
- More ROI exits than iteration 4 (tighter ROI cap + wider SL)
- Risk: if SL is still too tight for some pairs, WR stays low

## Iteration 5 Results: 33t | 12.1% WR | -$50.13 | SL avg -2.46%

**Result**: WR collapsed from 53.2% (iter 3) to 12.1%. Trades went from 62 to 33. Still deeply unprofitable.

**Per-pair**:
- ARB: 7t, 0% WR, -$10.77 (worst)
- ETH: 4t, 0% WR, -$9.73
- BTC: 4t, 0% WR, -$6.46
- AVAX: 2t, 0% WR, -$8.15
- OP: 2t, 0% WR, -$4.58
- AAVE: 2t, 0% WR, -$2.83
- NEAR: 4t, 25% WR, -$3.43
- SOL: 8t, 37.5% WR, -$4.18
- APT/ATOM: 0 trades (overfiltered)

**Exit breakdown**: ROI: 4t avg +2.52% (+$9.96) | SL: 11t avg -2.46% (-$26.93) | TrailingSL: 7t avg -1.20% (-$8.34) | Other: 11t (-$24.82). Long/Short: 13/20.

**Root cause — Short bias + SL dominance + trailing confusion**:
1. SHORT BIAS: 20/33 trades are shorts. Crypto upward bias makes shorting consistently lose. All 10 worst trades are likely shorts.
2. SL is main loss driver: 11 SL exits at -$26.93 (54% of total loss). R:R ≈ 1:1 (ROI +2.52% vs SL -2.46%) but WR 12.1% needs 50%+ to break even.
3. TRAILING CONFUSION: TrailingSL exits avg -1.20% despite trailing_only_offset_is_reached=True at +1.8%. The custom_stoploss ATR-based SL overrides the trailing floor, causing trades to exit at losses even when trailing should protect them.
4. LATE ENTRY: BB expanding + MACD rising + volume surge all confirm momentum EXISTS but enter at the PEAK. All conditions align when the move is already exhausted.

## Iteration 6: Fix Short Bias & Entry Quality (Changes 28-32)

**Diagnosis**: Three compounding problems destroy P&L: (1) short bias with 20 losing shorts, (2) entry signals that fire at momentum peaks, (3) freqtrade trailing interacting badly with custom_stoploss.

**Strategy**: Strengthen short requirements to reduce bad short trades, add ROC confirmation to filter stalled momentum, replace unreliable freqtrade trailing with explicit custom_stoploss profit tiers, and tighten ROI/SL for better R:R.

### CHANGE 28: Add ROC(3) momentum confirmation
- Compute 3-candle rate of change in populate_indicators
- Longs require ROC > 0 (price actively rising over last 45min)
- Shorts require ROC < 0 (price actively falling)
- Why: All existing filters confirm a trend exists but not that price is CURRENTLY moving in the right direction. ROC detects when momentum has stalled despite indicators still being positive.

### CHANGE 29: Strengthen short entry requirements
- Shorts require ADX ≥ 25 (longs stay at ADX ≥ 20)
- Shorts require volume > 1.5x SMA (longs stay at 1.2x)
- Why: 20/33 trades are shorts with near-0% WR. Crypto's upward bias means shorts need significantly stronger confirmation. Requiring ADX 25 + 1.5x volume should cut short trades to ~5-8 and filter the weakest entries.

### CHANGE 30: Tighter ROI table
- 0: 1.8% → 20m: 0.8% → 60m: 0.3% → 150m: 0
- Was: 0: 2.5% → 30m: 1.5% → 90m: 0.6% → 240m: 0
- Why: Only 4/33 trades ever reached the 2.5% cap. Lower cap (1.8%) with faster time decay should produce more ROI exits and higher WR. The 20m/60m tiers force exits before positions degrade.

### CHANGE 31: Tighter ATR stoploss
- Multiplier: 2.5 → 2.0 (trades get 2 ATR of noise room)
- Cap: 3.5% → 3.0% (static fallback also -3.0%)
- Why: Avg SL loss (-2.46%) nearly equals avg ROI win (+2.52%). Tighter SL (expected ~-2.0%) improves R:R without going as extreme as iteration 4 (1.5x, 5% WR).

### CHANGE 32: Replace freqtrade trailing with custom_stoploss profit protection
- Disable trailing_stop (was causing -1.20% avg exits due to SL override)
- +0.6% profit: SL at breakeven (return -0.006)
- +1.2% profit: SL at ~+0.9% from entry (return -0.003)
- +2.0% profit: SL at ~+1.5% from entry (return -0.005)
- Why: Freqtrade's trailing mechanism interacted badly with custom_stoploss — the ATR-based SL overrode the trailing floor, producing -1.20% avg exits that should have been +1.0%+. Explicit profit tiers in custom_stoploss give predictable, reliable gain protection.

### Expected impact
- Fewer trades: 15-25 (stronger short filter + ROC)
- Short trades: ~5-8 (was 20), hopefully higher WR
- Avg SL: ~-2.0% (was -2.46%)
- Avg ROI: ~1.0-1.8% (lower cap, more exits at lower tiers)
- R:R: ~0.7-0.9 (slight improvement from tighter SL)
- Breakeven WR at new R:R: ~55-60%
- Risk: if ROC + short filter over-filter, could get 0 trades again (unlikely — long conditions unchanged except ROC)
