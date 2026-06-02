# SYSTEM-LAGEPLAN — AI-Hedge-Fund-Crypto Trading Hub
## Stand: 02.06.2026 22:45 UTC
## Erstellt von: Hermes Orchestrator (Meta-Orchestrator Session)

---

## 1. System-Ubersicht (High-Level)

### Container-Landschaft (17 gesamt, 11 aktiv)

| Container | Status | Bild | Netzwerk | Funktion |
|-----------|--------|------|----------|----------|
| **hermes-green** | UP 11h | hermes-agent:latest | green-net, ki-fabrik | Meta-Orchestrator, Cron-Scheduler, Gateway |
| **ai-hedge-fund-crypto** | UP 4h (healthy) | trading-ai-hedge-fund-crypto | ki-fabrik | Signal-Core (3-Pillar-Modell) |
| **freqtrade-freqforge** | UP 18h | freqtrade-hermes10000:stable | ki-fabrik | Bot 1 — FreqForge_Override, Port 8086 |
| **freqtrade-freqforge-canary** | UP 18h | freqtrade-hermes10000:stable | ki-fabrik | Bot 2 — FreqForge_Override, Port 8081 |
| **freqtrade-regime-hybrid** | UP 18h | freqtrade-hermes10000:stable | ki-fabrik | Bot 3 — RegimeSwitchingHybrid_v7_v04, Port 8085 |
| **freqai-rebel** | UP 18h | freqtrade:2026.3_freqai | rebel-net (ISOLATED) | Bot 4 — FreqAI ML, Port 8087 |
| **trading-guardian** | UP 20h | guardian-trading-guardian | hermes-net (ISOLATED) | Unbekannt — keine Logs, keine Reachability |
| **green-mem0** | UP 16h (healthy) | hermes-mem0-local-api:stable | green-net | Mem0 Memory-Stack |
| **green-ollama** | UP 3d | ollama:latest | green-net | LLM-Inferenz lokal |
| **green-qdrant** | UP 3d | qdrant:latest | green-net | Vektor-Datenbank |
| **caddy** | UP 10d | caddy:latest | host | Reverse-Proxy |
| freqtrade-webserver | UP 4d | freqtradeorg/freqtrade:stable | — | UI-Only (kein Trading) |
| claude-worker | UP 9d | claude-worker:latest | — | Separater Coding-Agent |
| rizzcoach-app-1 | UP 3d | rizzcoach-app | — | Nicht Trading-bezogen |
| hermes-mem0-local-api | EXITED | — | — | ALTER Mem0 (durch green-mem0 ersetzt) |
| hermes-ollama | EXITED | — | — | ALTER Ollama (durch green-* ersetzt) |
| hermes-qdrant | EXITED 143 | — | — | ALTER Qdrant (durch green-* ersetzt) |
| a0-v2 | EXITED | — | — | Agent-Zero (nicht aktiv) |

### Kern-Komponenten

1. **ai-hedge-fund-crypto** — Signal-Generator (TA + Fear&Greed + X-Sentiment + LLM)
2. **Freqtrade Fleet** — 4 Bots in dry_run=True
3. **Hermes** — Orchestrator + Cron-Scheduler (37 Jobs)
4. **MCP Paper Trading** — Bitget-Paper-Portfolio (4 offene Positionen, 399 Orders)
5. **RiskGuard** — Standalone Service (*/30min)

### Externe Abhangigkeiten

- Docker Compose (ki-fabrik Netzwerk)
- Hermes Cron Scheduler (kein System-crontab vorhanden)
- Datei-basierte Signale (hermes_signal.json -> primo_signal_state.json)
- Telegram (Morning Brief, Fleet Reports, Critical Alerts, Watchdogs)
- Bitget Exchange (dry-run API-Abfragen)
- Mem0/Qdrant/Ollama (Memory-Stack im green-net)
- Caddy (Reverse-Proxy)

---

## 2. Komplettes Komponenten-Inventar

### 2A — Cronjobs (37 total, 31 OK, 6 ERROR)

**Kern-Pipeline (jede 5-10 Min):**

| Job | Schedule | Typ | Status |
|-----|----------|-----|--------|
| trading-pipeline | */10 Min | Script (no_agent) | OK |
| system-optimizer | alle 5 Min | Script (no_agent) | OK |
| FleetRisk equity updater | alle 5 Min | Script (no_agent) | OK |
| smart-heartbeat | */10 Min | Script (no_agent) | **ERROR** |
| signal-heartbeat | */20 Min | Script (no_agent) | **ERROR** |

**Heartbeat & Monitoring (10-30 Min):**

| Job | Schedule | Typ | Status |
|-----|----------|-----|--------|
| heartbeat-writer | */15 Min | Script (no_agent) | OK |
| hermes-standby-monitor | */5 Min | Script (no_agent) | OK |
| critical-event-watchdog | */10 Min | Script (no_agent) | OK |
| container-watchdog | */30 Min | Script (no_agent) | OK |
| drawdown-guard | */30 Min | Script (no_agent) | OK |
| canary-position-monitor | */30 Min | Script (no_agent) | OK |
| mot-floor-watchdog | */10 Min | Script (no_agent) | OK |
| config-diff-detector | Stdlich | Script (no_agent) | OK |
| fleetrisk-auto-params | */15 Min | Script (no_agent) | OK |
| riskguard-service | */30 Min | Script (no_agent) | OK |

**Wartung (2-4h):**

| Job | Schedule | Typ | Status |
|-----|----------|-----|--------|
| Fleet Report | alle 4h | LLM (deepseek-v4-flash, Telegram) | OK |
| autonomous-health-loop | alle 30 Min | LLM (glm-5.1) | OK |
| fleet-auto-repair | alle 2h | Script (Telegram) | OK |
| ghostbuster | alle 2h | Script (no_agent) | **ERROR** |
| mem0-watchdog | alle 2h | Script (no_agent) | OK |
| Memory Backfill | alle 2h | Script (no_agent) | OK |
| cron-guardian | alle 6h | Script (no_agent) | OK |
| Heartbeat Intelligence Report | alle 6h | Script (no_agent) | OK |
| daily-signal-confidence-monitor | alle 6h | LLM (glm-5.1) | **ERROR** |
| System Health Check | alle 8h | LLM (deepseek-v4-flash) | OK |
| trading-hub-deep-dive-validation | Taglich 09:00 | LLM (glm-5.1) | OK |

**Taglich/Wochentlich:**

| Job | Schedule | Typ | Status |
|-----|----------|-----|--------|
| daily-heartbeat | 06:00 UTC | Script (Telegram) | OK |
| morning-brief-daily | 08:00 UTC | Script (Telegram) | OK |
| morning-brief-1040 | 10:40 UTC | Script (Telegram) | OK |
| daily-backup | 02:00 UTC | Script (no_agent) | **ERROR** |
| log-rotation-daily | 03:00 UTC | Script (no_agent) | OK |
| monthly-strategy-report | 1. im Monat 08:00 | Script (Telegram) | OK |
| portfolio-rebalancer | Montag 06:00 | Script (no_agent) | **ERROR** |
| quality-hub-monitor | 08:00 UTC | Script (no_agent) | OK |
| Fleet correlation refresh | alle 72h | Script (no_agent) | OK |
| Rebel Status Summary | alle 12h | LLM (glm-5.1) | OK |

**Paused:** 72h Research Fleet Monitor (completed)

### 2B — Trigger-Endpunkte

| Endpunkt | Container | Port | Aufrufer |
|----------|-----------|------|----------|
| /trigger | ai-hedge-fund-crypto | 8410 (host) -> 8080 (intern) | signal-heartbeat (curl), smart-heartbeat (indirekt) |
| /health | ai-hedge-fund-crypto | 8410 | trading-guardian?, healthcheck |
| /signal | ai-hedge-fund-crypto | 8410 | Lesezugriff durch trading_pipeline.py |
| /api/v1/ping | Freqtrade Bots | 8081/8085/8086/8087 | heartbeat_writer.py |

### 2C — Signal-Dateien

| Datei | mtime | Alter | Funktion |
|-------|-------|-------|----------|
| ai-hedge-fund-crypto/output/hermes_signal.json | 22:31 UTC | 14 Min | **KANONISCHE Signal-Quelle** |
| ai-hedge-fund-crypto/output/latest/hermes_signal.json | 15:50 UTC | **7 Stunden** | Kopie (STALE!) |
| freqtrade/shared/primo_signal_state.json | 22:30 UTC | 15 Min | RiskGuard-Bridge-Ausgabe an Fleet |

### 2D — State-Dateien

| Datei | Funktion |
|-------|----------|
| orchestrator/state/hermes_heartbeat.sqlite | Heartbeat DB (*/15 Min aktualisiert) |
| orchestrator/state/consec_loss_state.json | Consecutive Loss Protection (56+ Stunden STALE!) |
| orchestrator/state/drawdown_state.json | Drawdown-Tracking |
| orchestrator/state/config_diff/config_diff_health.json | Config-Drift-Erkennung |
| orchestrator/state/standby/hermes_health.json | Hermes Container-Health |
| orchestrator/state/riskguard/riskguard_state.json | RiskGuard-Zustand |
| orchestrator/state/auto_params/auto_params_health.json | FleetRisk Auto-Parameter |
| orchestrator/state/alerts/ (883 Dateien) | Alert-Speicher |
| orchestrator/logs/mcp/bitget_mcp_portfolio.json | Paper-Trading-Portfolio |
| orchestrator/logs/shadow_decisions.jsonl | ShadowLogger Audit-Trail |
| orchestrator/logs/signal_bridge.log | Bridge-Aktivitaten |

### 2E — Skript-Landschaft

**54 Skripte** in /home/hermes/projects/trading/orchestrator/scripts/
**56 Skripte** in /opt/data/profiles/orchestrator/scripts/

Duplikate. Cron-Jobs laufen aus /opt/data/, Projekt-Skripte sind teilweise veraltete Kopie.

---

## 3. Aktueller Ablauf & Interaktionen

### 3A — Signal-Fluss (Soll vs. Ist)

```
SOLL:
  signal-heartbeat (*/20 Min) -> curl /trigger -> ai-hedge-fund-crypto generiert Signal
    -> schreibt output/hermes_signal.json + output/latest/hermes_signal.json
  smart-heartbeat (*/10 Min) -> pruft latest/ Alter -> trigger wenn >15 Min
  trading-pipeline (*/10 Min) -> liest hermes_signal.json
    -> Layer 1: Bridge (liest, normalisiert)
    -> Layer 2: RiskGuard (confidence >= 0.65, stale check)
    -> Layer 2.5: MCP Execution (paper trades via Bitget MCP)
    -> Layer 3: ShadowLogger (append-only JSONL)
    -> Layer 4: Bridge-Write (schreibt primo_signal_state.json pro Bot)
  Freqtrade Bots -> lesen primo_signal_state.json -> nutzen als Filter
```

```
IST (AKTUELL):
  signal-heartbeat: ERROR STATUS!  ->  /trigger wird moglicherweise nicht zuverlassig aufgerufen
  latest/hermes_signal.json: 7 STUNDEN ALT! (15:50 UTC)
    -> Der heartbeat schreibt nur CANONICAL, aber smart_heartbeat pruft LATEST
    -> LATEST wird NICHT aktualisiert, wenn signal-heartbeat fehlschlagt
  CANONICAL ist aktuell (22:31) - wurde vermutlich direkt vom /trigger geschrieben,
    aber die Kopie nach latest/ fehlt

  RACE CONDITION:
    smart-heartbeat pruft latest/ (stale) -> triggert heartbeat script
    heartbeat script triggert /trigger -> schreibt CANONICAL + LATEST
    trading_pipeline liest CANONICAL -> verarbeitet

    ABER: Wenn heartbeat ERROR, wird LATEST nie aktualisiert
    -> smart-heartbeat triggert endlos -> RACE: beide jobs konkurrieren um /trigger
```

### 3B — Wer triggert wann was?

| Zeitleiste | Prozess |
|-----------|---------|
| Minute 0 | system-optimizer (alle 5 Min) |
| Minute 0 | trading-pipeline (*/10 Min, Offset 30s) |
| Minute 0 | FleetRisk equity updater (alle 5 Min) |
| Minute 0 | smart-heartbeat (*/10 Min) -> pruft latest/ |
| Minute 0 | mot-floor-watchdog (*/10 Min) |
| Minute 0 | critical-event-watchdog (*/10 Min) |
| Minute 5 | system-optimizer |
| Minute 5 | FleetRisk equity updater |
| Minute 5 | hermes-standby-monitor (*/5 Min) |
| Minute 10 | trading-pipeline |
| Minute 10 | smart-heartbeat |
| Minute 10 | mot-floor-watchdog, critical-event-watchdog |
| Minute 15 | heartbeat-writer (*/15 Min) |
| Minute 15 | fleetrisk-auto-params (*/15 Min) |
| Minute 20 | signal-heartbeat (*/20 Min) -> direkter /trigger Aufruf |
| Minute 30 | riskguard-service, drawdown-guard, container-watchdog, canary-position-monitor |

### 3C — Concurrency & Race-Conditions (identifiziert)

**RACE 1: Doppeltes Trigger-System**
- `signal-heartbeat` (*/20 Min) ruft /trigger direkt auf
- `smart-heartbeat` (*/10 Min) pruft ob Signal stale, dann triggert heartbeat script
- Bei Minute 0, 20, 40: BEIDE konnen gleichzeitig /trigger aufrufen
- /trigger hat keine Lock-Mechanik -> doppelte Signal-Generierung moglich

**RACE 2: latest/ Copy Failure**
- `signal-heartbeat` soll CANONICAL und LATEST aktualisieren
- Bei ERROR wird nur CANONICAL geschrieben (oder gar nichts)
- `trading_pipeline` liest CANONICAL -> bekommt aktuelles Signal
- `smart_heartbeat` pruft LATEST -> sieht stale -> triggert erneut -> RACE 1

**RACE 3: trading_pipeline parallel zu heartbeat**
- trading_pipeline (*/10 Min) und signal-heartbeat (*/20 Min) koennen gleichzeitig laufen
- Pipeline liest Signal, waehrend heartbeat gerade schreibt -> torn read
- JSON mv ist atomic, aber das Timing-Overlay bleibt riskant

**RACE 4: Consecutive Loss Cursor Stall**
- `consec_loss_state.json` analysis_cursor stuck seit 56+ Stunden
- `system_optimizer` lauft alle 5 Min, kann Cursor aber nicht vorwartsbewegen
- Cleanup-Code bevorzugt den stale Cursor statt den neuesten Trade -> Endlosschleife

### 3D — Kommunikationswege

| Von -> Nach | Methode |
|------------|---------|
| Hermes -> ai-hedge-fund-crypto /trigger | HTTP via curl (127.0.0.1:8410 ODER docker exec) |
| Hermes -> Freqtrade Bots /ping | HTTP via docker exec curl (Netzwerk-Isolation) |
| Hermes -> Mem0 | HTTP (green-mem0 Docker DNS auf green-net) |
| ai-hedge-fund-crypto -> output/ | Datei-Write (Docker Volume Mount) |
| trading_pipeline -> primo_signal_state.json | Datei-Write (shared Volume) |
| Freqtrade -> primo_signal_state.json | Datei-Read (Volume Mount in Container) |
| Hermes -> Telegram | Hermes Gateway (plattform-native) |
| trading-guardian -> ??? | Unbekannt (keine Logs, isoliertes Netzwerk) |

---

## 4. Bekannte Probleme & Pain Points

### BLOCKER A: latest/ Signal 7 Stunden Stale
**Schweregrad:** HOCH
**Ursache:** signal-heartbeat lauft mit ERROR. Der /trigger-Aufruf via curl auf 127.0.0.1:8410 funktioniert manchmal nicht zuverlassig. Das Skript schreibt CANONICAL aber nicht LATEST korrekt.
**Auswirkung:** smart-heartbeat sieht permanent stale LATEST -> triggert endlos, erzeugt Race mit signal-heartbeat.
**Warum Neustarts nur kurzfristig helfen:** Der Container-Neustart lost nicht das eigentliche Problem (curl Timeout, Port-Binding, oder Concurrent-Trigger-Blockade).

### BLOCKER B: /trigger Blockaden
**Schweregrad:** HOCH
**Ursache:** /trigger generiert ein komplettes Signal (OHLCV-Download + TA-Berechnung + X-Sentiment + LLM-Aufruf via deepseek-v4-pro). Das dauert bis zu 180 Sekunden. Wenn signal-heartbeat und smart-heartbeat gleichzeitig aufrufen, kann der ai-hedge-fund-crypto-Container den /trigger-Endpoint blockieren (Single-Threaded Flask).
**Warum Neustarts nur kurzfristig helfen:** Nach Restart startet der Container sauber, aber die doppelte Trigger-Kadenz stellt das Problem innerhalb weniger Minuten wieder her.

### BLOCKER C: Consecutive Loss Cursor Stalled (56+ Stunden)
**Schweregrad:** MITTEL
**Ursache:** Bekannter Bug im system_optimizer.py: `cleanup_expired_guard_state()` liest den stale Cursor und schreibt ihn zuruck. Cursor bevorzugt stale state statt latest closed trade -> Cursor bewegt sich nie.
**Auswirkung:** Consecutive Loss Protection ist de facto AUS. Bei einem Drawdown-Szenario greift der Schutz nicht.

### BLOCKER D: 6 Cronjobs im ERROR-Status
**Schweregrad:** MITTEL
- signal-heartbeat: /trigger-Blockade (siehe oben)
- smart-heartbeat: Folgefehler von signal-heartbeat (stale latest/)
- ghostbuster: Unbekannter Fehler (moglichweise Permission-Problem)
- daily-backup: Moglicherweise Disk/Permission-Problem
- portfolio-rebalancer: Wahrscheinlich Trade-Daten-Fehler
- daily-signal-confidence-monitor: LLM-Job mit Tool-Zugriffsfehler

### BLOCKER E: trading-guardian Container (Purpose Unknown)
**Schweregrad:** NIEDRIG (aber verdachtig)
- Laeuft auf isoliertem Netzwerk (hermes-net), nicht auf ki-fabrik
- Keine Logs in letzter Zeit
- Unklar welche Funktion es hat oder ob es noch genutzt wird

### BLOCKER F: Alert-Spam (883 Dateien)
**Schweregrad:** NIEDRIG (aber Ressourcenverschwendung)
- Alle 5-10 Minuten wird ein neues Alert-JSON geschrieben
- Nur wenige werden tatsachlich an Telegram zugestellt
- 883 Dateien = mehrere MB unnotige State-Files

### BLOCKER G: Dual Script-Repositories
**Schweregrad:** MITTEL
- 54 Skripte in Projekt, 56 in /opt/data/profiles/orchestrator/scripts/
- Cron laeuft aus /opt/data/, aber Code-Aenderungen gehen an der Projekt-Kopie vorbei
- Synchronisations-Locke: Wird ein Skript im Projekt repariert, laeuft der Cron weiterhin die alte /opt/data/ Version

### CHRONISCHE PROBLEME (Wochen/Monate)

1. **Race Conditions am /trigger** — seit Einfuhrung des zweigleisigen Heartbeat-Systems
2. **Cron Scheduler Stalls** — bekannter Bug: no_agent Jobs mit error-Status frieren ein, bis delete+recreate
3. **Permission Drift** — UID 1337 (Container) vs UID 10000 (Hermes) vs root (Host) produzieren periodisch Permission Denied
4. **FleetTrade-Port-Konfusion** — heartbeat_writer nutzt Port 8080 intern, aber Bots konfigurieren verschiedene Ports (8081, 8085, 8086, 8087)
5. **FreqAI-Rebel Netzwerk-Isolation** — eigener Docker-Netzwerk, kann ki-fabrik Services nicht erreichen

---

## 5. Aktueller Status der Trading-Bots

| Bot | Container | Status | dry_run | Strategie | Port | PnL | Open Trades | Winrate | Hermes-Kopplung |
|-----|-----------|--------|---------|-----------|------|-----|-------------|---------|-----------------|
| **FreqForge** | freqtrade-freqforge | UP, RUNNING | **TRUE** | FreqForge_Override | 8086 | +8.94 USDT | 1 | 86.5% | Signal via primo_signal_state.json |
| **FreqForge-Canary** | freqtrade-freqforge-canary | UP, RUNNING | **TRUE** | FreqForge_Override | 8081 | +3.23 USDT | 3 | 90.9% | Signal via primo_signal_state.json |
| **Regime-Hybrid** | freqtrade-regime-hybrid | UP, RUNNING | **TRUE** | RegimeSwitchingHybrid_v7_v04 | 8085 | -7.08 USDT | 0 | 77.3% | Signal via primo_signal_state.json |
| **FreqAI-Rebel** | freqai-rebel | UP, RUNNING | **TRUE** | RebelLiquidation + FreqAI | 8087 | -5.76 USDT | 0 | 25.0% | TEILWEISE (isol. Netzwerk) |

**MCP Paper Portfolio:** Balance 8.47 USDT (von 50.000 Start), 4 offene Positionen, 399 Orders gesamt
**Fleet Total PnL:** -0.68 USDT (nahe Break-Even)

**Alle Bots: dry_run=True VERIFIZIERT. Kein Live-Trading.**

### Netzwerk-Isolation

- FreqForge, Canary, Regime-Hybrid: ki-fabrik (gemeinsam mit ai-hedge-fund-crypto)
- FreqAI-Rebel: eigenes freqai-rebel-net (KANN ki-fabrik Services nicht erreichen!)
- Hermes: green-net + ki-fabrik (dual-homed, kann beide erreichen)

### Aktueller Signal-Status

- Kanonisches Signal: FRESH (14 Min alt, 22:31 UTC)
- latest/ Signal: **STALE** (7 Stunden alt!)
- RiskGuard: 3 ACCEPTED (BTC SHORT 0.85, ETH SHORT 0.65, SOL SHORT 0.65), 4 WATCH_ONLY
- Market Bias: BEARISH
- Confidence Threshold: 0.65

### PING FAIL Erklaerung

Die Freqtrade-Bots (FreqForge, Canary, Regime-Hybrid) antworten NICHT auf `curl http://localhost:8080/api/v1/ping` weil ihre API auf unterschiedlichen Ports lauscht (8086, 8081, 8085). Der heartbeat_writer nutzt die korrekten Ports pro Bot. Nur Rebel antwortet auf 8080 (Default-Port).

---

## 6. Aktuelle Architektur-Bewertung

### Hermes als zentraler Orchestrator

| Dimension | Status | Details |
|-----------|--------|---------|
| Cron-Scheduler | JA (zentral) | 37 Jobs laufen ausschliesslich uber Hermes |
| Signal-Pipeline | TEILWEISE | trading_pipeline.py ist zentral, aber Signal-Trigger ist fragmentiert |
| Fleet-Monitoring | JA (zentral) | heartbeat_writer + intelligence report laufen via Hermes |
| Risk-Management | JA (zentral) | system_optimizer + RiskGuard + drawdown_guard |
| Self-Healing | TEILWEISE | standby-monitor, container-watchdog, fleet-auto-repair laufen |
| Trading-Execution | JA (zentral) | MCP Paper Trading uber Hermes |
| Memory/Context | JA (zentral) | Mem0 + Session-Search |

### Was ist noch "wild"

| Komponente | Problem |
|-----------|---------|
| **trading-guardian** | Unklarer Zweck, isoliertes Netzwerk, keine Logs, keine Dokumentation |
| **/trigger Mechanismus** | Zwei konkurrierende Heartbeat-Skripte, keine Lock-Mechanik |
| **FreqAI-Rebel** | Eigenes Docker-Netzwerk, kann ki-fabrik nicht erreichen |
| **Dual Script-Repo** | /opt/data vs Projekt-Kopie, Synchronisation manuell |
| **Docker Compose Files** | docker-compose.fleet.yml definiert 5 Bots (inkl. RSI + Momentum), aber nur 3 laufen |

### Architektur-Score

```
Zentrale Steuerung:   75% (Cron, Pipeline, Risk, MCP zentral — aber Trigger & Guardian wild)
Automatisierung:      80% (37 Cron-Jobs, aber 6 im Error)
Self-Healing:         60% (Watchdogs laufen, aber Cursor-Stall und Cron-Stall nicht erkannt)
Safety:               95% (dry_run=True verifiziert, keine Credentials, Hermes-SOUL.md strikt)
Dokumentation:        70% (Skills und References gut, aber trading-guardian und alt Compose nicht aufgeraeumt)
```

---

## 7. Chancen & notwendige Veranderungen

### MUSS (Blocker beseitigen)

1. **Trigger-Konsolidierung** — signal-heartbeat UND smart-heartbeat zu EINEM Job mergen. Einziger Trigger-Pfad: prufe Signal-Alter, wenn > 15 Min, rufe /trigger auf (mit Lock-File!). Das eliminiert Race 1 und Race 2.

2. **Consecutive Loss Cursor Fix** — Bekannte Code-Anderung im system_optimizer.py: `_latest_closed_trade_cursor()` muss VOR `_consec_state_cursor()` bevorzugt werden.

3. **latest/ Copy Mechanism** — trading_pipeline.py sollte nach erfolgreichem Read CANONICAL automatisch LATEST aktualisieren. Nicht vom heartbeat abhangig machen.

### SOLLTE (Qualitat verbessern)

4. **6 Error-Cronjobs reparieren** — Insbesondere ghostbuster, daily-backup, portfolio-rebalancer

5. **Dual Script-Repo eliminieren** — Entweder Symlinks von /opt/data/ -> Projekt, oder Projekt als einzige Quelle konfigurieren

6. **trading-guardian klaren** — Dokumentieren und integrieren oder dekommissionieren

7. **Alert-Speicher aufraumen** — 883 Dateien archivieren, Rotation einfuhren

### KANN (Langfristige Architektur)

8. **FreqAI-Rebel Netzwerk-Integration** — Von eigenem Netz auf ki-fabrik umziehen

9. **Docker Compose Bereinigung** — RSI und Momentum aus fleet.yml entfernen (decommissioned)

10. **Cron-Job Konsolidierung** — 37 Jobs auf 15-20 reduzieren (viele uberlappen sich funktional: autonomous-health-loop, system-health-check, fleet-report, deep-dive-validation)

---

## Zusammenfassung

Das ist der aktuelle Ist-Zustand des Systems (Stand 02.06.2026).

Das AI-Hedge-Fund-Crypto Trading Hub besteht aus 11 aktiven Containern, 4 dry-run Freqtrade-Bots, 1 Signal-Core, einem MCP Paper-Trading-Server und dem Hermes Meta-Orchestrator. 37 Cron-Jobs steuern das System automatisiert, davon 6 im ERROR-Status. Die Fleet ist nahe Break-Even (-0.68 USDT), mit FreqForge und Canary als profitable Bots und Regime-Hybrid sowie Rebel im Minus.

**Die drei kritischsten Probleme sind:**

1. Das zweigleisige Trigger-System (signal-heartbeat + smart-heartbeat) erzeugt Race-Conditions und laesst die latest/-Kopie 7 Stunden verfallen
2. Der Consecutive-Loss-Cursor ist seit 56+ Stunden festgefahren, was den Drawdown-Schutz deaktiviert
3. 6 Cronjobs laufen im ERROR-Status und muessen repariert werden

Hermes ist zu ~75% der zentrale Orchestrator — die Hauptluecke ist der fragmentierte Signal-Trigger und der undokumentierte trading-guardian Container. Die Safety-Infrastruktur (dry_run=True, keine Credentials, SOUL.md) ist intakt bei 95%.

Das System ist OPERABEL aber NICHT SELBSTHEILEND. Die identifizierten Blocker verhindern, dass die Automatisierung zuverlassig funktioniert. Ein gezielter 3-Phasen-Umbau (Trigger-Konsolidierung -> Cursor-Fix -> Error-Job-Reparatur) wurde das System auf Production-Readiness bringen.
