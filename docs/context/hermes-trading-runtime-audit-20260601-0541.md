# Hermes Trading Hub -- Runtime-Audit 2026-06-01

**Audit-Typ:** Read-Only Infrastruktur-Audit
**Auditor:** Claude Code (automatisiert, 4 parallele Agenten)
**Host:** Agent0 | User: hermes
**Start:** 2026-06-01 05:41 UTC
**End:** 2026-06-01 ~06:00 UTC
**Change-Proof:** `git status` zeigt nur 1 untracked File (`mcp_daemon.pid`), kein diff. Audit ist read-only.

---

## Executive Verdict

| Metrik | Wert | Klassifikation |
|--------|------|----------------|
| LIVE_RISK | Nein | **VERIFIED** |
| DRY_RUN_FLEET | 4/4 True, Keys leer | **VERIFIED** |
| CANONICAL_HERMES | hermes-green (einziger Agent) | **VERIFIED** |
| MEM0_CLOUD_FREE | Kein Cloud-Bezug im Stack | **VERIFIED** |
| SIGNAL_FRESHNESS | 9.6 min (Threshold: 30) | **VERIFIED** |
| DRAWDOWN | 0%, Portfolio +$48.92 | **VERIFIED** |
| GUARDIAN_SYSTEMD | Alle 5 min, OK | **VERIFIED** |
| RISKGUARD_INTEGRATED | Aktiv, 7 Regeln, 1.208 Zyklen | **VERIFIED** |
| SHADOWLOGGER_INTEGRATED | Aktiv, 1.208 Eintraege | **VERIFIED** |
| MEM0_LLM_EXTRACTION | 401 Unauthorized (ollama.com/v1) | **BROKEN** |
| BLUE_STACK_STATUS | Verwaist, ~8.2 GB Duplikat | **DUPLICATE** |
| GUARDIAN_DOCKER | Laeuft, 0 Log-Zeilen | **WARNING** |
| HYPEROPT_LEER | Seit 2026-05-14 keine Ergebnisse | **STALE** |
| CRITICAL_BLOCKERS | 1 (Mem0 LLM Extraction) | **BROKEN** |

**Gesamtbewertung:** Infrastruktur stabil und sicher. Alle Trading-Bots im Dry-Run, keine Exchange-Keys, kein Live-Risiko. Ein kritischer Bug in der Mem0 LLM-Extraction muss gefixt werden. Blue-Stack ist Duplikat und kann nach Code-Anpassung aufgeraeumt werden.

---

## 1. Kanonische Laufzeitkarte (Canonical Runtime Map)

### Verdict: VERIFIED

**Kanonischer Agent: `hermes-green`**

Evidenz:
- `hermes-green` (Image: `nousresearch/hermes-agent:latest`) ist der **einzige** Hermes-Agent-Container
- Kein `hermes-agent` (Blue) Container existiert -- weder running noch stopped
- Compose-Quelle: `/opt/hermes-green/docker-compose.yml`
- Mount: `/opt/hermes-green/config` -> `/opt/data`
- Netzwerke: `hermes-green_green-net` + `ki-fabrik` (Dual-Homed)

```
hermes-green (Up 6h)
  ├── green-mem0:8787     [green-net]
  ├── green-qdrant:6333   [green-net]
  └── green-ollama:11434  [green-net]
      + ki-fabrik (Trading Fleet Access)
```

---

## 2. Mem0 / Qdrant / Ollama Verdict

### Verdict: VERIFIED (aktiv) + BROKEN (LLM Extraction)

**Aktiver Memory-Pfad:**
```
hermes-green -> green-mem0:8787 -> green-qdrant:6333 -> green-ollama:11434
```

### Beide Stacks im Vergleich

| Eigenschaft | Blue Stack | Green Stack (kanonisch) |
|---|---|---|
| Mem0 API | `hermes-mem0-local-api:8787` | `green-mem0:8788` |
| Status | Up 6d, healthy | Up 2d, healthy |
| Qdrant Points | 1.167 (`hermes_memories_v2`) | 1.167 (identisch) |
| Embedder | `qwen3-embedding:4b` (1024-dim) | Identisch |
| LLM URL | `https://ollama.com/v1` (401!) | `https://ollama.com/v1` (401!) |
| cloud_required | false | false |
| Traffic | Null seit Erstellung (May 25) | Aktiv (luke-hermes Memory Adds) |
| Volume-Groesse | Qdrant 2.8 GB + Ollama 5.4 GB | Identische Groesse |
| Netzwerk | `hermes_memory` (isoliert) | `hermes-green_green-net` (verbunden) |

### Kritischer Bug: Mem0 LLM Extraction

**BROKEN** -- Beide Mem0-Instanzen nutzen `MEM0_LLM_BASE_URL=https://ollama.com/v1` (in Docker-Image gebacken, nicht von Compose ueberschrieben). Dieser externe Endpoint returned **401 Unauthorized** bei jedem Memory-Add. Embeddings funktionieren (lokaler Ollama), aber die LLM-basierte Extraction/Refinement schlaegt fehl.

**Impact:** Memories werden gespeichert, aber ohne LLM-Refinement. Die Qualitaet der gespeicherten Fakten ist reduziert.

**Fix:** `MEM0_LLM_BASE_URL` auf lokalen Ollama zeigen lassen:
```yaml
# In /opt/hermes-green/docker-compose.yml ergaenzen:
MEM0_LLM_BASE_URL: "http://green-ollama:11434/v1"
MEM0_LLM_MODEL: "qwen2.5:3b"
```

### Blue Stack: Verwaist, aber Code referenziert ihn noch

4 aktive Scripts referenzieren noch den Blue-Container:
- `orchestrator/scripts/system_optimizer.py:250` -- hardcoded `hermes-mem0-local-api`
- `orchestrator/scripts/daily_heartbeat.py:88` -- `docker inspect hermes-mem0-local-api`
- `orchestrator/scripts/mem0_watchdog.py:15` -- Default `MEM0_CONTAINER_NAME = "hermes-mem0-local-api"`
- `orchestrator/scripts/mem0_watchdog.py:44` -- Fallback `http://mem0-local-api:8787` (nicht aufloesbar)

**Empfehlung:** Blue-Stack erst entfernen, wenn diese 4 Scripts auf `green-mem0` aktualisiert sind.

### Mem0 Cloud: VERIFIED frei

Keine Referenzen auf `mem0.ai`, `cloud.mem0`, `api.mem0.ai` in aktivem Code. `MEM0_API_KEY` nur in einer Recovery-Dokumentation (2026-05-17), nicht in Runtime-Code.

---

## 3. Docker-Netzwerk Verdict

### Verdict: VERIFIED (korrekt isoliert)

| Netzwerk | Container | Zweck | Klassifikation |
|---|---|---|---|
| `ki-fabrik` | freqforge, canary, regime-hybrid, hermes-green, claude-worker, ai-hedge-fund-crypto | Trading Fleet + Signal + Agent | **VERIFIED** |
| `hermes-green_green-net` | hermes-green, green-mem0, green-qdrant, green-ollama | Green Memory Stack (isoliert) | **VERIFIED** |
| `hermes_memory` | hermes-mem0-local-api, hermes-ollama, hermes-qdrant | Blue Memory Stack (verwaist) | **DUPLICATE** |
| `trading_hermes-net` | trading-guardian | Guardian (isoliert) | **VERIFIED** |
| `freqai-rebel_freqai-rebel-net` | freqai-rebel | FreqAI Bot (isoliert) | **INTENTIONAL_ISOLATION** |
| `agenten_auto_trade_trading-network` | freqtrade-webserver | Altes Projekt (verwaist) | **STALE** |
| `trading-network` | *(leer)* | Ueberbleibsel | **STALE** |
| `trading_proxy-net` | *(leer)* | Ueberbleibsel | **STALE** |

### freqai-rebel Isolierung: INTENTIONAL_ISOLATION

freqai-rebel laeuft auf einem eigenen Netzwerk, ist aber voll funktionsfaehig:
- Outbound Internet: VERIFIED (Bitget API erreichbar)
- dry_run=True, Exchange Keys leer
- Aktives FreqAI-Inferencing (BTC/USDT, ETH/USDT, ~0.8s Latenz)
- Keine Abhaengigkeit von anderen Containern (kein Redis, keine Shared DB)

### freqtrade-webserver: STALE / MISCONFIGURED

- Gehoert zu Projekt `agenten_auto_trade` (nicht Trading Hub)
- Port-Mismatch: Docker mappt 8080->8180, aber Freqtrade hoert auf 8081 -> API unereichbar
- Isoliert auf eigenem Netzwerk, dry_run=True, Keys leer -- kein Risiko, aber kein Nutzen

---

## 4. Freqtrade-Fleet Verdict

### Verdict: VERIFIED -- 4/4 dry_run=True, alle Keys leer, alle erreichbar

| Bot | Port | dry_run | Mode | Exchange | Strategy | API Ping | PnL |
|---|---|---|---|---|---|---|---|
| **freqtrade-freqforge** | 8086 | True | futures | bitget | FreqForge_Override | pong | +$58.55 |
| **freqtrade-freqforge-canary** | 8081 | True | futures | bitget | FreqForge_Override | pong | +$3.23 |
| **freqtrade-regime-hybrid** | 8085 | True | futures | bitget | RegimeSwitchingHybrid_v7 | pong | -$7.10 |
| **freqai-rebel** | 8087 | True | futures | bitget | RebelLiquidation+XGBoost | pong | -$5.76 |
| freqtrade-webserver | 8180 | True | spot | bitget | N/A | **UNREACHABLE** | N/A |

**Portfolio-Gesamt:** $3,498.92 (Start: $3,450.00, PnL: +$48.92, Drawdown: 0%)

**Exchange Keys:** Alle 4 aktiven Bots haben leere `key` und `secret` Felder. Kein Live-Trade moeglich.

**Trade-Persistenz:** 3 Bots haben aktive tradesv3-DBs mit heutigen Writes (WAL-Files aktuell). freqai-rebel hat keine heutige Trade-DB (Trainings-Modus).

**Cross-Contamination (WARNING):** 10+ 0-Byte-Trade-DBs von falschen Bots in falschen Verzeichnissen. Ein literal `tradesv3.*.dryrun.sqlite` Filename in freqforge (Shell-Glob-Bug).

---

## 5. Training-System Verdict

### Verdict: VERIFIED (aktiv) + STALE (Hyperopt leer)

**FreqAI-Modelle (8 Varianten):**

| Modell | Letzte Aenderung | Bemerkung |
|---|---|---|
| rebel-liquidation-v1 | 2026-05-14 | Basis |
| rebel-liquidation-v1-wrapper-n80-es20-t0005 | 2026-06-01 04:59 | **Aktuellster Lauf (heute)** |
| rebel-liquidation-wf-top15-t45 | 2026-05-26 | Walk-Forward, 53 Subdirs |
| 5 weitere Varianten | 2026-05-14/16 | Parametervariationen |

**Backtest-Ergebnisse:** 9 Result-Sets vorhanden, davon Walk-Forward mit 8 Rolling Windows (2026-03-18 bis 2026-05-13). Neuester Walk-Forward-Pilot: 2026-05-26.

**Hyperopt:** Verzeichnis existiert seit 2026-05-14, aber **leer**. Keine Hyperopt-Epochen gespeichert. **STALE**.

**Strategien:** 20 Strategie-Dateien in 6 Bot-Verzeichnissen. Aktuellste: `RegimeSwitchingHybrid_v7_v04_Integration.py` (2026-05-30).

**Daily Lab:** 4 Daily-Strategien (MomentumDaily, RegimeSafe, SafeEntryDaily, TrendDaily). 7 konsekutive Daily-Backups (2026-05-26 bis 2026-06-01).

---

## 6. Guardian / Cron / Self-Healing Verdict

### Verdict: VERIFIED (Systemd) + WARNING (Docker Guardian idle)

### Systemd Guardian

| Komponente | Status | Details |
|---|---|---|
| `trading-cron-guardian.timer` | active (waiting) | Alle 5 min, OnBootSec=2min |
| `trading-cron-guardian.service` | Exit-Code 0 | Letzter Lauf: heute 07:43 CEST |
| `trading-permfix.timer` | active (waiting) | Alle 10 min, laeuft als root |
| `trading-permfix.service` | Exit-Code 0 | Letzter Lauf: heute 07:39 CEST |

Host-Guardian-Log: Durchgehend OK-Eintraege. Signal-Frische unter 12 min (Threshold: 30 min). Permission-Checks alternierend zwischen Guardian und Permfix.

### Docker Guardian Container

**WARNING:** `trading-guardian` Container laeuft (Up 3h) aber hat **0 Log-Zeilen**. Die Guardian-Logik laeuft ausschliesslich ueber systemd. Der Container scheint ein Placeholder zu sein.

### Cron Jobs (10 definiert, alle enabled)

| # | Name | Schedule | Script | Existiert |
|---|---|---|---|---|
| 1 | signal-heartbeat | */20 min | ai_hedge_signal_heartbeat.sh | OK |
| 2 | trading-pipeline | */10 min | trading_pipeline.py | OK |
| 3 | drawdown-guard | */30 min | drawdown_guard.py | OK |
| 4 | container-watchdog | */5 min | container_watchdog.sh | OK |
| 5 | mcp-watchdog | */5 min | mcp_watchdog.sh | OK |
| 6 | daily-backup | 0 2 * * * | backup_rotation.py | OK |
| 7 | portfolio-rebalancer | 0 6 * * 1 | portfolio_rebalancer.py | OK |
| 8 | cron-guardian | 0 */6 * * * | restore_cron_jobs.sh | OK |
| 9 | smart-heartbeat | */10 min | smart_heartbeat.py | OK |
| 10 | Fleet Report | alle 4h | (prompt-basiert) | N/A |

**WARNING:** Alle `last_run_at`, `last_status`, `last_error` Felder in jobs.json sind `null`. Telemetrie wird nicht aktualisiert. Systemd-Service referenziert Projekt-Pfad direkt, nicht Deploy-Pfad (`/opt/data/profiles/orchestrator/scripts/` hat nur 6 von 50+ Scripts).

---

## 7. RiskGuard / ShadowLogger Verdict

### Verdict: IMPLEMENTED (nicht Spec) -- beide in integrierter Version aktiv

### RiskGuard

| Variante | Status | Details |
|---|---|---|
| **Standalone** (`tools/riskguard/riskguard.py`) | **IMPLEMENTED** aber **STALE** | 7 Funktionen, echter Code. Letzter Lauf: 2026-05-28. 2 Eintraege. Threshold: 0.60 / 15 min. Superseded. |
| **Integriert** (`trading_pipeline.py` L158) | **IMPLEMENTED** und **AKTIV** | 5 Regeln (RG-1 bis RG-5). Threshold: 0.65 / 25 min. State heute aktualisiert. 1.208 Zyklen. |

**Kein SPEC ONLY.** Keine TODO/FIXME/PLACEHOLDER-Marker. Beide Versionen sind echter Code. Die integrierte Version ist produktiv.

**WARNING:** Unterschiedliche Thresholds (0.60 vs 0.65, 15 vs 25 min). Potential fuer Verwirrung. Standalone sollte als "superseded" dokumentiert werden.

### ShadowLogger

| Variante | Status | Details |
|---|---|---|
| **Standalone** (`tools/freqforge/freqforge_shadow.py`) | **IMPLEMENTED** aber **STALE** | 10 Funktionen, 17 KB Code, 350 Per-Trade-Eintraege. Letzter Lauf: 2026-05-21 (11 Tage). |
| **Integriert** (`trading_pipeline.py` L505) | **IMPLEMENTED** und **AKTIV** | 1.208 Pipeline-Zyklus-Snapshots. Neuester Eintrag: heute. |

**Wichtig:** Standalone und integrierte ShadowLogger decken verschiedene Audit-Zwecke ab:
- Standalone: Per-Trade Events (entry, exit, open_risk pro Bot)
- Integriert: Per-Pipeline-Zyklus Snapshots (alle Pair-Entscheidungen)

Standalone hat 350 einzigartige Per-Trade-Eintrage die im integrierten Log nicht existieren.

**WARNING:** RiskGuard Audit-Log hat nur 1 Eintrag trotz 1.208 Shadow-Zyklen. `audit_written: false` im Health-File. Audit-Logging moeglicherweise deaktiviert oder bedingt.

---

## 8. Stale / Duplicate / Cleanup-Kandidaten

### STALE (sicher entfernbar nach Pruefung)

| Ressource | Details | Risiko |
|---|---|---|
| Container `a0-v2` (Agent-Zero) | Exited seit 45h | Kein Risiko |
| 5 anonyme Hash-Volumes | Ueberbleibsel entfernter Container | Kein Datenverlust |
| `claude-worker-data` Volume | Kein Container angehaengt | Kein Risiko |
| `ollama-data` + `ollama_data` Volumes | Superseded durch `green-ollama-data` | Duplikat |
| `regime-hybrid-vol` Volume | Bot nutzt jetzt Bind-Mount | Kein Risiko |
| `shared-signals` Volume | Kein Container angehaengt | Kein Risiko |
| Netzwerke `trading-network`, `trading_proxy-net` | 0 Container | Kein Risiko |
| 13+ Config-Backup-Dateien (.bak) | FreqForge + Canary | Redundant |
| 13+ Compose-Backups in `/opt/hermes/` | Historisch | Redundant |
| Standalone RiskGuard decisions.jsonl | 2 Eintraege, superseded | Archivieren |
| Standalone FreqForge shadow (350 Eintraege) | Einzigartige Per-Trade-Daten | **Vor Loeschung archivieren** |

### DUPLICATE

| Ressource | Details | Naechster Schritt |
|---|---|---|
| Blue Stack (Mem0+Qdrant+Ollama) | ~8.2 GB Duplikat | Erst nach Code-Update auf green-Referenzen |
| 4 inaktive Bot-Verzeichnisse | fomo-phase3, momentum, mvs, rsi | Strategie-Configs archivieren |
| `freqtrade-webserver` | Gehoert zu agenten_auto_trade, nicht Trading Hub | Nach Klaerung entfernen |

### BROKEN

| Ressource | Details | Fix |
|---|---|---|
| Mem0 LLM Extraction | `ollama.com/v1` returned 401 | `MEM0_LLM_BASE_URL` auf `green-ollama:11434/v1` setzen |
| freqtrade-webserver Port | 8080->8180, aber API auf 8081 | Port-Mapping korrigieren oder entfernen |
| Literal Glob-Filename | `tradesv3.*.dryrun.sqlite` in freqforge | Shell-Bug in Script fixen |

---

## 9. Kritische Blocker

### BLOCKER 1: Mem0 LLM Extraction fehlgeschlagen (BROKEN)

- **Betroffen:** `green-mem0` (und `hermes-mem0-local-api`)
- **Evidenz:** `MEM0_LLM_BASE_URL=https://ollama.com/v1` gebacken im Docker-Image, nicht von Compose ueberschrieben. Jeder Memory-Add-Call erzeugt 401 Unauthorized.
- **Impact:** Memories werden gespeichert (Embeddings funktionieren), aber ohne LLM-Refinement. Reduzierte Memory-Qualitaet.
- **Fix:** In `/opt/hermes-green/docker-compose.yml` die Environment-Variablen ergaenzen:
  ```yaml
  MEM0_LLM_BASE_URL: "http://green-ollama:11434/v1"
  MEM0_LLM_MODEL: "qwen2.5:3b"
  ```
  Danach `docker compose up -d green-mem0` (Container-Neustart noetig).
- **Prio:** HOCH -- betrifft alle Memory-Operationen

### BLOCKER 2: Docker Guardian Container ohne Funktion (WARNING)

- **Betroffen:** `trading-guardian`
- **Evidenz:** Container laeuft (Up 3h) aber 0 Log-Zeilen. Guardian-Logik laeuft via systemd.
- **Impact:** Container verbraucht Ressourcen ohne Nutzen. Verwirrend bei Debugging.
- **Fix:** Entweder Guardian-Logic in Container aktivieren oder Container entfernen (systemd reicht).
- **Prio:** NIEDRIG -- kein Risiko, nur Cleanup

---

## 10. Empfohlene Naechste Schritte

### Sofort (Prio: HOCH)

1. **Mem0 LLM Extraction fixen** -- `MEM0_LLM_BASE_URL` in Green Compose auf lokalen Ollama zeigen lassen und Container neustarten
2. **Blue-Stack-Referenzen aktualisieren** -- 4 Scripts (system_optimizer, daily_heartbeat, mem0_watchdog x2) auf `green-mem0` umstellen

### Kurzfristig (Prio: MITTEL)

3. **Blue Stack evaluieren** -- Nach Code-Update: Blue Qdrant-Daten mit Green abgleichen (bereits identisch), dann Blue Stack entfernen (~8.2 GB frei)
4. **freqtrade-webserver Klaerung** -- Gehoert zu agenten_auto_trade. Entfernen oder Port-Fix?
5. **Standalone ShadowLogger archivieren** -- 350 Per-Trade-Eintraege sichern, dann als superseded markieren
6. **RiskGuard Audit-Logging pruefen** -- Nur 1 Eintrag trotz 1.208 Zyklen. `audit_written:false` klaeren

### Mittel- bis langfristig (Prio: NIEDRIG)

7. **Cron-Telemetrie aktivieren** -- jobs.json `last_run_at`/`last_status` Felder werden nicht geschrieben
8. **Orphan-Volumes und leere Netzwerke aufraeumen** -- Nach Bestaetigung
9. **Cross-Contamination Trade-DBs bereinigen** -- 0-Byte-Dateien von falschen Bots entfernen
10. **Glob-Filename Bug fixen** -- `tradesv3.*.dryrun.sqlite` literal filename in freqforge
11. **Hyperopt pipeline aufbauen** -- Verzeichnis existiert aber ist leer

### Ressourcen-Uebersicht

```
Docker Stats (Snapshots):
  green-ollama:       3.5 GB RAM (11.4%)  -- groesster Single-Consumer
  freqai-rebel:       1.3 GB RAM (4.3%)   -- FreqAI Inferencing
  hermes-green:       610 MB RAM (2.0%)   -- Agent
  green-qdrant:       310 MB RAM (1.0%)   -- Vector DB
  freqforge/canary:   ~253 MB je (0.8%)   -- Trading Bots
  regime-hybrid:      ~251 MB (0.8%)      -- Trading Bot
  Blue Stack gesamt:  ~300 MB RAM         -- Verwaist
  ----------------------------
  Gesamt:             ~6.3 GB / 30.6 GB (~20%)
```

---

## Audit-Methodik

- 4 parallele Explore-Agenten in Phase 1 (Runtime/Mem0, Netzwerke/Fleet, Training/Guardian, RiskGuard/Cleanup)
- Phase 2: Signal-Frische, Drawdown-State, System-Ressourcen, Konsistenz-Pruefung
- Phase 3: Report-Generierung
- Change-Proof: `git status` zeigt nur 1 untracked PID-File, kein diff zum Start
- Alle Befunde durch Laufzeit-Evidenz verifiziert, keine Vorannahmen verwendet
