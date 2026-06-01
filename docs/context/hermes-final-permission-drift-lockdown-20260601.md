# Hermes Final Permission Drift Lockdown

**Datum:** 2026-06-01

## Ergebnis

Der Lockdown ist auf einen deterministischen Zustand gebracht:

- Git bleibt Source of Truth.
- Runtime-Skripte liegen als deployte Kopien unter `10000:10000`.
- `jobs.json` ist `640` und nicht ausfuehrbar.
- State und Logs sind `hermes:ftuser`, `2775` auf Verzeichnissen, `664` auf Mutable Files.
- `claudio` besitzt keine aktiven Runtime-Dateien.

## Geaenderte Pfade

- `/home/hermes/projects/trading/orchestrator/scripts/deploy_cron_scripts.sh`
- `/home/hermes/projects/trading/orchestrator/scripts/external_cron_guardian.sh`
- `/home/hermes/projects/trading/orchestrator/scripts/setup_permanent_permissions.sh`
- `/home/hermes/projects/trading/orchestrator/scripts/ghostbuster.py`
- `/opt/data/profiles/orchestrator/scripts/*`
- `/opt/data/profiles/orchestrator/cron/jobs.json`
- `/home/hermes/projects/trading/orchestrator/state/*`
- `/home/hermes/projects/trading/orchestrator/logs/*`

## Was sich geaendert hat

- `deploy_cron_scripts.sh` verlangt Root, prueft aktive Jobs gegen Git und Runtime und faellt bei Owner/Mode/Exec-Drift laut aus.
- Doppel-Reparaturlogik wurde in Report-Only umgewandelt.
- State- und Log-Pfade wurden auf das `ftuser`-Schreibmodell gezogen.
- Runtime-Skripte wurden auf `10000:10000` normalisiert.

## Validierungsbefehle

- `bash orchestrator/scripts/deploy_cron_scripts.sh --check`
- `bash orchestrator/scripts/deploy_cron_scripts.sh`
- `python3 -m py_compile orchestrator/scripts/drawdown_guard.py orchestrator/scripts/smart_heartbeat.py orchestrator/scripts/trading_pipeline.py orchestrator/scripts/backup_rotation.py orchestrator/scripts/portfolio_rebalancer.py orchestrator/scripts/ghostbuster.py orchestrator/scripts/fleet_api_client.py`
- `bash -n orchestrator/scripts/deploy_cron_scripts.sh orchestrator/scripts/external_cron_guardian.sh orchestrator/scripts/setup_permanent_permissions.sh orchestrator/scripts/restore_cron_jobs.sh orchestrator/scripts/guardian_loop.sh orchestrator/scripts/container_watchdog.sh orchestrator/scripts/ai_hedge_signal_heartbeat.sh orchestrator/scripts/mcp_watchdog.sh`
- `python3 orchestrator/scripts/drawdown_guard.py`
- `bash orchestrator/scripts/container_watchdog.sh`

## Verbleibende Risiken

- Externe Container oder Host-Jobs koennen Runtime-Dateien erneut ausserhalb von Git beruehren.
- `jobs.json` ist absichtlich nicht Hermes-schreibbar; Aenderungen laufen ueber den autorisierten Deploy-Pfad.
- `setup_permanent_permissions.sh` und `external_cron_guardian.sh` melden nur noch Drift; sie reparieren nichts mehr.
