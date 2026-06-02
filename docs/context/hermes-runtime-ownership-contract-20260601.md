# Hermes Runtime Ownership Contract

**Datum:** 2026-06-01
**Status:** ACTIVE

## Canonical Sources

- Git ist die einzige Quelle fuer Runtime-Skripte.
- Runtime-Kopien duerfen nur via `orchestrator/scripts/deploy_cron_scripts.sh` aktualisiert werden.
- `jobs.json` ist Laufzeitzustand, kein Git-Artefakt.

## Validierte Eigentumsmodelle

### Source Tree

- Pfad: `/home/hermes/projects/trading/orchestrator/scripts`
- Owner: `hermes:hermes`
- Verzeichnisse: `2775`
- Ausfuehrbare Skripte: `775`

### Runtime Scripts

- Pfad: `/opt/data/profiles/orchestrator/scripts`
- Owner: `10000:10000`
- Verzeichnisse: `755`
- Aktive Skripte: `755`
- Nicht-Skripte/Helper: `644`
- Keine manuelle Bearbeitung.

### jobs.json

- Pfad: `/opt/data/profiles/orchestrator/cron/jobs.json`
- Owner: `10000:10000`
- Mode: `640`
- Nicht ausfuehrbar.
- Hermes kann lesen, aber nicht direkt schreiben.

### State und Logs

- Pfade: `/home/hermes/projects/trading/orchestrator/state`, `/home/hermes/projects/trading/orchestrator/logs`
- Owner/Group: `hermes:ftuser`
- Verzeichnisse: `2775`
- Mutable Files: `664`

## Autorisierter Repair-Pfad

- Einziger autorisierter Reparaturpfad fuer Runtime-Skripte: `deploy_cron_scripts.sh`
- `setup_permanent_permissions.sh`, `external_cron_guardian.sh` und `ghostbuster.py` sind report-only.
- `permission_autopilot.sh` ist Host-only, selektiv und nur fuer explizite Daten-/Log-Mounts gedacht.
- `permission_autopilot_alert.py` ist Host-only, CRITICAL-only und sendet keine Fixes.
- `permission_autopilot.sh` ersetzt nicht `deploy_cron_scripts.sh` und repariert keine `jobs.json`-Pfadangaben.
- Cron soll nur `permission_autopilot.sh --summary` ausfuehren; `--apply` bleibt manuell und root-only.
- Cron soll `permission_autopilot_alert.py` nur versetzt und ohne root ausfuehren.
- Keine Broad-`find`-Repair-Loops fuer Ownership oder Mode.

## Validierung

- `bash orchestrator/scripts/deploy_cron_scripts.sh --check`
- `bash orchestrator/scripts/deploy_cron_scripts.sh`
- `python3 -m py_compile orchestrator/scripts/*.py` fuer die betroffenen Jobs
- `bash -n orchestrator/scripts/*.sh` fuer die betroffenen Shell-Jobs

## Rest-Risiken

- Externe Prozesse koennen Runtime-Kopien erneut driftet lassen, wenn sie ausserhalb von Git schreiben.
- `jobs.json` ist absichtlich nicht Hermes-schreibbar; Statusaenderungen muessen ueber den autorisierten Runtime-Pfad erfolgen.
- State/Log-Dateien bleiben schreibbar fuer die reale Writer-Group `ftuser`.
