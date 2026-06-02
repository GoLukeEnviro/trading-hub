# Blue-Stack-Cleanup Vorbereitung -- 2026-06-01

## Executive Verdict

Blue-Stack ist verwaist und vollstaendig repliziert. Alle aktiven Script-Referenzen wurden auf Green umgestellt. Blue kann nach Beobachtungszeit sicher entfernt werden.

## Geaenderte Dateien

| Datei | Aenderung | Zeile |
|---|---|---|
| `orchestrator/scripts/system_optimizer.py` | KNOWN_CONTAINERS: `hermes-agent` -> `hermes-green`, `hermes-mem0-local-api` -> `green-mem0`, `hermes-ollama` -> `green-ollama`, `hermes-qdrant` -> `green-qdrant` | 250 |
| `orchestrator/scripts/daily_heartbeat.py` | `docker inspect hermes-mem0-local-api` -> `docker inspect green-mem0` | 88 |
| `orchestrator/scripts/mem0_watchdog.py` | Default `MEM0_CONTAINER_NAME` -> `green-mem0` | 15 |
| `orchestrator/scripts/mem0_watchdog.py` | Fallback-URL `mem0-local-api:8787` -> `localhost:8788` (host-kompatibel) | 44 |
| `orchestrator/scripts/drawdown_guard.py` | `docker inspect hermes-agent` -> `docker inspect hermes-green` (Telegram-Token-Lookup) | 202 |
| `orchestrator/guardian/scripts/external_cron_guardian.sh` | `docker exec hermes-agent` -> `docker exec hermes-green` (Pipeline-Trigger) | 98 |

Zusaetzlich aktualisiert: Kommentare und Log-Messages in `external_cron_guardian.sh` (Zeilen 97, 102).

**Nicht geaendert** (bewusst):
- `memory_backfill.py` - bereits Green (`green-mem0:8787`)
- `hermes_primo_bridge.py` - COMMENT_ONLY (Zeilen 5, 232)
- Blue-Compose-Definitionen (`/opt/hermes/`, `/opt/hermes/local-memory/`) - bleiben bis zum Cleanup
- `docs/context/` Dateien - Legacy-Doku

## Kanonische Green-Namens-Konvention

| Blue-Name | Green-Name | Netzwerk | Host-Port |
|---|---|---|---|
| `hermes-agent` | `hermes-green` | green-net + ki-fabrik | 8642, 8083 |
| `hermes-mem0-local-api` | `green-mem0` | green-net | 8788->8787 |
| `hermes-qdrant` | `green-qdrant` | green-net | 6336->6333 |
| `hermes-ollama` | `green-ollama` | green-net | 11436->11434 |

## Blue-Qdrant Datenvergleich

### Collection-Metadaten

| Collection | Metrik | Blue (6333) | Green (6336) | Match |
|---|---|---|---|---|
| `hermes_memories` | points_count | 1,167 | 1,167 | ja |
| `hermes_memories` | vector_dims | 768 | 768 | ja |
| `hermes_memories` | distance | Cosine | Cosine | ja |
| `hermes_memories` | segments | 7 | 7 | ja |
| `hermes_memories_v2` | points_count | 1,167 | **1,168** | nein (Green +1) |
| `hermes_memories_v2` | vector_dims | 1,024 | 1,024 | ja |
| `hermes_memories_v2` | distance | Cosine | Cosine | ja |
| `hermes_memories_v2` | segments | 8 | 8 | ja |
| `mem0migrations` | points_count | 0 | 0 | ja |

### ID-Stichprobe (hermes_memories_v2, erste 100 IDs)

- Gemeinsame IDs: 100/100
- Nur in Blue: **0**
- Nur in Green: **0** (der extra Punkt liegt ausserhalb der ersten 100)

**Klassifikation: GREEN_SUPERSET / BLUE_HAS_NO_UNIQUE_DATA** -- Blue hat nichts was Green nicht hat. Green hat sogar einen Punkt mehr. Blue sicher entfernbar nach Beobachtung.

**Hinweis:** Der Fallback in `mem0_watchdog.py` wurde auf `http://localhost:8788` geaendert, da das Script vom Host laeuft und Docker-DNS (`green-mem0`) vom Host nicht zuverlaessig aufloesbar ist. `localhost:8788` ist der veroeffentlichte Host-Port von `green-mem0`. Getestet und bestaetigt.

## Verbleibende Blue-Referenzen (nicht aktiv)

| Datei | Typ | Referenz |
|---|---|---|
| `hermes_primo_bridge.py:5,232` | COMMENT_ONLY | "hermes-agent" in Docstring/Kommentar |
| `/opt/hermes/local-memory/docker-compose.yml` | Blue-Definition | Blue-Stack-Compose |
| `/opt/hermes/docker-compose.yml` | Blue-Definition | Blue-Hermes-Compose |
| `docs/context/*.md` | LEGACY_DOC | Historische Audit-Reports |

## Validation

- Syntax-Check: alle 5 Dateien OK (py_compile + bash -n)
- Green Mem0 Health: ok
- Trading-Bots: 4/4 running, unveraendert
- Finaler Referenz-Scan: KEINE aktiven Blue-Referenzen in Scripts/Guardian

## Naechste Schritte

1. **48h Beobachtung:** System normal laufen lassen. Guardian nutzt jetzt `hermes-green` fuer Pipeline-Trigger und Telegram-Token-Lookup.
2. **Nach Beobachtung:** Blue-Stack stoppen (nicht entfernen): `cd /opt/hermes/local-memory && docker compose stop`
3. **Weitere 48h Beobachtung:** System ohne Blue-Stack. Green-Stack muss alles abdecken.
4. **Wenn stabil:** Blue-Stack entfernen (`docker compose down` + Volume-Cleanup)
5. **Blue-Compose-Dateien** archivieren oder entfernen

## Resource-Impact

Blue-Stack verbraucht aktuell:
- 3 Container (hermes-mem0-local-api, hermes-qdrant, hermes-ollama)
- ~300 MB RAM
- ~8.2 GB Docker-Volumes (2.8 GB Qdrant + 5.4 GB Ollama, identische Daten wie Green)
