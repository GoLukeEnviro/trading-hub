# Multi-User Ownership Audit

## Executive Verdict
- Kein aktiver `claudio`-Besitz an den überprüften Runtime-Dateien oder Containern gefunden.
- `claudio` ist trotzdem nicht außen vor: er ist Mitglied der `hermes`-Gruppe und der `docker`-Gruppe und kann dadurch indirekt viele Hermes-Dateien und Container beeinflussen.
- Der aktuelle Zustand ist kein Ein-Pfad-Modell, sondern ein Mehr-Writer-Modell mit drei konkurrierenden Schreibkontexten: Host-`hermes`, Container-UID `10000`, und Root-Docker-Operatoren.

## User / Group Map
- `root`: uid 0, gid 0.
- `hermes`: uid 1337, gid 1337, Gruppen `docker` und `ftuser`.
- `claudio`: uid 1000, gid 1000, Gruppen `adm`, `systemd-journal`, `docker`, `ollama`, `hermes`.
- `ftuser`: Gruppenzuordnung gid 10000, Mitglied `hermes`.
- Direktes Fazit: `claudio` kann `hermes:*`-Dateien mit Gruppenschreibrecht direkt verändern, aber nicht die `ftuser`-Gruppe direkt.

## Claudio Involvement Verdict
- Nicht Eigentümer der aktiven Runtime-Pfade.
- Nicht Benutzer der laufenden Container laut `docker inspect`.
- Indirekt beteiligt durch `docker`-Gruppenmitgliedschaft und durch Schreibzugriff auf `hermes:hermes`-Dateien.
- Für den Runtime-Contract sollte `claudio` aus den produktiven Schreibpfaden ausgeschlossen bleiben.

## Runtime Writer Map
- `hermes-green`: `user=root`, RW auf `/home/hermes/projects` und `/opt/hermes-green/config`.
- `trading-guardian`: schreibt RW auf `/opt/data/profiles/orchestrator/cron`, `/opt/data/profiles/orchestrator/scripts`, `/home/hermes/projects/trading`.
- `ai-hedge-fund-crypto`: schreibt RW auf `/home/hermes/projects/trading/ai-hedge-fund-crypto/output`.
- `freqtrade-regime-hybrid`, `freqtrade-freqforge`, `freqtrade-freqforge-canary`: schreiben RW auf `/home/hermes/projects/trading/freqtrade/shared`, `/home/hermes/projects/trading/freqtrade/logs`, plus ihre jeweiligen `user_data`-Binds.
- `freqtrade-webserver`: schreibt RW in Docker-Volume plus bind-mounts unter `/var/lib/docker/volumes/a0-v2-usr/_data/projects/agenten_auto_trade/...`.
- `freqai-rebel`: schreibt RW in Docker-Volume `freqai-rebel-data`.
- Kein Container mit `claudio` als `.Config.User` gefunden.

## Repair Loop Findings
- `guardian/scripts/external_cron_guardian.sh` ist der aktive Repair-Loop im `trading-guardian`-Container; er wird per `guardian/scripts/guardian_loop.sh` und `guardian/Dockerfile` gebootstrapped.
- Dort gibt es echte Repair-Aktivität für `jobs.json`, fehlende Skripte, Container-Start, und `PERMISSION_GUARD_MODE=repair` für explizite Pfade.
- `scripts/external_cron_guardian.sh` im Projektbaum ist eine andere, ältere Host-Variante mit deaktiviertem Permission-Drift-Loop; funktional überschneidend, aber nicht der Container-Entrypoint.
- `scripts/setup_permanent_permissions.sh` repariert `chgrp/chmod` für State-/Log-/Cron-Pfade, ist aber in der Repo-Suche nicht als aktiver Runner referenziert und wirkt damit wie ein toter oder vergessener Helper.
- `scripts/deploy_cron_scripts.sh` deployt aktive Cron-Skripte per `cp` und versucht danach `chown/chmod`.
- `scripts/ghostbuster.py` repariert Log-Datei- und Log-Verzeichnis-Berechtigungen per `os.chown/os.chmod`.
- `scripts/restore_cron_jobs.sh` stellt `jobs.json` aus Backup wieder her, aber ohne Ownership-Normalisierung.
- `scripts/fleet_auto_repair.py` ist advisory-only; es schreibt keine Ownership-Reparaturen.

### Klassifizierung
- `guardian/scripts/external_cron_guardian.sh`: REQUIRED, aber DUPLICATE in Bezug auf andere Permission-Helper; DANGEROUS nur wegen breiter Schreibfähigkeit.
- `scripts/deploy_cron_scripts.sh`: REQUIRED für Deployment, aber DANGEROUS bei stillen `chown/chmod`-Fehlern.
- `scripts/setup_permanent_permissions.sh`: OBSOLETE/UNKNOWN, weil nirgends als aktiver Pfad referenziert.
- `scripts/external_cron_guardian.sh`: OBSOLETE/UNKNOWN bzw. Legacy-Duplicate.
- `scripts/ghostbuster.py`: REQUIRED für Logs, aber DUPLICATE zu anderen Log-Fixern.
- `scripts/restore_cron_jobs.sh`: REQUIRED für Restore, kein Permission-Repair.

## Current Ownership Mismatches
- `/home/hermes/projects/trading/orchestrator/scripts`: 85 Einträge `hermes:hermes`, 1 `root:root`-Ausreißer.
- `/opt/data/profiles/orchestrator/scripts`: 7 Einträge `hermes:hermes`, 6 Einträge `root:ftuser`.
- `/home/hermes/projects/trading/orchestrator/state`: 846 `hermes:hermes`, 12 `10000:ftuser`, 5 `root:hermes`, 1 `root:ftuser`, 1 `hermes:ftuser`.
- `/home/hermes/projects/trading/orchestrator/logs`: 16 `hermes:hermes`, 13 `hermes:ftuser`, 7 `10000:ftuser`.
- `/opt/data/profiles/orchestrator/cron/jobs.json`: `root:ftuser` mit Mode `775`.
- Auffällige Einzelpfade: `state/riskguard/*` ist `root:ftuser`/`10000:ftuser`; `logs/*.log` sind gemischt `hermes:hermes` und `hermes:ftuser`.

## Recommended Final Ownership Contract
- Source scripts: `/home/hermes/projects/trading/orchestrator/scripts/*` -> `hermes:hermes`, Mode `775`.
- Runtime cron scripts: `/opt/data/profiles/orchestrator/scripts/*` -> einheitlich `10000:10000`, Mode `755`.
- Cron database: `/opt/data/profiles/orchestrator/cron/jobs.json` -> `10000:10000`, Mode `600` oder höchstens `640`, niemals executable.
- Mutable runtime state/logs: `/home/hermes/projects/trading/orchestrator/state/**` und `/home/hermes/projects/trading/orchestrator/logs/**` -> Gruppe `ftuser`, Verzeichnisse `2775`, Dateien `664`; Owner nach Möglichkeit konsolidiert auf den jeweiligen Writer, aber ohne `root:root`-Persistenz.
- Container writers: nur die explizit gemounteten Writer-Container dürfen diese Pfade anpassen; kein zweiter Host-Repair-Loop mit breiterem Scope.
- Claudio: aus dem produktiven Runtime-Write-Set ausgeschlossen; nur indirekte Beteiligung über `hermes`-Gruppenrechte und Docker-Zugriff.

## Safe Execution Plan
- Den aktuellen Zustand nicht anfassen, solange die Writer-Landschaft nicht konsolidiert ist.
- Einen einzigen autoritativen Writer pro Pfad festlegen: `deploy_cron_scripts` für Runtime-Skripte, `trading-guardian` für `jobs.json` und Recovery, `setup_permanent_permissions` entweder deaktivieren oder eindeutig in denselben Contract einhängen.
- Danach nur noch read-only Validierung: Ownership-Zähler, `docker inspect`-Mounts, Drift-Check auf `jobs.json`, und ein Diff zwischen Source- und Runtime-Skripten.
- Erst wenn die Contract-Regeln eindeutig sind, die veralteten Reparaturpfade entfernen oder deaktivieren.
