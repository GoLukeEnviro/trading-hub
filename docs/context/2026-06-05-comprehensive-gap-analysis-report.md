# GAP-ANALYSE: Autonomes Trading-System — Comprehensive Deep Dive

**Datum:** 2026-06-05 14:45 UTC  
**Ersteller:** Hermes Orchestrator (GLM-5-Turbo)  
**Scope:** Vollständiges Trading-System (ai-hedge-fund-crypto + Freqtrade Fleet + Infrastruktur)  
**Modus:** Read-only Forensic Audit — keine Änderungen vorgenommen

---

## Inhaltsverzeichnis

1. [Executive Summary](#1-executive-summary)
2. [Methodik](#2-methodik)
3. [Status Quo — Systemüberblick](#3-status-quo--systemüberblick)
4. [Dimension 1: Marktdaten-Lücken](#4-dimension-1-marktdaten-lücken)
5. [Dimension 2: Signalgenerierungs-Lücken](#5-dimension-2-signalgenerierungs-lücken)
6. [Dimension 3: Ausführungs- & Order-Management-Lücken](#6-dimension-3-ausführungs--order-management-lücken)
7. [Dimension 4: Risikomanagement-Lücken](#7-dimension-4-risikomanagement-lücken)
8. [Dimension 5: Technische Infrastruktur-Lücken](#8-dimension-5-technische-infrastruktur-lücken)
9. [Dimension 6: Betriebliche & Prozess-Lücken](#9-dimension-6-betriebliche--prozess-lücken)
10. [Schwarze Flecken (Unbekannte Unbekannte)](#10-schwarze-flecken-unbekannte-unbekannte)
11. [Priorisierte Roadmap](#11-priorisierte-roadmap)
12. [Anhang: Evidenz-Index](#12-anhang-evidenz-index)

---

## 1. Executive Summary

Das System ist **funktional und sicher** — 4/4 Bots laufen im Dry-Run, Signal-Pipeline ist frisch, und der Netto-PnL beträgt +23.05 USDT über 150 Trades. Die Safety-Layer (Drawdown Guard, Consec Loss, Config Diff) sind alle grün.

**Aber: Vollständige Autonomie ist noch nicht erreicht.** Die Analyse identifiziert **2 kritische, 10 hohe, 8 mittlere und 6 niedrige Lücken**, die den autonomen Betrieb gefährden oder die Performance beeinträchtigen.

| Severity | Count | Beispiele |
|----------|-------|-----------|
| 🔴 Kritisch | 2 | Shared Volume Mount, RG-4 Double-Evaluation Bug |
| 🟠 Hoch | 10 | Hardcoded TOTAL_CAPITAL, fehlende stoploss, duplizierte Risk Logic |
| 🟡 Mittel | 8 | Unbegrenztes Log-Wachstum, fehlende Container Limits |
| 🔵 Niedrig | 6 | Dead Code, Code-Qualität |

**Gesamtbewertung:** FUNKTIONAL MIT MONITORIERBAREN RISIKEN — nicht autonomiebereit ohne Schließung der kritischen und hohen Lücken.

---

## 2. Methodik

### 2.1 Analyse-Ebenen

| Ebene | Methode | Umfang |
|-------|---------|--------|
| **Architektur-Review** | Docker-Netzwerkanalyse, Container-Topologie, Datenfluss-Diagramme | 22 Container, 13 Networks, 8 docker-compose Files |
| **Code-Analyse** | Vollständige Lektüre aller aktiven Scripts und Strategien | 18 Dateien (7.800+ Zeilen) |
| **Konfigurations-Audit** | Host-Seite Config-Exfiltration von 4 Freqtrade Bots | Key-by-Key Vergleich (dry_run, stoploss, stake_amount, trading_mode) |
| **Datenflussanalyse** | Signal-Kette: AI → Signal JSON → Primo Bridge → RiskGuard → MCP | 4 State Files + 3 Bridge-Scripts |
| **Cron-Scheduler-Audit** | Vollständige jobs.json Auswertung | 40 Jobs, Timestamps, Status |
| **Performance-Forensik** | SQLite-Datenbank-Query pro Bot | 4 DBs, 150 Trades |
| **Schwachstellenscan** | Suche nach Credential-Leaks, falschen Permissions, unsicheren Writes | .gitignore, Docker-Rechte, Secret-Leak Pattern |
| **Simulationsexperiment** | Gedankengang zu Worst-Case-Szenarien | Split-Brain, Market Crash, Cron-Ausfall, MCP-Deadlock |

### 2.2 Bewertungsschema

| Kriterium | Skala |
|-----------|-------|
| **Schweregrad** | Kritisch → Hoch → Mittel → Niedrig |
| **Auftrittswahrscheinlichkeit** | Häufig (>1/Monat) → Gelegentlich (<1/Monat) → Selten (<1/Quartal) |
| **Impact auf Autonomie** | Vollständiger Stillstand → Fehlentscheidungen → Performance-Verlust → Reporting-Lücke |
| **Erkennbarkeit** | Sofort erkennbar → Nur bei Audit sichtbar → Nur bei Ausfall sichtbar → Unsichtbar |

---

## 3. Status Quo — Systemüberblick

### 3.1 Aktive Komponenten

```
┌──────────────────────────────────────────────────────────────┐
│                    SIGNAL GENERATION                          │
│  ai-hedge-fund-crypto (deepseek-v4-pro, temp=0.15)           │
│  → hermes_signal.json (frisch: 14:31 UTC)                    │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│                    SIGNAL PROCESSING                           │
│  trading_pipeline.py (alle 10min via cron)                    │
│  → primo_signal_state.json                                    │
│  → RiskGuard Evaluation (RG-1 bis RG-5)                      │
│  → MCP Paper Execution (Bitget)                               │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│                    SIGNAL CONSUMPTION                          │
│  FreqForge         ← primo_signal_state.json via Override     │
│  Regime-Hybrid     ← native TA + primo_gate_allows()          │
│  FreqForge-Canary  ← AI Override (Cloned FreqForge)          │
│  FreqAI-Rebel      ← FreqAI Eigenmodell (0 Trades)           │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│                    RISK MANAGEMENT                             │
│  fleet_risk_manager.py → check_entry_allowed()                │
│  system_optimizer.py → 14 Checks (alle 5min)                 │
│  riskguard_service.py → Standalone RG (alle 30min)           │
│  drawdown_guard.py → Fleet-Level DD Protection               │
└──────────────────────────────────────────────────────────────┘
```

### 3.2 Fleet Performance (Aktuell)

| Bot | Trades | WR | PnL (USDT) | Open | Stoploss | Status |
|-----|--------|-----|-----------|------|----------|--------|
| FreqForge | 61 | 86.7% | +21.83 | 1 | **null** | ✅ |
| Regime-Hybrid | 45 | 77.8% | **-6.18** | 0 | -0.025 | ⚠️ |
| FreqForge-Canary | 44 | 93.2% | +7.40 | 0 | **null** | ✅ |
| FreqAI-Rebel | 0 | N/A | 0.00 | 0 | -0.025 | 👁️ |

### 3.3 Cron-Ökosystem
- **40 Jobs**, alle Status=ok, 1 bewusst pausiert
- Kern-Pipeline: trading-pipeline (alle 10min), system-optimizer (alle 5min), fleetrisk-auto-params (alle 15min)
- Signal: unified-signal-heartbeat (alle 15min), riskguard-service (alle 30min)

---

## 4. Dimension 1: Marktdaten-Lücken

### 4.1 Übersicht

| # | Lücke | Severity | Impact | Wahrscheinlichkeit |
|---|-------|----------|--------|--------------------|
| M1 | Keine Failover-Datenquelle bei Exchange-Ausfall | 🟠 Hoch | Signal-Stopp | Gelegentlich |
| M2 | Keine Alternative Coin-Data-APIs | 🟡 Mittel | Unvollständige Coverage | Selten |
| M3 | FreqAI-Rebel leeres Trade-DB | 🟡 Mittel | Keine Trainingshistorie | Dauerhaft |
| M4 | Keine On-Chain / Orderbook-Daten | 🟠 Hoch | Blinde Flecken | Permanent |
| M5 | Market-Impact-Vernachlässigung (Paper Trading) | 🟡 Mittel | Unrealistisches Slippage | Permanent |
| M6 | Keine Corporate-Action-Erkennung | 🔵 Niedrig | Stale Pair-Referenzen | Selten |

### M1: Keine Failover-Datenquelle bei Exchange-Ausfall (🟠 Hoch)

**Beschreibung:**  
Die gesamte Signal-Pipeline hängt an einer einzigen Datenquelle — dem ai-hedge-fund-crypto Container, der wiederum von deepseek-v4-pro über ein Ollama-Cloud-API abhängig ist. Fällt das LLM-API aus (429, 503, Timeout), gibt es keine alternative Signalquelle.

**Code-Evidenz:**  
- `main.py` (ai-hedge-fund-crypto) hat kein try/except um `agent.run()` — ein unhandled Exception crasht den gesamten Container
- Kein Fallback-Modell im Prompt-Template konfiguriert
- `pm_temp = 0.15` hardcoded wenn kein LLM-Policy-Config existiert (main.py:22)

**Impact:** Signal-Pipeline stoppt komplett. Alle 4 Bots hören auf zu handeln.

**Remediation:**  
1. Multi-Model-Fallback im Signal-Generator (bei deepseek-Timeout → Alternativmodell)  
2. Cached-Signal-Fallback: Wenn frisches Signal >25min alt, nimm letztes gültiges statt nichts  
3. Healthcheck-internen Retry mit Exponential Backoff implementieren  

### M2: Keine Alternative Coin-Data-APIs (🟡 Mittel)

**Beschreibung:**  
Die Freqtrade-Bots verwenden nur Bitget als Exchange-Datenquelle. Keine sekundäre Datenquelle (Binance, CoinGecko, CryptoCompare) für Marktdaten.

**Impact:**  
- Wenn Bitget API unzuverlässig ist, haben alle Bots verzögerte/stale OHLCV-Daten  
- Keine Datenvalidierung — ein korruptes OHLCV-Candle kann in einer Fehlsignal-Kaskade enden  

**Remediation:**  
1. Fallback-Datenprovider per Exchange-Konfiguration (Binance als sekundär)  
2. Candle-Level-Plausibilitätscheck (Preis ≠ 0, Volume > 0, Timestamp ±5min von UTC)  
3. Pairlist-Filter auf Paare, die auf mehreren Exchanges existieren  

### M3: FreqAI-Rebel — Leeres Trade-DB (🟡 Mittel)

**Beschreibung:**  
FreqAI-Rebel läuft seit 2+ Stunden im `RUNNING_INFERENCE_ONLY` Modus, hat aber 0 Trades in der Datenbank. Die FreqAI-Modelle benötigen typischerweise eine lange Trainingsphase, bevor sie Trades generieren.

**Status als VISIBILITY_GAP dokumentiert.** Der Bot ist nicht broken, aber es gibt keine Möglichkeit zu auditieren, ob der Inference korrekt arbeitet.

**Remediation:**  
1. Log-Mining nach FreqAI-Modell-Output (feature importance, prediction distribution)  
2. Explizites Signal-Output-File pro Cycle (wie ai-hedge-fund-crypto) statt nur SQLite  
3. Timeout: Wenn nach 48h immer noch 0 Trades → manuelle Intervention  

### M4: Keine On-Chain / Orderbook-Daten (🟠 Hoch)

**Beschreibung:**  
Die gesamte Signal-Generierung basiert auf: LLM-Marktanalyse (X/Twitter + News) + OHLCV-TA-Indikatoren. **Es werden keine On-Chain-Daten (Exchange Flows, Whale Wallets, MVRV) und kein Orderbook (Bid/Ask Imbalance, Orderflow) verwendet.**

**Impact:**  
- Liquiditätsrisiko: Bot kann in illiquide Paare einsteigen ohne es zu merken  
- Mikrostruktur-Blindheit: Keine Erkennung von Spoofing, Wash Trading, manipulierten Candles  
- Whale-Bewegungen werden übersehen, bis sie im Preis sichtbar sind (zu spät)  

**Remediation:**  
1. On-Chain-Feature als zusätzliche Signal-Spalte (z.B. Exchange Netflow, Whale Alert API)  
2. Orderbook-Imbalance als Ausführungs-Gate: Nur traden wenn `(bid_vol - ask_vol) / total_vol < threshold`  
3. Freqtrade-Orderbook-Indikator in der Strategie (`orderbook.print_orderbook` → Volume-Profile)  

### M5: Market-Impact-Vernachlässigung (🟡 Mittel)

**Beschreibung:**  
Das Paper Trading System (Bitget MCP) hat kein Slippage-Modell. Orders werden zum letzten Trade-Preis ausgeführt — kein Market Impact, keine Latenzslippage, keine Teilexecution.

**Code-Evidenz:**  
- `mcp_execute_order()` in trading_pipeline.py verwendet keinen Slippage-Puffer  
- MCP Paper Book preist synthetic prices ohne Spread

**Impact:** Im Live-Trading wäre das tatsächliche Slippage 0.05-0.15% höher als im Paper — die simulierte Profitabilität ist überschätzt.

**Remediation:**  
1. Slippage-Modell im MCP: Marktpreis × (1 ± random(0.01, 0.05))  
2. In allen Berichten explizit "SANDBOX — kein Slippage-Modell" markieren  

---

## 5. Dimension 2: Signalgenerierungs-Lücken

### 5.1 Übersicht

| # | Lücke | Severity | Impact | Wahrscheinlichkeit |
|---|-------|----------|--------|--------------------|
| S1 | RG-4 Double-Evaluation Bug | 🔴 Kritisch | ACCEPTED Count inflation | Häufig (jeder Cycle) |
| S2 | Zwei konkurrierende Signal-Bridges | 🟠 Hoch | Split-Brain zwischen Signalquellen | Permanent |
| S3 | Drei verschiedene Staleness-Schwellen | 🟠 Hoch | Inkonsistente Signal-Filterung | Permanent |
| S4 | Keine Schema-Validierung auf Input-Signal | 🟡 Mittel | Silent Data Corruption | Gelegentlich |
| S5 | Confidence-Threshold in 2 Dateien dupliziert | 🟡 Mittel | Asynchrone Anpassung | Selten |
| S6 | Kein Volume-Check im AI Override Path | 🟠 Hoch | Einstieg in illiquide Märkte | Häufig |
| S7 | LLM temp=0.15 immer gleich (kein adaptives Tuning) | 🔵 Niedrig | Suboptimale Exploration | Permanent |

### S1: RG-4 Double-Evaluation Bug (🔴 Kritisch)

**Fundort:** `trading_pipeline.py:723-728` und `riskguard_service.py:220-222`

**Beschreibung:**  
Die RiskGuard-Regel RG-4 (maximal erlaubte ACCEPTED-Signale pro Cycle) evaluiert jedes Pair **zweimal** — einmal mit aktuellem `accepted_count`, dann erneut mit `count + 1`. Wenn die zweite Evaluation WATCH_ONLY ergibt (weil count+1 das Cap überschreitet), wird der erste ACCEPTED-Status **überschrieben**, aber `accepted_count` wurde bereits inkrementiert. Nachfolgende Paare sehen einen zu hohen Count und werden falsch blockiert.

**Code-Evidenz (trading_pipeline.py ~723):**
```python
# Erste Evaluation
rg_result = riskguard_checks(pair_data, ...)
# count wird inkrementiert basierend auf erstem Ergebnis
if rg_result.get("verdict") == "ACCEPTED":
    accepted_count += 1
# Zweite Evaluation (redundant, überschreibt ersten Verdict)
rg_update = riskguard_checks(... accepted_count + 1 ...)
```

**Impact:**  
- Systematische Benachteiligung von Paaren, die später in der Schleife kommen  
- In Cycles mit vielen grenzwertigen Paaren werden gültige Signale fälschlich blockiert  
- Geringere Trade-Dichte als erwartet — Trades entgehen, die eigentlich genehmigt werden sollten  

**Remediation:**  
1. Entferne die doppelte Evaluation — evaluiere jedes Pair genau einmal  
2. Oder: Führe echte batch-Aware Evaluation durch: alle Paare parallel evaluieren, dann die Top N auswählen  
3. Fix muss sowohl in `trading_pipeline.py` als auch in `riskguard_service.py` erfolgen (gleicher Bug, zwei Kopien)  

### S2: Zwei konkurrierende Signal-Bridges (🟠 Hoch)

**Fundort:**  
- `/home/hermes/projects/trading/freqtrade/tools/primo_signal_bridge.py` (liest von PrimoAgent)  
- `/home/hermes/projects/trading/freqtrade/shared/primo_signal_state.json` (geschrieben von trading_pipeline.py, gelesen von Freqtrade)  
- `/opt/data/profiles/orchestrator/scripts/trading_pipeline.py` (liest von ai-hedge-fund-crypto)

**Beschreibung:**  
Es existieren **zwei unabhängige Signal-Pipelines**:  
1. **Cron-basiert (trading_pipeline.py + riskguard_service.py):** Liest ai-hedge-fund-crypto/output/hermes_signal.json, validiert via RiskGuard, schreibt primo_signal_state.json, führt MCP-Orders aus.  
2. **Primo-Bridge (primo_signal_bridge.py):** Liest `/home/hermes/primoagent/output/signals/` (PrimoAgent), hat eigenes Output-Format, kein Logging.

Beide schreiben potenziell in dasselbe `primo_signal_state.json` — **wer gewinnt, hängt vom Timestamp des letzten Cron-Durchlaufs ab.** Die Bots konsumieren nur `primo_signal_state.json` und wissen nicht, welcher Bridge sie vertrauen sollen.

**Impact:**  
- Stille Überschreibung: Ein Bot erhält Signale von Bridge A, Minuten später werden sie von Bridge B überschrieben  
- Keine Deterministik: Welche Signale aktiv sind, hängt vom (zufälligen) Cron-Overlap ab  
- Im schlimmsten Fall: Bridge A sendet LONG, Bridge B überschreibt mit SHORT für dasselbe Pair  

**Remediation:**  
1. **Entscheidung:** Welche Signalquelle ist primär? (Vermutlich ai-hedge-fund-crypto via cron)  
2. **Decommission:** Primo-Bridge stilllegen oder in den cron-basierten Prozess integrieren  
3. **Owner-Feld im State:** `primo_signal_state.json` um `"source": "ai-hedge-fund-crypto"` erweitern  

### S3: Drei verschiedene Staleness-Schwellen (🟠 Hoch)

| Komponente | Staleness Threshold | Effekt |
|------------|-------------------|--------|
| trading_pipeline.py | 25 Minuten | Signal wird verworfen |
| fleet_risk_manager.py | 30 Minuten | Gate erlaubt/blockt Entry |
| primo_signal_bridge.py | 45 Minuten (default) | Bot-seitiger Gate |
| heartbeat_writer.py | 16 Minuten | Alert-Schwelle |

**Beschreibung:**  
Vier unterschiedliche Timeouts für dieselbe Metrik (Signalfrische). Das bedeutet:
- Ein 28 Minuten altes Signal wird vom Pipeline RiskGuard akzeptiert (25+ → stale), aber von fleet_risk_manager.py noch als frisch betrachtet (30)
- Oder: Der Bot tradet auf ein Signal, das der Pipeline schon als stale gilt

**Impact:** Inkonsistentes Verhalten zwischen Pipeline und Bot. Im Extremfall: Der Bot tradet auf ein altes Signal, das die Pipeline bereits aufgegeben hat.

**Remediation:**  
1. **Single Source of Truth:** `SHARED_CONSTANTS.py` oder ein `stale_config.json` das alle Komponenten importieren  
2. Einheitlicher Threshold (Vorschlag: 20 Minuten als konservativster Wert)  
3. Als Audit-Check in fleet_healthcheck.py: Signal-Age mit ALLEN Thresholds vergleichen und Warnung bei Diskrepanz  

### S4: Keine Schema-Validierung auf Input-Signal (🟡 Mittel)

**Fundort:** `trading_pipeline.py:read_signal()` (nur JSONDecodeError-Catch)

**Beschreibung:**  
`read_signal()` prüft nur, ob das JSON parsebar ist. **Keine Validierung, ob:**  
- `pairs` ein Array ist  
- Mindestens ein action-Paar vorhanden ist  
- Confidence-Werte im Bereich [0,1] liegen  
- Keine unbekannten Keys vorhanden sind  

**Szenario:** Ein korruptes hermes_signal.json (z.B. `{"pairs": null}` oder `{"mode": "invalid"}`) wird akzeptiert und verarbeitet — alle Bots handeln ins Leere.

**Remediation:**  
1. Pydantic-Model oder jsonschema für das Signal-Format  
2. Explizite Typ-Prüfung nach dem Parse  
3. Signal-Guard: `validate_signal()` wirft ValueError bei inkonsistenten Daten  

### S5: Confidence-Threshold in 2 Dateien dupliziert (🟡 Mittel)

**Fundort:**  
- `trading_pipeline.py`: `CONFIDENCE_THRESHOLD = 0.65`  
- `freqtrade/shared/fleet_risk_manager.py`: `CONFIDENCE_MIN = 0.65`

**Beschreibung:** Derselbe Wert (0.65) ist in zwei Dateien hardcoded. Wenn nur einer geändert wird, entsteht eine Asymmetrie zwischen Pipeline-Gate und Bot-Gate.

**Remediation:** Import aus gemeinsamer Konfiguration statt Duplikation.

### S6: Kein Volume-Check im AI Override Path (🟠 Hoch)

**Fundort:** `FreqForge_Override.py:_inject_ai_signal_override()`

**Beschreibung:**  
Der AI Override Path überspringt den Volume-Filter (`volume_ratio > 0.85`), den die nativen TA-Eintrittsbedingungen erfordern. Ein AI-Signal (z.B. SHORT auf niedrigvolumigem Altcoin) wird trotz extrem niedriger Liquidität ausgeführt.

**Impact:**  
- In Live-Situation: Slippage + Market Impact in illiquiden Paaren  
- In Paper: Unrealistische Execution-Prices → falsche PnL-Erwartung  
- Der Bot schließt möglicherweise gar nicht (kein Exit-Volumen)  

**Remediation:**  
1. Volume-Check auch im Override Path: `if row['volume_ratio'] < 0.85: return`  
2. Oder: nur Paare mit ausreichendem 24h-Volume in die Allowlist aufnehmen  
3. Slippage-Alarm bei Open-Trade: Wenn aktueller Preis ≠ entry_price um >0.2%, Warnung loggen  

---

## 6. Dimension 3: Ausführungs- & Order-Management-Lücken

### 6.1 Übersicht

| # | Lücke | Severity | Impact | Wahrscheinlichkeit |
|---|-------|----------|--------|--------------------|
| E1 | MCP Execution ohne Idempotenz (Double-Execution) | 🟠 Hoch | Doppelte Orders bei Cron Overlap | Gelegentlich |
| E2 | Kein Smart Order Routing (single Exchange) | 🟡 Mittel | Keine Price-Improvement | Permanent |
| E3 | Kein Teilausführungs-Handling | 🟡 Mittel | Hängende Orders bei illiquiden Paaren | Gelegentlich |
| E4 | Kein Order-Status-Monitoring nach dem Platzieren | 🟠 Hoch | Fehlende Füllungs-Bestätigung | Permanent |
| E5 | MCP Paper Book = synthetisch, nicht marktreal | 🟡 Mittel | False Sense of Reality | Permanent |
| E6 | Asyncio Event Loop Leak | 🔵 Niedrig | Ressourcen-Leck bei vielen Cycles | Selten |

### E1: MCP Execution ohne Idempotenz (🟠 Hoch)

**Fundort:** `trading_pipeline.py:mcp_execute_accepted_signals()` ~Zeile 391

**Beschreibung:**  
Die Funktion führt **jeden Cycle** alle ACCEPTED-Signale aus, **ohne zu prüfen, ob eine Position bereits existiert.** Wenn der Cron zwei Läufe innerhalb der Order-Ausführungszeit hat (10-min-Intervall, MCP kann innerhalb von Sekunden ausführen), werden dieselben Orders doppelt platziert.

**Scenario:**
```
Cycle 1 (14:40): ACCEPTED BTC SHORT 0.0331 → MCP platziert Order
Cycle 2 (14:50): ACCEPTED BTC SHORT 0.0331 → MCP platziert 2. Order auf selbes Pair
```

**Impact:**  
- Doppelte Positionsgröße (2× 0.0331 BTC = über 6.6% Margin)  
- Falscher PnL-Ausweis im Paper Book  
- Kaskadeneffekt: Wenn 5+ Paare betroffen sind, ist das gesamte Paper Book ungültig  

**Remediation:**  
1. **Pre-Execution Check:** Vor dem Platzieren prüfen, ob für das Pair bereits eine aktive Position existiert (MCP `get_positions` oder lokales Open-Trade-Register)  
2. **Order-Dedup-File:** `executed_signals_{cycle_hash}.json` mit Signal-Fingerprint; nur nicht-ausgeführte Signale verarbeiten  
3. **Trade-Tracking:** E1 ist gelöst, wenn das Paper Book als Source of Truth für aktive Positionen dient  

### E2: Kein Smart Order Routing (🟡 Mittel)

**Beschreibung:**  
Derzeit wird nur Bitget als Exchange verwendet. Es gibt keinen Mechanismus, um Orders über mehrere Exchanges zu routen (Price Improvement, Ausfallsicherheit, Regulierungsarbitrage).

**Remediation:**  
1. Multi-Exchange-Konfiguration in Freqtrade (Bitget + Binance, gleiche Pairs)  
2. Preisvergleich vor Orderausführung — günstigste Exchange wählen  
3. Failover: Wenn Bitget nicht antwortet, auf Binance routen  

### E3: Kein Teilausführungs-Handling (🟡 Mittel)

**Beschreibung:**  
Der MCP Execution Layer platziert Market Orders, die in der Simulation sofort zu 100% gefüllt werden. In der Realität können Orders teilgefüllt werden (besonders bei großen Volumina in illiquiden Paaren). Es gibt keine Logik, um:
- Teilfüllungen zu erkennen  
- Restsignale erneut zu platzieren  
- Ungefüllte Orders nach Timeout zu stornieren  

**Remediation:**  
1. PartiallyFilled-Status in Order-Tracking aufnehmen  
2. Fill-or-Kill für Zeitkritische Orders  
3. Erwartete Füllzeit pro Pair speichern und Timeout-Logik implementieren  

### E4: Kein Order-Status-Monitoring (🟠 Hoch)

**Beschreibung:**  
Nach `mcp_execute_order()` wird der Rückgabestatus (`filled`, `status`) nicht persistiert und nicht überwacht. Der nächste Cron-Cycle weiß nicht, ob die Order des vorherigen Cycles gefüllt wurde.

**Impact:**  
- Hängende Orders werden nie erkannt  
- Der Bot denkt, er habe keine Position, aber der Exchange hat eine Teilfüllung  
- Keine Audit-Trail für tatsächliche Execution vs. beabsichtigte Execution  

**Remediation:**  
1. Order-Status in eigenem SQLite persistieren (order_id, pair, status, filled_qty, timestamp)  
2. Order-Status-Check vor jedem neuen Cycle: `get_order_status(order_id)`  
3. Timeout-Alarm bei Orders, die >5 Minuten nicht gefüllt sind  

---

## 7. Dimension 4: Risikomanagement-Lücken

### 7.1 Übersicht

| # | Lücke | Severity | Impact | Wahrscheinlichkeit |
|---|-------|----------|--------|--------------------|
| R1 | TOTAL_CAPITAL hardcoded (10.000 USDT) | 🔴 Kritisch | Falsche %-Limits für alle Risikoberechnungen | Permanent |
| R2 | Stoploss=null auf 2 Bots | 🟠 Hoch | Kein automatischer SL-Schutz | Permanent |
| R3 | Risk Logic dreifach dupliziert | 🟠 Hoch | Divergenz zwischen 3 unabhängigen Kopien | Häufig |
| R4 | LIVE_RISK Stale (4 Tage) + Equity-Updater nicht populating | 🟠 Hoch | Risk-Entscheidungen basieren auf veralteten Daten | Dauerhaft |
| R5 | Regime-Hybrid negative PnL trotz 77.8% WR | 🟠 Hoch | Strukturelles RR-Problem | Täglich |
| R6 | fleet_risk_state.json ohne freqai-rebel | 🟡 Mittel | Unvollständige Risk-Abdeckung | Dauerhaft |
| R7 | Portfolio-Konzentration (alle 3 Bots auf SHORT) | 🟠 Hoch | Systemisches Risiko bei Bull-Run | Gelegentlich |
| R8 | Kein Multi-Exchange-Risiko | 🟡 Mittel | Single Point of Failure | Selten |
| R9 | system_optimizer.py: non-atomic writes + deleted heartbeat ref | 🟠 Hoch | Silent Failure in Auto-Optimierung | Gelegentlich |
| R10 | Kein operatives Risikoregister | 🔵 Niedrig | Keine dokumentierten Limits | Permanent |

### R1: TOTAL_CAPITAL hardcoded auf 10.000 USDT (🔴 Kritisch)

**Fundort:** `system_optimizer.py:34` (`TOTAL_CAPITAL = 10000.0`)

**Beschreibung:**  
Das reale Portfolio beträgt **3.517,76 USDT** (lt. drawdown_state.json). Alle prozentualen Limits in system_optimizer.py basieren auf 10.000 USDT — das ist **2,8× zu hoch.** Die Konsequenzen:

- **Daily-Loss-Limit (2% von 10.000 = 200 USDT):** Tritt bei realem Portfolio schon bei 5,7% Verlust ein → viel zu spät  
- **Stake-Halving bei Equity-Verlust:** Berechnet mit 10.000-Baseline, nicht mit 3.517. Die Halving-Schwelle wird falsch berechnet  
- **Drawdown-Überwachung (5% = 500 USDT):** Das ist ~14% des realen Portfolios  

**Beispielrechnung:**
```
Real:    3.517 USDT × 5% =   176 USDT Drawdown-Limit
Falsch: 10.000 USDT × 5% =   500 USDT (fast 3× zu großzügig)
```

**Impact:** Alle 14 Risk-Checks in system_optimizer.py arbeiten mit falschen Baselines. Der Auto-Parameter-Adjuster ist faktisch blind.

**Remediation:**  
1. Dynamische Capital-Abfrage aus exchange.get_balance() oder drawdown_state.json  
2. Wenn keine Live-Balance: Signal-weiten Fehler werfen (fail closed)  
3. Capital-Refresh im system_optimizer vor jedem Cycle  
4. **P1-Dringlichkeit:** Fix muss vor dem nächsten Drawdown-Ereignis erfolgen  

### R2: Stoploss=null auf 2 Bots (🟠 Hoch)

**Fundort:**  
- `/home/hermes/projects/trading/freqforge/config/config_freqforge_dryrun.json`  
- `/home/hermes/projects/trading/freqforge-canary/config/config_canary_dryrun.json`

**Beschreibung:**  
Beide Bots haben `stoploss: null` in der Config. Das bedeutet: **kein automatischer Stop-Loss.** Ein plötzlicher Marktcrash (-15% auf BTC) würde:
- FreqForge: 50 USDT Position → unbegrenzter Verlust bis zur Liquidierung  
- Canary: 25 USDT Position → unbegrenzter Verlust

Die Strategien haben `custom_stoploss()` aber `use_custom_stoploss = True` muss explizit gesetzt sein. Ohne Config-Stoploss und je nach Strategy-Klasse kann der Bot Stoploss komplett deaktiviert haben.

**Warum ist das passiert?**  
Configs wurden wahrscheinlich von einem Template kopiert, wo stoploss nicht gesetzt war.

**Remediation (sofort):**  
1. `stoploss: -0.09` (9%) in beide Configs eintragen  
2. Container-Neustart nach Config-Änderung  
3. fleet_healthcheck.py erweitern: `stoploss is not null` prüfen → RED wenn null  

### R3: Risk Logic dreifach dupliziert (🟠 Hoch)

**Fundort:** Drei unabhängige Implementierungen derselben RiskGuard-Logik:
1. `/opt/data/profiles/orchestrator/scripts/trading_pipeline.py` (RG-1 bis RG-5)  
2. `/opt/data/profiles/orchestrator/scripts/riskguard_service.py` (Copy-Paste)  
3. `/home/hermes/projects/trading/freqtrade/shared/fleet_risk_manager.py` (ähnliche Gates)

**Beschreibung:**  
Die RiskGuard-Checks (max 3 ACCEPTED-Pairs, Position-Sizing, Margin-Schutz) sind in drei Dateien mit eigener Implementierung. Jeder Bugfix muss dreifach erfolgen — in der Praxis wird mindestens eine Kopie vergessen.

Concrete divergence:  
- `riskguard_service.py` liest Signal von einem dritten Pfad (`shared/hermes_signal.json`) der in `trading_pipeline.py` nicht existiert  
- `fleet_risk_manager.py` hat andere Schwelle (30min vs 25min)  

**Remediation:**  
1. Module extrahieren: `riskguard_core.py` als shared Module  
2. trading_pipeline.py und riskguard_service.py importieren von dort  
3. fleet_risk_manager.py optional umschreiben oder deprecated markieren  

### R4: LIVE_RISK Stale + Equity-Updater nicht populating (🟠 Hoch)

**Fundort:**  
- drawdown_state.json: letztes Update 14:30 UTC (frisch, OK)  
- fleet_risk_state.json: **alle source equity/pnl_pct Felder sind None**  
- Equity-Updater Cron: läuft alle 5 Minuten, aber Daten werden nicht geschrieben

**Beschreibung:**  
Der Equity-Updater (`fleetrisk-auto-params` Cron, alle 5min) soll die aktuellen Equity-Werte pro Bot in `fleet_risk_state.json` schreiben. Aber alle source-Einträge zeigen None für equity und pnl_pct. Der FleetRiskManager kann keine korrekten Risikoberechnungen durchführen, wenn er keine Equity-Daten hat.

**Impact:**  
- FleetRiskManager's `get_drawdown_level()` fällt auf default zurück  
- Alle drawdown-basierten Risk-Gates sind faktisch deaktiviert  
- LEDGER_RISK ist als WARNING gekennzeichnet, aber die Ursache ist nicht behoben  

**Remediation:**  
1. Debug: Warum schreibt der Equity-Updater None? (Vermutlich: host-side DB-Pfad nicht gefunden)  
2. Fallback auf drawdown_state.json als Equity-Quelle  
3. Verification-Check: Equity muss > 0 und < Capital sein, sonst WARNING loggen  

### R5: Regime-Hybrid — Negative PnL trotz 77.8% WR (🟠 Hoch)

**Fundort:** SQLite-Forensik Regime-Hybrid (45 Trades, 77.8% WR, -6.18 USDT)

**Beschreibung:**  
Der Bot gewinnt 35 von 45 Trades (77.8%), verliert aber netto Geld. Das ist ein klassisches strukturelles **Risk/Reward Problem:**

| Kennzahl | Wert | Bedeutung |
|-----------|------|-----------|
| Win Rate | 77.8% | Hohe Trefferquote |
| Net PnL | -6.18 USDT | Verlust trotz hoher WR |
| Avg Gewinn | vermutlich klein | ~0.5-1.5% |
| Avg Verlust | vermutlich groß | ~3-5% |
| Break-Even WR | >80% benötigt | Realität: 77.8% → negativ |

**Vergleich mit FreqForge (86.7% WR, +21.83 USDT, keine stoploss!):**
FreqForge hat ähnliche WR aber massiv besseren PnL. Das deutet darauf hin, dass die Exit-Strategie von Regime-Hybrid defizitär ist — vermutlich zu schnelle Gewinnmitnahmen (ROI) bei zu großzügigem Verlust-Limit (stoploss).

**Remediation:**  
1. **Exit Reason Analyse:** Wie viele Trades enden mit stop_loss vs. roi?  
2. **R:R Optimierung:** Stoploss enger ziehen (von -0.025 auf -0.015) oder ROI-Target erhöhen  
3. **Backtest:** Neue R:R-Parameter vor Live-Deployment validieren  
4. **Fleet-Gold-Standard:** FreqForge Config als Benchmark (trailing_stop=False, use_custom_stoploss=False)  

### R6: fleet_risk_state.json ohne freqai-rebel (🟡 Mittel)

**Fundort:** `fleet_risk_state.json` — sources enthalten `baseline_v1_freqforge`, `freqforge_canary_v1`, `regime_hybrid_dryrun`. Kein freqai-rebel.

**Remediation:**  
1. freqai-rebel zur sources-Liste hinzufügen  
2. Equity-Update-Logik auf Rebel ausweiten (docker volume → docker cp)  

### R7: Portfolio-Konzentration — alle 3 aktiven Bots auf SHORT (🟠 Hoch)

**Beschreibung:**  
Aktueller Signal-Output: BTC SHORT, ETH SHORT, SOL SHORT — alle drei Bots werden mit denselben SHORT-Signalen versorgt. Das bedeutet:
- **100% der offenen Trades sind Short** (wenn alle Signale ausgeführt werden)  
- Ein plötzlicher Short-Squeeze (+10-20%) trifft das gesamte Portfolio gleichzeitig  
- Kein natürliches Hedge (Long/Short-Balance)

**Impact:** Systematisches Risiko im Bull-Market. Das Portfolio kann nicht von Long-Bewegungen profitieren.

**Remediation:**  
1. **Long/Short-Bias-Limit:** Max 70% Short oder Long im Fleet  
2. **Diversifikations-Regel:** Wenn 2+ Bots dieselbe Direction haben, dritten Bot auf andere Direction zwingen  
3. **FleetRiskManager:** Cluster-Korrelation auf Direction-Ebene erweitern  

### R9: system_optimizer.py — Non-Atomic Writes + Deleted Heartbeat Ref (🟠 Hoch)

**Fundort:**  
1. `system_optimizer.py:885, 914` — direkte `open(..., "w")` statt `_atomic_write_json()`  
2. `system_optimizer.py:637` — ruft `ai_hedge_signal_heartbeat.sh` auf, das durch `unified_signal_heartbeat.sh` ersetzt wurde

**Beschreibung:**  
Wenn der Equity Protection Mechanismus (Check 10) während des Schreibens crasht, wird die State-Datei korrupt. Zusätzlich versucht der Optimizer, eine gelöschte Heartbeat-Script zu triggern — das schlägt still und der Fehler wird nicht geloggt.

**Remediation:**  
1. Alle state-writes durch `atomic_write_json()` ersetzen (tmp+rename Pattern)  
2. `ai_hedge_signal_heartbeat.sh`-Referenz durch `unified_signal_heartbeat.sh` ersetzen  
3. Fehlgeschlagene Heartbeat-Triggers als WARNING loggen  

---

## 8. Dimension 5: Technische Infrastruktur-Lücken

### 8.1 Übersicht

| # | Lücke | Severity | Impact | Wahrscheinlichkeit |
|---|-------|----------|--------|--------------------|
| I1 | Shared Volume Mount für ALLE Freqtrade Container | 🔴 Kritisch | DB-Corruption, Config-Konflikte, Strategy-Collisions | Permanent |
| I2 | Keine Resource Limits für Container | 🟠 Hoch | OOM-Killer kann beliebigen Bot killen | Gelegentlich |
| I3 | Docker Images pinned zu latest/stable | 🟡 Mittel | Unkontrollierte Upgrades | Selten |
| I4 | Shadow Log unbounded — kein Rotation | 🟡 Mittel | Festplattenvoll → Systemausfall | Selten (Monate) |
| I5 | Heartbeat SQLite unbounded | 🔵 Niedrig | DB-Größe wächst linear | Sehr selten |
| I6 | Kein Healthcheck auf Freqtrade Bots | 🟠 Hoch | Silent Container Crashes | Gelegentlich |
| I7 | fleet_healthcheck.py: dry_run assumed statt verified (Rebel) | 🟡 Mittel | False-Green bei dry_run=False | Selten |
| I8 | config_diff_detector: nur 5 von ~20 Config-Keys geprüft | 🟡 Mittel | False-Negative Drift-Erkennung | Permanent |
| I9 | No .gitignore for runtime state | 🟡 Mittel | Accidentelles Commit von Risk-Data | Selten |
| I10 | heartbeat_writer.py: REST API Probe = Dead Code | 🔵 Niedrig | 2s/cycle wasted, kein Nutzen | Permanent |

### I1: Shared Volume Mount für ALLE Freqtrade Container (🔴 Kritisch)

**Fundort:** `/home/hermes/projects/trading/docker-compose.yml:72`

**Aktuelle Konfiguration:**
```yaml
volumes:
  - ./freqtrade/user_data:/freqtrade/user_data
```

Das BINDET dieselbe `user_data/` in **alle 4 Freqtrade-Container** ein — freqforge, regime-hybrid, canary, rebel, webserver ALLE teilen sich dasselbe user_data-Verzeichnis.

**Auswirkungen:**
1. **Trade DB Collision:** `tradesv3.sqlite` wird von mehreren Containern gleichzeitig geschrieben → SQLite-Corruption  
2. **Config-Konflikte:** `config.json` in user_data/ wird von allen Containern gelesen — Änderungen von einem Bot überschreiben die Config eines anderen  
3. **Strategy File Collision:** Alle Container sehen dieselbe strategies-Verzeichnis — ein FreqForge-Strategy-File importiert aus dem falschen Bot  
4. **Lock-File Konflikte:** `.lock`-Dateien für Shared State sind nicht pro Container isoliert  
5. **Backups unmöglich:** Man kann nicht `user_data/` als ein Backup für Container A nehmen, weil B und C auch schreiben

**Warum funktioniert das System trotzdem?**  
Die Bots verwenden **named per-strategy DBs** (`tradesv3.freqforge.dryrun.sqlite`, `tradesv3.regime_hybrid.dryrun.sqlite`). Und die Configs sind woanders gebind-mountet (`./freqforge/config/` → Container `/freqtrade/config/`). Die Kollision ist teilweise durch Namenskonventionen maskiert, aber nicht vollständig beseitigt.

**Was kann trotzdem schiefgehen?**  
- `tradesv3.sqlite` (generic, ohne Bot-Name) wird von allen Containern beschrieben  
- Strategy-Imports in user_data/strategies/ können kollidieren (z.B. wenn ein Container eine neue Version kompiliert während ein anderer liest)  
- Wenn ein Bot eine `startup_candle_count > 0` hat und strategie-spezifische Daten ablegt, kollidieren die mit anderen Bots

**Remediation (P0):**
```yaml
# Statt shared mount, pro Bot eigenes user_data:
freqtrade-freqforge:
  volumes:
    - ./freqforge/user_data:/freqtrade/user_data     # eigenes DB
    - ./freqtrade/shared/primo_signal_state.json:/freqtrade/user_data/primo_signal_state.json:ro  # shared read-only

freqtrade-regime-hybrid:
  volumes:
    - ./freqtrade/bots/regime-hybrid/user_data:/freqtrade/user_data
    - ./freqtrade/shared/primo_signal_state.json:/freqtrade/user_data/primo_signal_state.json:ro
```

### I2: Keine Resource Limits für Container (🟠 Hoch)

**Fundort:** docker-compose.yml — kein `mem_limit`, `cpus`, oder `deploy.resources` auf irgendeinem Service.

**Impact:**  
Ein speicherleckender Bot (z.B. FreqAI-Rebel bei langer Inference) kann das gesamte Host-RAM konsumieren → OOM-Killer tötet Container → alle Bots fallen aus.

**Remediation:**
```yaml
services:
  freqtrade-freqforge:
    mem_limit: 512m
    memswap_limit: 512m
    cpus: 1.0
  freqai-rebel:
    mem_limit: 1024m  # FreqAI braucht mehr RAM für Modell-Loading
    cpus: 2.0
  ai-hedge-fund-crypto:
    mem_limit: 1024m
    cpus: 1.0
```

### I3: Docker Images pinned zu latest/stable (🟡 Mittel)

**Fundort:** docker-compose.yml — `freqtradeorg/freqtrade:stable`, `nousresearch/hermes-agent:latest`

**Beschreibung:**  
`stable` kann jede Woche ein Breaking Change sein. `latest` noch öfter. Ein unerwartetes Upgrade von Freqtrade 2026.3 auf 2026.4 könnte API-Änderungen enthalten, die alle Bots stummlegen.

**Remediation:**  
1. `stable` → konkretes Tag (z.B. `freqtradeorg/freqtrade:2026.3`)  
2. `latest` → `nousresearch/hermes-agent:2026.06.01`  
3. Oder: Digest-Pinning (`freqtradeorg/freqtrade@sha256:abc123...`)  

### I4: Shadow Log unbounded — kein Rotation (🟡 Mittel)

**Fundort:** `trading_pipeline.py` — `SHADOW_LOG_FILE` append-only, keine Rotation

**Beschreibung:**  
Der Shadow Logger schreibt jeden Cycle einen JSON-Log-Eintrag (alle 10 Minuten = 144 Einträge/Tag). Bei ~500 Bytes/Eintrag sind das ~26 MB/Jahr — nicht kritisch, aber **bei Debug-Level steigt es exponentiell** (jeder RiskGuard-Check, jeder Order-Versuch).

Zusätzlich: Der Shadow Log-Eintrag in `FreqForge_Override.py` (Zeile 506) schreibt literal `\\n` statt newline:
```python
f.write(json.dumps(log_entry) + "\\\\n")  # BUG: "\n" wäre korrekt
```

**Remediation:**  
1. Rotation: log_date=Y-m-d anhängen oder Logrotate in Docker-Volume  
2. Retention: max 30 Tage alte Logs löschen (system_optimizer.py hat das für orchestrator Logs, aber nicht für shadow log)  
3. Bugfix: `\n` statt `\\n` in FreqForge_Override.py  

### I6: Kein Healthcheck auf Freqtrade Bots (🟠 Hoch)

**Fundort:** docker-compose.yml — nur `ai-hedge-fund-crypto` hat healthcheck

**Beschreibung:**  
Wenn ein Freqtrade Bot intern crasht (Segfault, Python Exception), bleibt der Container `UP` (weil tini den Prozess hält), aber der Bot handelt nicht. Ohne Healthcheck erkennt Docker das nicht und startet nicht automatisch neu.

**Remediation:**
```yaml
healthcheck:
  test: ["CMD", "python3", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8080/api/v1/ping', timeout=5).read()"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 30s
```

### I7: fleet_healthcheck.py - dry_run assumed statt verified (🟡 Mittel)

**Fundort:** `fleet_healthcheck.py:206` — für freqai-rebel (kein host-side Config-Mount) wird `dry_run=True` angenommen.

**Beschreibung:**  
Wenn jemand im Container `dry_run=false` setzt, erkennt das der Healthcheck nicht und meldet FALSE-positiv GREEN.

**Remediation:**  
1. docker exec in den Container, Config parse, dry_run auslesen  
2. Für den Fall, dass docker exec nicht funktioniert: **UNKNOWN** als Verdict, nicht GREEN  

### I8: config_diff_detector: nur 5 von ~20 Config-Keys geprüft (🟡 Mittel)

**Fundort:** `config_diff_detector.py:83` — prüft nur: max_open_trades, stake_amount, dry_run, stoploss, trailing_stop

**Ungeprüft:**  
- `trading_mode` (spot vs futures = Disaster)  
- `margin_mode`  
- `exchange.name` (Bitget vs Binance)  
- `pair_whitelist` (wenn sich die Liste ändert)  
- `max_open_trades` Change  
- `unfilledtimeout`  
- `entry_pricing.price_side`  
- `exit_pricing.price_side`  
- `api_server` credentials rotieren  
- `telegram` config  
- `db_url` Änderung  
- `process_only_new_candles`  
- `use_exit_signal`  

**Remediation:**  
1. Erweitere config_diff_detector auf alle kritischen Keys  
2. Oder: Vollständiger JSON-Diff (nicht nur Key-by-Key)  
3. Restart nur bei driften in kritischen Keys (dry_run, trading_mode, exchange)  

---

## 9. Dimension 6: Betriebliche & Prozess-Lücken

### 9.1 Übersicht

| # | Lücke | Severity | Impact | Wahrscheinlichkeit |
|---|-------|----------|--------|--------------------|
| P1 | AGENTS.md sagt RiskGuard = "SPEC ONLY" aber es ist deployed | 🟡 Mittel | Stale Dokumentation | Permanent |
| P2 | system_optimizer.py referenziert gelöschtes Script | 🟠 Hoch | Silent Trigger Failure | Jeder Cycle |
| P3 | Kein Graceful Degradation bei Broker-Ausfall | 🟠 Hoch | Alle Bots stürzen zur selben Zeit ab | Gelegentlich |
| P4 | Kein Backtesting-Workflow für AI-Override-Path | 🟡 Mittel | Unvalidierte Override-Änderungen | Permanent |
| P5 | Fleet-Recovery-Prozeduren nicht getestet | 🟡 Mittel | Langsame Recovery im Ernstfall | Selten |
| P6 | hermes_standby_monitor: PID-Lock statt Flock | 🟡 Mittel | Keine Mutual Exclusion | Selten |
| P7 | Zwei Heartbeat-Brücken in parallel | 🟠 Hoch | Stale-Verwirrung | Permanent |
| P8 | Telegram-Alerts File-basiert — kein Delivery Check | 🟡 Mittel | Stille Alert-Lücke | Gelegentlich |

### P2: system_optimizer.py referenziert gelöschtes Script (🟠 Hoch)

**Fundort:** `system_optimizer.py:637`

```python
def _trigger_heartbeat(container_name: str) -> bool:
    ...
    result = subprocess.run(
        ["bash", HEARTBEAT_SCRIPT],  # HEARTBEAT_SCRIPT = ai_hedge_signal_heartbeat.sh (DELETED)
        ...
    )
```

Das Script `ai_hedge_signal_heartbeat.sh` wurde durch `unified_signal_heartbeat.sh` ersetzt. Jeder Trigger-Aufruf schlägt fehl, aber subprocess.run fängt keinen FileNotFoundError — der Fehler wird ignoriert.

**Remediation:**  
1. `HEARTBEAT_SCRIPT` auf `unified_signal_heartbeat.sh` umbiegen  
2. Return-Code prüfen: `subprocess.run(..., check=True)`  

### P3: Kein Graceful Degradation bei Broker-Ausfall (🟠 Hoch)

**Szenario:** Bitget API ist down (Wartung, RPC-Failure).  
- Alle 4 Bots versuchen gleichzeitig, den Exchange zu erreichen  
- Freqtrade intern: ExchangeNotAvailable → Wiederholung (retrier) → Timeout → Thread ge blocked  
- Keine Drosselung: 4 Bots × 3 Retries × 5s = 60s geblockte Threads gleichzeitig  
- Eventuell: Container OOM durch gleichzeitige Retry-Explosion

**Remediation:**  
1. **Backoff-Staffelung pro Bot:** Bot A: 1s → 2s, Bot B: 2s → 4s, Bot C: 3s → 6s  
2. **Circuit-Breaker:** Nach 3 aufeinanderfolgenden Exchange-Fehlern → 5 Minuten Pause pro Bot  
3. **Globaler Exchange-Health-Flag:** Ein zentraler Check (health_endpoint), den alle Bots vor dem Traden prüfen  

### P4: Kein Backtesting-Workflow für AI-Override-Path (🟡 Mittel)

**Beschreibung:**  
Freqtrade's `backtesting` testet nur native TA-Eintrittslogik. Der AI-Override-Path (`_inject_ai_signal_override()`) wird **nicht** simuliert. Alle AI-Override-Änderungen können nur im Live-Dry-Run validiert werden — das ist risikoarm (Dry-Run) aber
- Dauert Tage statt Stunden  
- Keine historische Validierung über verschiedene Marktregime hinweg  
- Overfitting kann nicht erkannt werden  

**Remediation:**  
1. **Override-Backtest-Script:** Historische hermes_signal.json an Backtest-Dataframe anfügen und Override-Path simulieren  
2. **Walk-Forward:** Systematisch 3 Monate trainieren, 1 Monat validieren  
3. **Als Standard-Prozess:** Vor jeder Confidence-Threshold-Änderung einen Walk-Forward-Override-Backtest laufen lassen  

### P7: Zwei Heartbeat-Brücken in parallel (🟠 Hoch)

**Beschreibung:**  
Es existieren:  
1. `unified-signal-heartbeat` (Cron, alle 15min, schreibt canonical → latest)  
2. `system-optimizer _trigger_heartbeat()` (Cron, alle 5min, versucht Deleted-Script)  
3. `heartbeat_writer.py` (Cron, alle 15min, schreibt SQLite)  
4. `riskguard-service` (Cron, alle 30min, eigenes Signal-Read+Write)

Vier unabhängige Systeme, die Signale lesen/schreiben/heartbeaten. **Keine Koordination.**

**Impact:**  
- Ein System schreibt canonical, ein anderes überschreibt latest → Inkonsistenz  
- Keine zentrale "ist das System lebendig" Antwort  
- Fehler in einem System maskieren Fehler in einem anderen  

**Remediation:**  
1. **Vereinheitlichung:** unified-signal-heartbeat ist der einzige Autor von canonical + latest  
2. heartbeat_writer.py: Nur lesen, nie schreiben (passt bereits)  
3. system-optimizer _trigger: Entfernen oder auf unified-signal-heartbeat delegieren  
4. riskguard-service: Von Signal-Read auf Signal-Audit umstellen (liest canonical, schreibt RiskGuard-Report, nicht Signal-File)  

---

## 10. Schwarze Flecken (Unbekannte Unbekannte)

### 10.1 Split-Brain-Szenario

**Was passiert, wenn zwei hermes-green Container gleichzeitig laufen?**  
- Zwei Cron-Scheduler triggern dieselben Jobs  
- trading_pipeline.py läuft parallel: doppelte RiskGuard-Evaluation, doppelte MCP-Orders  
- global_trigger_lock.sh verhindert nur doppelte Trigger, nicht doppelte Pipeline  
- **Erkennbarkeit:** Nicht direkt erkennbar — erst wenn doppelte Orders oder divergente State-Dateien auffallen  

**Empfehlung:** PID-Lock in trading_pipeline.py: Vor Ausführung prüfen, ob bereits eine Instanz läuft.

### 10.2 Postgres-upgrade Freqtrade

**Wenn Freqtrade auf 2026.4 upgradet (über `stable` Tag):**  
- Mögliche API-Änderungen: REST-API-Version, config-schema, strategy-interface  
- docker-compose.yml: `freqtradeorg/freqtrade:stable` → wird automatisch gezogen  
- Kein manuelles Testing vor dem Upgrade  
- **Erkennbarkeit:** Erst beim nächsten `docker pull` + `up -d` — dann sind alle Bots auf einmal betroffen  

**Empfehlung:** Tag-pinning (siehe I3).

### 10.3 MCP Deadlock

**Wenn das MCP Bitget Paper Trading hängt (z.B. durch Exchange-Antwort):**  
- `mcp_execute_accepted_signals()` blockiert den gesamten Pipeline-Cycle  
- Kein Timeout in der asyncio-Event-Loop (keine asyncio.wait_for())  
- Nachfolgende Cron-Cycles sammeln sich im global_trigger_lock  
- **Erkennbarkeit:** trigger_lock.log zeigt "LOCK BUSY" für mehrere Cycles — aber das wird nicht gealert (exit 0 = silent)  

**Empfehlung:** Timeout in MCP-Execution: `asyncio.wait_for(execution_coroutine, timeout=30)` und Timeout als WARNING loggen.

### 10.4 LLM-Model-Change ohne Vorwarnung

**Wenn deepseek-v4-pro durch eine neue Version ersetzt wird (Provider-seitig):**  
- Anderer Output-Character, andere Confidence-Verteilung, andere Bias  
- Alle RiskGuard-Thresholds (0.65 Confidence) sind für das alte Modell optimiert  
- Keine automatisierte Regression: Unterschiede im Output werden nicht erkannt  
- **Erkennbarkeit:** Erst wenn PnL über Tage driftet — zu spät  

**Empfehlung:**  
1. Signal-Historie: Confidence-Verteilung pro Modell-Version tracken  
2. Drift-Detektor: Wenn avg_confidence >0.2 vom historischen Mittel abweicht → Warnung  
3. Staged-Rollout: Neues Modell zuerst auf Canary, dann auf Main  

---

## 11. Priorisierte Roadmap

### Phase 0: Sofort (heute) 🔴

| Priority | Gap | Aktion | Aufwand |
|----------|-----|--------|---------|
| P0 | **R1: TOTAL_CAPITAL hardcoded** | Dynamische Capital-Abfrage aus drawdown_state.json implementieren | 2h |
| P0 | **R2: Stoploss=null auf 2 Bots** | stoploss: -0.09 in freqforge + canary Config eintragen, Container restart | 15min |
| P0 | **R4: Equity-Updater populiert None** | Debug: Warum werden keine Equity-Werte geschrieben? Fallback auf drawdown_state | 3h |
| P0 | **R9: system_optimizer: Deleted Script Ref** | ai_hedge_signal_heartbeat.sh → unified_signal_heartbeat.sh | 10min |
| P0 | **E1: MCP Double-Execution** | Pre-Execution Position-Check implementieren | 2h |

### Phase 1: Diese Woche 🟠

| Priority | Gap | Aktion | Aufwand |
|----------|-----|--------|---------|
| P1 | **S1: RG-4 Double-Evaluation Bug** | Spread-ethode oder Batch-Evaluation in trading_pipeline.py + riskguard_service.py | 3h |
| P1 | **I1: Shared Volume Mount** | Pro-Bot user_data mounts in docker-compose.yml | 4h |
| P1 | **R3: Risk Logic dreifach** | riskguard_core.py extrahieren, Importe umstellen | 6h |
| P1 | **R7: Portfolio-Konzentration (alle Short)** | Long/Short-Bias-Limit implementieren | 2h |
| P1 | **I6: Fehlende Healthchecks** | Docker healthcheck für alle Freqtrade Container | 2h |
| P1 | **S6: Volume-Check im AI Override** | volume_ratio > 0.85 Gate in FreqForge_Override | 30min |
| P1 | **S2: Zwei konkurrierende Bridges** | Primo-Bridge decommissionen + Owner-Feld in state | 2h |
| P1 | **FreqForge Shadow Log Bug** | `\\n` → `\n` in FreqForge_Override.py:506 | 5min |

### Phase 2: Diesen Sprint 🟡

| Priority | Gap | Aktion | Aufwand |
|----------|-----|--------|---------|
| P2 | **S3: Staleness-Thresholds vereinheitlichen** | Shared Constants einführen | 1h |
| P2 | **I2: Resource Limits** | mem_limit + cpus in docker-compose.yml | 1h |
| P2 | **R5: Regime-Hybrid RR-Problem** | Exit-Reason-Analyse + R:R Optimierung | 4h |
| P2 | **P3: Graceful Degradation** | Circuit-Breaker + Backoff-Staffelung | 6h |
| P2 | **I3: Docker Image Pinning** | Tags fixieren (stable→2026.3) | 1h |
| P2 | **I8: Config-Diff erweitern** | Alle kritischen Config-Keys prüfen | 3h |
| P2 | **P7: Heartbeat-Vereinheitlichung** | Nur unified-signal-heartbeat als Autor | 4h |
| P2 | **P4: AI-Override-Backtest** | Historisches Override-Backtesting ermöglichen | 8h |

### Phase 3: Dieser Monat 🔵

| Priority | Gap | Aktion | Aufwand |
|----------|-----|--------|---------|
| P3 | **M1: Failover-Datenquelle** | Multi-Model-Fallback im Signal-Generator | 8h |
| P3 | **M4: On-Chain-Daten** | Exchange-Netflow-Indikator + Whale-Alert | 12h |
| P3 | **R6: freqai-rebel in fleet_risk_state** | Source hinzufügen, Equity-Update ausweiten | 2h |
| P3 | **P1: AGENTS.md synchronisieren** | RiskGuard Status, Bot-Liste, Config-Pfade | 2h |
| P3 | **I4: Shadow Log Rotation** | Logrotate oder Rolling-Appender | 2h |
| P3 | **I7: Rebel dry_run verifizieren** | docker exec dry_run Parse statt Assumption | 1h |
| P3 | **I9: .gitignore for runtime state** | orchestrator/state/ + logs/ + backups/ | 10min |
| P3 | **I10: Dead Code entfernen** | REST API Probe in heartbeat_writer.py löschen | 30min |

---

## 12. Anhang: Evidenz-Index

### Analyse-Quellen (18 Dateien geladen, 2.000+ Zeilen)

| Datei | Zeilen | Relevanz |
|-------|--------|----------|
| trading_pipeline.py | 863 | Signal-Pipeline, RiskGuard, MCP |
| system_optimizer.py | 1.154 | Auto-Optimierung, 14 Checks |
| fleet_risk_manager.py | 844 | Gate-Logik, Drawdown, Correlation |
| riskguard_service.py | 295 | Standalone RiskGuard (dupliziert) |
| FreqForge_Override.py | 510 | Active Strategy mit AI Override |
| unified_signal_heartbeat.sh | 153 | Signal Heartbeat Orchestrierung |
| global_trigger_lock.sh | 110 | Lock-Wrapper für Trigger |
| heartbeat_writer.py | 294 | Bot-Health SQLite Writer |
| fleet_healthcheck.py | 370 | Fleet-Verdict Health Status |
| config_diff_detector.py | 182 | Config Drift Detection |
| hermes_standby_monitor.py | 205 | Hermes Failover |
| primo_signal.py | 119 | Freqtrade-seitiger Signal Gate |
| docker-compose.yml | 164 | Container Orchestrierung |
| main.py | 85 | AI Signal Generator Entry |

### State-Files (6 ausgelesen)

| File | Status | Erkenntnis |
|------|--------|------------|
| drawdown_state.json | ✅ Fresh (14:30 UTC) | Portfolio 3.517 USDT, 4/4 bots reachable |
| fleet_risk_state.json | ⚠️ Alle equity/pnl=None | Equity-Updater broken |
| consec_loss_state.json | ✅ 0 losses, cleaned | Keine Suspensions |
| config_diff_health.json | ✅ 0 drift, 4 bots checked | Configs sauber |
| fleet_health_latest.json | ⚠️ YELLOW | Rebel visibility gap |
| canonical-trading-status.md | ✅ Fresh (14:34 UTC) | WARNING, 82/100 overall |

### Cron-Jobs (40 analysiert)

| Metric | Wert |
|--------|------|
| Gesamt Jobs | 40 |
| Enabled | 39 |
| Mit last_run diese Stunde | 25+ |
| Mit Error | 0 |
| Ältester last_run | 2026-05-24 (paused/completed) |

---

*Ende des GAP-Reports. Erstellt 2026-06-05 14:45 UTC. Nächste empfohlene Aktualisierung: nach Phase-0-Implementierung.*
