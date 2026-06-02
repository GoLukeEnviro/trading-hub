# Blue-Stack Stop-only Test -- 2026-06-01

## Aktion

Blue-Stack gestoppt (nur stop, kein down, kein prune).

```bash
cd /opt/hermes/local-memory && docker compose stop     # hermes-ollama, hermes-qdrant
docker stop hermes-mem0-local-api                       # separater Container
```

## Pre-State

| Container | Status |
|---|---|
| hermes-mem0-local-api | Up 6d (healthy) |
| hermes-ollama | Up 12d (healthy) |
| hermes-qdrant | Up 13d (healthy) |

## Post-State

| Container | Status |
|---|---|
| hermes-mem0-local-api | **Exited (0)** |
| hermes-ollama | **Exited (0)** |
| hermes-qdrant | **Exited (143)** |

Exit-Code 143 = SIGTERM (normaler Docker-Compose-Stop).

## Verifikation (alle bestanden)

| Check | Ergebnis |
|---|---|
| Green Mem0 Health | ok, cloud_required=false |
| Mem0 Watchdog | OK, 1156 memories, API 200 |
| Freqtrade-Fleet | 4/4 running |
| Guardian Timer | active (waiting), naechster Lauf in <2 min |
| Guardian Log | OK: All checks passed |
| Signal Frische | 9.3 min (< 30 min) |

## Nicht-gestaerte Services

| Container | Status |
|---|---|
| green-mem0 | Up (healthy) |
| green-qdrant | Up |
| green-ollama | Up |
| hermes-green | Up |
| freqtrade-freqforge | Up |
| freqtrade-freqforge-canary | Up |
| freqtrade-regime-hybrid | Up |
| freqai-rebel | Up |
| ai-hedge-fund-crypto | Up |
| trading-guardian | Up |
| claude-worker | Up |

## Beobachtungszeitraum

**Start:** 2026-06-01 08:21 UTC
**Mindestdauer:** 48h
**Ende fruehestens:** 2026-06-03 08:21 UTC

Waehrend der Beobachtung pruefen:
- Green Mem0 bleibt healthy
- Trading-Bots laufen ungestoert
- Guardian meldet OK
- Mem0 Watchdog meldet OK
- Keine Blue-Referenz-Fehler in Logs

## Rollback

Falls Probleme auftreten:
```bash
cd /opt/hermes/local-memory && docker compose start
docker start hermes-mem0-local-api
```

## Naechster Schritt nach 48h

Wenn System stabil bleibt:
1. Remove-Plan erstellen
2. Blue-Stack entfernen (`docker compose down` im local-memory-Dir)
3. Blue-Volumes evaluieren (`hermes-qdrant-data`, `local-memory_ollama_data`, `local-memory_qdrant_data`)
4. Blue-Compose-Dateien archivieren
5. `docs/context/` mit Remove-Protokoll aktualisieren
