# Phase 1: Observation System — Completion Document

**Datum:** 2026-06-02
**Status:** COMPLETE — Ready for 2-week stable-run observation period
**Author:** Hermes Meta-Orchestrator

---

## 1. Architektur-Uebersicht

Das Observation System besteht aus zwei unabhaengigen Komponenten, die ueber einen
gemeinsamen Heartbeat-Mechanismus kommunizieren.

### Runner (observation_runner.py)
- **Intervall:** Alle 5 Minuten
- **Zweck:** Erzeugt einen vollstaendigen System-Snapshot (Container, Cron-Jobs, Signal-Frische)
- **Output:** Report-Datei, Heartbeat-Datei, State-Datei, optionale Eskalations-Datei
- **Lock:** `state/locks/observation.lock` (Stale-Threshold: 10 Min)

### Watchdog (observation_watchdog.py)
- **Intervall:** Alle 10 Minuten
- **Zweck:** Prueft ob der Runner noch aktiv ist (Heartbeat-Frische)
- **Output:** Eskalations-Datei bei Stale/Missing/Corrupt Heartbeat
- **Lock:** `state/locks/watchdog.lock` (Stale-Threshold: 15 Min)

### Locking-Konzept
- Zwei unabhæangige Lock-Verzeichnisse (mkdir-basiert, kein flock)
- Jeweils mit `pid` und `timestamp` Metadaten
- Stale-Threshold: Runner 10 Min, Watchdog 15 Min
- Bei Stale-Lock: automatischer Takeover mit Issue-Eintrag
- Lock wird in `finally`-Block freigegeben

### Health-Score-Logik (deterministisch)

| Score-Komponente    | Berechnung                                                                 |
|----------------------|-----------------------------------------------------------------------------|
| Container-Score      | `max(0, 100 - unhealthy*30 - exited*40)`                                  |
| Pipeline-Score       | `max(0, 100 - failed_cronjobs*20 - stale_signal*30)`                       |
| Overall-Status      | `critical` if min(container, pipeline) <= 50                              |
|                      | `degraded` if min(container, pipeline) <= 79                               |
|                      | `healthy` otherwise                                                         |
| Eskalation           | Bei `critical` ODER Issue mit confidence >= 85                             |

### Eskalationspfad
1. Eskalations-Datei wird geschrieben nach `escalations/escalation_{cycle_id}.json`
2. Optional: Webhook POST an URL aus `HERMES_ALERT_WEBHOOK` env var
3. Keine automatischen Fixes in Phase 1 — rein report_only Modus

---

## 2. Datei-Uebersicht

| Komponente           | Pfad                                                             | Zweck                          |
|----------------------|------------------------------------------------------------------|--------------------------------|
| observation_common.py | orchestrator/scripts/observation_common.py                     | Shared Helpers (I/O, Parsing, Lock, Health-Eval) |
| observation_runner.py | orchestrator/scripts/observation_runner.py                     | 5-Minuten-Beobachtung (1007 Zeilen) |
| observation_watchdog.py | orchestrator/scripts/observation_watchdog.py                 | 10-Minuten-Heartbeat-Check (449 Zeilen) |
| expected_state.json  | /opt/data/profiles/orchestrator/config/expected_state.json    | Soll-Zustand (manuell pruefen!) |
| test_observation_common.py | orchestrator/tests/test_observation_common.py               | Tests fuer Shared Helpers        |
| test_observation_runner.py  | orchestrator/tests/test_observation_runner.py             | Tests fuer Runner                |
| test_observation_watchdog.py | orchestrator/tests/test_observation_watchdog.py           | Tests fuer Watchdog              |

---

## 3. Cron-Eintraege (Hermes Cronjob Format)

Beide Jobs laufen als Hermes Cronjobs (kein System-crontab noetig in dieser Umgebung).

**Observation Runner — alle 5 Minuten:**
```
Name:     observation-runner
Schedule: */5 * * * *
Script:   observation_runner.py
Workdir:  /home/hermes/projects/trading
Mode:     no-agent (script stdout delivered)
```

**Observation Watchdog — alle 10 Minuten:**
```
Name:     observation-watchdog
Schedule: */10 * * * *
Script:   observation_watchdog.py
Workdir:  /home/hermes/projects/trading
Mode:     no-agent (script stdout delivered)
```

Falls System-crontab verwendet werden soll (z.B. Container-Reset-Szenario):
```cron
# Observation Runner – alle 5 Minuten
*/5 * * * * /usr/bin/python3 /home/hermes/projects/trading/orchestrator/scripts/observation_runner.py >> /var/log/hermes_observation_cron.log 2>&1

# Observation Watchdog – alle 10 Minuten
*/10 * * * * /usr/bin/python3 /home/hermes/projects/trading/orchestrator/scripts/observation_watchdog.py >> /var/log/hermes_watchdog_cron.log 2>&1
```

---

## 4. Verzeichnisstruktur & Rechte

```
/opt/data/profiles/orchestrator/
  state/
    locks/                        # observation.lock + watchdog.lock
    observation_state.json         # Runner: vollstaendiger State mit History
    heartbeat_observation.json    # Runner: letzter erfolgreicher Cycle
  reports/                        # observation-runner Reports
  escalations/                    # Eskalations-Dateien (Runner + Watchdog)
  logs/
    observation.log                # Runner Log
    observation_watchdog.log       # Watchdog Log
  config/
    expected_state.json            # Soll-Zustand — HANDS OFF bis Review!
  cron/
    jobs.json                      # Cron-Registry Input

/home/hermes/projects/trading/
  orchestrator/
    scripts/
      observation_common.py       # Shared Helpers (477 Zeilen)
      observation_runner.py       # Runner (1007 Zeilen)
      observation_watchdog.py      # Watchdog (449 Zeilen)
    tests/
      test_observation_common.py
      test_observation_runner.py
      test_observation_watchdog.py
    config/
      cron_jobs_backup.json
```

---

## 5. Eskalations-Verhalten

### Runner Eskalation
- **Trigger:** `overall_status == "critical"` ODER Issue mit `confidence >= 85`
- **Ausgabe:** `escalations/escalation_{cycle_id}.json` + optionaler Webhook
- **Inhalt:** Alle detektierten Issues, Scores, State-Snapshot, Empfehlung

### Watchdog Eskalation
- **Trigger:** Heartbeat stale (>12 Min), missing, unreadable, oder eigener Lock stale
- **Ausgabe:** `escalations/watchdog_escalation_{timestamp}.json` + optionaler Webhook
- **Schwere:** Immer `critical` (Runner ist der primaere Sensor)

### Keine automatischen Fixes
Phase 1 ist rein observierend. Bei Eskalation wird der Operator informiert,
aber keine automatische Korrektur durchgefuehrt.

---

## 6. Naechste Schritte nach Phase 1

1. **2 Wochen stabile Laufzeit** ohne Fehlalarme beobachten
2. **False-Positive-Rate messen** — wie viele Eskalationen waren echte Probleme?
3. **expected_state.json validieren** — Container-Liste und Cron-Job-Liste auf aktuelle Infrastruktur abgleichen
4. **Evaluation fuer Phase 2** — kontrollierte Safe-Fixes:
   - Container-Restart bei `restarting` > 5 Min
   - Cron-Job-Restart bei 3x aufeinanderfolgenden Failures
   - Webhook-Integration aktivieren (Telegram-Alert)
5. **Phase 2 erfordert** SOUL.md / AGENTS.md Approval vor Implementierung
