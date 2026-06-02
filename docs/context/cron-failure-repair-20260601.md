# Cron-Failure Repair P0/P1 -- 2026-06-01

## Kontext

Der Full Read-Only Runtime Audit (2026-06-01 09:01 UTC) identifizierte zwei aktive Cron-Fehler:
1. **drawdown-guard** BROKEN: `ModuleNotFoundError: No module named 'fleet_api_client'`
2. **container-watchdog** WARNING: Permission-Risiko auf `container_watchdog_state.json`

Dieser Report dokumentiert die Fixes.

## P0: drawdown-guard Reparatur

### Root Cause

`drawdown_guard.py` importiert `from fleet_api_client import freqtrade_api_get` (Zeile 24, kein try/except).
Die Datei `fleet_api_client.py` existierte nur im Projekt-Dir, fehlte im Profile-Dir (`/opt/data/profiles/orchestrator/scripts/`).
Zusaetzlich hatte die Profil-Version von `drawdown_guard.py` noch die alte `hermes-agent` Referenz statt `hermes-green`.

### Fixes

| Aktion | Detail |
|---|---|
| fleet_api_client.py kopiert | Projekt -> Profile (`/opt/data/profiles/orchestrator/scripts/fleet_api_client.py`) |
| drawdown_guard.py synchronisiert | Projekt-Version (hermes-green) -> Profile-Version |
| hermes-green Referenz bestaetigt | Zeile 202: `docker inspect hermes-green` |
| Guardian-Sync-Liste erweitert | `fleet_api_client.py` zu `external_cron_guardian.sh` Zeile 134 hinzugefuegt |

### Validierung

```
fleet_api_client.py: SYNTAX OK
drawdown_guard.py: SYNTAX OK
fleet_api_client import (from profile dir): OK
hermes-agent reference check: KEINE hermes-agent Referenz mehr
hermes-green reference: Zeile 202 bestaetigt
```

## P1: container-watchdog Permission Fix

### Root Cause

`container_watchdog_state.json` hatte Ownership `hermes:hermes 664`, aber das State-Verzeichnis nutzt SGID mit GID 10000 (ftuser). Wenn der Watchdog als UID 10000 laeuft (Guardian-Container), konnte er die Datei nicht aktualisieren weil die Gruppe `hermes` war, nicht `ftuser`.

### Fix

| Vorher | Nachher |
|---|---|
| hermes:hermes 664 | hermes:ftuser 664 |

```bash
chgrp 10000 /home/hermes/projects/trading/orchestrator/state/container_watchdog_state.json
```

### Validierung

```
State file readable: OK (5 containers)
State file writable: OK
Permissions: 664
Group: ftuser (10000)
```

## Geaenderte Dateien

| Datei | Aktion |
|---|---|
| `/opt/data/profiles/orchestrator/scripts/fleet_api_client.py` | NEU (kopiert aus Projekt) |
| `/opt/data/profiles/orchestrator/scripts/drawdown_guard.py` | aktualisiert (Projekt-Version) |
| `/home/hermes/projects/trading/orchestrator/guardian/scripts/external_cron_guardian.sh` | Sync-Liste erweitert (Zeile 134) |
| `/home/hermes/projects/trading/orchestrator/state/container_watchdog_state.json` | Group ownership korrigiert |

## System-Integritaets-Check (Post-Fix)

| Check | Ergebnis |
|---|---|
| Green Mem0 Health | ok, cloud_required=false |
| Trading Bots | 4/4 running, alle dry_run=true |
| Blue Stack | Exited (Stop-only Test unverändert) |
| Guardian Timer | active (waiting) |
| Syntax alle Scripts | OK |
| fleet_api_client import (profile dir) | OK |
| container_watchdog_state.json writable | OK |
| container_watchdog.sh syntax | OK |
| external_cron_guardian.sh syntax | OK |

## Nicht geaendert (bewusst)

- Keine Trading-Bot-Restarts
- Keine dry_run-Aenderungen
- Keine Docker compose up/down/start/stop
- Keine Blue-Stack-Aenderungen
- Keine Volume/Network-Loeschungen
- Keine Equity-High/Reporting-Aenderungen (separater Task)
- `mem0_watchdog.py`, `daily_heartbeat.py`, `system_optimizer.py` nicht in Sync-Liste aufgenommen (nicht als aktive Cron-Abhaengigkeiten identifiziert)

## Naechste Schritte (nach 48h Beobachtung)

1. Pruefen ob drawdown-guard Cron-Jobs jetzt erfolgreich durchlaufen (Telegram-Output pruefen)
2. Pruefen ob container-watchdog State-Datei weiter aktualisiert wird
3. Equity-High-Bereinigung (P3)
4. Reporting-Konsistenz (P4)
5. Blue-Stack Remove-Plan nach 48h Stabilitaet
