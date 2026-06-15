# GAP-Bericht — Trading Hub Gesamtsystem

**Erstellt:** 2026-05-16 21:30 UTC
**Author:** Hermes Agent (deepseek-v4-flash via Ollama Cloud → deepseek-v4-flash via DeepSeek)
**Profil:** orchestrator
**CWD:** /home/hermes/projects/trading
**Methode:** 3-Parallel-Subagent Evidence Collection (Trading Hub, Twister Lab, Hermes Infra) + Architecture-Doc Cross-Referenz

---

## LEGENDE

| Symbol | Bedeutung |
|--------|-----------|
| 🔴 KRITISCH | Systemausfall, Live-Geld-Risiko, Sicherheitslücke |
| 🟠 HOCH | Funktionale Lücke, Zombie-Prozess, falsche Status-Meldung |
| 🟡 MITTEL | Dokumentations-Lücke, veraltete Referenz, unterschwellige Ineffizienz |
| 🔵 INFO | Kosmetisch, Optimierung, Future-Architektur |
| ✅ GESCHLOSSEN | Gap wurde im Ist-Zustand geschlossen |

---

## TEIL 1: ARCHITEKTUR-GAPS (Cross-Component)

### 1.1 Signal Chain — DIREKTER PFAD VOM SIGNAL ZUM TRADE

**IST:**  
ai-hedge-fund-crypto → `hermes_signal.json` (alle 30min) → ⛔ KEIN CONSUMER

**SOLL (laut AGENTS.md + ORCHESTRATOR_CHARTER.md):**  
ai-hedge-fund-crypto → hermes_signal.json → **RiskGuard** → ShadowLogger → **Bridge** → Freqtrade per-bot state files → **Freqtrade Strategien als Filter**

| # | Gap | Schwere | Beschreibung |
|---|-----|---------|-------------|
| G1.1.1 | 🔴 KRITISCH | **Signal-Bridge vollständig unterbrochen.** PrimoAgent dekommissioniert am 2026-05-12, aber *kein* Ersatz wurde deployed. `hermes_primo_bridge.py` existiert noch (unter `bridge/` und `orchestrator/scripts/`), ist aber an kein laufendes System angebunden. |
| G1.1.2 | 🟠 HOCH | **`primo_signal_state.json`-Dateien sind STALE.** 4 Kopien existieren (shared, regime-hybrid, rsi, momentum). Alle zeigen `allow_long_bias: false, allow_short_bias: false`. Momentum-Bot liest sie immer noch und blockiert damit ALLE Entry-Entscheidungen. |
| G1.1.3 | 🟡 MITTEL | **RiskGuard existiert als Konzept in AGENTS.md aber nicht als laufender Service.** Kein Container, kein Skript, kein Regelwerk ausserhalb der Dokumentation. RiskGuard-Verdikte werden nirgendwo berechnet. |
| G1.1.4 | 🟡 MITTEL | **ShadowLogger existiert nur als Konzept.** Keine `var/freqforge/shadow_decisions.jsonl`, kein `state.json`, keine `snapshots/`. Die FreqForge Shadow Evaluator (v0.1) in `tools/freqforge/` läuft (polling in der Theorie), aber der Output existiert nicht im Dateisystem. |
| G1.1.5 | 🔴 KRITISCH | **Gate 5 (Freqtrade Sync) ist nicht implementiert.** Charter sagt: "Bridge writes per-bot signal state files" → niemand schreibt sie. |
| G1.1.6 | 🟡 MITTEL | **Signal-Konfidenz < 0.60 HARD-LIMIT wird von keinem Bot erzwungen.** Charter § "Trading Hard Limits" definiert Confidence >= 0.60. Alle aktuellen Signale sind conf=0.03-0.09 (hold). Kein Bot validiert gegen diese Schwelle. |

### 1.2 Freqtrade Fleet — Container-Status vs. Soll-Zustand

**IST:** 6 Container (freqforge, canary, regime-hybrid, momentum, freqai-rebel, webserver) + 1 Exited (rsi)

**SOLL (laut Charter v2.0):**  
5 aktive Bots + 1 Webserver + 0 Zombies + 0 untracked exits

| # | Gap | Schwere | Beschreibung |
|---|-----|---------|-------------|
| G1.2.1 | 🟠 HOCH | **Momentum-Bot = ZOMBIE.** Container läuft, API antwortet, CPU wird verbraucht — aber 0 Trades seit PrimoAgent-Dekommission. `max_open_trades=0` setzt entries auf HALT. Systemstatus fälschlicherweise GREEN. |
| G1.2.2 | 🟠 HOCH | **RSI-Container Exited aber nicht entfernt.** `freqtrade-rsi` ist seit ~6h mit Exit-Code 130 beendet. Ersetzt durch Canary, aber der alte Container blockiert Ressourcen und verschmutzt die Fleet-Übersicht. |
| G1.2.3 | 🟡 MITTEL | **MVS und FOMO Phase 3 in AGENTS.md gelistet aber NICHT deployed.** Charter und README listen sie als aktive Komponenten → kein Container existiert. |
| G1.2.4 | 🔵 INFO | **RSI in AGENTS.md als "QUARANTINE" markiert.** Ist aber Exited → sollte als "DESTROYED / REPLACED" aktualisiert werden. |
| G1.2.5 | 🟠 HOCH | **freqai-rebel verbraucht 972% CPU.** Erwartet für XGBoost-Training, aber kein Monitoring-Alarm bei Überschreitung. Wenn der Host 30.6 GiB RAM hat und hermes-agent bereits 4.26 GiB + a0-v2 3.07 GiB belegt, ist die Gesamtauslastung kritisch (39.5% RAM, aber CPU-Spitzen können alles blocken). |

### 1.3 Signal Quality — Inhaltliche Diskrepanz

**IST:**  
ai-hedge-fund-crypto generiert Signale mit conf=0.03-0.09 und action="hold" für ALLE 3 Pairs. Risk mode: "neutral".

**SOLL (laut Charter Gate 2):**  
Confidence im Bereich [0.60, 1.0]. Actions in {BUY, SELL, HOLD}.

| # | Gap | Schwere | Beschreibung |
|---|-----|---------|-------------|
| G1.3.1 | 🟠 HOCH | **Alle Signale sind "hold" mit conf < 0.10.** Das ist technisch gültig, aber die LLM-Konfiguration (temperature=0.15) erzeugt keine aussagekräftigen Signale. Seit Tagen kein BUY/SELL. |
| G1.3.2 | 🟡 MITTEL | **Keine Baseline/LLM-Disagreement-Erkennung aktiv.** RiskGuard (AGENTS.md) soll "baseline/LLM disagreement detection" machen → existiert nicht. |
| G1.3.3 | 🟡 MITTEL | **Signal-Age-Check existiert nur in der Theorie.** Charter Gate 2 definiert max 45 Minuten. Der Autopilot prüft es, aber kein Bot reagiert auf stale signals. |

---

## TEIL 2: TWISTER LAB — PAPER TRADING ISOLATION

**IST:**  
Twister Lab v0.2 unter `/home/hermes/twister-lab/`. Dockerized, synthetische Daten, 5 Strategien, virtuelles Portfolio.

| # | Gap | Schwere | Beschreibung |
|---|-----|---------|-------------|
| G2.1 | 🟠 HOCH | **Backtest-Engine findet 0 Trades bei optimalen Parametern.** 314 Grid-Search-Experimente durchgeführt, alle zeigen 0 Trades, 0 Win Rate, 0 Profit Factor. Kein Kandidat promotionsfähig (0/60 trades). |
| G2.2 | 🟠 HOCH | **Live-Paper-Trading läuft mit HYPOTHESE statt mit STRATEGIE.** Das SMA-RSI-Hypothesen-Modul hat 3 Trades platziert (50% WR, PF 0.93, -5.6% DD). Aber kein einziger Grid-Search-Kandidat wurde in den Live-Betrieb übernommen. |
| G2.3 | 🔵 INFO | **Portfolio bei 943.71 USDT (Start 1.000).** Max DD 5.84% < 8% Limit. Kann sich erholen, aber die Trade-Qualität ist unzureichend (nur ETH/USDT). |
| G2.4 | 🔴 KRITISCH | **Keine Verbindung zum Trading Hub.** Twister ist ein isoliertes System. Keine Signal-Bridge, kein Freqtrade-Bot, keine gemeinsame Datenquelle. Die 314 Experimente-Erkenntnisse sind NICHT ins Trading Hub eingeflossen. |
| G2.5 | 🟡 MITTEL | **Synthetische OHLCV-Daten.** Kein Live-Marktdaten-Stream. Fallback auf CoinGecko (wenn verfügbar) → keine Garantie für Echtdaten. |
| G2.6 | 🟡 MITTEL | **State-Files inkonsistent.** `open_paper_trades.json`, `closed_paper_trades.json`, `approval_queue.json`, `strategy_hypotheses.json` sind ALLE leer (`[]`). Aber `virtual_portfolio.json` zeigt 1 open Trade + 2 closed Trades. Die Queue-Dateien sind entkoppelt vom Portfolio. |
| G2.7 | 🟡 MITTEL | **Cron jobs laufen extern (Systemd/Docker-basiert)**, nicht über Hermes-cron. `cron/`-Verzeichnis leer. Keine zentrale Cron-Übersicht. |
| G2.8 | 🔵 INFO | **Keine RiskGuard oder ShadowLogger ähnliche Schicht.** Twister hat eigene Risk-Regeln (`twister_risk.py`), aber kein append-only Audit-Log analog zum Trading Hub. |

---

## TEIL 3: HERMES INFRASTRUKTUR — CRON, MEMORY, NETZWERK

### 3.1 Cron-System

| # | Gap | Schwere | Beschreibung |
|---|-----|---------|-------------|
| G3.1.1 | 🟠 HOCH | **Hermes cron_mode=deny.** `crontab` binary fehlt auf dem Host. Kein einziges Cron-Job läuft aktuell über Hermes. |
| G3.1.2 | 🟡 MITTEL | **Backup-Cron-Konfiguration existiert** (`/home/hermes/backups/cron/hermes-cron-backup-20260515-182338.bak`) aber wurde nicht wiederhergestellt. |
| G3.1.3 | 🔵 INFO | **ai-hedge-signal-heartbeat läuft alle 30min.** Im log sichtbar (`cron_cycle.log`). Aber: läuft das über einen externen Scheduler (Docker-basiert)? Der Pfad ist unklar. |

### 3.2 Holographic Memory

| # | Gap | Schwere | Beschreibung |
|---|-----|---------|-------------|
| G3.2.1 | ✅ GESCHLOSSEN | **372 Fakten, DB gesund.** WAL-Mode, FTS aktiv. 132 trading-relevante Fakten. |
| G3.2.2 | 🔵 INFO | **Dokumentation in SOUL.md sagt "354 Facts"** — Ist: 372. Minimale Drift, kein Problem. |
| G3.2.3 | 🟡 MITTEL | **Keine Risiko-Fakten im Holographic Memory.** Es gibt keine Fact-Entity für "current_drawdown", "bot_zombie_status", "signal_bridge_status" — alles runtime-Zustand, der nicht persistiert wird. |

### 3.3 Docker-Netzwerk

| # | Gap | Schwere | Beschreibung |
|---|-----|---------|-------------|
| G3.3.1 | 🟠 HOCH | **Signal-Bridge kann nicht kommunizieren.** `ai-hedge-fund-crypto` läuft in `ki-fabrik`-Netzwerk (br: docker-compose.ai-hedge-fund-crypto.yml). Freqtrade-Bots laufen in `trading-network`. **Kein gemeinsames Netzwerk.** Selbst wenn eine Bridge deployed würde, müsste sie in BEIDEN Netzwerken sein oder ein shared Network brücken. |
| G3.3.2 | 🟡 MITTEL | **Agenten_Auto_Trade läuft in eigenem Netzwerk** (`agenten_auto_trade_trading-network`). Keine Netzwerkverbindung zum Trading Hub. |
| G3.3.3 | 🟡 MITTEL | **Tailscale Funnel exponiert Freqtrade Web UI** (`agent0.taile6801f.ts.net:9092`). Caddy-Proxying ist aktiv, aber Audit-Log der eingehenden Verbindungen existiert nicht. |

---

## TEIL 4: DOKUMENTATION — SOLL/IST-ABWEICHUNG

### 4.1 AGENTS.md (System Architecture — 10.674 Zeichen)

| # | Gap | Schwere | Beschreibung |
|---|-----|---------|-------------|
| G4.1.1 | 🟡 MITTEL | **Honcho noch als "ACTIVE" gelistet.** Honcho ist vollständig dekommissioniert (Containers removed, DB archived). AGENTS.md beschreibt Honcho-Details (PostgreSQL, Redis, Ollama, Deriver MQG v2.0.0) → ALLES veraltet. |
| G4.1.2 | 🟡 MITTEL | **MVS und FOMO Phase 3 als "Active Bots" gelistet.** Kein Container existiert. Sollten unter "Stopped / Staged" stehen oder entfernt werden. |
| G4.1.3 | 🟡 MITTEL | **RSI unter "Active Bots" mit Status "QUARANTINE".** Ist Exited seit 6h. Sollte "EXITED / REPLACED BY CANARY" heissen. |
| G4.1.4 | 🔵 INFO | **Strategy Lineage (regime-hybrid) korrekt.** v7_v04_Integration aktiv, v9.1_Sentient research. Das ist aktuell. |
| G4.1.5 | 🟡 MITTEL | **Bridge/Verzeichnisse genannt aber outdated.** AGENTS.md listet `bridge/hermes_primo_bridge.py` und `primo/primo_api.py` als aktive Komponenten → PrimoAgent ist dekommissioniert. |

### 4.2 ORCHESTRATOR_CHARTER.md (Binding Rules — v2.0)

| # | Gap | Schwere | Beschreibung |
|---|-----|---------|-------------|
| G4.2.1 | 🟡 MITTEL | **Honcho im Charter noch als aktive Komponente.** § "Role Split: Honcho — Persistent Memory" beschreibt live-System. Ist archiviert. |
| G4.2.2 | 🟠 HOCH | **Gate 0 (Reality Lock) wurde nie ausgeführt.** Das Charter definiert "Verify Hermes version, profiles, cronjobs / Docker containers / filesystem paths / Output reality-lock-YYYY-MM-DD.md" — kein solcher Report existiert. |
| G4.2.3 | 🟡 MITTEL | **Gate 6 (Performance Gate) Kriterien sind teilweise unmet.** "Minimum 60 non-overlapping trades" → kein Bot erreicht das. "Walk-forward validation passed" → FreqAI hat Walk-Forward, aber die anderen Bots nicht dokumentiert. |
| G4.2.4 | 🔵 INFO | **Definition of Done (12 Punkte).** Punkt 2 ✅, 6 ✅, 7 ✅, 8 ✅, 11 ✅, 12 ✅. Punkt 1 🔴 (Signal canonical path unambiguous? NO — bridge broken), 3 🔴 (RiskGuard validates? NO), 4 🔴 (ShadowLogger? NO), 5 🔴 (Bridge max-age? NO), 9 🔴 (stale telemetry reported as GREEN? YES — Momentum), 10 🟡 (git-auditable? Mostly). |
| G4.2.5 | 🟡 MITTEL | **GREEN-Monitoring-Farbe für Momentum ist FALSCH.** Charter sagt: "All Freqtrade APIs pong" ✅, "No config drift" ✅ — aber Momentum hat entries HALTED und 0 trades. Farbgebung maskiert das Problem. |

### 4.3 SOUL.md (Project Identity)

| # | Gap | Schwere | Beschreibung |
|---|-----|---------|-------------|
| G4.3.1 | 🟡 MITTEL | **Rule 5: "RiskGuard ist die Safety-Layer"** — existiert nicht als Service. |
| G4.3.2 | 🟡 MITTEL | **Rule 6: "ShadowLogger ist die Beweis-Schicht"** — existiert nicht als Service. |
| G4.3.3 | 🔵 INFO | **"49 Strategie-Files versioniert"** — Stand 2026-05-14. Ist aktuell noch zutreffend. |
| G4.3.4 | 🔵 INFO | **"Nested repos ignoriert"** — korrekt. .gitignore zeigt das. |

### 4.4 current-operational-state.md

| # | Gap | Schwere | Beschreibung |
|---|-----|---------|-------------|
| G4.4.1 | 🟡 MITTEL | **"Momentum has 0 new trades since PrimoAgent decommission"** — korrekt dokumentiert. |
| G4.4.2 | 🟡 MITTEL | **"2 Honcho cronjobs still alive"** — wurden laut Backup-JSON inzwischen entfernt (REMOVED). Der Report wurde 06:26 UTC erstellt, die Löschung geschah später. Report ist outdated (13h alt). |
| G4.4.3 | 🟡 MITTEL | **Freqforge PnL: +$12.41** im Report vs. **+$2.9493** im Autopilot (19:02 UTC). Differenz von ~$9.46 — entweder update-Lücke oder unterschiedliche Berechnungsbasis. Operational state ist 13h alt. |

---

## TEIL 5: CROSS-INDUSTRY ANALYSIS

### 5.1 Trading Hub ⇔ Twister Lab (Signal Research ↔ Paper Execution)

| Aspekt | Trading Hub | Twister Lab | Gap |
|--------|------------|-------------|-----|
| Datenquelle | Live CoinGecko / Exchange OHLCV | Synthetische Daten | 🔴 Kein Datenaustausch |
| Strategien | 43 tracked files, 46 in nested | 5 research strategies | 🟡 Kein Cross-Pollination |
| Backtesting | Walk-Forward, daily_lab | Grid Search, 314 experiments | 🟡 Keine Methoden-Synchronisation |
| Signal-Pipeline | ai-hedge-fund-crypto (LLM) | SMA-RSI-Hypothese (deterministisch) | 🟡 Verschiedene Paradigmen |
| Execution | Freqtrade Dry-Run Fleet | Eigenes Virtual Portfolio | 🔴 Kein Austausch von Execution-Daten |
| Risk Layer | RiskGuard (Konzept) | twister_risk.py (implementiert) | 🟡 Twister hat funktionierendes Risk, Hub nicht |
| Audit | ShadowLogger (Konzept) | experiment_log.jsonl (implementiert) | 🟡 Twister hat funktionierenden Logger |

**Synergiepotenzial:**
- Twisters funktionierender Risk-Manager (`twister_risk.py`) könnte als Blaupause für RiskGuard im Trading Hub dienen
- Twisters Grid-Search-Engine (`twister_research.py`) könnte parametrisierte Backtests für Trading-Hub-Strategien liefern
- Trading Hubs Live-Daten (Bitget OHLCV) könnten Twisters synthetische Daten ersetzen

### 5.2 Trading Hub ⇔ Agenten_Auto_Trade (Hauptsystem ↔ Sidecar)

| Aspekt | Trading Hub | Agenten_Auto_Trade | Gap |
|--------|------------|--------------------|-----|
| Container | 6 laufend (trading-network) | 1 laufend (agenten_auto_trade_trading-network) | 🔴 Getrennte Netzwerke |
| Strategies | 43 tracked, 3 active | 46 strategies | 🟡 Kein Cross-Referencing |
| Exchange | Bitget | Bitget | ✅ Gleiche Exchange |
| Mode | Dry-Run | Paper (näher an Live) | 🟡 Unterschiedliche Risikostufen |
| Compliance | Germany, FIFO | Germany, 10-year retention | ✅ Beide compliant |
| Pairs | 7 (freqforge) + LINK/DOT/ATOM/UNI/AAVE (canary) + BTC/ETH/SOL (signal) | 12 pairs (BTC, ETH, SOL, XRP, DOGE, ADA, AVAX, DOT, LINK, NEAR, AAVE, ATOM) | 🟡 80% Overlap, aber keine abgestimmte Pair-Allokation |
| Telegram | Alerts enabled | Alerts enabled | ✅ Beide melden |

### 5.3 Trading Hub ⇔ Hermes Infrastruktur

| Aspekt | Soll | Ist | Gap |
|--------|------|-----|-----|
| Cron-Integration | Hermes cron verwaltet alle Trading-Jobs | cron_mode=deny, crontab fehlt | 🔴 Kein Cron-Management |
| Holographic Memory | 132 trading-relevante Fakten runtime | Fakten passiv (keine runtime-state-Fakten) | 🟡 Keine dynamische Zustandspeicherung |
| Skill-Abdeckung | 14 Trading-Skills vorhanden | Genutzt? Selten systematisch geladen | 🟡 Skills sind Library, kein aktiver Workflow |
| Container-Orchestrierung | Trading-Container in einem Netzwerk | 3 separate Netzwerke | 🟠 Fragmentierte Kommunikation |
| Autopilot | V0.1 aktiv (read-only fleet monitor) | Läuft, aber zeigt Momentum GREEN (falsch) | 🟡 Farbcodierung maskiert Zombie-Zustand |

### 5.4 Container-Ressourcenanalyse (Host-overcommitment)

| Container | RAM | CPU% | Uptime | Risiko |
|-----------|-----|------|--------|--------|
| freqai-rebel | 3.46 GiB | 972% | 3h | 🟠 CPU-Spike kann andere Container drosseln |
| hermes-agent | 4.26 GiB | 3.86% | 20h | 🟡 Hoher RAM-Footprint für CLI-Agent |
| a0-v2 (Agent Zero) | 3.07 GiB | 0.27% | 39h | 🟡 3.07 GiB für inaktives System |
| freqtrade-freqforge | 181 MiB | 1.90% | 5d | ✅ Effizient |
| freqtrade-canary | 255 MiB | 0.17% | 3h | ✅ |
| freqtrade-regime-hybrid | 160 MiB | 0.17% | 5d | ✅ |
| freqtrade-momentum | 238 MiB | 3.94% | 3h | 🟡 Läuft für 0 Trades |
| ai-hedge-fund-crypto | 153 MiB | 0.00% | 4d | ✅ Sehr effizient |
| caddy | 15 MiB | 0.00% | 2w | ✅ |
| claude-worker | 49 MiB | 0.00% | 4w | ✅ |
| **GESAMT** | **~12.1 GiB / 30.6 GiB** | — | — | 🟡 39.5% RAM genutzt. Spielraum vorhanden, aber freqai-rebel kann Host bei 972% CPU lahmlegen. |

---

## TEIL 6: STATE-MACHINE-GAPS

### 6.1 Global System State

| State | Soll | Ist | Gap |
|-------|------|-----|-----|
| INIT | System startet | ✅ Läuft | — |
| PREFLIGHT | Reality Lock ausführen | ❌ Nie ausgeführt | 🔴 Gate 0 skipped |
| DATA_READY | Daten verfügbar | ✅ ai-hedge-fund-crypto healthy | — |
| SIGNAL_READY | Signal generiert | ✅ Alle 30min | — |
| RISK_FILTERED | RiskGuard validiert | ❌ RiskGuard existiert nicht | 🔴 Gate 3 skipped |
| SHADOW_LOGGED | ShadowLogger schreibt | ❌ ShadowLogger existiert nicht | 🔴 Gate 4 skipped |
| FLEET_SYNCED | Bridge schreibt bot-state | ❌ Bridge tot (PrimoAgent gone) | 🔴 Gate 5 skipped |
| MONITORING | Autopilot läuft | ✅ V0.1 aktiv | ✅ |

**Der aktuelle Pfad ist:** SIGNAL_READY → MONITORING. **3 von 7 States werden übersprungen.**

### 6.2 Error States

| Error | Soll | Ist | Gap |
|-------|------|-----|-----|
| DATA_STALE | max 45 min → Alarm | Nicht implementiert | 🟡 Keine Reaktion auf stale signals |
| SIGNAL_INVALID | Schema-Validation | Nicht implementiert | 🟡 |
| RISK_BLOCKED | Verdict: BLOCK_ENTRY | Nicht implementiert | 🟡 |
| FLEET_UNHEALTHY | Bot API unerreichbar | Autopilot prüft das ✅ | — |
| CRON_DRIFT | Cron stale | cron_mode=deny → N/A | 🟡 Kann nicht auftreten, weil Cron deaktiviert |
| HUMAN_ESCALATION | Live-Geld-Risiko | charter-getriggert | ✅ Charter regelt das |

---

## TEIL 7: DETAIL-GAPS (Micro-Level)

### 7.1 Config-Drift

| Datei | Parameter | Soll | Ist | Gap |
|-------|-----------|------|-----|-----|
| `freqforge/config/config_freqforge_dryrun.json` | dry_run | true | true | ✅ |
| `freqforge-canary/config/config_canary_dryrun.json` | dry_run | true | true | ✅ |
| `ai-hedge-fund-crypto/config.yaml` | mode | live (signal) | live | ✅ |
| `freqforge/config` | jwt_secret_key | N/A | Present | 🟡 Key vorhanden, aber gitignoriert ✅ |

### 7.2 Bridge-Code-Staleness

| Datei | Zeilen | Letzte Änderung | Status |
|-------|--------|-----------------|--------|
| `orchestrator/scripts/hermes_primo_bridge.py` | unbekannt | unbekannt | 🟡 Existiert, nicht angebunden |
| `freqtrade/shared/primo_signal.py` | ~200 | unbekannt | 🟡 Veraltet (PrimoAgent gone) |
| `freqtrade/shared/primo_gate.py` | unbekannt | unbekannt | 🟡 Momentum liest immer noch stale states |
| `tools/freqforge/freqforge_shadow.py` | unbekannt | unbekannt | 🟡 Polling aktiv, aber Output nirgends persistiert |

### 7.3 Pair-Screening

| Bot | Pairs | Overlap mit anderen |
|-----|-------|---------------------|
| FreqForge | BTC, ETH, SOL, AVAX, NEAR, ARB, OP | ✅ Eigenständig |
| Canary | LINK, DOT, ATOM, UNI, AAVE | ✅ Non-overlapping (Designziel erreicht) |
| Regime-Hybrid | (aus Fleet-Compose) | 🟡 Nicht explizit auditiert |
| Momentum | (aus Fleet-Compose) | 🟡 Zombie → irrelevant |
| Signal | BTC, ETH, SOL | 🟡 Überlappt mit FreqForge, aber kein Consumer |

### 7.4 Portfolio-Risiko

| Metrik | Twister Lab (Ist) | Trading Hub (Soll) |
|--------|--------------------|-------------------|
| Max DD | 5.84% < 8% Limit | Nicht berechnet für Fleet |
| Konfidenz der Trades | 0.6558 (ETH/USDT open) | Charter: >= 0.60 ✅ |
| Min Trades für Promotion | 3 von 60 (5%) | Hard Limit ❌ |

---

## TEIL 8: ZUSAMMENFASSUNG — TOP 10 KRITISCHE GAPS

| Rang | ID | Gap | Impact | Priority |
|------|-----|-----|--------|----------|
| 🔴 1 | G1.1.1 | Signal-Bridge tot — kein Bot konsumiert Signale | Signal-Layer wertlos ohne Consumer | SOFORT |
| 🔴 2 | G1.1.5 | Gate 5 (Freqtrade Sync) nie implementiert | Charter-Versprechen uneingelöst | SOFORT |
| 🔴 3 | G2.4 | Twister Lab komplett isoliert vom Trading Hub | 314 Experimente-Erkenntnisse verloren | HOCH |
| 🔴 4 | G1.2.1 | Momentum-Bot = Zombie (0 Trades, GREEN gemeldet) | CPU/RAM-Verschwendung + falsche Telemetrie | HOCH |
| 🟠 5 | G1.1.3 | RiskGuard existiert nicht als Service | Safety-Layer fehlt komplett | HOCH |
| 🟠 6 | G1.1.4 | ShadowLogger existiert nicht als Service | Audit-Trail fehlt komplett | HOCH |
| 🟠 7 | G3.3.1 | Kein gemeinsames Docker-Netzwerk für Signal ↔ Fleet | Bridge kann nicht deployed werden | HOCH |
| 🟠 8 | G3.1.1 | Hermes cron_mode=deny | Kein zentrales Cron-Management | HOCH |
| 🟠 9 | G1.2.2 | RSI-Container Exited but not removed | Ressourcen-Verschwendung + falscher Fleet-State | HOCH |
| 🟠 10 | G4.2.2 | Gate 0 (Reality Lock) nie ausgeführt | Kein Baseline-Audit existiert | HOCH |

---

## TEIL 9: EMPFOHLENE AKTIONEN

### Phase 1 — Stabilisierung (sofort, read-only möglich)

1. **G1.2.2**: RSI-Container stoppen/entfernen → kann als read-only-audit eingeleitet werden
2. **G1.2.1**: Momentum-Audit durchführen → read-only, Klärung ob fix oder decommission
3. **G4.2.2**: Reality Lock (Gate 0) Report erstellen → read-only, keine Config-Änderung
4. **G3.1.2**: Cron-Backup wiederherstellen → genehmigungspflichtig

### Phase 2 — Architektur-Korrektur (genehmigungspflichtig)

5. **G1.1.1 + G1.1.5**: Neue Signal-Bridge bauen (ai-hedge-fund-crypto → per-bot state files)
6. **G3.3.1**: Docker-Netzwerk konsolidieren (shared network zwischen allen Trading-Containern)
7. **G1.1.3**: RiskGuard als Container/Skript implementieren (Blaupause: `twister_risk.py`)
8. **G1.1.4**: ShadowLogger als append-only JSONL-Service implementieren (Blaupause: `experiment_log.jsonl`)

### Phase 3 — Integration (mittelfristig)

9. **G2.4**: Twister Lab an Trading Hub anbinden (Signal-Daten teilen, Strategie-Erkenntnisse importieren)
10. **G3.1.1**: Hermes cron_mode aktivieren, alle Trading-Jobs migrieren
11. **Dokumentation**: AGENTS.md, Charter, SOUL.md auf aktuellen Stand bringen (Honcho entfernen, MVS/FOMO Status korrigieren, RSI-Status updaten)
12. **G4.2.1**: Honcho aus Charter entfernen

---

*Ende des GAP-Reports. Erstellt durch Hermes Agent (orchestrator) — Phase A: 3 Parallel-Subagent Evidence Collections. Phase B: Cross-Industry/Cross-Component Abgleich. Phase C: Granulare Soll/Ist-Matrix mit Mikro-Ebene Analyse.*
