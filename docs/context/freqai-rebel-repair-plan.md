# FreqAI Rebel Bot — Repair Plan
## 2026-06-22 | Status: DRAFT → awaiting approval

---

## Diagnose-Zusammenfassung

| Problem | Schwere | Evidenz |
|---------|---------|---------|
| Interne Restart-Schleife (585×) | KRITISCH | `worker found ... calling exit` + `SIGINT received` ohne Docker-Restart |
| FreqAI Pipeline Feature Mismatch | KRITISCH | Modell erwartet `%-rsi_1h_14_ETH/USDTUSDT_1h`, Daten liefern `%-rsi-period_14_ETH/USDTUSDT_5m` |
| Keine Trades seit 5 Tagen | KRITISCH | Letzter Trade #10 am 17. Juni; Bot nie lang genug stabil |
| Performance negativ | MODERAT | 10 Trades, 4W/6L, -0.32 USDT, 40% Winrate |
| Kein Docker-Healthcheck | INFO | `NO_HEALTHCHECK_CONFIGURED` — compose-File nicht zum Start verwendet |

---

## Phase 1: SIGINT-Quelle identifizieren & neutralisieren

### 1.1 Container-Prozessbaum inspizieren
- `docker top trading-freqai-rebel-1` — wer läuft da noch außer Freqtrade?
- `docker exec ... ps aux` — voller Prozessbaum
- Prüfen, ob ein Supervisor/init-System im Container SIGINT feuert

### 1.2 Freqtrade-Konfiguration auf Reload-Trigger prüfen
- `config.json` des Bots auf `internals.process_throttle_secs` oder Reload-Mechanismen checken
- `--reload` Flag? (aktuell nicht im compose, aber runtime-Config könnte es setzen)
- API-Endpoints: `/stop` offen ohne Auth?

### 1.3 Externe Signal-Quellen ausschließen
- Host-Prozesse: `ps aux | grep -E "kill.*freqai|signal.*rebel"` 
- Cron-Jobs im `orchestrator`- und `default`-Profil
- Systemd-Timer
- Docker-Events auf `kill`/`die` filtern (gezielt, nicht Stream)

### 1.4 Live-Monitoring (10 min)
- Bot-Logs live verfolgen während einer FreqAI-Inferenz
- Exakten Trigger-Zeitpunkt und Kontext identifizieren

### 1.5 Fix anwenden
- Je nach Ursache:
  - Internen Reload deaktivieren
  - API-Auth für `/stop` aktivieren
  - Externen SIGINT-Sender stoppen
- Verifikation: Bot muss >30 min ohne Restart laufen

---

## Phase 2: FreqAI-Modell reparieren

### 2.1 Modell-Verzeichnis inspizieren
- `ls -la /freqtrade/user_data/models/rebel-liquidation-v2/`
- Gespeicherte Pipeline-Dateien und deren Feature-Listen prüfen
- Timestamps: Wann wurde das Modell zuletzt trainiert?

### 2.2 Strategie-Feature-Naming prüfen
- `RebelLiquidation.py`: Welche Feature-Namen produziert die Strategie aktuell?
- `RebelXGBoostClassifier.py`: Welche Features erwartet der Classifier?
- Abgleich: Wo genau entsteht der Mismatch?

### 2.3 Altes Modell löschen & Neutrainieren
- Modell-Verzeichnis sichern (nach `/tmp/rebel-model-backup`)
- `rebel-liquidation-v2/` löschen
- Bot neu starten → FreqAI trainiert frisch mit aktuellen Features
- Predictions validieren: keine "Pipeline expected X but got Y"-Errors mehr

---

## Phase 3: Handelsfähigkeit validieren

### 3.1 Signal-Generierung prüfen
- Bot-Logs auf `buy signal` / `entry signal` monitoren
- `custom_entry_signal` / `custom_exit_signal` Logs
- Whitelist: `BTC/USDT:USDT`, `ETH/USDT:USDT` aktiv?

### 3.2 Ersten Trade abwarten
- Sobald stabil: ersten neuen Trade dokumentieren
- Entry-Conditions loggen

### 3.3 24h-Monitoring einrichten (optional)
- Cron-Job: stündlicher Healthcheck + Trade-Count
- Alert bei erneutem Restart-Loop

---

## Phase 4: Dokumentation

- `docs/context/freqai-rebel-repair-report.md` mit:
  - Ursachenanalyse
  - Durchgeführte Fixes
  - Vorher/Nachher-Performance
- `docs/state/current-operational-state.md` aktualisieren

---

## Risiken

| Risiko | Eintritts-Wkt | Mitigation |
|--------|--------------|------------|
| Modell-Neutraining schlägt fehl | Niedrig | Backup des alten Modells vorhanden |
| SIGINT-Quelle nicht identifizierbar | Mittel | Fallback: Container mit `docker run` frisch starten |
| Bot findet keine Trades nach Fix | Mittel | Ist marktbedingt; erst Stabilität sicherstellen |
| Datenverlust (DB) | Niedrig | DB ist nur 88K, 10 Trades — akzeptabler Verlust |

---

## Approval-Gates

- [ ] **GATE 1**: Phase-1-Plan approved → Phase 1 ausführen
- [ ] **GATE 2**: SIGINT-Quelle gefunden + Bot stabil >30 min → Phase 2 freigeben
- [ ] **GATE 3**: FreqAI-Modell repariert + Predictions sauber → Phase 3 freigeben
- [ ] **GATE 4**: Erster Trade nach Fix → Abschluss-Report
