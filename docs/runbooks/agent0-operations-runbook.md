# Agent0 Operations Runbook — Dry-Run-Fleet, SI-v2, Scheduler, Backup

**Stand:** 2026-09-16 · **Basis:** `origin/main` @ `0d83a28`
**Gilt für:** den Zielhost `Agent0` (`agent0-1`, Hetzner instance-id `125365346`)
**Issue:** #730 (Phase 6)

> Dieses Runbook beschreibt die **vorgesehenen** Abläufe. Es ist keine Behauptung, dass
> sie auf Agent0 bereits ausgeführt wurden. Der aktuelle Umsetzungsstand steht in
> `docs/state/current-operational-state.md` und im #730-Kommentarverlauf.

Alle Pfade sind die bindenden Verträge aus `AGENTS.md` und `orchestrator/scripts/repo_writer.py`.

## 1. Statusprüfung (read-only, in dieser Reihenfolge)

```bash
# 1.1 Fleet — muss genau 5 Container zeigen, alle "Up (healthy)", RestartCount 0
docker compose -f /workspace/projects/trading-hub/docker-compose.hermestrader-dryrun.yml \
  -p hermestrader-dryrun ps

# 1.2 Bild-Provenienz gegen den Lock (fail-closed)
docker image inspect hermestrader/freqtrade-r5a:r7a-5bcb50fc8186-7ca1e4f9b150 --format '{{.Id}}'
#   soll: sha256:aa4ab78532d996b0d3ac7b034819918e2085495dd1368399705b208d331bd380
docker image inspect hermestrader/rainbow-r5a:6e850c8f8ba1-faa2e3d8c351 --format '{{.Id}}'
#   soll: sha256:7e2fab4a87790a1aadebed29b2688ec4c45a80ed9763e69f0d3d285093cc5db0

# 1.3 Automatisierte Fleet-Prüfung (read-only)
python3 /workspace/projects/trading-hub/hermes_root/r5a_recovery.py verify-only

# 1.4 Dry-Run-Invariante (je Bot; darf NIE false sein)
for p in 8086 8081 8085 8180; do
  docker exec $(docker ps -qf "publish=$p") \
    sh -c 'grep -o "\"dry_run\": *[a-z]*" /freqtrade/user_data/config.example.json'
done

# 1.5 SI-v2-Lesezyklus (read-only; erwartet total_bots=3, mutations 0)
cd /workspace/projects/trading-hub/self_improvement_v2
PYTHONPATH=src /workspace/projects/trading-hub/.venv/bin/python \
  src/si_v2/loop/active_cycle_runner.py

# 1.6 Kill switch — effektiver Modus (fail-closed bei fehlender Datei)
PYTHONPATH=/workspace/projects/trading-hub/freqtrade/shared \
  python3 -c "import kill_switch as k; print('mode =', k.get_kill_mode())"
```

**Erwartete Werte bei grünem Betrieb:** 5 Container healthy · beide Image-IDs == Lock ·
`verify-only` PASS · alle `dry_run: true` · `total_bots=3`, `ping_ok_count=3`,
alle Mutations 0 · `mode = NORMAL`.

## 2. Logs

```bash
# Container-Logs (json-file, max-size 10m, max-file 3 — Rotation ist im Compose gesetzt)
docker compose -f .../docker-compose.hermestrader-dryrun.yml -p hermestrader-dryrun logs -f <service>

# Bot-Logdatei im Volume
docker exec <container> tail -f /freqtrade/user_data/logs/freqtrade.log

# SI-v2-Zyklus
ls -t /workspace/projects/trading-hub/self_improvement_v2/reports/phase2/evidence/ | head
cat /workspace/projects/trading-hub/self_improvement_v2/reports/phase2/active_cycle_runner_report.md

# Executor-Audit (append-only; nie rotieren oder löschen)
tail -f /opt/data/hermes/audit/runtime-actions.jsonl
```

**Logrotation:** Container über die Compose-Logging-Optionen; keine Host-`logrotate`-Regel
nötig. Speichergrenzen sind pro Dienst gesetzt (`mem_limit` aus der Soll-Liste).

## 3. Stop / Start

```bash
# Über den vorgesehenen privilegierten Pfad (Executor), NICHT direkt:
#   Aktion r5a_compose_stop / r5a_compose_start_existing über hermes-root-executor

# Einzelnen Dienst stoppen (nie "down -v" — das würde Volumes entfernen)
docker compose -f .../docker-compose.hermestrader-dryrun.yml -p hermestrader-dryrun stop <service>

# Start BESTEHENDER Container (verifiziert die exakte Fleet und startet nur neu)
python3 /usr/local/sbin/hermes_root/r5a_recovery.py start-existing <service>
```

**Verboten ohne explizite Freigabe:** `down -v`, `docker volume prune`, `docker system prune`,
Container-`rm` mit Volumes. Diese entfernen Dry-Run-Datenbanken.

## 4. Gezielter Wiederanlauf-Test (ohne Datenverlust)

```bash
# 4.1 Vorher: DB-Integrität + Zeilenzahl festhalten
docker exec <container> python3 -c "
import sqlite3; c=sqlite3.connect('/freqtrade/user_data/tradesv3.dryrun.sqlite')
print('integrity:', c.execute('PRAGMA integrity_check').fetchone()[0])
print('trades:', c.execute('SELECT COUNT(*) FROM trades').fetchone()[0])"

# 4.2 Einen Dienst neu starten
docker compose ... restart freqtrade-freqforge

# 4.3 Nachher: gleiche Werte erwartet; trades >= vorher (nie kleiner)
#     plus: Up (healthy), RestartCount 1, Logs zeigen Marktdaten-Ladung, kein Crash-Loop
```

Ein Wiederanlauf gilt nur als belegt, wenn **vorher/nachher** dieselbe Integrität und
eine nicht gesunkene Trade-Zahl gemessen wurden und der Dienst danach healthy ist.

## 5. Backup

```bash
# Vorgesehene Skripte (Repository)
ops/hermes/hermestrader-backup.sh              # Host-Backup inkl. Writer-Lock-Bewusstsein
ops/hermes/hermestrader_sqlite_snapshot.py     # konsistente SQLite-Snapshots (kein rohes cp!)
```

**Regel für laufende Datenbanken:** eine aktive SQLite-Datei wird **nicht** unkoordiniert
kopiert. Der Snapshot-Helfer nutzt die SQLite-Snapshot-API, damit WAL-Zustände konsistent
sind. Rohes `cp` einer Datei im WAL-Modus kann eine unbrauchbare Kopie erzeugen.

Auf dem Quellhost existiert zusätzlich ein Restic→Backblaze-B2-Lauf (Timer, täglich).
Auf Agent0 ist ein solcher Lauf **noch nicht** eingerichtet — das ist ein eigener Schritt.

## 6. Restore-Test (isoliert, nie über Produktion)

```bash
ops/hermes/hermestrader_backup_restore_proof.py    # isolierter Restore + Verifikation
```

Der Restore wird **in ein separates Zielverzeichnis** entpackt und dort geprüft
(Dateizahl, Checksummen, `PRAGMA integrity_check`). Erst wenn der isolierte Restore
vollständig grün ist, gilt ein Backup als brauchbar. Ein Backup ohne durchgeführten
Restore-Test zählt nicht als Nachweis.

## 7. Rollback

| Situation | Rollback |
|---|---|
| Falsche Config/Overlay aktiv | Overlay-Datei entfernen, Dienst über `r5a_compose_start_existing` neu starten |
| Bild-Drift | Lock-ID prüfen; bei Abweichung deployt `verify-only` nicht — Zustand einfrieren und eskalieren |
| SI-v2-Apply schlug fehl | Der Apply-Pfad hat einen eigenen Rollback (`apply_actuator`); Ausführung nur über den dokumentierten Kettenpfad |
| Fleet komplett defekt | `docker compose ... stop`, dann `start-existing` mit verifizierter Fleet; Volumes bleiben unangetastet |
| Host-Namespace beschädigt | Rückweg in `docs/reports/agent0-host-state-revalidation-2026-09-16.md` §4.4 |

**Kill switch:** Ein bestehender `HALT_NEW`/`EMERGENCY`-Zustand wird **nicht** gelöscht, um
einen grünen Status zu erhalten. Fehlende Kill-Switch-Konfiguration wird über das
vorgesehene Initialisierungsverfahren hergestellt, nicht durch Setzen von `NORMAL`.

## 8. Runtime-Konfiguration und Secrets (Agent0)

Die vier Freqtrade-Dienste lesen ihre Konfiguration über interpolierte Mount-Quellen (`${VAR:-<getracktes Beispiel>}`). Default bleibt das getrackte, sanitized `config.example.json` (HermesTrader-Verhalten unverändert).

Für Agent0 werden in der **gitignorierten** `.env` im Projektverzeichnis folgende Variablen gesetzt, die auf untracked `user_data/config.json`-Dateien mit host-lokalen Runtime-Secrets zeigen (Mount-Ziel und `:ro` bleiben identisch):

| Variable | Default (getrackt) | Agent0-Ziel |
|---|---|---|
| `FREQFORGE_CONFIG_FILE` | `./freqforge/user_data/config.example.json` | `./freqforge/user_data/config.json` |
| `FREQFORGE_CANARY_CONFIG_FILE` | `./freqforge-canary/user_data/config.example.json` | `./freqforge-canary/user_data/config.json` |
| `REGIME_HYBRID_CONFIG_FILE` | `./freqtrade/bots/regime-hybrid/user_data/config.example.json` | `./freqtrade/bots/regime-hybrid/user_data/config.json` |
| `WEBSERVER_CONFIG_FILE` | `./freqtrade/bots/webserver/user_data/config.example.json` | `./freqtrade/bots/webserver/user_data/config.json` |

Keine Secret-Werte dürfen in Compose, Git, Tests oder Reports erscheinen. Die SI-v2-Secrets bleiben in `/opt/data/secrets/si-v2-freqtrade.env` (außerhalb des Repositorys, 0600).

Der SI-v2-Wrapper löst das Repository über `SI_V2_REPO_ROOT` auf (Default bleibt der HermesTrader-Pfad); auf Agent0 wird der Wert explizit auf das kanonische Checkout gesetzt. Fehlt das Verzeichnis, bricht der Wrapper explizit ab — kein stiller Fallback.

## 9. Scheduler — genau einer, mit Überlappungsschutz

Vorgesehen ist **genau ein** Scheduler: der SI-v2-Active-Cycle-Job
(`orchestrator/scripts/si_v2_active_cycle_cron.sh`, 6h-Takt).

Regeln:
- Kein zweiter, konkurrierender Cron-Eintrag für denselben Zweck.
- Keine doppelte Steuerung durch alte und neue Jobs oder laufende Agent-Sitzungen.
- Der Job besitzt Überlappungsschutz (Lock + Cleanup-Trap im Wrapper).
- Ein Scheduler-Test muss einen **tatsächlichen automatischen Lauf** belegen
  (Heartbeat + Logzeile + neue Cycle-ID), nicht nur die Registrierung.

Prüfung:

```bash
hermes cron status          # Ticker-Heartbeat muss frisch sein
hermes cron list            # genau ein Job, kein Duplikat
```

## 10. Doppelbetriebsschutz (Quellhost ↔ Zielhost)

Solange derselbe Bot-Role auf beiden Hosts laufen könnte, ist das ein **Datenrisiko**
(zwei Dry-Run-DBs divergieren; Messdaten sind nicht mehr eindeutig zuordenbar).

Vor jeder Zielaktivierung klären:
1. Läuft dieselbe Rolle auf dem Quellhost noch? (Inventar)
2. Wenn ja: **vor** Zielstart Rollen trennen — Scheduler und Steuerung nur auf einem Host.
3. Ein Stop auf dem Quellhost wird **zuvor konkret mit Rückweg vorgelegt**, nie pauschal.

## 11. Was dieses Runbook nicht autorisiert

Kein Live-Trading, kein `dry_run=false`, keine Exchange-Keys, keine Risikolimit-Erhöhung,
kein Kill-Switch-Bypass, kein Löschen oder Abschalten des Quellhosts. Der privilegierte
Pfad ist der Executor — `sudo`/`docker`-Gruppenrechte sind **keine** Freigabe, ihn zu umgehen.

## 10. Apply-Kette (AUTONOMOUS_DRY_RUN, aktiviert 2026-09-18)

Der Modus `AUTONOMOUS_DRY_RUN` ist auf Agent0 aktiviert
(Marker: `docs/decisions/APPROVED_AUTONOMOUS_DRY_RUN_AGENT0.md`). Er bleibt
strikt Dry-Run, canary-first und fail-closed.

### 10.1 Ablauf je Zyklus (automatisch)

1. Der SI-v2-Active-Cycle-Job läuft (6h-Takt, `.active-cycle.lock`).
2. Danach läuft die Apply-Ketten-Auswertung (`.apply-chain.lock`, eigener
   Overlap-Schutz) über den Evaluator:
   `self_improvement_v2/scripts/si_v2_apply_chain_evaluator.py`.
3. Der Evaluator liest ausschließlich echte Evidenz: Marker, Kill-Switch,
   RiskGuard-State, neuestes Cycle-Bundle, Canary-Config. Fehlt oder
   korrumpiert etwas, blockiert er fail-closed (Status `BLOCKED_*`).
4. Ein Kandidat für einen anderen Bot als `freqtrade-freqforge-canary`
   ergibt `NO_QUALIFIED_PROPOSAL` (Stage 1 ist canary-only).
5. Ein qualifizierter Canary-Kandidat wird vollständig vorbereitet
   (Overlay, Rollback-Plan, Audit-Event, Messplan) und die
   Ceremony-Preflight läuft. Die **Runtime-Ausführung** (Canary-Recreate)
   ist in dieser Stage bewusst nicht verdrahtet; der Datensatz vermerkt
   `runtime_execution_wired=false`.

### 10.2 Status und Evidenz

```bash
# Letzte Auswertung (atomarer Record)
ls -t /opt/data/logs/si-v2-apply-chain/state/results/ | head -3
cat "$(ls -t /opt/data/logs/si-v2-apply-chain/state/results/*.json | head -1)"

# Append-only Audit
tail -5 /opt/data/logs/si-v2-apply-chain/state/audit/apply_chain_audit.jsonl
```

Statuswerte: `NO_QUALIFIED_PROPOSAL` (korrektes Nicht-Anwenden),
`APPLY_PREPARED_RUNTIME_STAGE_NOT_WIRED` (vorbereitet, bewusst kein
Runtime-Schritt), `BLOCKED_*` (fail-closed — Ursache im `reason`).

### 10.3 Alarmierung

Der Scheduler meldet an Telegram nur bei Problemen: `BLOCKED_*`,
`APPLY_PREPARED_*` sowie alle Watchdog-Verletzungen (`SI-V2 APPLY-CHAIN
ALERT` / `SI-v2 WATCHDOG ALERT`). `NO_QUALIFIED_PROPOSAL` ist still.

### 10.4 Watchdog (Fleet, RiskGuard, Kill-Switch, Speicher, Zyklusfrische)

Eigener stündlicher Alert-Job (`si-v2-watchdog-agent0`, rein meldend, kein
Zyklus-Scheduler). Geprüft werden: 5/5 Container healthy, Kill-Switch
`NORMAL`, RiskGuard `PASS`, freier Speicher ≥ 512 MB, Zyklusfrische < 13 h.
Der Watchdog repariert nichts — er meldet nur.

### 10.5 Grenzen

- Kein Live-Trading, kein `dry_run=false`, keine Exchange-Keys.
- Kein Kandidat wird erzeugt, keine Schwelle gesenkt: Angewendet wird nur,
  was als echter ShadowProposal-Kandidat im Cycle-Bundle steht.
- Ein Runtime-Apply bleibt gesperrt, bis die R7A-Topologie der Kette
  verifiziert verdrahtet ist (separater, belegter Schritt).
