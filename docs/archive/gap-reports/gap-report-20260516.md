# GAP-Report — Hermes-Kosmos 2026-05-16

**Erstellt:** 2026-05-16T22:02 UTC
**Scope:** Hermes Agent, Trading Hub, Hermes-Infrastruktur (VPS)
**Ausgeschlossen:** Twister Lab (isoliertes Paper-Lab), Agenten_Auto_Trade, Honcho (archiviert)

---

## 1. Executive Summary

Der Hermes-Kosmos produziert Signale (`ai-hedge-fund-crypto` → `hermes_signal.json`), aber **kein Signal erreicht einen Trading-Bot**. Die dokumentierte 6-Gate-Signal-Chain ist an 4 von 6 Gates unterbrochen. Drei von 5 Freqtrade-Bots sind funktional tot (Momentum = Zombie seit PrimoAgent-Dekommission, RSI = EXITED, webserver = UI ohne Backend), während 2 nicht-dokumentierte Container (freqai-rebel, freqforge-canary) im Background laufen. RiskGuard und ShadowLogger existieren als Dokumentations-Konzepte aber nicht als Services — das ist der kritischste Architektur-Bruch. Die Docker-Netzwerke sind faktisch vereint (ki-fabrik), obwohl AGENTS.md von einer Trennung ausgeht. Docs referenzieren Honcho noch als ACTIVE (decommissioned seit Wochen) und PrimoAgent-Komponenten als aktiv (decommissioned seit 2026-05-12).

---

## 2. Signal-Chain Analyse

### Soll-Pfad (laut ORCHESTRATOR_CHARTER.md + AGENTS.md):

```
ai-hedge-fund-crypto → Gate INIT →
    hermes_signal.json → Gate PREFLIGHT →
    RiskGuard → Gate RISK_FILTERED →
    ShadowLogger → Gate SHADOW_LOGGED →
    Bridge → Gate FLEET_SYNCED →
    per-bot primo_signal_state.json →
    Freqtrade Strategien (konservativer Filter) →
    Gate MONITORING
```

### Ist-Pfad (gemessen 2026-05-16):

```
ai-hedge-fund-crypto → hermes_signal.json ✅ (frisch, 21:37 UTC)
    → ⛔ RiskGuard existiert NICHT als Service
    → ⛔ ShadowLogger existiert NICHT als Service
    → ⛔ Bridge-Code existiert, aber kein Bridge-Container deployed
    → ⛔ primo_signal_state.json STALE (6 Tage alt)
    → ⛔ Momentum-Bot blockiert alle entries (WATCH_ONLY via primo_gate)
```

### Schritt-für-Schritt-Brüche:

| Schritt | Status | Detail |
|---------|--------|--------|
| ai-hedge-fund-crypto produziert Signal | ✅ | `analysis_only` mode, 3 pairs, alle confidence <0.06 |
| hermes_signal.json im shared-Pfad | ❌ | Signal liegt unter `ai-hedge-fund-crypto/output/`, NICHT `shared/hermes_signal.json` |
| RiskGuard validiert Signal | ❌ | Existiert nur als Konzept in Docs |
| ShadowLogger loggt Entscheidung | ❌ | Existiert nur als Konzept in Docs |
| Bridge deployed & angebunden | ❌ | `bridge/hermes_primo_bridge.py` existiert, kein Container |
| per-bot signal state aktualisiert | ❌ | State-Datei 6 Tage alt, unwired |
| Bot liest & respektiert Signal | ❌ | Momentum via `primo_gate.py` blockiert alle entries |

---

## 3. Fleet-Status Matrix

### Alle Container

| Container | Status | Uptime | Ports | dry_run | Netzwerk | Docs-Eintrag |
|-----------|--------|--------|-------|---------|----------|-------------|
| freqtrade-freqforge | ✅ Up | 5d | 0.0.0.0:8086 | ✅ true | ki-fabrik (172.18.0.8) | ACTIVE ✅ |
| freqtrade-regime-hybrid | ✅ Up | 5d | 127.0.0.1:8085 | (default) | ki-fabrik (172.18.0.7) | ACTIVE ✅ |
| freqtrade-momentum | ✅ Up | 3h | 127.0.0.1:8084 | (default) | ki-fabrik (172.18.0.4) | ACTIVE → ZOMBIE 🟠 |
| freqtrade-freqforge-canary | ✅ Up | 3h | 127.0.0.1:8081 | ✅ true | ki-fabrik (172.18.0.6) | NICHT in AGENTS.md 🟡 |
| freqtrade-webserver | ✅ Up | 4d | — | — | (unknown) | ACTIVE (nur UI) |
| freqtrade-rsi | ❌ EXITED (130) | — | — | — | ki-fabrik | QUARANTINE ✅ |
| ai-hedge-fund-crypto | ✅ Up (healthy) | 4d | 127.0.0.1:8410 | — | ki-fabrik (172.18.0.12) | ACTIVE ✅ |
| freqai-rebel | ✅ Up | 3h | 127.0.0.1:8087 | — | freqai-rebel-net | NICHT in AGENTS.md 🟡 |
| hermes-agent | ✅ Up | 20h | 0.0.0.0:8642 | — | ki-fabrik (172.18.0.2), trading-network (172.20.0.2) | ACTIVE ✅ |
| caddy | ✅ Up | 2w | — | — | (unknown) | ACTIVE ✅ |
| claude-worker | ✅ Up (healthy) | 4w | 127.0.0.1:5050 | — | ki-fabrik (172.18.0.3) | Nicht erwähnt 🔵 |

### Kritische Fleet-Gaps

**freqtrade-momentum — ZOMBIE** 🟠
- Läuft, aber `primo_gate.py` blockiert ALLE entries (WATCH_ONLY, allow_long_bias=false)
- 0 Trades seit PrimoAgent-Dekommission (2026-05-12)
- CPU: 0.18% — praktisch idle

**freqtrade-rsi — EXITED** 🟠
- Exit Code 130 (SIGINT / manuell gestoppt)
- Soll laut AGENTS.md in QUARANTINE sein
- Seit wann exited? Nicht dokumentiert

**freqforge-canary — UNDOKUMENTIERT** 🟡
- Läuft erfolgreich (dry_run, 500 USDT wallet)
- Wird in AGENTS.md nicht erwähnt
- Soll RSI ersetzen, aber nirgends dokumentiert

**freqai-rebel — UNDOKUMENTIERT** 🟡
- Läuft mit 910% CPU (dauerhaft AI-heavy)
- Kein Eintrag in AGENTS.md
- Kein Eintrag in docker-compose.fleet.yml
- Netzwerk isoliert (eigenes freqai-rebel-net)

---

## 4. Docker-Netzwerk-Topologie

### Netzwerke

| Netzwerk | Typ | Containers |
|----------|-----|------------|
| **ki-fabrik** (172.18.0.0/16) | bridge | hermes-agent, claude-worker, freqtrade-momentum, a0-v2, freqtrade-freqforge-canary, freqtrade-regime-hybrid, freqtrade-freqforge, ai-hedge-fund-crypto |
| **trading-network** (172.20.0.0/16) | bridge | hermes-agent (nur dieser) |
| freqai-rebel-net | bridge | freqai-rebel |
| agenten_auto_trade_trading-network | bridge | isoliert (separates System) |
| twister-lab_default | bridge | isoliert (separates Lab) |
| paperclip-docker_default | bridge | isoliert |

### Erkenntnis: Netzwerk-Isolation ist KEIN Problem

Der vorherige GAP-Report (G3.3.1) behauptete: *"Kein gemeinsames Netzwerk — ai-hedge-fund-crypto in ki-fabrik, Freqtrade in trading-network"*.

**Das ist FALSCH.** Tatsächlich hängen **alle** Trading-Container + ai-hedge-fund-crypto + hermes-agent im **ki-fabrik**-Netzwerk (172.18.0.0/16). Die container können sich gegenseitig erreichen.

`trading-network` ist quasi tot (nur hermes-agent hängt drin) — vermutlich ein Überbleibsel aus der Zeit vor der ki-fabrik Migration.

### Netzwerk-Problem: Bridge nicht angebunden

Obwohl die Container im selben Netzwerk sind, gibt es **keinen aktiven Bridge-Service**, der `hermes_signal.json` in `primo_signal_state.json` übersetzt. Die Netzwerk-Ebene ist bereit, die Service-Ebene nicht.

---

## 5. Dokumentations-Drift

### AGENTS.md — 11 KB

| Behauptung in Docs | Realität | Gap | Schwere |
|--------------------|----------|-----|---------|
| Honcho ACTIVE (PostgreSQL, Redis, Ollama, Deriver) | DECOMMISSIONED seit Wochen | ❌ Veraltet | 🟡 |
| PrimoAgent Bridge-Komponenten gelistet | DECOMMISSIONED seit 2026-05-12 | ❌ Veraltet | 🟡 |
| Gate 5: "Bridge writes per-bot signal state files" | Kein Bridge-Container deployed | ❌ Nicht implementiert | 🟠 |
| RSI: QUARANTINE mit Status | RSI: EXITED (130) | ✅ Status passt grob | 🔵 |
| Momentum: ACTIVE mit Trades | Momentum: 0 Trades seit Dekommission | ❌ Irreführend | 🟠 |
| Canary nicht erwähnt | Canary läuft als RSI-Ersatz | ❌ Fehlt | 🟡 |
| FreqAI-Rebel nicht erwähnt | Läuft mit 910% CPU | ❌ Fehlt | 🟡 |
| RiskGuard als Service beschrieben | Nicht implementiert | ❌ Dokumentiert ≠ deployed | 🔴 |
| ShadowLogger als Service beschrieben | Nicht implementiert | ❌ Dokumentiert ≠ deployed | 🔴 |

### ORCHESTRATOR_CHARTER.md — 8.5 KB v2.0

| Behauptung | Realität | Gap |
|------------|----------|-----|
| Changelog: "PrimoAgent decommissioned" | ✅ Korrekt | ✅ |
| Gate 3: RiskGuard | Nicht implementiert | 🟠 |
| Gate 4: ShadowEvidence | Nicht implementiert | 🟠 |
| Gate 5: Bridge schreibt per-bot state | Nicht implementiert | 🟠 |
| Gate 0: Reality Lock Report | Nie ausgeführt | 🟡 |
| Signal-Chain Beschreibung | Korrekt als Soll-Pfad | ✅ |

### SOUL.md — 2.3 KB

| Regel | Realität | Gap |
|-------|----------|-----|
| Rule 5: "RiskGuard ist die Safety-Layer" | Nicht implementiert | 🟠 |
| Rule 6: "ShadowLogger ist die Beweis-Schicht" | Nicht implementiert | 🟠 |
| Rule 7: "Bridge wird von keinem Bot zum Trade gezwungen" | Korrekt — keine Bridge existiert | ✅ |

---

## 6. Hermes-Infrastruktur

### Cron-Jobs (Hermes-intern, 8 Jobs)

| Job | Schedule | Typ | Status | Läuft? |
|-----|----------|-----|--------|--------|
| freqtrade-daily-report | 0 7 * * * | Agent (prompt) | 6 completed | ✅ |
| freqtrade-4h-fleet-snapshot | every 240m | Agent + Script | 29 completed | ✅ |
| ai-hedge-signal-heartbeat | every 30m | no-agent, Script | 46 completed | ✅ |
| trading-fleet-signal-audit | every 60m | Agent + Script | 17 completed | ✅ |
| twister-paper-cycle | every 15m | no-agent | 10 completed | ✅ |
| twister-daily-report | 0 8 * * * | no-agent | **0 runs** | ❌ Noch nie gelaufen |
| twister-healthcheck | 0 */6 * * * | no-agent | **0 runs** | ❌ Noch nie gelaufen |
| twister-research | 0 */6 * * * | no-agent | **0 runs** | ❌ Noch nie gelaufen |

**Feststellung:** 4 Trading-Jobs laufen zuverlässig. 3 Twister-Jobs sind nie initial gelaufen (twister-daily-report, healthcheck, research). Das könnte an fehlenden Scripts liegen.

### Holographic Memory

- DB: `/home/hermes/.hermes/shared-memory/holographic/memory_store.db` (372 facts ✅)
- Categories: general=268, project=79, tool=2, user_pref=23
- Canonical path `/home/hermes/.hermes/memory_store.db` existiert NICHT (lt. Memory erwartet)
- **Memory-Desync:** Subagent 2 fand canonical path nicht. DB liegt nur unter shared-memory/.
- state.db: `/home/hermes/.hermes/state.db` (295 MB) mit Symlink aus profiles/

### Skills (29 Skills)

- Vollständiges Skillset installiert ✅
- trading, devops, github, mlops, research, etc. vorhanden
- Ein Skill-Verzeichnis pro Kategorie
- Keine fehlende Kritikalität

### Profile

- 4 Profile: orchestrator (aktiv ✅), mira, trading, weatherbot
- orchestrator config: glm-5.1 via zai, cwd=trading, toolsets=hermes-cli

### Versions-Problem

- `hermes` CLI **nicht installiert** 🟡
- `crontab` (system) **nicht installiert** 🟡 — kein `crontab -l`
- `tailscale` **nicht installiert** 🟡
- Alles läuft über Hermes-internen Cron-Scheduler + Docker-Socket

---

## 7. Top 10 Kritische Gaps

| Rang | ID | Schwere | Komponente | Soll | Ist | Root Cause | Fix-Befehl |
|------|----|---------|------------|------|-----|------------|------------|
| 1 | G1 | 🔴 | **Signal-Chain (komplett)** | Signal erreicht Trading-Bots | Kein Signal erreicht Bot | RiskGuard/ShadowLogger/Bridge nie deployed | `docker compose -f docker-compose.ai-hedge-fund-crypto.yml build bridge && docker compose -f docker-compose.ai-hedge-fund-crypto.yml up -d bridge` |
| 2 | G2 | 🔴 | **RiskGuard Service** | Safety-Layer validiert Signale | Konzept existiert nur in Docs | Nie implementiert als Service | `touch bridge/riskguard_service.py` + Implementierung (1-2 Tage Aufwand) |
| 3 | G3 | 🔴 | **ShadowLogger Service** | Append-only JSONL-Log | Konzept existiert nur in Docs | Nie implementiert als Service | `touch bridge/shadow_logger.py` + Implementierung (1 Tag Aufwand) |
| 4 | G4 | 🟠 | **Bridge nicht deployed** | Bridge-Container läuft | Code existiert, kein Container | Kein Docker-Compose-Eintrag für Bridge | `docker build -t hermes-bridge ./bridge && docker run -d --network ki-fabrik --name hermes-bridge ...` |
| 5 | G5 | 🟠 | **freqtrade-momentum = ZOMBIE** | ACTIVE Bot mit Trades | Läuft seit Tagen ohne Trades | `primo_gate.py` blockiert entries (PrimoAgent tot) | `docker exec freqtrade-momentum cat /freqtrade/user_data/primo_signal_state.json` (diagnose), dann `touch freqtrade/bots/momentum/user_data/strat_change_log.md` |
| 6 | G6 | 🟠 | **hermes_signal.json Pfad** | Signal unter shared/ | Signal unter ai-hedge-fund-crypto/output/ | Kein Symlink/Copy in shared/ | `docker exec ai-hedge-fund-crypto cat /app/output/latest/hermes_signal.json > /home/hermes/projects/trading/shared/hermes_signal.json` (temporär) + Bridge-Fix dauerhaft |
| 7 | G7 | 🟡 | **primo_signal_state.json STALE** | State max 45 min alt | State 6 Tage alt | Kein Producer seit Dekommission | `cat > /home/hermes/projects/trading/freqtrade/shared/primo_signal_state.json << 'EOF' ...` — neues Signal von Hand schreiben |
| 8 | G8 | 🟡 | **AGENTS.md veraltet** | Aktuelle Fleet-Liste | Honcho ACTIVE, PrimoAgent erwähnt, Canary/Rebel fehlen | Nicht aktualisiert seit Dekommission | `cp AGENTS.md AGENTS.md.$(date +%Y%m%d) && vi AGENTS.md` (Phase 1) |
| 9 | G9 | 🟡 | **freqai-rebel 910% CPU** | Normale CPU-Last | 910% CPU dauerhaft | AI Loop oder Model-Overhead | `docker logs freqai-rebel --tail 50` (diagnose), `docker stats freqai-rebel --no-stream` (monitor) |
| 10 | G10 | 🔵 | **trading-network tot** | Wird für Fleet genutzt | Nur hermes-agent drin | Migration zu ki-fabrik unvollständig | `docker network rm trading-network` (nach Migration aller Container bestätigt) |

---

## 8. Phasen-Plan

### Phase 1: Read-Only & Diagnose (JETZT)

| Schritt | Aktion | Aufwand |
|---------|--------|---------|
| 1.1 | `docker logs freqai-rebel --tail 100` — CPU-Anomalie untersuchen | 2min |
| 1.2 | `docker exec freqtrade-momentum cat /freqtrade/user_data/primo_signal_state.json` — stale state bestätigen | 1min |
| 1.3 | `docker exec freqtrade-regime-hybrid cat /freqtrade/user_data/primo_signal_state.json` — auch stale? | 1min |
| 1.4 | `ls -la /home/hermes/projects/trading/freqware/bots/*/user_data/` — gibt es andere Bot-Verzeichnisse? | 2min |
| 1.5 | `du -sh /home/hermes/projects/trading/var/freqforge/ 2>/dev/null || echo "nicht vorhanden"` | 1min |
| 1.6 | AGENTS.md backup + Patch (Honcho ACTIVE → DECOMMISSIONED, PrimoAgent-Einträge entfernen, Canary+Rebel hinzufügen) | 15min |

### Phase 2: Config-Änderungen (nach Phase-1-Klarheit)

| Schritt | Aktion | Abhängigkeit |
|---------|--------|-------------|
| 2.1 | hermes_signal.json symlink/copy aus ai-hedge-fund-crypto output in shared/ | Phase 1.3 |
| 2.2 | Bridge-Container bauen & deployen (ki-fabrik Netzwerk) | Phase 1.1-1.6 |
| 2.3 | Momentum von primo_gate.py entkoppeln (direkt hermes_signal.json lesen) | Phase 2.1-2.2 |
| 2.4 | trading-network Container nach ki-fabrik migrieren + totes Netzwerk entfernen | Phase 2.2 |
| 2.5 | twister-cron Jobs fixen (daily, healthcheck, research nie gelaufen) | Phase 1.5 |

### Phase 3: Neue Implementierungen (nach Phase 2)

| Schritt | Aktion | Aufwand |
|---------|--------|---------|
| 3.1 | RiskGuard Service implementieren | 1-2 Tage |
| 3.2 | ShadowLogger implementieren (append-only JSONL) | 1 Tag |
| 3.3 | Neue hermes_signal Bridge schreiben (RiskGuard → ShadowLogger → Fleet) | 2-3 Tage |
| 3.4 | Momentum neustarten nach Signal-Bridge-Fix | 30min |
| 3.5 | End-to-End Signal-Chain Test (ai-hfc → Freqtrade Trade) | 1 Tag |

---

## Anhang: Offene Fragen (Phase 1 Diagnose)

1. **freqai-rebel CPU:** 910% seit wann? Ist das normal oder ein AI-Loop?
2. **freqtrade-momentum:** Wann zuletzt ein Trade? `freqtrade trade history`?
3. **a0-v2:** Was ist das? Läuft 39h, 2.35 GB RAM.
4. **freqtrade-webserver:** Welcher Bot steckt dahinter? `docker logs freqtrade-webserver | head`?
5. **twister-cron:** Warum nie gelaufen? Existieren `/home/hermes/twister-lab/twister_daily.py` und `twister_healthcheck.py`?
6. **Honcho:** Sind docker-compose Dateien noch im Repo? `find . -name "*honcho*"`?
