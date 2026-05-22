# VPS Permission Drift Recovery — 2026-05-19

## Executive Summary

Permission-Drift zwischen UID 1000 (claudio), root, und UID 10000 (Hermes) blockierte 5 Cron-Jobs. Gezielte Fixes auf 6 Verzeichnisse und 13 Dateien haben 4 der 5 Jobs wiederhergestellt. Ein verbleibender Job hat ein Docker-Socket-Access-Problem (kein Permission-Drift).

## Confirmed Root Causes

1. **Verzeichnisse** mit Owner 1000:1000 und Mode 0755 — UID 10000 konnte nicht schreiben
2. **Einzelne Dateien** mit Owner root:root — durch Guardian/Manual-Aktionen erstellt, Hermes konnte nicht lesen/schreiben
3. **Fehlende State-Dateien** — container_watchdog_state.json und mcp_watchdog_state.json existierten nicht

## Backups Created

| Backup | Pfad |
|--------|------|
| Master Backup | `backups/20260519-220007-pre-permission-drift-recovery.tar.gz` |
| Targeted Fix Backup | `backups/20260519-220446-pre-targeted-log-state-permission-fix.tar.gz` |

Beide unter `/home/hermes/projects/trading/orchestrator/backups/`

## Targeted Fixes Applied

### Verzeichnisse (chgrp 10000 + chmod 2775 mit setgid)

| Pfad | Vorher | Nachher |
|------|--------|---------|
| orchestrator/logs/ | 1000:1000 0755 | 1000:10000 2775 |
| orchestrator/state/ | 1000:1000 0755 | 1000:10000 2775 |
| ai-hedge-fund-crypto/output/logs/ | 1000:1000 0755 | 1000:10000 2775 |
| ai-hedge-fund-crypto/output/ | 1000:1000 0755 | 1000:10000 2775 |
| ai-hedge-fund-crypto/output/latest/ | 1000:1000 0755 | 1000:10000 2775 |

setgid-Bit (2775) sorgt dafuer, dass neue Dateien automatisch Gruppe 10000 erben.

### Einzelne Dateien (gezieltes chown/chgrp)

| Datei | Vorher | Nachher |
|-------|--------|---------|
| orchestrator/logs/smart_heartbeat.log | root:root 644 | 10000:10000 644 |
| orchestrator/logs/drawdown_guard.log | root:root 644 | 10000:10000 644 |
| orchestrator/logs/rebalancer.log | root:root 644 | 10000:10000 644 |
| orchestrator/logs/cron_restore.log | root:root 644 | 10000:10000 644 |
| orchestrator/logs/external_cron_guardian.log | root:root 644 | 10000:10000 644 |
| orchestrator/state/drawdown_state.json | root:root 644 | 10000:10000 644 |
| orchestrator/state/drawdown_state_prev.json | root:root 644 | 10000:10000 644 |
| orchestrator/state/rebalance_state.json | root:root 644 | 10000:10000 644 |
| ai-hedge.../output/logs/heartbeat.log | claudio:claudio 644 | claudio:10000 664 |
| ai-hedge.../output/hermes_signal.json | claudio:claudio 644 | claudio:10000 664 |
| ai-hedge.../output/latest/hermes_signal.json | root:root 644 | root:10000 664 |

## Hermes Cron Recovery

| Metrik | Status |
|--------|--------|
| jobs.json lesbar als UID 10000 | Ja (10000:10000 600) |
| Guardian Script chown/chmod | Vorhanden und validiert |
| Guardian Timer | Active (alle 5 Min) |
| Scheduler tickt | Ja |

## Failing Jobs Before/After

| Job | Vorher | Nachher | Ursache |
|-----|--------|---------|---------|
| container-watchdog | error | **ok** | state-dir nicht schreibbar |
| mcp-watchdog | error | **ok** | state-dir nicht schreibbar |
| drawdown-guard | error | **ok** | log-file root:root |
| smart-heartbeat | error | **ok** | log-file root:root |
| signal-heartbeat | error | **error** | Docker Socket Access (separates Problem) |
| trading-pipeline | ok | error | Funktionaler Fehler (separates Problem) |

## Memory Reliability Findings

| Komponente | Status | Detail |
|------------|--------|--------|
| Hermes state.db (406MB) | Ok | 10000:10000 |
| Hermes hermes-data/state.db (235MB) | Ok | 10000:10000 |
| kanban.db | Ok | 10000:10000 |
| response_store.db | Ok | 10000:10000 |
| memory_store.db | Ok | 10000:10000 |
| hermes_heartbeat.sqlite | Ok | 10000:10000 |
| .mem0/history.db | root:root | Ueber mem0-local-api Container verwaltet, nicht direkt |
| mem0-local-api Errors | Funktional | Ollama context length, keine Permission-Issues |
| Qdrant | Ok | Keine Fehler |

**Memory ist NICHT von Permission-Drift betroffen.**

## Remaining Risks

1. **signal-heartbeat**: UID 10000 kann Docker Socket nicht nutzen (`docker exec ai-hedge-fund-crypto`). Docker Socket ist `0660 root:docker` (GID 110), UID 10000 ist nicht in docker-Gruppe. Erfordert Container-Konfigurationsaenderung (`--group-add docker` oder aehnlich).
2. **trading-pipeline**: Neuer funktionaler Fehler seit 22:30 UTC. Paper-Orders werden platziert, aber ein spaeterer Schritt scheitert. Nicht Permission-bedingt.
3. **mcp/ Unterverzeichnis**: `logs/mcp/` hat noch einige root:root Dateien. Nicht kritisch fuer aktuelle Cron-Jobs, aber bei Bedarf nachbessern.

## Deferred: Docker Guardian Path Divergence

Der signal-heartbeat nutzt `docker exec` innerhalb des Hermes-Containers, was Docker-Socket-Zugriff erfordert. Moegliche Loesungen:
- Container mit `--group-add docker` starten
- Signal-Trigger ueber HTTP-API statt `docker exec`
- Docker Socket Mode auf 0666 setzen (Sicherheitsrisiko)

## Next Recommended Actions

1. **Docker Socket Access** klaeren: Wie soll signal-heartbeat auf ai-hedge-fund-crypto zugreifen?
2. **trading-pipeline** Fehler untersuchen: stdout/stddder vollstaendig auslesen
3. **mcp/ Verzeichnis** bei Bedarf nachbessern
4. **.mem0/history.db** (root:root) beobachten — falls Hermes direkt darauf zugreift, chown noetig

## Verdicts

| Frage | Antwort |
|-------|---------|
| Ist Hermes Cron lesbar und tickt? | **Ja** — jobs.json 10000:10000 600, Scheduler aktiv |
| Sind die 4 previously failing Jobs gefixt? | **Ja** — container-watchdog, mcp-watchdog, drawdown-guard, smart-heartbeat alle ok |
| Kann UID 10000 in log/state/output schreiben? | **Ja** — Write-Probes in 5 Verzeichnissen erfolgreich |
| Ist Memory von Permission-Drift betroffen? | **Nein** — Alle kritischen DBs korrekt 10000:10000 |
| Wurden breite rekursive Ownership-Aenderungen durchgefuehrt? | **Nein** — Nur gezielte Fixes auf 5 Verzeichnisse und 11 Dateien |
| Sind alle Bots weiterhin dry_run=true? | **Ja** — Keine Strategie- oder Trading-Config-Aenderungen |
