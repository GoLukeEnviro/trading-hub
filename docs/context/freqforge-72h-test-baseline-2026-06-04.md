# FreqForge 72h AI-Override Test — Baseline (04.06.2026 05:05 UTC)

## Bot Config (After Phase 1 Fix)

| Parameter | Wert |
|-----------|------|
| Strategy | FreqForge_Override |
| Timeframe | 15m |
| Stoploss | -0.050 (-5.0%) |
| Trailing | False (KEINE trailing-Parameter mehr im Code) |
| use_custom_stoploss | True |
| minimal_roi | {0: 0.060, 180: 0.040, 480: 0.025, 960: 0.015} |
| AI-Override Pairs | BTC/USDT, ETH/USDT, SOL/USDT |
| AI-Override Confidence | ≥ 0.75 |
| Dry-Run | True |
| Max Open Trades | 5 |
| Stake | 100 USDT |
| Container | freqtrade-freqforge (restarted 2026-06-04 05:04 UTC) |

## Baseline Metrics

| Metrik | Wert |
|--------|------|
| Total Trades | 58 |
| Closed Trades | 56 |
| Open Trades | 2 (ETH SHORT, SOL SHORT) |
| Total PnL | +13.43 USDT |
| Avg Profit | +0.0026% |
| Winrate | 85.7% |
| Best Trade | +3.55 USDT (+0.036%) |
| Worst Trade | -9.46 USDT (-0.095%) |

## AI-Override Metrics

| Metrik | Wert |
|--------|------|
| AI-Override Trades | 2 (closed) |
| AI-Override PnL | +1.58 USDT |
| AI-Override WR | 50.0% |

## Exit Reasons (All-Time)

| Exit Reason | Count | PnL |
|-------------|-------|-----|
| roi | 44 | +38.88 USDT |
| trailing_stop_loss | 9 | -4.33 USDT (PRE-FIX) |
| force_exit | 2 | -11.66 USDT |
| stop_loss | 1 | -9.46 USDT |

## Phase 1 Fix Applied

**Bug:** Trade #55 (BTC, -1.97 USDT) und #56 (SOL, +3.55 USDT) exited als `trailing_stop_loss`
obwohl `trailing_stop = False` gesetzt war.

**Root Cause:** In der Strategy-Klasse waren `trailing_stop_positive = 0.015`,
`trailing_stop_positive_offset = 0.025` und `trailing_only_offset_is_reached = True`
noch vorhanden. Freqtrade 2026.3' Strategy Resolver liest diese Parameter und verwendet
sie in Kombination mit `use_custom_stoploss = True` intern — das produziert
`trailing_stop_loss`-Exit-Reasons trotz `trailing_stop = False`.

**Fix:** Alle drei trailing-Parameter aus der Klasse entfernt. Container restarted.
Nach Restart zeigt Startup-Log `trailing_stop: False` und keine trailing-Parameter mehr.