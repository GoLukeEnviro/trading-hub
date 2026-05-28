# FREQAI MODEL DRIFT REPORT 26.05.2026

Zeitstempel: 2026-05-26 23:15 UTC
Bot: FreqAI-Rebel
Identifier: rebel-liquidation-v1-wrapper-n80-es20-t0005

## 1) Modell-Status & Files

Status: aktiv, Inferencing läuft laut Logs alle 5 Minuten; Training lief um 22:59 UTC für BTC und ETH durch.

Persistierte Artefakte im Volume `/freqtrade/user_data/models/`:
- `rebel-liquidation-v1/`
- `rebel-liquidation-v1-wrapper/`
- `rebel-liquidation-v1-wrapper-n80-es20/`
- `rebel-liquidation-v1-wrapper-n80-es20-t0005/` ← aktiver Satz
- `rebel-liquidation-v1-wrapper-n80-es20-t002/`
- `rebel-liquidation-v1-wrapper-n80-es20-t002-di00/`
- `rebel-liquidation-v1-wrapper-n80-es20-t002-di05/`

Aktiver Satz enthält je Pair u. a.:
- `historic_predictions.pkl`
- `historic_predictions.backup.pkl`
- `pair_dictionary.json`
- `run_params.json`
- `sub-train-BTC_*`
- `sub-train-ETH_*`

DB-Status:
- Trades DB: `/freqtrade/tradesv3.dryrun.sqlite`
- Gesamttrades: 73
- Offene Trades: 0
- Trades seit Bot-Restart 22:51 UTC: 0

Persistierte Prediction-Artefakte:
- Letztes gespeichertes Prediction-Paket (`historic_predictions.pkl`) mtime: 22:59 UTC
- Letzte im Paket enthaltene `date_pred`: 22:50 UTC
- Das spricht dafür, dass das persistierte Paket ein historischer Snapshot ist; Live-Inferencing läuft laut Logs zusätzlich weiter.

## 2) Wichtige Modellparameter

- timeframe: 5m
- train_period_days: 60
- backtest_period_days: 7
- label horizon: 12 candles
- DI_threshold: 1.1
- n_estimators: 80
- max_depth: 6
- learning_rate: 0.05
- early_stopping_rounds: 20

## 3) Drift-Metriken

Hinweis: Feature-Drift wurde aus den aktuellen Roh-Feather-Dateien + reproduzierter Feature-Engineering-Logik berechnet. Wenn die Live-Pipeline intern abweicht, muss dieser Teil gegen die echte FreqAI-Feature-Generierung gegengeprüft werden.

### BTC/USDT:USDT
- Feature drift avg PSI: 12.880 → ROT
- Feature drift avg KS: 0.957 → ROT
- Label drift PSI: 0.074 → GRÜN
- Label up-rate: Train 43.0% vs Live 30.0% = -13.0 pp
- Prediction confidence: 0.566 hist → 0.546 live(200) = -0.020
- Accuracy: 99.8% hist → 100.0% live(200)
- Letzte gespeicherte Prediction: down @ 0.5108
- 2h-Window im Artefakt: 7 up / 18 down / 25 do_predict / 7 Entry-Candidates

### ETH/USDT:USDT
- Feature drift avg PSI: 13.313 → ROT
- Feature drift avg KS: 1.000 → ROT
- Label drift PSI: 0.072 → GRÜN
- Label up-rate: Train 43.9% vs Live 31.0% = -12.9 pp
- Prediction confidence: 0.560 hist → 0.553 live(200) = -0.007
- Accuracy: 99.8% hist → 100.0% live(200)
- Letzte gespeicherte Prediction: down @ 0.5233
- 2h-Window im Artefakt: 3 up / 22 down / 25 do_predict / 3 Entry-Candidates

### Aggregiert
- Feature drift: PSI 13.097, KS 0.979 → ROT
- Label drift: PSI 0.073 → GRÜN, aber Up-Rate-Shift ~ -13 pp → inhaltlich relevant
- Prediction drift: Confidence leicht runter, aber nur um ca. 0.014
- Performance drift: Artefakt-Accuracy bleibt fast perfekt; das ist auffällig und sollte als potenzieller Artefakt-/Leakage-Effekt nachgeprüft werden, weil es nicht gut zu 0 Live-Trades passt

## 4) Live-Trade-Potential

- Logs zeigen Inferencing-Zyklen um 23:00 / 23:05 / 23:10 / 23:15 UTC.
- Logs zeigen keine neuen Trade-Open-Ereignisse seit dem Neustart um 22:51 UTC.
- DB: 0 Trades seit Neustart, 0 offene Trades.
- Damit ist die praktische Live-Trade-Umsetzung aktuell Null, obwohl der Modell-Loop läuft.

Wahrscheinliche Ursachen:
1. Persistierte Prediction-Artefakte sind historisch und nicht 1:1 die Live-Entscheidungsebene.
2. Die Feature-/Label-Artefakte zeigen starke Verschiebung, wodurch die aktuelle Live-Phase wahrscheinlich nicht sauber zur Trainingsverteilung passt.
3. Der aktuelle Live-Output erzeugt im operativen Run keine messbaren Entries/Orders.

## 5) Empfehlung

Retraining notwendig: JA.

Begründung:
- Feature Drift ist extrem rot.
- 2h-Window zeigt im operativen Run keine neuen Trades seit Start.
- Die persistierten Artefakt-Metriken sind zwar bei Accuracy auffällig gut, aber das ist in Kombination mit 0 Live-Trades nicht vertrauenswürdig genug.
- Ich würde das als NO-GO für weiteren Live-Betrieb in der jetzigen Form werten.

Empfohlene nächste Aktion:
- Sofort retrain mit sauberer OOS-/Walk-Forward-Verifikation.
- Vor dem nächsten Go: Feature-Alignment prüfen, Live- vs. Backtest-Artefakte trennen, und die Trade-Trigger im echten Live-Log gegen die Prediction-Artefakte abgleichen.

## 6) Alert-Regeln für fleet_auto_repair.py

- Feature PSI > 0.25 auf irgendeinem Top-10-Feature → Drift-Alarm
- Label PSI > 0.10 oder Up-Rate-Shift > 10 pp → Retrain-Alarm
- Live Confidence fällt > 0.05 unter historischen 200er-Schnitt → Modellqualitäts-Alarm
- 2h Entry-Candidates == 0 über 2 aufeinanderfolgende Zyklen → Signal-Starvation-Alarm
- Rolling Live Accuracy > 5 pp unter historischem Referenzwert → Performance-Alarm

## 7) Go / No-Go

Go/No-Go: NO-GO
Nächste Aktion: sofort retrain, dann Live-/Artefakt-Abgleich und erneute Drift-Prüfung.
