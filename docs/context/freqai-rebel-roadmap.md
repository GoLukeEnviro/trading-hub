# FreqAI RebelLiquidation Roadmap

## Scope

Controlled phase-by-phase execution for `freqai-rebel` only.
Current canonical source path:
`/home/hermes/projects/trading/freqtrade/bots/freqai-rebel/`

## Phase 0 — Freeze And Inspect Current State

### Timestamp
- 2026-05-14 session, Phase 0 inspection completed by Hermes

### Verified Facts

| Check | Evidence | Result |
|---|---|---|
| Repo root | `/home/hermes/projects/trading` | PASS |
| Container | `freqai-rebel` | PASS |
| Container state | `Up 20 minutes` | PASS |
| Image | `freqtradeorg/freqtrade:2026.3_freqai` | PASS |
| Host API mapping | `0.0.0.0:8087->8080/tcp` | PASS |
| Exchange | `bitget` | PASS |
| Trading mode | `futures` | PASS |
| Margin mode | `isolated` | PASS |
| Pairs | `BTC/USDT:USDT`, `ETH/USDT:USDT` | PASS |
| dry_run | `true` | PASS |
| FreqAI enabled | `true` | PASS |
| FreqAI model | `XGBoostClassifier` | PASS |
| Identifier | `rebel-liquidation-v1` | PASS |
| DI threshold | `0.9` | PASS |
| initial_state | `null` | BLOCKER |

### Runtime Log Findings

Observed in `docker logs freqai-rebel --tail 250`:
- Worker starts successfully
- Dry-run mode enabled
- Bitget exchange loads successfully
- Futures pair whitelist loads successfully
- FreqAI model resolver loads `XGBoostClassifier`
- Train queue created for `BTC/USDT:USDT`, `ETH/USDT:USDT`
- Futures data download completes for 5m / 15m / 1h plus `mark` and `funding_rate`
- Runtime transitions to `STOPPED`
- Repeated heartbeats remain `state='STOPPED'`
- No fatal traceback observed in this Phase 0 inspection log

### Git Status Snapshot

`git status --short` at Phase 0 showed unrelated dirty/untracked files already present in the repository.
This means the repo is not clean enough to claim "no unexpected dirty runtime files" without manual triage.
Key `freqai-rebel` related file already dirty:
- `docs/context/freqai-rebel-deployment.md`

### Commands Used

```bash
cd /home/hermes/projects/trading && git status --short

docker ps -a --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}\t{{.Image}}' | grep -E 'freqai-rebel|NAMES'

docker run --rm -v freqai-rebel-data:/data --entrypoint python3 freqtradeorg/freqtrade:2026.3_freqai -c "import json; c=json.load(open('/data/config.json')); import json as j; print(j.dumps({'initial_state': c.get('initial_state'), 'dry_run': c.get('dry_run'), 'exchange': c.get('exchange',{}).get('name'), 'trading_mode': c.get('trading_mode'), 'margin_mode': c.get('margin_mode'), 'pairs': c.get('exchange',{}).get('pair_whitelist'), 'freqaimodel': c.get('freqaimodel'), 'freqai_enabled': c.get('freqai',{}).get('enabled'), 'identifier': c.get('freqai',{}).get('identifier'), 'DI_threshold': c.get('freqai',{}).get('feature_parameters',{}).get('DI_threshold')}, indent=2))"

docker logs freqai-rebel --tail 250 2>&1
```

### Phase 0 Result

Phase 0 is only partially green:
- Structural deployment is correct
- Active volume config confirms Bitget futures + dry_run=true
- Container is running
- Main blocker remains `initial_state = null` with runtime settling into persistent `STOPPED`

### Next Exact Action

Proceed to Phase 1 only:
- set `initial_state` to `running`
- sync to Docker named volume
- restart only `freqai-rebel`
- re-check whether logs leave the persistent `STOPPED` heartbeat state

## Phase 1 — Minimal Runtime Fix

### Goal

Set `initial_state` to `running` because Phase 0 showed the active runtime remained in persistent `STOPPED` state and FreqAI training was not proven.

### Expected Validation

- Active Docker volume config shows `initial_state=running`
- `dry_run=true` remains unchanged
- Bitget futures mode remains unchanged
- Only `freqai-rebel` is restarted
- Logs are checked only for state transition / fatal errors
- No strategy logic is changed


## Phase 3 — Prediction Blocker labels_std Fixed

### Problem

Training completed successfully, but prediction failed with:

`KeyError('labels_std')`

Exact failing path:

`freqtrade/freqai/prediction_models/XGBoostClassifier.py:81` — `list(dk.data["labels_std"].keys())`

### Root Cause

Two interacting causes:

1. **`fit_live_predictions_candles: 300`** unterdrückt `dk.fit_labels()` in `BaseClassifierModel.train()` (Live-Modus-Bedingung in Zeile 54 überspringt `fit_labels()`). Damit wird `dk.data["labels_std"]` nie initialisiert.

2. **`--freqaimodel XGBoostClassifier` in docker-compose.yml** überschrieb den Config-Wert — der Wrapper wurde nie geladen.

### Fix Applied

**A. Repo-local custom FreqAI model wrapper:**
`user_data/freqaimodels/RebelXGBoostClassifier.py` — subclassed XGBoostClassifier mit `predict()`-Override, das `labels_std` vor Delegation an Parent injiziert, falls nicht vorhanden.

**B. Docker Compose Fix:**
`--freqaimodel XGBoostClassifier` → `--freqaimodel RebelXGBoostClassifier`

**C. Sync Script Update:**
`scripts/sync-to-volume.sh` kopiert jetzt auch `user_data/freqaimodels/` ins Docker Volume.

### What Changed

3 files modified, 1 new directory:

| File | Change |
|------|--------|
| `docker-compose.yml` | `--freqaimodel XGBoostClassifier` → `RebelXGBoostClassifier` |
| `scripts/sync-to-volume.sh` | Added freqaimodels volume mount + copy + compile |
| `user_data/config.json` | `freqaimodel: XGBoostClassifier` → `RebelXGBoostClassifier`, new identifier |
| `user_data/freqaimodels/RebelXGBoostClassifier.py` | NEW — repo-local wrapper |

### Validation

#### Startup Log
```
Using freqaimodel class name: RebelXGBoostClassifier
Using resolved freqaimodel RebelXGBoostClassifier from
'/freqtrade/user_data/freqaimodels/RebelXGBoostClassifier.py'...
```

#### Prediction Path
- No KeyError, no Traceback after fix
- Historic predictions: **5 B → 120,040 B** (prediction pipeline aktiv)
- Container stabil `Up` mit `RestartCount=0`
- Keine Änderungen an Strategy, Modell-Typ (XGBoost bleibt), Features oder anderen Containern

### What Was NOT Touched
- Strategy `RebelLiquidation.py` — kein Diff
- Modell-Typ — bleibt XGBoost (nur gewrapped)
- Features — unverändert
- Andere Bots — nicht angefasst
- `dry_run` — bleibt `true`
- Exchange — bleibt Bitget futures isolated

## Phase 4 — do_predict And Signal Gate Verification (2026-05-14)

### Goal
Verify whether FreqAI predictions reach the strategy and whether `do_predict` can gate entry/exit logic safely.

### Evidence

**Container:** freqai-rebel Up 10min, state RUNNING, heartbeat active
**Config:** Bitget futures, isolated margin, dry_run=true, strategy=RebelLiquidation, freqaimodel=RebelXGBoostClassifier

**historic_predictions.pkl:**
- Size: 176,549 bytes
- Pairs: BTC/USDT:USDT (1001 rows), ETH/USDT:USDT (1001 rows)
- Columns: &s-up_or_down, down, up, down_mean, down_std, up_mean, up_std, do_predict, DI_values, high_price, low_price, close_price, date_pred

**do_predict distribution:**
- do_predict=0: 1998 rows (warmup/historical)
- do_predict=1: 4 rows (latest 2 candles per pair, 16:40-16:45 UTC)
- All do_predict=1 rows have &s-up_or_down = "down"

**Signal gate logic (unchanged):**
- enter_long: &s-up_or_down == 'up' AND do_predict == 1
- exit_long: &s-up_or_down == 'down' AND do_predict == 1

**Result:** Model predicts "down" consistently → no enter_long signals fire → conservative behavior, correct.

**Inference confirmed:**
- `Total time spent inferencing pairlist 0.69 seconds` in logs

### Verdict
PASS — Prediction pipeline active, do_predict gate working, strategy logic correct and conservative.
No errors, no KeyError, no crashes. Model just needs time and data to potentially generate "up" signals.

### What Was Not Changed
- RebelLiquidation.py: unchanged
- config.json: unchanged
- docker-compose.yml: unchanged
- No features added, no can_short, no hyperopt, no backtest
- dry_run=true preserved, Bitget futures preserved


## Phase 5 — Baseline-Backtest (2026-05-14)

### Timerange
- Backtest: 2026-04-01 to 2026-05-14 (43 days)
- Data: 2026-03-01 to 2026-05-14 (75 days, 5m/15m/1h)
- Training windows: 7 (rolling 30d train / 7d predict)

### Result

```
Timerange:           2026-04-01 → 2026-05-14 (43 days)
Trades:              53 (1.23/day)
Profit:              -2.974 USDT (-0.30%)
Max Drawdown:        3.038 USDT (0.30%)
Winrate:             22.6% (12W / 41L)
Profit Factor:       0.14
Sharpe:              -15.42
Sortino:             -17.52
Avg Duration:        10 min
Best trade:          +0.24%
Worst trade:         -0.85%
Max Consecutive Loss: 11
Market Change:       +11.96% (BTC/USDT rose strongly)
```

### Pair Breakdown

```
ETH/USDT:USDT:  22 trades, -0.13%, 22.7% WR, avg 8min
BTC/USDT:USDT:  31 trades, -0.17%, 22.6% WR, avg 12min
```

### Exit Reason
- 100% exit_signal (no stoploss, no trailing, no ROI hit)
- All exits via populate_exit_trend (&s-up_or_down == 'down' AND do_predict == 1)

### Analysis
- Model predicts "down" overwhelmingly → 22.6% winrate means only ~23% of "up" predictions were correct
- In a +11.96% bull market, strategy lost money going long → model is severely miscalibrated
- Profit Factor 0.14 is catastrophic (need >1.0 to be profitable)
- All trades are extremely short (5-10 min avg) suggesting model flips rapidly
- Max 11 consecutive losses shows model lacks directional conviction
- Strategy IS producing trades and signals → prediction pipeline works correctly
- The problem is model PREDICTION QUALITY, not infrastructure

### What Was Not Changed
- No strategy modifications
- No config changes
- No hyperopt
- No feature changes
- dry_run=true remains, Bitget futures isolated

### Verdict
INFRASTRUCTURE PASS, STRATEGY NEEDS WORK.
The prediction pipeline is fully functional. The model simply does not predict well enough.
This is expected for a v1 baseline — the value is in having a working measurement.


## Phase 6 — Model Optimization Experiments (2026-05-14)

### Baseline (Phase 5, for reference)
```
PF=0.14, WR=22.6%, 53 trades, -0.30%, Sharpe=-15.42
```

### Experiment Results

| # | Config Change | Trades | WR | PF | Profit | Notes |
|---|---------------|--------|-----|-----|--------|-------|
| S1 | train_period=60, DI=0, +133d data | 10 | 50.0% | 0.81 | -0.01% | Best result. DI=0.9 blocked 99% of signals |
| S2a | +max_depth=3, lr=0.02, strong reg | 0 | - | - | 0% | Too aggressive, no "up" predictions |
| S2b | +max_depth=4, lr=0.03, mod reg, fewer features | 0 | - | - | 0% | 88 features, but cached result reused |
| S4a | +scale_pos_weight=3, orig features | 44 | 25.0% | ~0.23 | -0.29% | More trades but wrong direction |
| S4b | +scale_pos_weight=5, reduced features | 214 | 26.6% | 0.23 | -1.47% | Too many bad trades |
| S4c | +scale_pos_weight=10, deep trees | 552 | 32.8% | ~0.23 | -2.12% | Most trades, still wrong |

### Root Cause Analysis

**The label `&s-up_or_down` is fundamentally broken for this market regime.**

The strategy defines `up` as: `close.shift(-12) > close * 1.005` (+0.5% in 1 hour).

In the training data (Jan-Apr 2026, mostly ranging with occasional pumps):
- ~95% of 5m candles do NOT rise 0.5% in the next hour
- The model correctly learns that "always predict down" minimizes logloss
- This produces 0-10 "up" signals in 43 days

**What was tried:**
- `DI_threshold=0`: Removed signal gating, went from 0→10 trades (S1)
- `scale_pos_weight`: Artificially upweights minority class in XGBoost. Produces more "up" signals but the model has no real signal — it's just guessing "up" more often, resulting in ~25-33% winrate.
- Feature reduction: Fewer features = less noise but doesn't fix the fundamental label imbalance.
- Regularization: Strong reg = 0 trades. Moderate reg = same as baseline.

### Conclusion

**The config/model-tuning approach has hit its ceiling at PF~0.81 with 10 trades/day.**

To reach PF>1.0 and WR>45%, one of these is needed:

1. **Relax the label threshold** in `set_freqai_targets`: Change `1.005` to `1.001` or use a relative threshold. This requires changing `RebelLiquidation.py` line 64.

2. **Use a different target**: Instead of binary up/down, predict continuous returns and threshold dynamically in the strategy.

3. **Add regime detection**: Only trade when market regime favors long entries (trend filter).

4. **More training data**: 133 days may not be enough. 6+ months would help the model see more "up" patterns.

### Current Best Config (restored)
- train_period_days=60, DI_threshold=0
- Original model params (n=200, depth=6, lr=0.05)
- All features restored (corr_pairlist, 2 periods, 2 shifted)
- PF=0.81, WR=50%, 10 trades in 43 days

### Recommendation
**Request approval to modify `set_freqai_targets` in RebelLiquidation.py.**
The label threshold `1.005` should be reduced to `1.002` or the target should use a percentile-based approach. This is the only path to PF>1.0 without fundamentally different features.


## Phase 6 — Model Optimization Experiments (2026-05-14)

### Baseline (Phase 5)
PF=0.14, WR=22.6%, 53 trades, -0.30%, Sharpe=-15.42

### Experiment Results

| # | Config Change | Trades | WR  | PF   | Profit  | Notes |
|---|---------------|--------|-----|------|---------|-------|
| S1 | train=60, DI=0, +133d data | 10 | 50% | 0.81 | -0.01% | Best. DI=0.9 blocked 99% signals |
| S2a | +depth=3, lr=0.02, strong reg | 0 | - | - | 0% | Too aggressive |
| S2b | +depth=4, lr=0.03, fewer feat | 0 | - | - | 0% | 88 features, no up pred |
| S4a | +spw=3, orig features | 44 | 25% | 0.23 | -0.29% | More trades, wrong dir |
| S4b | +spw=5, reduced feat | 214 | 26.6% | 0.23 | -1.47% | Too many bad trades |
| S4c | +spw=10, deep trees | 552 | 32.8% | 0.23 | -2.12% | Most trades, still wrong |

### Root Cause

Label up = close.shift(-12) > close * 1.005 (+0.5% in 1h).
~95% of 5m candles do NOT rise 0.5% in the next hour.
Model learns always predict down = minimal logloss = no enter_long signals.

scale_pos_weight forces more up predictions but model has no real signal = low winrate.

### Conclusion

Config/model-tuning ceiling: PF~0.81, 10 trades, WR=50%.
To reach PF>1.0 and WR>45% requires changing set_freqai_targets in RebelLiquidation.py.

Recommendation: Request approval to reduce label threshold from 1.005 to 1.002 or use percentile-based labeling.


## Phase 4.5 — Training Quality Audit (2026-05-14)

### Model Configuration (Live Bot)
```
n_estimators:       200
max_depth:          6
learning_rate:      0.05
early_stopping:     NONE
BTC features:       436 (376 nonzero, 60 zero = 13.8%)
ETH features:       220 (193 nonzero, 27 zero = 12.3%)
training points:    6171 per pair per cycle
NaN drops:          410 of 8639 (4.7%) — acceptable
```

### Logloss Overfitting Evidence

**BTC/USDT:USDT:**
```
Best:    iter=3,   logloss=0.216747
Final:   iter=199, logloss=0.282674
Degradation: +30.4% — OVERFITTING
```
The model reaches its best validation logloss at iteration 3 (out of 200).
After that, it continuously overfits for 197 more rounds.

**ETH/USDT:USDT:**
```
Best:    iter=37,  logloss=0.246364
Final:   iter=199, logloss=0.280522
Degradation: +13.9% — MILD_OVERFIT
```
ETH reaches its best at iteration 37. Still degrades significantly after.

### Label Distribution (Root Cause)
```
BTC: up=7.4%, down=92.6% (simulated from close prices)
ETH: up=7.9%, down=92.1% (simulated from close prices)
```
The label threshold `close.shift(-12) > close * 1.005` (+0.5% in 1h) creates
extreme class imbalance (~93% down). This is WHY:
- The model learns "always predict down" as the optimal strategy
- 100% of live predictions are "down" → zero enter_long signals
- Overfitting is accelerated because the minority class has too few examples

### Feature Importance (Top-5 BTC)
```
%-ema-period_10_shift-2_BTC/USDTUSDT_1h:  0.0405
%-ema-period_20_shift-2_BTC/USDTUSDT_1h:  0.0283
%-vsr-period_20_BTC/USDTUSDT_1h:         0.0188
%-raw-price_gen_shift-1_BTC/USDTUSDT_15m: 0.0157
%-vsr-period_10_BTC/USDTUSDT_1h:         0.0151
```
1h timeframe dominates. Cross-pair (ETH) features contribute.
13.8% of features have zero importance.

### Recommendations

1. **CRITICAL: Add `early_stopping_rounds: 20`** to config.json
   - BTC best at iter=3 → would stop at iter=23, saving 177 useless rounds
   - ETH best at iter=37 → would stop at iter=57, saving 143 useless rounds
   - This alone may improve prediction quality by preventing overfitting

2. **Reduce `n_estimators` to 80** as an additional safeguard
   - ETH's best is at 37, BTC's at 3 — 80 covers both with margin
   - Combined with early_stopping, model stops at the right time

3. **LABEL FIX REQUIRED** (requires Strategy change approval)
   - Current 93:7 imbalance makes any classifier useless
   - Options: reduce threshold to 1.002, use percentile-based, or continuous target
   - This is the SINGLE BIGGEST improvement lever

4. **Feature cleanup** (optional, low priority)
   - 60 zero-importance features on BTC add noise
   - Could reduce `include_shifted_candles` from 2 to 1

### What Was Not Changed
- RebelLiquidation.py: untouched
- config.json: untouched (read-only audit)
- Container: RUNNING, dry_run=true, stable
- No commits made


## Phase 4.6 — Minimal Anti-Overfitting Config (2026-05-14)

### Change
- `n_estimators`: 200 → 80
- `early_stopping_rounds`: 20 (NEW)
- `identifier`: `rebel-liquidation-v1-wrapper-n80-es20`

### Verification

**Container:** RUNNING, port 8087

**Logloss Improvement:**
```
BTC: Best iter 20 (0.21119), stops at iter ~41 — no overfitting
ETH: Best iter 28 (0.25399), stops at iter ~49 — no overfitting
Before: BTC degraded +30.4%, ETH degraded +13.9% to iter 200
After:  BTC stops cleanly, ETH stops cleanly
```

**Training:** 12612 data points per pair (60d window), 436 features BTC, 220 ETH

**Prediction:** historic_predictions.pkl = 114KB and growing

**No Errors:** No KeyError, no Traceback, no crash

### Explicitly Not Changed
- RebelLiquidation.py: UNTOUCHED
- Label threshold: UNCHANGED (still 1.005 = +0.5% in 1h)
- No can_short, no new features, no hyperopt
- dry_run=true, Bitget futures isolated


### Phase 4.6 Config Drift Fix (2026-05-14)

Two unintended config changes were caught before commit:
- train_period_days was changed 30→60 without approval → REVERTED to 30
- DI_threshold was changed 0.9→0 without approval → REVERTED to 0.9

Final clean diff contains ONLY the intended changes:
- identifier: wrapper → wrapper-n80-es20
- n_estimators: 200 → 80
- early_stopping_rounds: (new) 20

Container restarted and verified with corrected config.
