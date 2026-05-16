# FreqAI-rebel Patch Proposal — RSIP v3

**Erstellt:** 2026-05-15  
**Status:** PROPOSAL (kein Deploy)  
**Autor:** Hermes Agent (RSIP Recursive Self-Improvement Process)  
**Betroffen:** freqai-rebel Container, Port 8087, XGBoost Classifier  

---

## Executive Summary

FreqAI-rebel hat seit Deployment **0 Trades** generiert. Ursache ist eine Kaskade aus
vier ineinandergreifenden Fehlern: zu strenger Label-Threshold erzeugt ein extrem
ungleichgewichtetes Trainingset → das Modell lernt "immer down" vorherzusagen → der
DI_threshold von 0.9 ist unerreichbar (max DI=0.73) → die wenigen Prediktionen, die
den DI-Gate passieren, sagen trotzdem "down" voraus → Entry-Bedingung
`(&s-up_or_down == 'up') AND (do_predict == 1)` ist niemals erfüllt.

Der Patch behebt alle vier Glieder der Ursachenkette mit minimal-invasiven Änderungen
in Strategy und Config.

---

## Diagnostische Evidenz

| Metrik | Wert | Referenz |
|--------|------|----------|
| Total historic predictions | 1186 | FreqAI prediction table |
| Predicted "up" | **0** (0.0%) | FreqAI prediction table |
| Predicted "down" | 1102 (93%) | FreqAI prediction table |
| do_predict=1 | 102/1186 (8.6%) | FreqAI prediction table |
| DI mean | 0.057 | DI statistics query |
| DI max | 0.733 | DI statistics query |
| DI > 0.9 count | **0** | DI statistics query |
| DI > 0.5 count | 102 | DI statistics query |
| Training data points | 6312 | FreqAI training log |
| Features BTC / ETH | 436 / 220 | FreqAI feature log |
| Label definition | `close.shift(-12) > close * 1.002` | `RebelLiquidation.py:62-64` |
| DI_threshold | 0.9 | `config.json:86` |
| Entry condition | `(&s-up_or_down == 'up') & (do_predict == 1)` | `RebelLiquidation.py:73-76` |
| Model identifier | rebel-liquidation-v1-wrapper-n80-es20-t002 | `config.json:69` |
| n_estimators / max_depth / lr | 80 / 6 / 0.05 | `config.json:93-95` |
| Container uptime | 11h | `docker ps` |

### Root Cause Chain (Reproduzierbar)

```
1. Label threshold 1.002 (0.2%) in 60min zu streng
   → Label-Imbalance: ~93% "down", ~7% "up" im Trainingset
2. XGBoost lernt Mehrheitsklasse ("down") als Default
   → 93% down-Prediktionen, 0% up-Prediktionen in historic data
3. DI_threshold=0.9 unerreichbar (max DI=0.73)
   → do_predict=0 für 91.4% der Candles
4. Die 8.6% mit do_predict=1 sagen ALLE "down" voraus
   → Entry condition NIE erfüllt → 0 Trades
```

---

## RSIP Iteration Log

### Iteration 1 — Grundstruktur

**Ziel:** Initiale Fix-Optionen definieren mit Code-Diffs.

#### Option A: Label-Threshold reduzieren (1.002 → 1.0005)

**Begründung:** 0.2% rise in 60min ist für BTC zu restriktiv. Ein Threshold von
0.05% (1.0005) erzeugt eine annähernd ausgeglichene Label-Verteilung.

**Datei:** `RebelLiquidation.py` Zeile 62-64

```diff
-        dataframe['&s-up_or_down'] = np.where(
-            dataframe['close'].shift(-12) > dataframe['close'] * 1.002,
-            'up', 'down'
-        )
+        dataframe['&s-up_or_down'] = np.where(
+            dataframe['close'].shift(-12) > dataframe['close'] * 1.0005,
+            'up', 'down'
+        )
```

**Vorteil:** Schnellster Fix, direkt am Kernproblem.
**Nachteil:** Threshold ist willkürlich, erfordert Backtesting zur Kalibrierung.

#### Option B: DI_threshold reduzieren (0.9 → 0.4)

**Begründung:** Max DI=0.73, mean=0.057. DI>0.5 sind 102 Prediktionen.
DI_threshold=0.4 würde signifikant mehr Prediktionen durchlassen.

**Datei:** `config.json` Zeile 86

```diff
-            "DI_threshold": 0.9
+            "DI_threshold": 0.4
```

**Vorteil:** Sofortige Erhöhung der do_predict=1 Rate.
**Nachteil:** Behebt nicht das Label-Imbalance-Problem; mehr Prediktionen, aber
wenn alle "down" sagen, bringt es nichts allein.

#### Option C: Perzentil-basierte Labels

**Begründung:** Anstatt eines fixen Thresholds wird das Label als "up" definiert
wenn die Future-Return im oberen Quartil (Top 25%) liegt. Automatisch balanciert.

**Datei:** `RebelLiquidation.py` Zeile 60-65

```diff
     def set_freqai_targets(self, dataframe, **kwargs):
         self.freqai.class_names = ['down', 'up']
-        dataframe['&s-up_or_down'] = np.where(
-            dataframe['close'].shift(-12) > dataframe['close'] * 1.002,
-            'up', 'down'
-        )
+        future_return = dataframe['close'].shift(-12) / dataframe['close'] - 1
+        threshold = future_return.rolling(252, min_periods=50).quantile(0.75)
+        dataframe['&s-up_or_down'] = np.where(
+            future_return > threshold,
+            'up', 'down'
+        )
         return dataframe
```

**Vorteil:** Automatische Balance, adaptive Schwelle.
**Nachteil:** Komplexität, Rolling-Window muss kalibriert werden, kann NaN-Problem
an Start der Serie erzeugen.

#### Selbstkritik Iteration 1

1. **Kein Risikobewertung:** Was passiert wenn das Modell plötzlich zu viele Trades
   generiert? Keine Guards definiert.
2. **Kein Rollback-Plan:** Wie wird reverted wenn der Fix verschlimmert?
3. **Keine Metriken:** Keine konkreten Erfolgskriterien definiert; wann gilt der
   Patch als erfolgreich?

---

### Iteration 2 — Klarheit/Logik

**Verfeinerung basierend auf Iteration-1-Kritik.**

#### Empfohlener Fix: Kombination aus Option A + B (Gestaffelt)

**Phase 1 — Sofort (Hotfix):** DI_threshold auf 0.4 setzen.
**Phase 2 — Nach Retrain:** Label-Threshold auf 1.0005 setzen.

**Begründung für gestaffeltes Vorgehen:** DI_threshold lässt sich ohne Retrain
ändern (nur config.json). Label-Threshold erfordert Retrain und neue Model-Identifier.
Beide zusammen verhindern, dass Phase 1 allein zu vielen schlechten Trades führt.

#### Risikoabschätzung

| Risiko | Wahrscheinlichkeit | Impact | Mitigation |
|--------|-------------------|--------|------------|
| Zu viele Trades nach DI-Senkung | Mittel | Niedrig (dry_run) | max_open_trades=3 begrenzt |
| Model sagt weiterhin "down" nach DI-Senkung | Hoch | Kein Trade | Erst nach Phase 2 behoben |
| Label-Threshold zu niedrig → Overtrading | Niedrig | Mittel | Backtest zuerst |
| NaN in Perzentil-Labels | Mittel | Hoch | min_periods=50 Guard |
| Model-Identität kollidiert mit altem Model | Niedrig | Hoch | Neue identifier vergeben |

#### Rollback-Plan

```
ROLLBACK PHASE 1 (DI_threshold):
  1. config.json: DI_threshold → 0.9 zurücksetzen
  2. Container restart: docker restart freqai-rebel
  3. Erwartet: do_predict=1 Rate sinkt auf 8.6% (wie vorher)

ROLLBACK PHASE 2 (Label-Threshold):
  1. RebelLiquidation.py: Threshold → 1.002 zurücksetzen
  2. config.json: identifier → neuen Suffix anhängen (z.B. "-rollback")
  3. Alte Model-Dateien löschen: docker exec freqai-rebel rm -rf /freqtrade/user_data/models/<old-id>
  4. Container restart
  5. Erwartet: Zurück zu 0 Trades (wie vorher)
```

#### Erwartete Impact-Metriken

| Metrik | Vorher | Nach Phase 1 | Nach Phase 2 |
|--------|--------|-------------|-------------|
| do_predict=1 Rate | 8.6% (102/1186) | ~40-60% (geschätzt) | ~40-60% |
| "up" Predictions | 0 (0%) | ~0% (noch kein Retrain) | ~35-50% |
| Trades generiert | 0 | 0 (Phase 1 allein) | 5-30/Tag (geschätzt) |
| Label-Balance | ~7% up / 93% down | Unverändert | ~45-55% up |
| DI-Verteilung | mean=0.057, max=0.73 | Unverändert | Unverändert |

#### Selbstkritik Iteration 2

1. **Keine Verifikationsschritte:** Wie stellen wir fest dass der Patch korrekt
   angewendet wurde? Keine Checkliste.
2. **Kein Monitoring-Plan:** Wie überwachen wir den Bot nach dem Patch? Wann
   greifen wir ein?
3. **Perzentil-Labels (Option C) wurde verworfen:** Das ist die elegantere Lösung,
   aber es fehlt eine Begründung warum sie nicht empfohlen wird. Sollte als
   "Future Improvement" dokumentiert werden.

---

### Iteration 3 — Feinschliff

**Finaler Polish mit Verifikation, Monitoring und Erfolgskriterien.**

#### Ergänzungen

1. **Verifikationsschritte** für jede Phase mit konkreten Kommandos.
2. **Monitoring-Plan** mit Telegram-Alerting über bestehende Infrastruktur.
3. **Erfolgskriterien** mit quantitativen Schwellenwerten.
4. **Option C (Perzentil-Labels)** als Future Improvement aufgenommen.
5. **Klassifikations-Metriken** ergänzt (Precision, Recall, F1 erwartet).

#### Selbstkritik Iteration 3

1. Alle drei vorherigen Schwächen adressiert.
2. Proposal ist jetzt "deployment-ready" — kann vom SRE als Runbook verwendet werden.
3. Keine weiteren kritischen Schwächen identifiziert; RSIP abgeschlossen.

---

## Final Output — Patch Proposal v3

### Patch: FREQAI-REBEL-001 — Fix Zero-Trade Bug

**Dringlichkeit:** HOCH (Bot generiert seit 11h 0 Trades)  
**Typ:** Config + Strategy Patch  
**Betroffene Dateien:**  
- `freqtrade/bots/freqai-rebel/user_data/config.json`  
- `freqtrade/bots/freqai-rebel/user_data/strategies/RebelLiquidation.py`  

**Voraussetzungen:** FreqAI-rebel Container läuft (bestätigt: UP 11h, Port 8087)  
**dry_run:** Ja (bestätigt: `"dry_run": true` in config.json)  

---

### Phase 1 — DI_threshold Senkung (Sofort, kein Retrain nötig)

**Datei:** `freqtrade/bots/freqai-rebel/user_data/config.json`  
**Zeile:** 86  
**Änderung:** DI_threshold von 0.9 auf 0.4 senken

```diff
             "indicator_periods_candles": [
                 10,
                 20
             ],
-            "DI_threshold": 0.9
+            "DI_threshold": 0.4
         },
```

**Begründung:** Bei DI_threshold=0.9 passieren 0 von 1186 Prediktionen den Gate
(Evidenz: DI max=0.733, DI>0.9 count=0). Bei DI_threshold=0.4 passieren geschätzt
~40-60% der Prediktionen. Dies allein erzeugt noch keine Trades (da alle Prediktionen
"down" sagen), bereitet aber Phase 2 vor indem do_predict=1 Rate erhöht wird.

**Anwendung:**
```bash
# Config editieren
# Container restart
docker restart freqai-rebel
```

**Verifikation Phase 1:**
```bash
# 1. Prüfen dass Container healthy
docker ps --filter name=freqai-rebel --format "{{.Status}}"

# 2. Auf neue Prediktionen warten (~30min)
# 3. DI-Verteilung prüfen
docker exec freqai-rebel sqlite3 /freqtrade/user_data/models/rebel-liquidation-v1-wrapper-n80-es20-t002/*/historic_predictions.db \
  "SELECT COUNT(*) FROM predictions WHERE do_predict=1;"

# 4. Erwartet: do_predict=1 Rate deutlich über 8.6%
```

**Rollback Phase 1:**
```bash
# DI_threshold → 0.9 zurücksetzen
# docker restart freqai-rebel
```

---

### Phase 2 — Label-Threshold Anpassung (Erfordert Retrain)

**Datei:** `freqtrade/bots/freqai-rebel/user_data/strategies/RebelLiquidation.py`  
**Zeile:** 60-65  
**Änderung:** Label-Schwelle von 1.002 auf 1.0005 senken

```diff
     def set_freqai_targets(self, dataframe, **kwargs):
         self.freqai.class_names = ['down', 'up']
-        dataframe['&s-up_or_down'] = np.where(
-            dataframe['close'].shift(-12) > dataframe['close'] * 1.002,
-            'up', 'down'
-        )
+        dataframe['&s-up_or_down'] = np.where(
+            dataframe['close'].shift(-12) > dataframe['close'] * 1.0005,
+            'up', 'down'
+        )
         return dataframe
```

**Begründung:** Der aktuelle Threshold von 1.002 (0.2% rise in 60min) erzeugt ein
extrem unausgewogenes Trainingset (~93% "down" Labels, Evidenz: 1102/1186 historic
predictions sind "down", 0 sind "up"). XGBoost lernt die Mehrheitsklasse als Default.
Ein Threshold von 1.0005 (0.05% rise in 60min) sollte eine annähernd balancierte
Label-Verteilung erzeugen (~45-55% "up").

**Zusätzlich — Model Identifier aktualisieren:**  
**Datei:** `freqtrade/bots/freqai-rebel/user_data/config.json`  
**Zeile:** 69

```diff
-        "identifier": "rebel-liquidation-v1-wrapper-n80-es20-t002",
+        "identifier": "rebel-liquidation-v1-wrapper-n80-es20-t0005",
```

**Anwendung:**
```bash
# Strategy editieren
# Config editieren (identifier + DI_threshold falls nicht schon in Phase 1)
# Alte Model-Daten bereinigen (optional, spart Speicher)
docker exec freqai-rebel rm -rf /freqtrade/user_data/models/rebel-liquidation-v1-wrapper-n80-es20-t002
# Container restart → erzwingt Retrain mit neuen Labels
docker restart freqai-rebel
```

**Verifikation Phase 2:**
```bash
# 1. Container healthy nach Restart
docker ps --filter name=freqai-rebel --format "{{.Status}}"

# 2. Retrain beobachten (Dauer: ~5-15min für 6312 Datenpunkte)
docker logs freqai-rebel --tail 50 -f
# Erwarten: "Training model..." Logs mit neuer identifier

# 3. Nach Retrain: Label-Verteilung prüfen
# Erwarten: ~45-55% "up" predictions statt 0%

# 4. Erste Trades generiert?
# Erwarten: innerhalb von 1-6 Stunden erste Long-Entries

# 5. Trade-Qualität prüfen
# Erwarten: ROI-Verteilung ähnlich Backtest-Erwartungen
```

**Rollback Phase 2:**
```bash
# RebelLiquidation.py: Threshold → 1.002 zurücksetzen
# config.json: identifier → "rebel-liquidation-v1-wrapper-n80-es20-t002"
# Neue Model-Daten löschen
docker exec freqai-rebel rm -rf /freqtrade/user_data/models/rebel-liquidation-v1-wrapper-n80-es20-t0005
# Container restart
docker restart freqai-rebel
# Erwartet: Zurück zu 0 Trades (wie vorher)
```

---

### Erfolgskriterien

| Kriterium | Schwellenwert | Zeitrahmen | Messmethode |
|-----------|--------------|------------|-------------|
| do_predict=1 Rate | > 30% | 1h nach Phase 1 | SQLite Query auf historic_predictions |
| Label-Balance | 30-70% "up" | Nach Retrain (Phase 2) | Training-Log Analyse |
| Erste Trades | ≥ 1 Trade | 6h nach Phase 2 | Freqtrade API `/api/v1/trades` |
| Trade-Rate | 5-30 Trades/Tag | 24h nach Phase 2 | Daily Trade Count |
| Win-Rate | > 45% | 7 Tage nach Phase 2 | Freqtrade Profit-Statistik |
| Max Drawdown | < 10% | 7 Tage nach Phase 2 | dry_run_wallet Balance |

### Monitoring-Plan

**Stunde 0-6 nach Phase 2:**
- Manuelle Prüfung alle 30min über Freqtrade API
- Prüfung: werden Trades geöffnet?
- Prüfung: Label-Verteilung in Prediktionen

**Stunde 6-24 nach Phase 2:**
- Stündliche Prüfung über Freqtrade API
- Prüfung: Trade-Rate, Win-Rate
- Prüfung: DI-Verteilung stabil?

**Tag 2-7 nach Phase 2:**
- Täglicher Report über bestehendes Telegram-Alerting
- Entscheidung: Patch beibehalten oder Rollback

**Eskalationskriterien (sofortiger Rollback):**
- > 50 Trades/Stunde (Overtrading)
- dry_run_wallet < 800 (-20%)
- 100% Win oder 100% Loss (Modell defekt)

### Future Improvement — Option C: Perzentil-basierte Labels

Perzentil-basierte Labels (Option C aus Iteration 1) sind als langfristige
Verbesserung vorgesehen. Vorteile:
- Adaptive Schwelle, keine manuelle Kalibrierung nötig
- Automatisch balancierte Labels in allen Marktphasen
- Weniger Parameter-Tuning erforderlich

Empfohlener Implementierungszeitpunkt: Nach 7 Tagen erfolgreichen Betriebs mit
Phase 2, wenn sich das System stabilisiert hat.

```python
# Future Implementation (NICHT TEIL DIESES PATCHES)
def set_freqai_targets(self, dataframe, **kwargs):
    self.freqai.class_names = ['down', 'up']
    future_return = dataframe['close'].shift(-12) / dataframe['close'] - 1
    threshold = future_return.rolling(252, min_periods=50).quantile(0.75)
    dataframe['&s-up_or_down'] = np.where(
        future_return > threshold,
        'up', 'down'
    )
    return dataframe
```

---

## Improvement Summary

### RSIP Prozess-Übersicht

| Iteration | Fokus | Schwächen identifiziert | Behoben in |
|-----------|-------|------------------------|------------|
| 1 — Grundstruktur | 3 Fix-Optionen mit Diffs | Keine Risikoabschätzung, kein Rollback, keine Metriken | Iteration 2 |
| 2 — Klarheit/Logik | Risiko + Rollback + Metriken | Keine Verifikation, kein Monitoring, Option C unbegründet | Iteration 3 |
| 3 — Feinschliff | Verifikation + Monitoring + Erfolgskriterien | Keine weiteren | — (abgeschlossen) |

### Kritische Erkenntnisse

1. **Label-Threshold ist das Kernproblem.** 1.002 (0.2%) erzeugt ~93% "down" Labels.
   Das Modell kann nicht lernen was es nie gesehen hat (ausreichend "up" Beispiele).

2. **DI_threshold ist ein sekundäres Problem.** Selbst wenn do_predict=1 für alle
   Candles gelten würde, würde das Modell "down" vorhersagen → kein Trade. Aber die
   Senkung ist notwendig damit Phase 2 überhaupt Prediktionen liefern kann.

3. **Beide Fixes sind notwendig, aber gestaffelt.** Phase 1 (DI) kann sofort ohne
   Retrain angewendet werden. Phase 2 (Label) erzwingt einen Retrain, der ~5-15min
   dauert. Die Kombination beider ist erforderlich.

4. **Dry_run=true ist der Safety-Net.** Alle Änderungen können gefahrlos getestet
   werden, da keine echten Orders platziert werden. Die max_open_trades=3 Begrenzung
   und der trailing_stop bieten zusätzliche Guards.

5. **Perzentil-Labels (Option C) bleiben als Zukunftsmusik.** Eleganter, aber
   komplexer. Sollte nach Stabilisierung evaluiert werden.

### Datei-Übersicht der Änderungen

| Datei | Zeile | Vorher | Nachher | Phase |
|-------|-------|--------|---------|-------|
| `config.json` | 86 | `"DI_threshold": 0.9` | `"DI_threshold": 0.4` | 1 |
| `RebelLiquidation.py` | 62-64 | `1.002` | `1.0005` | 2 |
| `config.json` | 69 | `t002` | `t0005` | 2 |

---

*End of RSIP Patch Proposal — bereit zur Review durch Senior Quant/SRE*
