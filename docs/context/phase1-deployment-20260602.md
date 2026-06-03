# Phase 1 Deployment — Observation Runner & Watchdog

**Datum:** 2026-06-02
**Modus:** STRICT EXECUTION (no_agent, deliver=local)

## Cronjobs angelegt

| Job | job_id | Schedule | Script | Workdir |
|-----|--------|----------|--------|---------|
| observation-runner | 7dc5d0e284db | */5 * * * * | observation_runner.py | /home/hermes/projects/trading |
| observation-watchdog | cddc161b55be | */10 * * * * | observation_watchdog.py | /home/hermes/projects/trading |

## Deployed Scripts (Runtime)

| Script | Quellpfad | Zielpfad | Rechte |
|--------|-----------|----------|--------|
| observation_runner.py | orchestrator/scripts/ | /opt/data/profiles/orchestrator/scripts/ | 10000:10000 755 |
| observation_watchdog.py | orchestrator/scripts/ | /opt/data/profiles/orchestrator/scripts/ | 10000:10000 755 |
| observation_common.py | orchestrator/scripts/ | /opt/data/profiles/orchestrator/scripts/ | 10000:10000 755 |

## Verzeichnisse erstellt

- /opt/data/profiles/orchestrator/state/locks/
- /opt/data/profiles/orchestrator/reports/
- /opt/data/profiles/orchestrator/escalations/
- /opt/data/profiles/orchestrator/logs/ (war bereits vorhanden)

## Webhook-Status

HERMES_ALERT_WEBHOOK: nicht gesetzt.

## Smoke-Test Ergebnis

### observation_runner.py
- Exitcode: 0
- Report: report_20260602-190033.json (11831 bytes) unter /reports/
- Heartbeat: heartbeat_observation.json aktualisiert
- Lock-Datei: korrekt entfernt nach Lauf

### observation_watchdog.py
- Exitcode: 0
- Escalation: escalation_20260602-190033.json (1518 bytes) unter /escalations/
- Log: observation_watchdog.log (186 bytes) unter /logs/
- Lock-Datei: korrekt entfernt nach Lauf

## Jobs deaktivieren / pausieren

```bash
# Pausieren (wieder aktivierbar)
cronjob(action='pause', job_id='7dc5d0e284db')   # runner
cronjob(action='pause', job_id='cddc161b55be')   # watchdog

# Entfernen (permanent)
cronjob(action='remove', job_id='7dc5d0e284db')   # runner
cronjob(action='remove', job_id='cddc161b55be')   # watchdog
```

## Nächste Schritte

1. 2-Wochen-Beobachtung: beide Jobs laufen autonom, Logs unter /opt/data/profiles/orchestrator/logs/
2. Bei Eskalationen: Prüfe /opt/data/profiles/orchestrator/escalations/
3. expected_state.json manuell durch User reviewen (bleibt read-only)
4. HERMES_ALERT_WEBHOOK konfigurieren für Telegram-Eskalationen (optional)
