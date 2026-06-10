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
