# Operational State — Trading Hub

**Stand:** 2026-05-28 (CEST)
**Quelle:** Live-Checks auf Host `Agent0` (nicht nur Repo-Stand)

> Dieser Snapshot ist eine belastbare Momentaufnahme. Vor produktiven Eingriffen trotzdem erneut live validieren.

---

## 1) Container- und Service-Status

Aktive Kernservices (Auszug):

- `hermes-green` — Up
- `green-mem0`, `green-ollama`, `green-qdrant` — Up
- `hermes-mem0-local-api` — Up (healthy)
- `ai-hedge-fund-crypto` — Up (healthy)
- `freqtrade-freqforge` — Up
- `freqtrade-freqforge-canary` — Up
- `freqtrade-regime-hybrid` — Up
- `freqai-rebel` — Up
- `freqtrade-webserver` — Up (nach Rechte-Fix)
- `caddy` — Up
- `claude-worker`, `a0-v2`, `trading-guardian`, `rizzcoach-app-1` — Up

Relevante Ports:

- Freqtrade/API-Ports: `8081`, `8085`, `8086`, `8087`, `8180` auf `127.0.0.1`
- Public Edge weiterhin nur über Caddy/Netzwerk-Policy

---

## 2) Speicherstatus

Snapshot zum Zeitpunkt dieser Datei:

- Filesystem `/`: `301G` gesamt / `211G` belegt / `78G` frei (`73%`)
- Filesystem `/`: `301G` gesamt / `180G` belegt / `109G` frei (`63%`)

Bewertung:

- Ziel `>= 90G frei` ist **erreicht**.
- Bereits erledigt: alte DB-Dumps (26./27.) entfernt, OpenClaw-Alt-Volumes entfernt, Caches bereinigt, `lossless-20260527-145953` entfernt.

---

## 3) Backup-Status (Restic + lokal)

- `restic-backblaze-backup.timer`: aktiv
- Letzter planmäßiger Service-Run: `SUCCESS` (heute Nacht)
- Zusätzlicher manueller Fix-Snapshot vorhanden: `1b81bd74` (Tag `manual-fix-20260528`)
- Neuester Snapshot enthält **nicht mehr**:
  - `/opt/backups`
  - `/home/claudio/hermes-backups`
  - `/opt/hermes-recovery-*`

Hinweis:

- Ältere Snapshots enthalten historisch noch `/opt/backups` (vor Fix), was erwartet ist.

---

## 4) Security-Status (Port-Bindings)

- `freqtrade-webserver` war vorher `0.0.0.0:8180`, jetzt auf `127.0.0.1:8180` umgestellt.
- UFW-Hardening-Regeln für `8180/8081/8085/8086/8087` auf `eth0` aktiv.
- `ss`-Prüfung zeigt für diese Zielports nur localhost-Bindings.

---

## 5) Dry-Run-Sicherheit

Direkt aus den geladenen Container-Konfigurationen verifiziert:

- `freqtrade-freqforge`: `dry_run=True`
- `freqtrade-freqforge-canary`: `dry_run=True`
- `freqtrade-regime-hybrid`: `dry_run=True`
- `freqai-rebel`: `dry_run=True`

---

## 6) Offene TODOs / Blocker

1. Offener großer Kandidat:
  - `/opt/hermes-recovery-20260517-111339` (~26G)
2. Konsolidierte Root-Compose erstellt (`/home/hermes/projects/trading/docker-compose.yml`), aber noch nicht als alleiniger Live-Orchestrator übernommen.

## Hermes Green Permission Model — 2026-05-28

Hermes Green uses a root-init model. The container may show root via default `docker exec id`, but the Hermes application runtime drops to UID/GID `10000:10000`.

Do not force Compose-level `user: "1337:1337"` for `hermes-green`; this caused startup failure because the image requires root during initialization.

Canonical runtime artifact ownership:

```text
10000:10000 700 /opt/hermes-green/config/profiles/orchestrator
10000:10000 600 /opt/hermes-green/config/profiles/orchestrator/config.yaml
10000:10000 600 /opt/hermes-green/config/profiles/orchestrator/sessions/sessions.json
10000:10000 600 /opt/hermes-green/config/profiles/orchestrator/cron/jobs.json
```

`gateway.lock` is runtime-owned and may be managed/rewritten by the application.

Validation passed: `hermes-green` running, restart_count `0`, runtime UID/GID `10000:10000`, no known permission-denied errors for `config.yaml`, `gateway.lock`, `sessions.json`, or `jobs.json`.

Backups:

```text
/root/hermes-permission-backups/20260528-170709
/root/hermes-permission-backups/sessions-cron-20260528-175435
```

