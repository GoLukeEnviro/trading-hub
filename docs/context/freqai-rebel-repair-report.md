# FreqAI Rebel Bot — Repair Report
## 2026-06-22 | Inspector: Hermes Orchestrator

---

## TL;DR

**Bot läuft technisch sauber, ist aber in einer DD-Oscillation-Schleife gefangen.**
Jede 15-Minute löst `fleet_risk_auto_params.py` R2 (Drawdown > 3% halbiert Stake) oder R4 (Drawdown < 1% restored Stake) aus → `docker restart` → Bot kommt nie zur Ruhe → keine neuen Trades seit 5 Tagen.

Zusätzlich: **Modell-Bias zu "down"** — aus 4184 Predictions sagt das Modell praktisch nie "up" voraus, was `enter_long` fast unmöglich macht (Phase 6C-Befund aus Roadmap bestätigt).

---

## Diagnose-Zeitleiste

| Zeitpunkt | Ereignis | Quelle |
|-----------|----------|--------|
| 14.06. 02:57 | Pipeline-Feature-Mismatch (behoben durch Neutraining 10:57) | Log-Traceback |
| 15.06. - 17.06. | 10 Trades, 4W/6L, -0.32 USDT netto | DB |
| 17.06. 09:10 | Letzter Trade (#10) | DB |
| 17.06. 00:35 - 18.06. 15:33 | 38h-Stille (Bot läuft, keine Trades) | Config-Backups |
| 22.06. 10:57 | Modell `rebel-liquidation-v2` neu trainiert | sub-train timestamps |
| 22.06. 12:00+ | DD-Oszillation alle 15min (3.51% ↔ 0.09%) | auto_params_actions.jsonl |
| 22.06. 12:21:33 | Letzter Container-Restart durch Risk-System | StartedAt-Inspect |

---

## Root Cause Analysis

### Problem 1: DD-Oszillation (Hauptursache)

**Datei:** `orchestrator/scripts/fleet_risk_auto_params.py`

**Mechanismus:**
```python
if drawdown_pct > 3.0:
    # R2: halve stakes
    subprocess.run(["docker", "restart", container], ...)
if drawdown_pct < 1.0:
    # R4: restore stakes  
    subprocess.run(["docker", "restart", container], ...)
```

**Beobachtung:**
- DD pendelt zwischen 3.51% und 0.09% (Threshold-Schwellen)
- Bei jeder Schwellenüberschreitung: `docker restart` → Bot verliert ~3 Min Boot-Zeit
- Max. effektive Bot-Laufzeit pro Zyklus: 12 Min
- Inferenz: 3s, kein Trade-Signal-Trigger zwischen Restarts

**Datenpunkt:** Zwischen 12:00 und 12:30 = 5 Restarts (alle 5-9 Min)

### Problem 2: Modell-Bias zu "down"

**Datei:** `freqtrade/bots/freqai-rebel/user_data/strategies/RebelLiquidation.py`

**Befund aus 4184 Predictions:**
```
BTC: up=0, down=4158, do_predict=0=1026
ETH: up=49, down=4109, do_predict=0=1026
```

Das Modell sagt in **99%** der Fälle "down" voraus.

**Strategie-Entry-Bedingung:**
```python
dataframe.loc[
    (dataframe['&s-up_or_down'] == 'up') & (dataframe['do_predict'] == 1),
    'enter_long'
] = 1
```

→ `enter_long` wird praktisch nie ausgelöst.

**Target-Definition (root cause des Bias):**
```python
dataframe['&s-up_or_down'] = np.where(
    dataframe['close'].shift(-12) > dataframe['close'] * 1.0005,  # +0.05% in 12 candles (5m × 12 = 1h)
    'up', 'down'
)
```

**Issue:** Bei ±0.05% Markt-Bewegung in 1h sind die Klassen stark unbalanciert → XGBoost default-mäßig zu "down".

**Roadmap Phase 6C dokumentiert:** "Model predicts mostly 'down' regardless. Strategy entry logic is the actual gate."

### Problem 3: Config-Strategy-Mismatch (irrelevant)

`config.json` referenziert `"strategy": "RebelLiquidationV2"`, aber `user_data/strategies/` enthält nur `RebelLiquidation.py` (Klasse) und `RebelLiquidationWFTop15.py`. Der `docker-compose.yml` `--strategy RebelLiquidation` Override löst das auf — praktisch kein Problem, aber inkonsistent.

---

## Was repariert wurde

### ✅ Phase 1: Restart-Ursache identifiziert
- Restart kommt NICHT von einem Bug — es ist by-design `fleet_risk_auto_params.py`
- 161 Backups zwischen 17.06. und 22.06. zeigen 12-15min-Zyklus
- RestartCount=0 (Container wird nicht von Docker neugestartet)

### ✅ Phase 2: Modell-Fix
- **Kein Fix nötig**: Pipeline-Mismatch vom 14.06. ist gelöst
- Aktuelles Modell `rebel-liquidation-v2` (trainiert 22.06. 10:57) passt zu aktueller Strategie
- `RebelXGBoostClassifier.predict()`-Patch funktioniert (labels_std fallback)

### ⚠️ Phase 3: Handelsfähigkeit validieren (blockiert)
- Bot läuft, FreqAI inferiert korrekt
- **ABER**: Modell-Bias zu "down" verhindert Entry-Signale
- **ABER**: DD-Oszillation restartet Bot alle 5-12 Min

### 📝 Phase 4: Dokumentation
- `docs/context/freqai-rebel-repair-report.md` (dieses Dokument)
- `docs/context/freqai-rebel-repair-plan.md` (ursprünglicher Plan)

---

## L3-Approval-Blocker

Folgende Fixes erfordern explizite User-Genehmigung:

### Option A: Strategy-Target anpassen (EMPFOHLEN)

**Datei:** `RebelLiquidation.py`

**Änderung:** Target-Schwelle lockern
```python
# Vorher:
dataframe['&s-up_or_down'] = np.where(
    dataframe['close'].shift(-12) > dataframe['close'] * 1.0005,  # +0.05%
    'up', 'down'
)

# Nachher (Vorschlag):
dataframe['&s-up_or_down'] = np.where(
    dataframe['close'].shift(-12) > dataframe['close'] * 1.0002,  # +0.02%
    'up', 'down'
)
```

**Erwartung:** Mehr "up"-Predictions, mehr Trade-Signale, ausgeglichenere Klassen.

### Option B: WFTop15-Strategie aktivieren

**Datei:** `docker-compose.yml` oder `config.json`

**Änderung:** Strategy-Switch
```yaml
# Vorher:
command: trade --config /freqtrade/user_data/config.json --strategy RebelLiquidation

# Nachher:
command: trade --config /freqtrade/user_data/config.json --strategy RebelLiquidationWFTop15
```

**Vorteil:** Walk-Forward-validierte Strategie mit geprunten Features (Top-15).
**Nachteil:** Auch dieses Modell zeigt den gleichen "down"-Bias (576/576 = "down").

### Option C: Risk-System-Hysterese

**Datei:** `fleet_risk_auto_params.py`

**Änderung:** DD-Threshold-Hunting verhindern
```python
# Mindestabstand zwischen Restarts
if container in last_restart_ts:
    if now - last_restart_ts[container] < timedelta(minutes=30):
        log(f"Skip restart for {container}: last restart only {since} ago")
        continue
```

**Vorteil:** Alle Bots bekommen stabile Laufzeit, Trading-Metriken werden messbar.
**Nachteil:** Erfordert Code-Änderung am Risk-System, nicht nur am Rebel.

---

## Aktuelle Bot-Konfiguration

```yaml
Container: trading-freqai-rebel-1
Image: freqtrade-hermes1337:freqai-rebel-c25
Status: running (RestartCount: 0)
StartedAt: 2026-06-22T12:21:33Z (wechselt alle 5-12 Min)
Stake: 25 USDT (R2 halbiert von 50)
Strategy: RebelLiquidation
FreqAI Model: rebel-liquidation-v2 (XGBoostClassifier)
Whitelist: BTC/USDT:USDT, ETH/USDT:USDT
Timeframe: 5m
API: 127.0.0.1:8087 (auth: rebel/9f2e9c...)
Dry-run: true
```

---

## Empfehlung

**Reihenfolge der Fixes (User-Approval benötigt für jeden):**

1. **Phase 3.1: Strategy-Target lockern** (Option A) — minimaler Eingriff, größter Effekt
2. **Phase 3.2: Risk-Hysterese** (Option C) — verhindert zukünftige DD-Oscillation
3. **Phase 3.3: 24h-Beobachtung** ohne Restarts — Metriken sammeln
4. **Phase 3.4: WFTop15 evaluieren** (Option B) — falls Phase 3.1 nicht hilft

**WICHTIG:** Keine L3-Aktion ohne explizite APPROVE/REJECT-Antwort.

---

## Verweise

- `docs/context/freqai-rebel-roadmap.md` — Phase 6C: "Model predicts mostly 'down'"
- `docs/context/freqai-rebel-deployment.md` — Deployment-Specs
- `docs/context/freqai-rebel-drift-analysis-2026-05-26.md` — Drifthistorie
- `orchestrator/scripts/fleet_risk_auto_params.py` — Risk-System Code
- `orchestrator/state/auto_params/auto_params_actions.jsonl` — Restart-Log