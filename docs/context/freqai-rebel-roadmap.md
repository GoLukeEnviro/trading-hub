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

