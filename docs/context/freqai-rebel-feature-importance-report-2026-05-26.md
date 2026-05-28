# FREQAI-REBEL FEATURE IMPORTANCE REPORT 26.05.2026

## 1. Model-Files & Metadaten

- Active model family: `rebel-liquidation-v1-wrapper-n80-es20-t0005`

- Model type: `XGBClassifier` per pair model

- Latest BTC training dir: `sub-train-BTC_1779836340` -> 2026-05-26 22:59:00 UTC

- Latest ETH training dir: `sub-train-ETH_1779836352` -> 2026-05-26 22:59:12 UTC

- BTC feature count: 436

- ETH feature count: 220

- Training points per pair (from logs): 12,639

- Recent retrain cadence observed: hourly (21:59 and 22:59 UTC)


## 2. Aggregate Top-30 Features (BTC+ETH latest models, normalized)

| Rank | Feature | Importance % | Kategorie | Bewertung |
|---|---|---:|---|---|
| 1 | `%-ema-period_20` | 4.9527 | Technical | GREEN |
| 2 | `%-adx-period_20_shift-2` | 4.8919 | Technical | GREEN |
| 3 | `%-raw-price_gen` | 4.4559 | Price | GREEN |
| 4 | `%-ema-period_10` | 4.3713 | Technical | GREEN |
| 5 | `%-rsi-period_20_shift-2` | 4.3254 | Technical | GREEN |
| 6 | `%-rsi-period_20` | 4.1123 | Technical | GREEN |
| 7 | `%-pct-move-period_10_shift-2` | 4.0423 | Price | GREEN |
| 8 | `%-pct-move-period_10` | 4.0216 | Price | GREEN |
| 9 | `%-adx-period_20_shift-1` | 3.9799 | Technical | GREEN |
| 10 | `%-mfi-period_20_shift-2` | 3.9798 | Technical | GREEN |
| 11 | `%-adx-period_10` | 3.9784 | Technical | GREEN |
| 12 | `%-mfi-period_20` | 3.8566 | Technical | GREEN |
| 13 | `%-pct-move-period_10_shift-1` | 3.8282 | Price | GREEN |
| 14 | `%-adx-period_10_shift-1` | 3.7186 | Technical | GREEN |
| 15 | `%-pct-move-period_20_shift-1` | 3.6657 | Price | GREEN |
| 16 | `%-pct-move-period_20` | 3.6483 | Price | GREEN |
| 17 | `%-adx-period_10_shift-2` | 3.5868 | Technical | GREEN |
| 18 | `%-rsi-period_10` | 3.5444 | Technical | GREEN |
| 19 | `%-raw-volume_gen` | 3.5054 | Volume | YELLOW |
| 20 | `%-vsr-period_20_shift-2` | 3.4326 | Volume | YELLOW |
| 21 | `%-pct-change_gen` | 3.3788 | Price | YELLOW |
| 22 | `%-adx-period_20` | 3.3202 | Technical | YELLOW |
| 23 | `%-mfi-period_20_shift-1` | 3.3184 | Technical | YELLOW |
| 24 | `%-raw-price_gen_shift-1` | 3.2564 | Price | YELLOW |
| 25 | `%-raw-price_gen_shift-2` | 3.2479 | Price | YELLOW |
| 26 | `%-ema-period_20_shift-2` | 3.2137 | Technical | YELLOW |
| 27 | `%-vsr-period_20` | 3.1627 | Volume | YELLOW |
| 28 | `%-ema-period_10_shift-2` | 3.1412 | Technical | YELLOW |
| 29 | `%-rsi-period_10_shift-1` | 3.1376 | Technical | YELLOW |
| 30 | `%-rsi-period_10_shift-2` | 3.1274 | Technical | YELLOW |

## 3. Pair-spezifische Spitzenreiter

### BTC

- Feature count: 436

- Top-10 concentration: 8.0051%

- Category mix: {'Price': 24.1183, 'Technical': 54.3416, 'Time': 0.9344, 'Volume': 20.6055}

| Rank | Feature | Importance % | Kategorie |
|---|---|---:|---|
| 1 | `%-pct-change_gen_ETH/USDTUSDT_1h` | 1.0319 | Price |
| 2 | `%-pct-move-period_10_BTC/USDTUSDT_15m` | 0.9243 | Price |
| 3 | `%-pct-change_gen_shift-2_BTC/USDTUSDT_1h` | 0.8196 | Price |
| 4 | `%-pct-move-period_10_ETH/USDTUSDT_1h` | 0.7925 | Price |
| 5 | `%-ema-period_10_shift-1_ETH/USDTUSDT_15m` | 0.7864 | Technical |
| 6 | `%-pct-move-period_10_shift-2_BTC/USDTUSDT_1h` | 0.7508 | Price |
| 7 | `%-vsr-period_20_shift-1_ETH/USDTUSDT_1h` | 0.7459 | Volume |
| 8 | `%-ema-period_10_shift-1_ETH/USDTUSDT_1h` | 0.7440 | Technical |
| 9 | `%-raw-volume_gen_shift-2_ETH/USDTUSDT_1h` | 0.7136 | Volume |
| 10 | `%-vsr-period_20_shift-2_BTC/USDTUSDT_1h` | 0.6961 | Volume |

### ETH

- Feature count: 220

- Top-10 concentration: 12.3269%

- Category mix: {'Price': 25.7567, 'Technical': 52.0649, 'Time': 1.6649, 'Volume': 20.5132}

| Rank | Feature | Importance % | Kategorie |
|---|---|---:|---|
| 1 | `%-raw-price_gen_ETH/USDTUSDT_15m` | 1.6739 | Price |
| 2 | `%-rsi-period_10_shift-1_ETH/USDTUSDT_1h` | 1.4026 | Technical |
| 3 | `%-adx-period_10_ETH/USDTUSDT_1h` | 1.2525 | Technical |
| 4 | `%-mfi-period_20_shift-2_ETH/USDTUSDT_1h` | 1.2049 | Technical |
| 5 | `%-ema-period_10_ETH/USDTUSDT_1h` | 1.1596 | Technical |
| 6 | `%-ema-period_10_shift-2_ETH/USDTUSDT_15m` | 1.1456 | Technical |
| 7 | `%-rsi-period_20_shift-2_ETH/USDTUSDT_1h` | 1.1406 | Technical |
| 8 | `%-ema-period_20_shift-2_ETH/USDTUSDT_15m` | 1.1263 | Technical |
| 9 | `%-raw-price_gen_shift-2_ETH/USDTUSDT_1h` | 1.1157 | Price |
| 10 | `%-raw-volume_gen_ETH/USDTUSDT_1h` | 1.1052 | Volume |

## 4. Predictions / Confidence letzte 50 Inferences

- BTC last-50 labels: 29x `down`, 21x `up`

- BTC confidence margin (`max(down,up)-min(down,up)`): mean 0.0387, min 0.0006, max 0.1143

- ETH last-50 labels: 33x `down`, 17x `up`

- ETH confidence margin: mean 0.0803, min 0.0032, max 0.2145

- `do_predict` = 1.0 for the sampled last-50 rows on both pairs -> model is allowed to predict, not blocked by DI filter.

- Interpretation: probabilities are mostly near 50/50 with a slight `down` bias. This is weak classifier conviction, not a hard system failure.

## 5. Drift-Indikator (latest vs previous retrain)

### BTC drift

| Feature | Latest % | Prev % | Delta % |
|---|---:|---:|---:|
| `%-rsi-period_20_shift-1` | 0.9130 | 2.0579 | -1.1449 |
| `%-rsi-period_10_shift-1` | 1.5537 | 0.6327 | +0.9209 |
| `%-raw-price_gen_shift-1` | 1.7401 | 2.6198 | -0.8797 |
| `%-ema-period_10_shift-1` | 1.8689 | 1.0791 | +0.7898 |
| `%-ema-period_20_shift-2` | 0.6426 | 1.3497 | -0.7070 |

### ETH drift

| Feature | Latest % | Prev % | Delta % |
|---|---:|---:|---:|
| `%-ema-period_20_shift-1` | 1.1670 | 2.5176 | -1.3506 |
| `%-raw-price_gen_shift-1` | 1.5164 | 2.5632 | -1.0468 |
| `%-ema-period_20_shift-2` | 2.5711 | 1.7306 | +0.8405 |
| `%-ema-period_10_shift-1` | 0.9569 | 1.7854 | -0.8285 |
| `%-ema-period_20` | 2.3867 | 1.6092 | +0.7774 |

## 6. Analyse & Interpretation

- There is **no single dominant feature >10%**. Even the top single-pair features are only ~1.0-1.7%. That means the model is highly distributed and no one feature is overpowering the decision process. This is structurally healthier than a one-feature overfit model.

- The model is dominated by **Technical + Price** features (~78-80% combined on both BTC and ETH). This fits the actual Rebel strategy far more than any regime-style logic: RSI, ADX, EMA, MFI, pct-move, raw-price, and shifted variants dominate.

- **Volume** contributes ~20.5% on both models. That is material but not dominant. Good sign: volume confirms, but does not drive, the classifier.

- **Time features** are tiny (~0.9% BTC, ~1.66% ETH). Good sign: no obvious time-of-day overfit.

- Unexpectedly strong: cross-timeframe shifted EMA/ADX/RSI and raw-price variants, especially 1h and 15m ETH-derived context even for BTC. This suggests the model is using ETH as market context/correlation proxy.

- Unexpectedly weak: liquidation-specific or explicit regime features are absent. This is not a RegimeSwitchingHybrid-style classifier at all; it behaves like a multi-timeframe technical momentum/mean-reversion classifier.

- Drift is present but moderate: the top changes vs previous retrain are about 0.7% to 1.35% absolute on normalized features. That is enough to show live adaptation, but not enough to scream unstable feature collapse.

- Why 0 trades so far: (1) the bot was only just re-enabled; (2) recent predictions are weak-conviction and slightly biased to `down`; (3) the strategy only enters long on `&s-up_or_down == up`, exits on `down`, so a mild down bias suppresses entries; (4) this is dry-run and classifier caution is normal directly after reactivation.

## 7. Empfehlungen

1. **Do not remove features yet.** No pathological feature dominance is visible. The model looks broad, not collapsed.

2. **Do not Hyperopt only top-10 features.** For XGBoost feature importance in this distributed regime, the top-10 only explain 8.0% (BTC) and 12.3% (ETH). That is too diffuse for aggressive feature-pruning.

3. **Retraining:** yes, but normal cadence only. Current hourly retrain is already happening. No emergency retrain needed tonight.

4. **Next check window:** if still 0 trades after ~6h of live inferencing with `max_open_trades=2`, inspect classifier output thresholds and actual entry rows, not feature importance.

5. **Potential future feature cleanup:** review duplicated shifted price/EMA variants if the model remains inactive for 24-48h. The issue is more likely entry threshold / target definition than missing features.

6. **Go/No-Go for live operation:** `YELLOW-GO` for dry-run live observation, `RED-NO` for any live-money interpretation. The model is healthy enough to watch, but not yet behavior-validated by trades.

## 8. Executive Verdict

- Ampel: **YELLOW**

- Model health: structurally okay, no single-feature overfit

- Operational status: training + inferencing active, but entries not yet proven

- Immediate next action: wait for the 23:36 Rebel check, then reassess at +6h if trades remain zero
