# Cron Hygiene Audit 2026-06-06

> **Audit-Datum:** 2026-06-06T05:39:52Z  
> **Auditor:** Hermes Orchestrator (Meta-Orchestrator)  
> **Letzter Report:** Initial-Audit  
> **Phase:** Read-only Audit — keine Mutationen durchgeführt

---

## 1. Executive Verdict

**GELB (YELLOW)** — System läuft, aber es gibt:

- **4 Script-not-found-Jobs** (SI analyze) durch falsches Script-Verzeichnis
- **1 config-diff-detector** mit alten Container-Namen → 4 falsche Errors
- **1 critical-event-watchdog** der auf config-diff-Fehleralarme feuert
- **1 hermes-standby-monitor** der durch Docker-Proxy-Exec-Limit SCHEDULER_STALLED meldet
- **Mehrere überlappende Health/Heartbeat-Jobs** (kein akutes Problem aber Cron-Rauschen)
- **Alte Once-Jobs bereits aufgeräumt** — die vom User erwähnten phase-12 / Baseline v1 Jobs existieren nicht mehr

**Keine Gefahr für Live-Geld oder Safety-Critical-Guards.**  
Alle Risiko-Guards (drawdown-guard, riskguard-service, ledger-watchdog, FleetRisk) laufen fehlerfrei.

---

## 2. Total Jobs Count

| Metrik | Wert |
|--------|------|
| Gelistete Cron-Jobs | **58** |
| User-Angabe | 61 (Differenz: 3 Jobs wurden wohl bereits entfernt) |
| Davon aktive (enabled=true) | **53** |
| Davon pausiert (enabled=false) | **3** (72h Research Fleet Monitor, si-bot-c-backtest, si-bot-c-walkforward) |
| Davon fehlerhaft (last_status=error) | **7** (4x SI analyze, config-diff-detector, hermes-standby-monitor, critical-event-watchdog) |
| Davon nie gelaufen (last_status=null) | **12** (alle SI backtest/daily/walkforward — noch nie ausgeführt) |

---

## 3. KEEP Jobs (44)

### Safety-Critical — KEIN Eingriff (9)
| Job | Script | Frequenz | Status |
|-----|--------|----------|--------|
| `drawdown-guard` | drawdown_guard.py | */30 * * * * | OK |
| `riskguard-service` | riskguard_service.py | */30 * * * * | OK |
| `container-watchdog` | container_watchdog.sh | */30 * * * * | OK |
| `daily-backup` | backup_rotation.py | 0 2 * * * | OK |
| `mem0-watchdog` | mem0_watchdog.py | 0 */2 * * * | OK |
| `FleetRisk equity updater` | fleet_risk_update_watchdog.sh | every 5m | OK |
| `fleetrisk-auto-params` | fleet_risk_auto_params.py | */15 * * * * | OK |
| `ledger-integrity-watchdog` | ledger_watchdog.py | every 30m | OK |
| `fleet-auto-repair` | fleet_auto_repair.py | 0 */2 * * * | OK |
| `mot-floor-watchdog` | mot_floor_watchdog.py | */10 * * * * | OK |

### Core Pipeline — KEEP (6)
| Job | Script | Frequenz | Status |
|-----|--------|----------|--------|
| `trading-pipeline` | trading_pipeline.py | */10 * * * * | OK |
| `system-optimizer` | system_optimizer.py | every 5m | OK |
| `portfolio-rebalancer` | portfolio_rebalancer.py | 0 6 * * 1 | OK |
| `Fleet correlation refresh` | fleet_correlation_refresh.sh | every 4320m | OK |
| `cron-guardian` | restore_cron_jobs.sh | 0 */6 * * * | OK |
| `log-rotation-daily` | log_rotation.py | 0 3 * * * | OK |

### Monitoring/Alerting — KEEP (8)
| Job | Script/Typ | Frequenz | Status |
|-----|------------|----------|--------|
| `critical-event-watchdog` | **SIEHE FIX** — false alarms | */10 * * * * | ERROR |
| `observation-runner` | observation_runner.py | */5 * * * * | OK |
| `observation-watchdog` | observation_watchdog.py | */10 * * * * | OK |
| `canary-position-monitor` | canary_position_monitor.py | */30 * * * * | OK |
| `daily-signal-confidence-monitor` | LLM (zai/glm-5.1) | 0 */6 * * * | OK |
| `Rebel Status Summary` | LLM (zai/glm-5.1) | every 720m | OK |
| `Fleet Report (alle 4h)` | LLM (ollama-cloud) | every 240m | OK |
| `System Health Check (alle 8h)` | LLM (ollama-cloud) | 0 */8 * * * | OK |

### Heartbeat/Health — KEEP (aber Overlap beachten) (5)
| Job | Script | Frequenz | Status |
|-----|--------|----------|--------|
| `Heartbeat Intelligence Report` | heartbeat_intelligence_wrapper.py | 0 */6 * * * | OK |
| `heartbeat-writer` | heartbeat_writer.py | */15 * * * * | OK |
| `daily-heartbeat` | daily_heartbeat.py | 0 6 * * * | OK |
| `unified-signal-heartbeat` | unified_signal_heartbeat.sh | */15 * * * * | OK |
| `Fleet Health Quickcheck` | LLM (skill fleet-health-quickcheck) | every 120m | OK |

### Memory — KEEP (3)
| Job | Script | Frequenz | Status |
|-----|--------|----------|--------|
| `Memory Backfill` | memory_backfill.py | 0 */2 * * * | OK |
| `Memory Hygiene Monitor` | memory_hygiene_monitor.py | 0 6 * * * | OK |
| `ghostbuster` | ghostbuster.py | 0 */2 * * * | OK |

### Trading Reports — KEEP (5)
| Job | Script | Frequenz | Status |
|-----|--------|----------|--------|
| `morning-brief-daily` | morning_brief.py | 0 8 * * * | OK |
| `trading-hub-deep-dive-validation` | LLM (zai/glm-5.1) | 0 9 * * * | OK |
| `monthly-strategy-report` | monthly_strategy_report.py | 0 8 1 * * | OK |
| `quality-hub-monitor` | quality_hub_monitor.py | 0 8 * * * | OK |
| `autonomous-health-loop` | LLM (zai/glm-5.1) | every 60m | OK |

---

## 4. FIX Jobs (7)

### 4.1 SI Analyze Script-Pfad (4 Jobs)

**Betroffen:**
- `si-bot-a-analyze-15min` (job_id: 7fc89baf94b0)
- `si-bot-b-analyze-20min` (job_id: 9f92e127ed0f)
- `si-bot-c-analyze-30min` (job_id: 6173b9ae1e4f)
- `si-bot-d-analyze-20min` (job_id: c80f00092f01)

**Ursache:** Die SI-Wrapper-Scripte liegen unter `/opt/data/profiles/orchestrator/home/.hermes/scripts/` — der Cron-Scheduler sucht im Verzeichnis `/opt/data/profiles/orchestrator/scripts/`.

**Gleiches Problem bei 12 weiteren SI-Jobs (backtest/daily/walkforward):**  
Noch nie gelaufen (last_status=null), würden ebenfalls `Script not found` werfen sobald der Scheduler sie ausführt.

**Fix:** Scripte kopieren (oder symlinken) in das korrekte Verzeichnis:

```bash
# 16 Scripte kopieren (nicht ausgeführt)
cp /opt/data/profiles/orchestrator/home/.hermes/scripts/si_bot_*.sh \
   /opt/data/profiles/orchestrator/scripts/
```

**Risiko bei Fix:** Gering. Scripte sind einfache Wrapper, die `run_analyze.sh`, `run_backtest.sh` etc. aufrufen.

### 4.2 config-diff-detector Container-Namen (1 Job)

**Betroffen:** `config-diff-detector` (job_id: 77f5e08b3492)

**Ursache:** Script verwendet alte Docker-Container-Namen ohne `trading-`-Prefix und ohne `-1`-Suffix:

| Alt im Script | Korrekt (aktuell) |
|---------------|-------------------|
| `freqtrade-freqforge` | `trading-freqtrade-freqforge-1` |
| `freqtrade-freqforge-canary` | `trading-freqtrade-freqforge-canary-1` |
| `freqtrade-regime-hybrid` | `trading-freqtrade-regime-hybrid-1` |
| `freqai-rebel` | `trading-freqai-rebel-1` |

**Fix in `/opt/data/profiles/orchestrator/scripts/config_diff_detector.py` (Zeile 32-43):**

```python
BOT_CONFIGS = [
    ("trading-freqtrade-freqforge-1",
     "/home/hermes/projects/trading/freqforge/config/config_freqforge_dryrun.json",
     "/freqtrade/config/config_freqforge_dryrun.json"),
    ("trading-freqtrade-freqforge-canary-1",
     "/home/hermes/projects/trading/freqforge-canary/config/config_canary_dryrun.json",
     "/freqtrade/config/config_canary_dryrun.json"),
    ("trading-freqtrade-regime-hybrid-1",
     "/home/hermes/projects/trading/freqtrade/bots/regime-hybrid/config/config_regime_hybrid_dryrun.json",
     "/freqtrade/config/config_regime_hybrid_dryrun.json"),
    ("trading-freqai-rebel-1",
     None,
     "/freqtrade/config/config.json"),
]
```

**Risiko bei Fix:** Gering. Container-Namen sind korrigiert. `docker exec` auf die Freqtrade-Container geht durch den Docker-Proxy (EXEC=0?) — **prüfen ob docker exec auf die trading-Container funktioniert.** Falls nicht, muss das Script auf DOCKER_HOST=unix:///var/run/docker.sock umgestellt werden oder die config_comparison muss anders erfolgen.

**⚠️ Wichtig:** Docker Proxy hat EXEC=0 gesetzt. `docker exec` funktioniert nur über den direkten Socket `/var/run/docker.sock`. Prüfen ob der config-diff-detector überhaupt `docker exec` können wird.

### 4.3 hermes-standby-monitor (1 Job)

**Betroffen:** `hermes-standby-monitor` (job_id: ff659be5aeaf)

**Ursache:** Script verwendet `docker exec hermes-green ps aux --no-headers`, was über den Docker-Proxy (EXEC=0) fehlschlägt. Der `hermes-green` Container läuft einwandfrei — aber der Standby-Monitor kann den Scheduler nicht prüfen und geht in EMERGENCY FALLBACK.

**Aktueller Zustand:**
- Container: `running` ✅
- Scheduler-Check: `docker exec failed` ❌ (Proxy-Block)
- Fallback aktiv: JA (läuft heartbeat_writer, trading_pipeline, riskguard_service redundant)

**Fix-Optionen (Reihenfolge der Präferenz):**
1. **Standby-Monitor pausieren** — da der Hermes-Scheduler tatsächlich läuft (wir sehen Cron-Jobs ausführen). Der Monitor erzeugt unnötigen Noise.
2. **Auf DOCKER_HOST umstellen** — `subprocess.run` mit env `DOCKER_HOST=unix:///var/run/docker.sock` für den exec-Aufruf.
3. **Alternative Scheduler-Prüfung** — statt `docker exec` einen HTTP-Health-Check auf Hermes-internen Endpoint nutzen.

**Risiko:** Der Monitor hat Safety-Fallback-Funktion. Bei Pausieren: andere Watchdogs decken Container-Health ab (container-watchdog, Fleet Health Quickcheck).

### 4.4 critical-event-watchdog — Folgealarm (1 Job)

**Betroffen:** `critical-event-watchdog` (job_id: ae387e595ca0)

**Ursache:** KEIN echter Fehler im Watchdog selbst. Der Watchdog prüft C3 (Config Drift) über die Datei `config_diff_health.json`, die vom config-diff-detector geschrieben wird. Da der config-diff-detector 4 Errors durch falsche Container-Namen produziert, meldet der Watchdog diese als kritische Config-Drift.

**Fix:** config-diff-detector reparieren (siehe 4.2) → Watchdog hört automatisch auf zu alarmieren.

**Risiko:** Kein direkter Eingriff nötig.

---

## 5. PAUSE Candidates (4)

### 5.1 `morning-brief-1040` (job_id: a72abde16f36)
- **Problem:** Duplikat von `morning-brief-daily` (gleiches Script `morning_brief.py`), nur andere Uhrzeit (10:40 vs 08:00)
- **Overhead:** Sendet täglich Telegram-Nachricht — doppelter Morning Brief
- **Vorschlag:** **DELETE** — `morning-brief-daily` behalten, `morning-brief-1040` löschen
- **Rollback:** Neu anlegen via `cronjob action='create'`

### 5.2 `unified-signal-heartbeat` (job_id: dcf21bfa3ab3)
- **Problem:** Läuft alle 15 Minuten, überschneidet sich mit `heartbeat-writer` (auch */15 * * * *)
- **Purpose:** Signal Bridge Heartbeat (unified_signal_heartbeat.sh) — Prüft ob die ai-hedge-fund Signal Bridge lebt
- **Vorschlag:** **PAUSE** wenn `heartbeat-writer` die gleiche Prüfung abdeckt. **KEEP** wenn `unified-signal-heartbeat` spezifisch den Signal-Bridge-Endpoint checkt (was der heartbeat-writer nicht tut)
- **UNKNOWN** — genauere Analyse nötig

### 5.3 `autonomous-health-loop` (job_id: 071c043a8fea)
- **Problem:** LLM-basierter Health-Check alle 60 Minuten. Überschneidet sich mit `System Health Check` (alle 8h) und `Fleet Health Quickcheck` (alle 2h)
- **Overhead:** Verbraucht LLM-Tokens (zai/glm-5.1) jede Stunde
- **Vorschlag:** **PAUSE** auf alle 4h oder **DELETE** wenn System Health Check + Fleet Health Quickcheck ausreichen
- **UNKNOWN** — genauen Scope vergleichen

### 5.4 `daily-heartbeat` (job_id: 1293995ea06b)
- **Problem:** Sendet täglich Telegram um 06:00. Überschneidet sich mit `morning-brief-daily` (08:00 Telegram). Beide liefern tägliche Zusammenfassung.
- **Vorschlag:** **KEEP** — heartbeat und morning-brief haben unterschiedliche Inhalte. Nur beobachten ob Redundanz besteht.

---

## 6. DELETE Candidates (3)

### 6.1 `72h Research Fleet Monitor (COMPLETED — paused)` (job_id: 31bbdb7708bd)
- **Status:** Paused seit 2026-05-24, 67/72 Durchläufen, next_run_at in der Vergangenheit
- **Begründung:** Research-Sprint abgeschlossen, wird nie wieder feuern
- **Lösch-Befehl:** `cronjob action='remove' job_id='31bbdb7708bd'`
- **Rollback:** Nicht möglich nach Delete — müsste neu erstellt werden

### 6.2 `freqforge-72h-test-daily` (job_id: df7291dbceda)
- **Status:** Aktiv, läuft täglich um 00:00, LLM-basiert (skills: trading-hub-operations, freqtrade-deployment-diagnostics)
- **Begründung:** Ursprünglich für 72h AI-Override-Change-Test. Der Test-Zeitraum ist vorbei.
- **⚠️ UNKNOWN** — Script läuft und produziert OK-Output. Könnte inzwischen einen anderen Zweck erfüllen.
- **Vorschlag:** Vor Löschung prüfen ob der Output noch wertvoll ist. Ggf. in daily-report integrieren.

### 6.3 `morning-brief-1040` (siehe PAUSE 5.1)
- **Begründung:** Doppelter Morning Brief
- **Lösch-Befehl:** `cronjob action='remove' job_id='a72abde16f36'`
- **Rollback:** Neu anlegen

---

## 7. UNKNOWN Jobs (1)

| Job | Grund |
|-----|-------|
| `freqforge-72h-test-daily` | Läuft OK, aber 72h-Test-Kontext ist wahrscheinlich abgeschlossen. Ohne Einsicht in den Output kann ich nicht entscheiden ob noch relevant. |

---

## 8. Broken Script Path Findings

### Problem
Die 16 SI-Wrapper-Scripte liegen unter:
```
/opt/data/profiles/orchestrator/home/.hermes/scripts/si_bot_*.sh
```

Der Hermes-Cron-Scheduler sucht `no_agent`-Scripte im Profil-Script-Verzeichnis:
```
/opt/data/profiles/orchestrator/scripts/
```

### Nachweis
- Alle funktionierenden `no_agent`-Jobs haben ihre Scripte in `/opt/data/profiles/orchestrator/scripts/` (z.B. `drawdown_guard.py`, `trading_pipeline.py`)
- Alle SI-Analyze-Jobs haben `last_status: "error"` und `script: "si_bot_*_analyze.sh"`
- Die Scripte existieren physikalisch, aber unter einem Pfad der nicht durchsucht wird

### Ziel-Scripte (existieren alle)
```
/home/hermes/projects/trading/self_improvement/bot_a/run_analyze.sh     ✅
/home/hermes/projects/trading/self_improvement/bot_a/run_backtest.sh    ✅
/home/hermes/projects/trading/self_improvement/bot_a/run_daily_report.sh ✅
/home/hermes/projects/trading/self_improvement/bot_a/run_walkforward.sh  ✅
... (alle 4 Bots × 4 Scripte = 16 Ziel-Scripte existieren)
```

---

## 9. Stale Container Name Findings

### config-diff-detector (config_diff_detector.py Zeilen 32-43)
Verwendet Docker-Container-Namen **ohne** Compose-Projekt-Prefix und Index-Suffix:

```
freqtrade-freqforge              → trading-freqtrade-freqforge-1
freqtrade-freqforge-canary       → trading-freqtrade-freqforge-canary-1
freqtrade-regime-hybrid          → trading-freqtrade-regime-hybrid-1
freqai-rebel                     → trading-freqai-rebel-1
```

### Auswirkung
- `docker exec` schlägt fehl → "container config unreadable" für alle 4 Bots
- `config_diff_health.json` zeigt `errors: 4`
- `critical-event-watchdog` liest das und alarmiert C3 (Config Drift)

### Fehlerkette
```
config-diff-detector (stale names) → errors: 4 in health file
→ critical-event-watchdog (C3 check) → false alarm → Telegram Alert
```

### Zusatzproblem: Docker Proxy EXEC=0
Selbst mit korrigierten Namen scheitert `docker exec` am Docker-Proxy (`trading-docker-proxy-1` mit `EXEC=0`).  
Das Script müsste `DOCKER_HOST=unix:///var/run/docker.sock` setzen, um direkt auf den Docker-Socket zuzugreifen.

---

## 10. Duplicate/Overlap Findings

### Heartbeat-Overlap (4 Jobs)
| Job | Frequenz | Telegram |
|-----|----------|----------|
| `heartbeat-writer` | */15 * * * * | ❌ local |
| `unified-signal-heartbeat` | */15 * * * * | ❌ local |
| `Heartbeat Intelligence Report` | 0 */6 * * * | ❌ local |
| `daily-heartbeat` | 0 6 * * * | ✅ Telegram |

**Analyse:**  
- `heartbeat-writer` & `unified-signal-heartbeat` beide alle 15min — ersterer schreibt generische Heartbeat-Daten, letzterer prüft Signal-Bridge. Unterschiedliche Zwecke, aber same Frequenz. Könnten in ein Script konsolidiert werden.
- `daily-heartbeat` (Telegram um 6) und `morning-brief-daily` (Telegram um 8) — beide morgendliche Telegram-Benachrichtigungen. Möglicherweise überschneidender Inhalt.

### Health-Overlap (3 Jobs)
| Job | Frequenz | Typ |
|-----|----------|-----|
| `autonomous-health-loop` | every 60m | LLM (zai/glm-5.1) |
| `Fleet Health Quickcheck` | every 120m | LLM (skill fleet-health-quickcheck) |
| `System Health Check` | 0 */8 * * * | LLM (ollama-cloud) |

**Alle 3 sind LLM-basiert und checken System-Health.**  
`autonomous-health-loop` läuft 8× häufiger als `System Health Check` und 2× häufiger als `Fleet Health Quickcheck` — das sind 24 LLM-Calls/Tag für Health-Checks.  
Konsolidierungsvorschlag: `autonomous-health-loop` auf every 4h reduzieren oder in Fleet Health Quickcheck integrieren.

### Memory-Overlap (3 Jobs)
| Job | Frequenz |
|-----|----------|
| `Memory Backfill` | 0 */2 * * * |
| `Memory Hygiene Monitor` | 0 6 * * * |
| `ghostbuster` | 0 */2 * * * |

**Analyse:** Unterschiedliche Zwecke (Backfill=Datensammlung, Hygiene=Audit, Ghostbuster=Bereinigung). Kein akutes Overlap-Problem, aber 3 Memory-Jobs könnten in einen Tages-Job konsolidiert werden.

### Morning Brief Overlap (2 Jobs — SAME SCRIPT)
| Job | Zeit |
|-----|------|
| `morning-brief-daily` | 0 8 * * * |
| `morning-brief-1040` | 40 10 * * * |

**Beide verwenden `morning_brief.py`.** Klarer Fall von Duplikat.

---

## 11. Recommended Minimal Cleanup — Batch 1

Basierend auf User-Vorentscheidung + Audit-Ergebnissen:

### FIX (niedriges Risiko)

```bash
# 1. SI Scripte ins korrekte Verzeichnis kopieren
cp /opt/data/profiles/orchestrator/home/.hermes/scripts/si_bot_*.sh \
   /opt/data/profiles/orchestrator/scripts/

# 2. config-diff-detector Container-Namen korrigieren
# DOCKER_HOST auf direct socket setzen (proxy bypass), Namen fixen
# Siehe Abschnitt 4.2 für genauen Patch
```

### DELETE (sicher)

```bash
# 1. Abgeschlossener Research-Monitor
cronjob action='remove' job_id='31bbdb7708bd'

# 2. Doppelter Morning Brief
cronjob action='remove' job_id='a72abde16f36'
```

### PAUSE (nach Prüfung)

```bash
# hermes-standby-monitor pausieren (erzeugt false SCHEDULER_STALLED)
cronjob action='pause' job_id='ff659be5aeaf'
```

---

## 12. Commands Prepared But NOT Executed

> ⚠️ **Read-only Audit — keine der folgenden Aktionen wurde ausgeführt**

### Delete: 72h Research Fleet Monitor
```bash
# cronjob remove — unwiderruflich
cronjob action='remove' job_id='31bbdb7708bd'
```
**Risiko:** Keins — Job ist bereits paused und abgeschlossen.

### Delete: morning-brief-1040
```bash
cronjob action='remove' job_id='a72abde16f36'
```
**Risiko:** Verlust des zweiten täglichen Briefings. `morning-brief-daily` bleibt erhalten.

### Fix: SI Script-Pfade
```bash
cp /opt/data/profiles/orchestrator/home/.hermes/scripts/si_bot_*.sh \
   /opt/data/profiles/orchestrator/scripts/
```
**Risiko:** Gering — nur Kopie, keine Löschung des Originals.

### Fix: config-diff-detector Container-Namen
```bash
# In config_diff_detector.py Zeile 32-43:
# Ersetze "freqtrade-freqforge" → "trading-freqtrade-freqforge-1"
# Ersetze "freqtrade-freqforge-canary" → "trading-freqtrade-freqforge-canary-1"
# Ersetze "freqtrade-regime-hybrid" → "trading-freqtrade-regime-hybrid-1"
# Ersetze "freqai-rebel" → "trading-freqai-rebel-1"
# Zusätzlich: env DOCKER_HOST=unix:///var/run/docker.sock setzen für docker exec
```
**Risiko:** Mittel — `docker exec` könnte auch mit korrigierten Namen am Proxy scheitern. Test nach Fix erforderlich. Siehe Docker-Proxy EXEC=0 Problem.

### Fix: hermes-standby-monitor (Option 1: pausieren)
```bash
cronjob action='pause' job_id='ff659be5aeaf'
```
**Risiko:** Der Standby-Monitor hat Fallback-Funktion. Bei Pause: container-watchdog und Fleet Health Quickcheck decken Container-Health ab. Hermes läuft stabil (>11h uptime).

### Fix: hermes-standby-monitor (Option 2: DOCKER_HOST fix)
```python
# In hermes_standby_monitor.py Zeile 72:
# subprocess.run(["docker", "exec", ...]) ändern zu:
env = os.environ.copy()
env["DOCKER_HOST"] = "unix:///var/run/docker.sock"
subprocess.run([...], env=env, ...)
```

---

## 13. Final Verdict

### Gesamt: **GELB**

| Bereich | Status | Begründung |
|---------|--------|------------|
| **Safety-Guards** | 🟢 GREEN | drawdown-guard, riskguard-service, ledger-watchdog, FleetRisk alle OK |
| **Pipeline** | 🟢 GREEN | trading-pipeline, system-optimizer laufen stabil |
| **Memory** | 🟢 GREEN | mem0, Qdrant, Backfill alle gesund |
| **SI-Bots** | 🟡 YELLOW | Script-Pfade falsch, analyze-Jobs error |
| **Konfig** | 🔴 RED | config-diff-detector kaputt (Container-Namen + Proxy-Exec) |
| **Alerting** | 🟡 YELLOW | critical-event-watchdog feuert false alarms durch config-diff-Kette |
| **Standby** | 🔴 RED | hermes-standby-monitor in Dauer-Fallback wegen Proxy-Exec |
| **Cron-Rauschen** | 🟡 YELLOW | 4 überlappende Heartbeat-Jobs, 3 überlappende Health-Checks, doppelter Morning Brief |

### Top 3 Prioritäten:

1. **🟢 config-diff-detector fixen** (Container-Namen + DOCKER_HOST) — behebt automatisch critical-event-watchdog-Folgealarm
2. **🟢 SI Script-Pfade korrigieren** — Kopie der Wrapper-Scripte
3. **🟡 Standby-Monitor pausieren** — oder auf Proxy-kompatible Prüfung umstellen

---

## Anhang A: Docker-Container-Status (2026-06-06T05:39)

| Container | Status | Image |
|-----------|--------|-------|
| trading-freqtrade-webserver-1 | Up 2h (healthy) | freqtradeorg/freqtrade:stable |
| trading-freqai-rebel-1 | Up 2h (healthy) | freqtrade-freqai-rebel:custom |
| trading-freqtrade-regime-hybrid-1 | Up 2h (healthy) | freqtradeorg/freqtrade:stable |
| trading-freqtrade-freqforge-canary-1 | Up 2h (healthy) | freqtradeorg/freqtrade:stable |
| trading-freqtrade-freqforge-1 | Up 2h (healthy) | freqtradeorg/freqtrade:stable |
| green-mem0 | Up 4h (healthy) | hermes-mem0-local-api:stable |
| green-ollama | Up 4h (healthy) | ollama/ollama:latest |
| green-qdrant | Up 4h | qdrant/qdrant:latest |
| hermes-fleet-dashboard | Up 4h (healthy) | python:3.13-slim |
| polymarket-fadi | Up 5h | node:20-slim |
| btc5m-bot | Up 5h (healthy) | btc5m-bot:latest |
| weatherhermes | Up 6h (healthy) | weatherhermes:latest |
| trading-docker-proxy-1 | Up 7h | tecnativa/docker-socket-proxy:latest |
| hermes-green | Up 11h | nousresearch/hermes-agent:latest |
| trading-ai-hedge-fund-1 | Up 11h (healthy) | trading-ai-hedge-fund-crypto:latest |
| trading-caddy-1 | Up 5h | caddy:alpine |
| trading-hermes-watchdog-1 | Up 12h | alpine:latest |
| trading-dashboard | Up 3d | python:3.13-slim |
| trading-guardian | Up 5d | guardian-trading-guardian |
| rizzcoach-app-1 | Up 7d (healthy) | rizzcoach-app |
| claude-worker | Up 13d (healthy) | claude-worker:latest |

---

## Anhang B: Git Status
```
M docs/context/ledger-watchdog-2026-06-06.md
M docs/state/canonical-trading-status.md
M docs/state/current-operational-state.md
M orchestrator/reports/canonical_trading_status_latest.json
?? docs/context/2026-06-06-data-refresh-preflight.md
?? docs/context/self-improvement-bot-a-b-data-refresh-and-cron-gate-20260606.md
?? docs/context/self-improvement-cron-reactivation-20260606.md
?? docs/context/self-improvement-hybrid-inventory-20260606.md
?? docs/context/self-improvement-ohlcv-and-cron-reactivation-gate-20260606.md
?? docs/context/self-improvement-ohlcv-smoke-consistency-check-20260606.md
?? docs/context/self-improvement-p0-p1-docker-trade-exporter-20260606.md
?? docs/context/self-improvement-post-implementation-qa-20260606.md
?? self_improvement/
```

---

*Audit completed 2026-06-06T05:39:52Z. No mutations performed.*
