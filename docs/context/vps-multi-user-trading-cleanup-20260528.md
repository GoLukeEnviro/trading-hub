# VPS Multi-User Trading System — Gate Review (Phase 0-2)

**Datum:** 2026-05-28 22:55 CEST
**Status:** GATE REVIEW — wartet auf Freigabe Phase 3+

---

## 1. User/Access Matrix

| User | UID:GID | Docker | Sudo | Gruppen | Home |
|------|---------|--------|------|---------|------|
| root | 0:0 | voll | voll | root | /root |
| hermes | 1337:1337 | NEIN | NOPASSWD:ALL | hermes | /home/hermes (hermes:hermes) |
| claudio | 1000:1000 | JA | PASSWD:ALL + NOPASSWD:docker,systemctl | docker,adm,hermes,ollama,systemd-journal | /home/claudio (claudio:claudio) |

**Wichtig:** hermes hat NOPASSWD:ALL (quasi-root), aber keinen direkten Docker-Socket-Zugriff. Der Guardian-Service bekommt docker-Gruppe via SupplementaryGroups.

---

## 2. Docker/Container Status

18 Container aktiv, alle `unless-stopped` restart policy:

| Container | User | Image | Status | Ports |
|-----------|------|-------|--------|-------|
| trading-guardian | 1337:1337 | trading-guardian:permission-hardening-candidate | Up 3h | none |
| hermes-green | root | nousresearch/hermes-agent:latest | Up 5h | 127.0.0.1:8642,8083 |
| rizzcoach-app-1 | nextjs | rizzcoach-app | Up 7h (healthy) | 127.0.0.1:8088 |
| freqtrade-webserver | ftuser | freqtradeorg/freqtrade:stable | Up 8h | 127.0.0.1:8180 |
| green-mem0 | default | hermes-mem0-local-api:stable | Up 28h (healthy) | 127.0.0.1:8788 |
| green-ollama | default | ollama/ollama:latest | Up 28h | 127.0.0.1:11436 |
| green-qdrant | 0:0 | qdrant/qdrant:latest | Up 28h | 127.0.0.1:6336 |
| hermes-mem0-local-api | default | hermes-mem0-local-api:stable | Up 3d (healthy) | 127.0.0.1:8787 |
| freqtrade-regime-hybrid | 10000:10000 | freqtrade-hermes10000:stable | Up 46h | 127.0.0.1:8085 |
| freqtrade-freqforge-canary | 10000:10000 | freqtrade-hermes10000:stable | Up 3d | 127.0.0.1:8081 |
| freqtrade-freqforge | 10000:10000 | freqtrade-hermes10000:stable | Up 3d | 127.0.0.1:8086 |
| claude-worker | default | claude-worker:latest | Up 5d (healthy) | 127.0.0.1:5050 |
| a0-v2 | default | agent0ai/agent-zero:latest | Up 5d (healthy) | 127.0.0.1:8082 |
| hermes-ollama | default | ollama/ollama:latest | Up 9d (healthy) | 11434 (internal) |
| hermes-qdrant | 0:0 | qdrant/qdrant:latest | Up 10d (healthy) | 127.0.0.1:6333-6334 |
| ai-hedge-fund-crypto | default | trading-ai-hedge-fund-crypto | Up 3d (healthy) | 127.0.0.1:8410 |
| freqai-rebel | ftuser | freqtradeorg/freqtrade:2026.3_freqai | Up 46h | 127.0.0.1:8087 |
| caddy | default | caddy:latest | Up 6d | host mode, *:3000 |

**UID-Konflikt:** Trading-Bots (freqforge, regime-hybrid, canary) laufen als UID 10000, aber der Host-User hermes ist UID 1337. trading-guardian laeuft absichtlich als 1337:1337.

---

## 3. Real Compose File Locations

7 aktive Compose-Projekte:

| Projekt | Compose-File |
|---------|-------------|
| trading | `/home/hermes/projects/trading/docker-compose.ai-hedge-fund-crypto.yml` |
| freqai-rebel | `/home/hermes/projects/trading/freqtrade/bots/freqai-rebel/docker-compose.yml` |
| hermes-green | `/opt/hermes-green/docker-compose.yml` |
| local-memory | `/opt/hermes/local-memory/docker-compose.yml` |
| claudio | `/home/claudio/docker-compose.yml` |
| rizzcoach | `/home/claudio/rizzcoach/docker-compose.yml` |
| agenten_auto_trade | `/var/lib/docker/volumes/a0-v2-usr/_data/projects/agenten_auto_trade/docker-compose.yml` |

Zusaetzliche Compose-Files (nicht aktiv geladen):
- `/home/hermes/projects/trading/docker-compose.yml` (Haupt-Compose, manuell verwaltet)
- `/home/hermes/projects/trading/freqtrade/docker-compose.fleet.yml`
- `/home/hermes/hermes-honcho-stack/honcho/docker-compose.yml`

---

## 4. Real Writable/Runtime Paths

Permission-Test-Ergebnisse (als hermes-User):

| Pfad | Status | Notiz |
|------|--------|-------|
| `/home/hermes/projects/trading/` | rw OK | |
| `/home/hermes/projects/trading/shared/` | rw OK | |
| `/home/hermes/projects/trading/logs/` | rw OK | |
| `/home/hermes/projects/trading/freqtrade/user_data/` | FEHLER | Existiert nicht (Pfad falsch) |
| `/home/hermes/projects/trading/freqforge/` | rw OK | |
| `/home/hermes/projects/trading/freqforge/user_data/` | rw OK | |
| `/home/hermes/projects/trading/freqforge-canary/user_data/` | rw OK | |
| `/home/hermes/freqtrade-regime-hybrid/user_data/` | FEHLER | Permission denied (root:root) |
| `/home/hermes/freqai-rebel/user_data/` | FEHLER | Permission denied (root:root) |

**Container-Mount-Map:**
- regime-hybrid: `/home/hermes/projects/trading/freqtrade/bots/regime-hybrid/{config,user_data}` + shared + logs
- freqforge: `/home/hermes/projects/trading/freqforge/{config,user_data}` + shared + logs
- canary: `/home/hermes/projects/trading/freqforge-canary/{config,user_data}` + shared + logs
- freqai-rebel: Docker-Volume `freqai-rebel-data` (kein Bind-Mount)

---

## 5. Git Status

**Branch:** main
**HEAD:** a3961c2
**Modified (working tree):**
- `freqforge-canary/user_data/primo_signal_state.json` (Runtime-Datei!)
- `orchestrator/scripts/git_guard.sh`

**Branches:** main, backup/pre-token-cleanup-20260522T004551Z, chore/final-docs-and-worktree-cleanup, chore/permission-hardening-guardian

---

## 6. Runtime Files Currently Tracked by Git

2 Dateien:
1. `freqforge-canary/user_data/primo_signal_state.json` — AKTIVE Runtime-Datei, wird vom Guardian aktualisiert
2. `freqtrade/bots/regime-hybrid/config/research/hermes_signal_fixture_20260520.json` — Test-Fixture (vermutlich OK)

---

## 7. Permission Test Results

Siehe Abschnitt 4. Zusammenfassung:
- **6 von 9** Pfaden fuer hermes beschreibbar
- **1 Pfad** existiert nicht (`freqtrade/user_data/` unter trading)
- **2 Pfade** Permission denied (root:root Ownership: regime-hybrid host, freqai-rebel host)

---

## 8. Dry-Run Safety Summary

Alle aktiven Trading-Bots: **dry_run = true**

| Bot | dry_run | wallet |
|-----|---------|--------|
| freqtrade-regime-hybrid | true | 1000 |
| freqtrade-freqforge | true | 1000 |
| freqtrade-freqforge-canary | true | 500 |
| freqai-rebel | true | 1000 |
| freqtrade-webserver | true | 1000 |

**Secrets:** Nur Library-Referenzen in .venv/ (ccxt, pyarrow). Keine echten API-Keys im Projektverzeichnis gefunden.

---

## 9. Port Exposure Summary

**Sicher (127.0.0.1):** Alle Trading-Ports (8081, 8085, 8086, 8087, 8180, 8410), Hermes (8642, 8083), Worker (5050), Memory (8787, 8788)

**Tailscale-only (100.65.117.122):** 443, 3001, 5000, 8080, 8083, 8088, 9090-9093

**Oeffentlich (0.0.0.0):**
- **Port 22** — SSH (erwartet)
- **Port 3000** — Caddy (host network mode, alle Interfaces!)
- **Port 4096** — opencode-Prozess (alle Interfaces!)

---

## 10. Backup Directory Path

`/root/vps-cleanup-backups/20260528-225216/`

**Inhalt (941M total):**
- docker-compose.yml (3.7K)
- docker-compose.ai-hedge-fund-crypto.yml (813B)
- .env.freqtrade-webui.local (3.6K)
- Caddyfile (856B)
- trading-cron-guardian.service + .timer
- root/hermes/claudio crontab.txt
- git-head.txt
- trading-project.tar.gz (941M)

---

## 11. Failed Commands

1. `/home/hermes/projects/trading/freqtrade/user_data/` — Pfad existiert nicht
2. `/home/hermes/freqtrade-regime-hybrid/user_data/` touch — Permission denied (root:root)
3. `/home/hermes/freqai-rebel/user_data/` touch — Permission denied (root:root)
4. freqai-rebel config.json ist ein Verzeichnis auf dem Host (Docker-Volume)
5. tar: "file changed as we read it" fuer freqtrade/shared (Live-Aenderung, harmlos)

---

## 12. Recommendation

### Gesamt-Farbe: GELB

**Kritische Befunde (vor Phase 3 klaeren):**

1. **Port 3000 (Caddy) auf 0.0.0.0** — Oeffentlich erreichbar. Caddy laeuft in host network mode.
2. **Port 4096 (opencode) auf 0.0.0.0** — Unbekannter Prozess, oeffentlich erreichbar.
3. **Runtime-File in Git getrackt** — primo_signal_state.json verursacht Git-Churn.
4. **UID-Mismatch** — Bots als 10000, hermes als 1337, Guardian als 1337.

**Nicht-kritisch:**
5. Swap zu 92% belegt (3.7G/4G)
6. Kein hermes-Crontab (alles ueber systemd/claudio)
7. freqai-rebel auf Docker-Volume (inkonsistent aber funktional)

### Empfehlung: BEDINGTES GO fuer Phase 3

Nach Klaerung:
1. Ports 3000 und 4096 — intentional oder Sicherheitsrisiko?
2. Runtime-File Cleanup — `git rm --cached` freigeben?
3. Ownership-Strategie — root:root Pfade akzeptieren oder fixen?

### System Health

- Uptime: 10 Tage, Load: 0.12
- Disk: 183G/301G (64%)
- Memory: 8.4G/30G used
- Swap: 3.7G/4G (92%)
- 0 failed systemd services
- Alle Container stabil

---

*Generated by Claude Code Gate Review — 2026-05-28 22:55 CEST*
