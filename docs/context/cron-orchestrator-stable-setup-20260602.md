# Cron + Orchestrator Stabilisierung — Hermes Cron als Quelle der Wahrheit

**Stand:** 2026-06-02 13:34 UTC
**Modus:** Read-only Audit + Dokumentation
**Quelle:** `cronjob(action='list')`, `/opt/data/profiles/orchestrator/cron/jobs.json`, Live-Stat von Logs/State, Source-vs-Runtime-Diff

---

## 1. Kurze Bestandsaufnahme

| Kennzahl | Wert |
|---|---:|
| Cron-Jobs gesamt | 36 |
| Aktiviert | 35 |
| Pausiert | 1 |
| `last_status=ok` | 36 |
| `no_agent=true` | 29 |
| Agent-Jobs | 7 |
| `deliver=local` | 25 |
| `deliver=telegram` | 10 |
| `deliver=origin` | 1 |

**Kurzfazit:** Das Hermes-Cron-Setup ist live, sauber getrennt und aktuell stabil. Es gibt keinen aktiven Fehlerzustand in der Job-Liste. Die alte Doppelkette `signal-heartbeat` / `smart-heartbeat` ist pausiert und durch `unified-signal-heartbeat` ersetzt.

**Wichtiger Realitätscheck:** In diesem Runtime gibt es weder den Unix-User `claudio` noch ein `crontab`-Binary; ein klassisches System-Crontab-Setup ist hier nicht verfügbar. Der operative Scheduler ist die Hermes-Cron-Quelle der Wahrheit (`cronjob(action='list')`).

---

## 2. Konkrete Änderungen

1. Dokumentiert den aktuellen, live geprüften Cron-/Orchestrator-Stand als eigene Kontext-Referenz.
2. Markiert die heutige Architektur als Hermes-Cron-first statt Linux-System-Crontab-first.
3. Hält fest, dass keine Runtime-Jobs geändert wurden, weil die bestehende Kette stabil läuft und der Deploy-Pfad für Script-Änderungen Root-Rechte erfordert.
4. Markiert `run_trading_cycle.sh` als Git-only/legacy; es ist nicht Teil der aktiven Cron-Kette.

**Nicht geändert:** Keine Cronjobs neu angelegt, keine Jobs pausiert, keine Strategien, keine Live-/Dry-Run-Konfigurationen, keine Exchange-Credentials.

---

## 3. ASCII-Skizze der Job-Kette

```text
ai-hedge-fund-crypto (Signal-Generator)
        │
        ▼
unified-signal-heartbeat (15m, no_agent)
        │
        ├─> global_trigger_lock.sh (serialisiert /trigger)
        │
        └─> canonical signal refresh + latest sync
                     │
                     ▼
         trading-pipeline (10m, no_agent)
                     │
                     ├─> RiskGuard
                     ├─> ShadowLogger
                     └─> State-Writes / Bridge
                     │
                     ▼
          system-optimizer (5m, no_agent)
                     │
                     ├─> Guard-States / Quarantine
                     ├─> max_open_trades safety
                     └─> Health / Cleanup / Retry policy
```

---

## 4. Ausführungslogik

### 4.1 Datenabruf / Signal-Frische
- `unified-signal-heartbeat` läuft alle 15 Minuten und ist die einzige aktive Trigger-Kette für das Signal-Refresh.
- `signal-heartbeat` und `smart-heartbeat` sind pausiert und nicht mehr Teil des aktiven Pfads.
- Die Trigger-Serialisierung läuft über `global_trigger_lock.sh`, damit keine doppelten /trigger-Aufrufe entstehen.

### 4.2 Verarbeitung / Orchestrierung
- `trading-pipeline` läuft alle 10 Minuten.
- `system-optimizer` läuft alle 5 Minuten und steuert Guard-States, Quarantäne-Logik und Recovery-Regeln.
- `FleetRisk equity updater` läuft alle 5 Minuten.
- `fleet_correlation_refresh` läuft alle 4320 Minuten.

### 4.3 Benachrichtigungen / Reports
Aktive Report-/Notify-Jobs:
- `Fleet Report (alle 4h)`
- `daily-heartbeat`
- `morning-brief-daily`
- `morning-brief-1040`
- `quality-hub-monitor`
- `daily-signal-confidence-monitor`
- `monthly-strategy-report`

### 4.4 Health / Retry / Error-Aggregation
Aktive Health-/Recovery-Jobs:
- `hermes-standby-monitor`
- `container-watchdog`
- `drawdown-guard`
- `fleet-auto-repair`
- `config-diff-detector`
- `ghostbuster`
- `mcp-watchdog`
- `riskguard-service`
- `critical-event-watchdog`
- `cron-guardian`
- `mem0-watchdog`
- `heartbeat-writer`

### 4.5 Entkopplung
- Cronjobs kommunizieren über Dateien, State-JSON, Logs und Job-Registry — nicht über harte Imports zwischen Scheduler und Business-Logik.
- Deterministische Jobs laufen als `no_agent=true`; Reasoning bleibt auf die Agent-Jobs beschränkt.
- Der Scheduler ist die Quelle der Wahrheit, nicht eine einzelne Script-Datei.

---

## 5. Verifikationsergebnisse

### 5.1 Live-Job-Status
- `cronjob(action='list')`: 36 Jobs total, 35 aktiviert, 1 pausiert.
- Alle 36 Jobs stehen aktuell auf `last_status=ok`.
- Kein aktiver Duplicate-Heartbeat: der alte Doppelpfad ist pausiert, `unified-signal-heartbeat` ist aktiv.

### 5.2 Freshness der kritischen Artefakte
| Artefakt | Letzte Aktualisierung | Bewertung |
|---|---:|---|
| `ai-hedge-fund-crypto/output/hermes_signal.json` | 2026-06-02 13:32 UTC | frisch |
| `ai-hedge-fund-crypto/output/latest/hermes_signal.json` | 2026-06-02 13:32 UTC | frisch |
| `orchestrator/logs/unified_heartbeat.log` | 2026-06-02 13:32 UTC | frisch |
| `orchestrator/logs/trigger_lock.log` | 2026-06-02 13:32 UTC | frisch |
| `orchestrator/logs/drawdown_guard.log` | 2026-06-02 13:30 UTC | frisch |
| `orchestrator/state/container_watchdog_state.json` | 2026-06-02 13:30 UTC | frisch |
| `orchestrator/state/drawdown_state.json` | 2026-06-02 13:30 UTC | frisch |

### 5.3 Source-vs-Runtime-Diff
Für die kritischen Cron-Skripte war der manuelle Diff gegen die Runtime-Kopie leer:
- `unified_signal_heartbeat.sh` → kein Diff
- `global_trigger_lock.sh` → kein Diff
- `trading_pipeline.py` → kein Diff
- `system_optimizer.py` → kein Diff
- `fleet_healthcheck.py` → kein Diff

**Zusatzbefund:** `run_trading_cycle.sh` existiert im Git, aber nicht in der Runtime. Es ist damit aktuell ein Legacy-/Git-only-Artefakt und kein aktiver Cron-Entry-Point.

### 5.4 Scheduler-/Config-Registry
- `/opt/data/profiles/orchestrator/cron/jobs.json` ist lesbar und aktuell (36 Jobs).
- `/opt/data/profiles/orchestrator/config.yaml` ist lesbar.
- Der Deploy-Check `deploy_cron_scripts.sh --check` verlangt Root und konnte in dieser Session nicht ausgeführt werden.

---

## 6. Offene Punkte / Blocker

1. **System-Crontab-Variante nicht verfügbar:** Kein `claudio`-User, kein `crontab`-Binary in diesem Runtime.
2. **Pfad `/home/hermes/logs/orchestrator` fehlt:** Der Pfad ist nicht vorhanden und konnte hier nicht angelegt werden (Permission Denied).
3. **Legacy-Artefakt:** `run_trading_cycle.sh` ist nicht deployed und sollte nur dann aktiviert werden, wenn es bewusst in die Cron-Registry überführt wird.
4. **Deploy-Pfad:** Script-Änderungen bleiben ohne Root-Deploy wirkungslos; deshalb wurde bewusst nichts an den Runtime-Skripten geändert.

**Empfehlung:** Die bestehende Hermes-Cron-Kette beibehalten und nicht durch ein zusätzliches Linux-System-Crontab-Setup überlagern. Die aktuelle Multi-Job-Kette ist sauber getrennt, frei von aktiven Fehlern und bereits stabil.
