# Rebuild Report — 2026-05-28

## Zusammenfassung

Dieser Lauf hat kritische Security- und Backup-Probleme behoben und den Zielzustand dokumentiert.  
Wichtig: Das freie Speicherziel `>= 90G` ist jetzt erreicht.

## Was wurde gemacht

### 1) Security-Fix Freqtrade-Port-Exposure

- Expositionstest auf Port `8180` ausgeführt.
- Sofort-Mitigation aktiv bestätigt (UFW DENY auf `eth0` für `8180/8081/8085/8086/8087`).
- Aktive Compose-Datei korrigiert:
  - `/var/lib/docker/volumes/a0-v2-usr/_data/projects/agenten_auto_trade/docker-compose.yml`
  - Port-Bindings auf localhost umgestellt (`127.0.0.1:*`).
- `freqtrade-webserver` neu erstellt und zusätzlich einen Rechtefehler auf Config-Datei behoben (Container war im Restart-Loop).

### 2) Restic Backup-von-Backup behoben

- Produktionsskript angepasst:
  - `/usr/local/sbin/restic-backblaze-backup.sh`
- Patch-Skript angepasst:
  - `/root/restic-dr-patch-backup-20260527-170920/restic-backblaze-backup.sh`
- Restic-Filter korrigiert:
  - `/etc/restic/includes.txt`: `/opt/backups` entfernt
  - `/etc/restic/excludes.txt`: `/opt/backups`, `/opt/hermes-recovery-*`, `/home/claudio/hermes-backups` explizit ergänzt
- Dry-Run durchgeführt und validiert.
- Neuer manueller Snapshot erstellt: `1b81bd74` (`manual-fix-20260528`).
- Nachweis: Neuester Snapshot enthält die ausgeschlossenen Pfade nicht mehr.

### 3) Speicher-Cleanup (sicherer Teil)

- Gelöscht:
  - `/opt/backups/db-dumps/2026-05-26_0200`
  - `/opt/backups/db-dumps/2026-05-27_0200`
- Entfernt:
  - Docker-Volumes `openclaw-fresh_openclaw-workspace`, `openclaw-fresh_openclaw-config`
- Bereinigt:
  - `/root/.vscode-server/data/User/workspaceStorage`
  - npm-Cache
- Retention-Fix in `/usr/local/bin/vps-backup.sh` ergänzt:
  - separate DB-Dump-Retention auf die 2 neuesten Dump-Verzeichnisse
- Zusätzlich gelöscht (R5-verifiziert):
  - `/home/claudio/hermes-backups/lossless-20260527-145953` (~31G)
  - Nachweis vor Löschung: `restic ls latest` enthielt `lossless-20260527` (`254` Treffer)

### 4) Architektur-Artefakte

- Neue konsolidierte Compose-Datei erstellt:
  - `/home/hermes/projects/trading/docker-compose.yml`
- Dry-Run der Compose-Datei erfolgreich nach Image-Korrekturen.

### 5) RiskGuard Minimal-Implementierung

- Neu erstellt:
  - `/home/hermes/projects/trading/tools/riskguard/riskguard.py`
- Verhalten:
  - liest `ai-hedge-fund-crypto/output/hermes_signal.json`
  - prüft Schema/Freshness/Confidence/Allowlist
  - schreibt append-only nach `tools/riskguard/decisions.jsonl`
- Cron:
  - `hermes`-User existiert auf diesem Host nicht
  - Fallback auf Nicht-Root-User `claudio` gesetzt

## Was wurde gelöscht (mit Begründung)

- Alte DB-Dumps vom 26./27.05. entfernt (durch ältere Restic-Snapshots abgedeckt).
- Alte OpenClaw-Volumes entfernt (nicht mehr von Containern referenziert).

Nicht gelöscht (bewusst):

- `/opt/hermes-recovery-20260517-111339` (~26G)

Grund: Für `lossless` war die Abdeckung im neuesten Snapshot nachweisbar und wurde daher gelöscht; `hermes-recovery` bleibt bis zur optionalen Archivierung bewusst erhalten.

## Speicher vorher/nachher

- Ausgangslage (Start): ca. `75G` frei
- Zwischenstand vor finalem Cleanup: ca. `78G` frei
- Nach finalem Cleanup (`lossless` entfernt): ca. `109G` frei

=> Ziel `>=90G` **erreicht**.

## Security-Fixes

- `8180` von `0.0.0.0` auf `127.0.0.1` umgestellt.
- UFW-Blockregeln auf `eth0` für Freqtrade-relevante Ports gesetzt.
- Zielports `8081/8085/8086/8087/8180` zeigen localhost-Bindings.

## Architektur-Änderungen

- Root-Compose mit Socket-Proxy und lokaler Port-Bindung erstellt.
- RiskGuard von reiner Spec zu lauffähigem Minimalservice gehoben.

## Offene Punkte

1. Optional: `hermes-recovery-20260517-111339` archivieren und danach löschen (zusätzliche ~26G frei).
2. Optional: echten `hermes`-Systemuser anlegen, wenn Cron strikt auf diesen User laufen muss.
