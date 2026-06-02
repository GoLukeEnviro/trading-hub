# Hermes Cron Scheduler Permission Recovery 2026-06-02

## Root Cause
Beim Delete+Recreate des Cronjobs wurden `jobs.json` und `config.yaml` als `root:root 0600` zurückgeschrieben. `hermes-green` konnte dadurch weder die Jobliste noch die Orchestrator-Konfiguration lesen.

Zusätzlich blockierten zwei vom Heartbeat beschriebene Logfiles den echten Lauf:
- `/home/hermes/projects/trading/orchestrator/logs/unified_heartbeat.log`
- `/home/hermes/projects/trading/orchestrator/logs/trigger_lock.log`

## Exakte Reparaturen
- `chmod 0644 /opt/hermes-green/config/profiles/orchestrator/cron/jobs.json`
- `chmod 0644 /opt/hermes-green/config/profiles/orchestrator/config.yaml`
- `chown 10000:10000 /home/hermes/projects/trading/orchestrator/logs/unified_heartbeat.log`
- `chown 10000:10000 /home/hermes/projects/trading/orchestrator/logs/trigger_lock.log`

## Before/After Stat
Vorher:
- `jobs.json`: `root:root 0600`
- `config.yaml`: `root:root 0600`
- `unified_heartbeat.log`: `root:ftuser 0644`
- `trigger_lock.log`: `root:ftuser 0644`

Nachher:
- `jobs.json`: `root:root 0644`
- `config.yaml`: `root:root 0644`
- `unified_heartbeat.log`: `10000:10000 0644`
- `trigger_lock.log`: `10000:10000 0644`

## Hermes-Green Readability Proof
Im Container `hermes-green` als Runtime-User `10000:10000` geprüft:
- `jobs.json` lesbar: `True`
- `config.yaml` lesbar: `True`
- `jobs.json` JSON-valid
- Job-Übersicht: 38 Jobs, 35 enabled
- `unified-signal-heartbeat` vorhanden: `True`
- `signal-heartbeat` pausiert: `True`
- `smart-heartbeat` pausiert: `True`

## Scheduler Recovery Evidence
Der Scheduler hat nach der Reparatur wieder real getickt.

Beobachtete Job-Zustände von `unified-signal-heartbeat`:
- Vor dem Tick-Fix: `last_run_at=None`, `last_status=None`
- Nach Leserechte-Fix: `last_run_at=2026-06-02T00:15:20.976099+00:00`, `last_status=error`
- Nach Logfile-Fix: `last_run_at=2026-06-02T00:45:54.893196+00:00`, `last_status=ok`
- `next_run_at` sprang auf `2026-06-02T01:00:00+00:00`

## Unified-Signal-Heartbeat Tick Evidence
- `job_id`: `dcf21bfa3ab3`
- `enabled`: `True`
- `state`: `scheduled`
- `last_run_at`: `2026-06-02T00:45:54.893196+00:00`
- `last_status`: `ok`
- `last_error`: `None`

## Signal Orchestration Status
- `signal-heartbeat` bleibt pausiert
- `smart-heartbeat` bleibt pausiert
- `unified-signal-heartbeat` läuft über den zentralen Lockpfad
- `trigger_lock.log` zeigt nach dem Fix wieder erfolgreiche Ausführung ohne Schreibfehler

## Trading Safety
Verifiziert, ohne Container-Neustarts oder Strategie-/Config-Änderungen:
- `freqtrade-regime-hybrid`: läuft, `dry_run=True`
- `freqtrade-freqforge-canary`: läuft, `dry_run=True`
- `freqtrade-freqforge`: läuft, `dry_run=True`
- `freqai-rebel`: läuft, `dry_run=True`
- `ai-hedge-fund-crypto`: healthy

## Guardrail Against Recurrence
Operative Regel:
- Nach jedem `cronjob remove/create` sofort `stat` auf `jobs.json` und `config.yaml` prüfen.
- `hermes-green` muss beide Dateien als Runtime-User lesen können, bevor Scheduler-Ticks als gesund gelten.

Pragmatische Folgemaßnahme:
- Ein read-only Health-Check sollte bei `Permission denied` auf `jobs.json` oder `config.yaml` sofort hart fehlschlagen und den Deploy-/Cron-Workflow abbrechen.

## Remaining Issues
- In den Logs tauchen noch Warnungen zu `auth.json` auf. Das blockiert den Scheduler-Tick nicht, ist aber ein separates Permission-Thema.
