# Phase 45C — Secret Leak Containment & PrimoAgent Mount Removal

**Datum:** 2026-05-12
**Ausloeser:** Phase 45B Agent schrieb `recreate-command.sh` mit Klartext-Secrets und entfernte den PrimoAgent-Mount nicht korrekt

---

## Executive Summary

Ein vorheriger Agent (Phase 45B) erstellte waehrend eines "cosmetic cleanup" eine `recreate-command.sh` die **alle API-Keys und Tokens im Klartext** enthielt. Die Datei lag mit Permissions `644` (weltlesbar) im Backup-Verzeichnis. Zusaetzlich wurde der PrimoAgent-Bind-Mount nicht aus der Compose-Datei entfernt.

Phase 45C hat beide Probleme behoben:
1. Secret-Leak eingedaemmt (Datei geloescht, Berechtigungen restriktiert)
2. PrimoAgent-Mount korrekt ueber Docker Compose entfernt

---

## Secret Leak Containment

### Massnahmen
- `chmod -R go-rwx` auf `/home/hermes/projects/trading/backups/phase45b-primoagent-bindmount-cleanup-20260512_035708Z/`
- `recreate-command.sh` geloescht
- Verbleibende Dateien gescannt (`grep -Rli`) — keine weiteren Secret-haltigen Dateien gefunden

### Verifizierung
- `SECRET_FILE_REMOVED_OK`
- `NO_SECRET_FILES_FOUND`

---

## Entfernte Dateien

| Datei | Aktion | Grund |
|-------|--------|-------|
| `phase45b-.../recreate-command.sh` | geloescht | Enthielt alle API-Keys im Klartext |

Verbleibende Datei im Backup-Verzeichnis:
- `hermes-agent-metadata.txt` — enthaelt Mount-Infos und Compose-Labels, keine Secrets

---

## PrimoAgent Bind Mount Removal

### Aenderung
**Datei:** `/opt/hermes/docker-compose.yml`
**Entfernte Zeile:** `- /home/hermes/trading/primoagent:/home/hermes/primoagent:rw`

### Compose Backup
- Pfad: `/opt/hermes/docker-compose.yml.bak_phase45c_*`
- Erstellung: vor dem Edit

### Neustart
- Befehl: `cd /opt/hermes && docker compose up -d hermes`
- Ergebnis: Container neu erstellt ("Recreated")
- Methode: Docker Compose (KEIN docker run)

---

## Post-Fix Validation

| Check | Ergebnis |
|-------|----------|
| `hermes-agent` laeuft | Up, compose-managed |
| PrimoAgent-Mount entfernt | Bestaetigt (0 Treffer bei grep) |
| Alle anderen Mounts intakt | 6 Mounts, alle erwartet |
| `ai-hedge-fund-crypto` | healthy |
| FreqTrade-Fleet (5 Container) | alle Up |
| Ports korrekt (8083, 8642) | Bestaetigt |
| Secret-Datei geloescht | Bestaetigt |
| Keine weiteren Secret-Files | Bestaetigt |

---

## Empfohlene Key Rotation

Da die Secrets in einer weltlesbaren Datei lagen, wird Rotation empfohlen:

- TELEGRAM_BOT_TOKEN
- API_SERVER_KEY
- OPENROUTER_API_KEY
- GLM_API_KEY
- DEEPSEEK_API_KEY
- OLLAMA_API_KEY

Die .env-Datei unter `/opt/hermes/.env` sollte geprueft werden ob die Keys dort noch aktuell sind. Rotation sollte nach Prioritaet erfolgen: Telegram-Bot-Token und OpenRouter zuerst (hoechstes Expositionsrisiko).

---

## Final Verdict: PASS

Alle Ziele erreicht:
- Secret-Leak eingedaemmt
- PrimoAgent-Mount korrekt ueber Compose entfernt
- Alle Services laufen
- Keine unbeabsichtigten Seiteneffekte
