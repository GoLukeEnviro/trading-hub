# Mem0 V3 Migration — nomic-embed-text mit Prefixes

**Datum:** 2026-06-10  
**Status:** Abgeschlossen  
**Betroffen:** hermes_memories_v2 → hermes_memories_v3, green-mem0 Service

## Was passiert ist

- Neue Collection `hermes_memories_v3` angelegt (768-dim, Cosine)
- 284/284 Memories aus `hermes_memories_v2` (2560-dim, qwen3-embedding:4b) re-embedded mit `nomic-embed-text` und korrektem `search_document:` Prefix
- Validierung erfolgreich: 8 relevante Trading-Queries returnieren Treffer
- Altes Modell `qwen3-embedding:4b` aus `green-ollama` entfernt (`ollama rm`)
- `green-mem0` Service auf v3 umgestellt (Env: `MEM0_COLLECTION=hermes_memories_v3`, `MEM0_EMBEDDER_MODEL=nomic-embed-text`, `MEM0_EMBEDDING_DIMS=768`)
- `embedding_model_dims` in `app.py` von 1024 auf 768 gefixt
- Docker-Netzwerk: green-mem0 läuft jetzt auf `trading_hermes-net` (war fälschlich auf `hermes-net`)

## Mem0-Plugin Fix (Hermes Agent)

- **Problem:** Das Mem0-Plugin im Hermes-Agent (`/opt/hermes/plugins/memory/mem0/__init__.py`) nutzte `MemoryClient(api_key=...)` gegen die Mem0-Cloud und bekam 401 (ungültiger Key). Alle `sync_turn()`, `mem0_search`, `mem0_conclude` waren funktionslos.
- **Fix:** Kompletter Austausch gegen lokale HTTP-Aufrufe an `green-mem0:8787`. Kein API-Key nötig. Kein Cloud-Call.
- **Datei:** `/opt/hermes-green/config/plugins/memory/mem0/__init__.py` (Host) → via docker-compose Bind-Mount ins Container-Verzeichnis `/opt/hermes/plugins/memory/mem0/__init__.py`
- **Status:** ✅ Funktionstüchtig – `mem0_profile` (276 Memories), `mem0_search` (20 Treffer), `mem0_conclude` getestet

## Sonstiges

- `mem0ai[nlp]` in green-mem0 installiert (spaCy-Warnings beseitigt)
- Alte Collection `hermes_memories_v2` bleibt als Backup (kann nach 2–3 Tagen gelöscht werden)

## Dateien

- `/opt/hermes/hermes_memory.py` — Migration + Validierung + PrefixedMemory Wrapper
- `/home/hermes/hermes_memory.py` — identisch
- `/opt/data/local-memory/app/app.py` — aktualisiert (768 dims)

## Neuer Embedding-Stack

| Komponente | Alt | Neu |
|-----------|-----|-----|
| Collection | `hermes_memories_v2` (2560-dim) | `hermes_memories_v3` (768-dim) |
| Embedder | `qwen3-embedding:4b` (2.5 GB) | `nomic-embed-text` (274 MB) |
| Prefixes | Keine | `search_document:` / `search_query:` |
| LLM | `gemma3:27b` via Ollama Cloud | Unverändert |
| Extraction Policy | v2 | Unverändert |

## Rollback

- Alte Collection `hermes_memories_v2` bleibt als Backup
- `MEM0_COLLECTION=hermes_memories_v2` + `docker compose restart green-mem0` = sofort zurück

## Cron-Fixes (2026-06-10)

**Problem (nicht klassischer Cron-Daemon):** Der Hermes Orchestrator Scheduler läuft zuverlässig (alle Jobs werden getriggert). Zwei spezifische Fehler betrafen die Memory-Cron-Jobs:

1. **memory_backfill (alle 2h) → Timeout nach 120s**
   - Root Cause: `_DEFAULT_SCRIPT_TIMEOUT = 120` in `/opt/hermes/cron/scheduler.py:919`
   - Fix: `script_timeout_seconds: 300` in `/opt/data/config.yaml` (cron section)
   - Wirkung: Nächster Lauf hat 300s statt 120s

2. **dream_mode + ledger-watchdog → PermissionError in docs/context/**
   - Root Cause: UID-Mismatch — Container läuft als UID 10000, aber `docs/context/` auf dem Host ist UID 1337 (`hermes`). Schreibzugriff blockiert.
   - Fix: `setfacl -R -m u:10000:rwx /home/hermes/projects/trading/docs/context/`
   - Wirkung: UID 10000 kann jetzt schreiben ✅

3. **Qdrant Backup-Cron**
   - Installiert: `/etc/cron.d/qdrant-backup`
   - Schedule: täglich 03:00 UTC
   - Kommando: `docker run alpine tar czf` → `/opt/backups/qdrant/`
   - Retention: 7 Tage (mtime +7)
   - Log: `/var/log/hermes-cron.log`
   - Getestet: 11 MB für ~290 Points ✅
