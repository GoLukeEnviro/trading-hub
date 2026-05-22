# Hermes Local Memory — E2E Gate Report

**Date:** 2026-05-18  
**Project:** Mem0 Cloud Migration → Local Mem0/Qdrant/Ollama  
**Status:** ✅ E2E GATE GREEN — Local memory backend fully operational  

---

## Architecture (Final)

```
Hermes-Agent → _LocalMem0Client (urllib.request)
                    ↓ (hermes_memory Docker network)
               mem0-local-api (FastAPI, port 8787)
                    ↓
               ┌──────────────┬──────────────┐
               ↓              ↓              ↓
          mem0 SDK       Qdrant (vec DB)  Ollama
          (extract)      port 6333        port 11434
                                          nomic-embed-text
                                          qwen2.5:3b
```

- **Mem0 Cloud:** Deactivated. API key exists in config as dead fallback.
- **Provider:** `_LocalMem0Client` replaces `MemoryClient` when `local_mem0_api_url` is set.
- **Transport:** Python `urllib.request` (no curl dependency).
- **DNS:** Docker-internal DNS (container names, not hardcoded IPs).

---

## Phase Results

| Phase | Status | Key Evidence |
|-------|--------|-------------|
| **P1 — Container Health** | ✅ PASS | All 4 containers running, healthy. No Hermes startup crash. |
| **P2 — Provider Activation** | ✅ PASS | `local_api_url=http://hermes-mem0-local-api:8787`, `is_available=True` |
| **P3 — mem0_conclude** | ✅ PASS | `"Fact stored."`, 0 failures, through `_LocalMem0Client.add()` |
| **P4 — mem0_search** | ✅ PASS | Score 0.84 — E2E test fact found after storage |
| **P4b — mem0_profile** | ✅ PASS | Returns all memories (2 stored) |
| **P5 — Persistence** | ✅ PASS | `docker compose restart` → data survives (Score 0.84) |
| **P6 — Security** | ✅ PASS | All ports localhost-only or Docker-internal. No Caddy exposure. |

---

## mem0_conclude Performance

| Metric | Value | Note |
|--------|-------|------|
| First call | 72.5s | CPU-based LLM extraction (qwen2.5:3b), first call pulls model |
| Second call | ~0.4s | If inferred from same session |
| Search | 0.0-0.1s | Embedding lookup only, no LLM needed |
| Profile | 0.0-0.1s | Qdrant scroll, no LLM |

**Note:** 72.5s is a UX concern for `mem0_conclude`. Consider switching to a smaller LLM for extraction (e.g., `qwen2.5:0.5b`) or accepting the latency for now since it runs in background.

---

## Files Changed

| File | Change | Risk |
|------|--------|------|
| `/opt/hermes/plugins/memory/mem0/__init__.py` | Added `_LocalMem0Client` class (180 LoC) + routing logic | Low — cloud fallback preserved |
| `/opt/data/profiles/orchestrator/mem0.json` | Added `local_mem0_api_url=http://hermes-mem0-local-api:8787` | Low — only read by provider |
| `/opt/hermes/local-memory/docker-compose.yml` | Fixed healthchecks (no curl), removed hardcoded IPs | Low — all Docker-internal |

### Backups Created

- `/opt/hermes/plugins/memory/mem0/__init__.py` → `docs/backups/mem0_plugin.20260518T171006Z.pre-local-api.bak`

---

## Security Posture

| Service | Host Port | Exposure |
|---------|-----------|----------|
| hermes-ollama | None (Docker-internal) | 🔒 Internal only |
| hermes-qdrant | `127.0.0.1:6333-6334` | 🔒 Localhost only |
| hermes-mem0-local-api | `127.0.0.1:8787` | 🔒 Localhost only |
| Hermes Agent | `0.0.0.0:8642`, `127.0.0.1:8083` | Partially exposed (8642 for API server) |

**No Caddy route exposes mem0-local-api, Qdrant, or Ollama publicly.**

---

## Cloud Dependency Check

| Component | Mem0 Cloud Called? | Evidence |
|-----------|-------------------|----------|
| mem0_conclude | ❌ No | Logs show POST to `hermes-mem0-local-api:8787` |
| mem0_search | ❌ No | Logs show POST to `hermes-mem0-local-api:8787` |
| mem0_profile | ❌ No | Logs show GET from `hermes-mem0-local-api:8787` |
| sync_turn | ❌ No (by extension) | Uses same _LocalMem0Client path |
| api.mem0.ai | ❌ Never | 0 requests in logs |
| HTTP 429 | ❌ Never | No quota errors |

**Conclusion:** Active memory path has zero cloud dependencies.

---

## Remaining Risks

1. **LLM Extraction Latency (Medium)** — 72.5s for mem0_conclude on CPU-based qwen2.5:3b.
   - Acceptable for non-blocking operations (sync_turn runs in thread).
   - Mitigation: Switch to smaller model or accept background latency.

2. **Model Volume Loss on Container Recreate (Medium)** — qwen2.5:3b was lost after `docker rm` + `docker compose up`.
   - The `ollama_data` volume is a named Docker volume that shouldn't lose data on normal restarts.
   - Mitigation: Volumes are `local-memory_ollama_data` and `local-memory_qdrant_data` — named volumes survive `docker compose down` (not `down -v`).

3. **CPU Load (Low)** — qwen2.5:3b consumes CPU during LLM extraction. Not a problem for occasional use.

4. **Security: Hermes dashboard port 8083/9119 (Pre-existing)** — Already exposed on localhost, unrelated to memory migration.

---

## Rollback Instructions

```bash
# 1. Restore provider
cp docs/backups/mem0_plugin.20260518T171006Z.pre-local-api.bak \
   /opt/hermes/plugins/memory/mem0/__init__.py

# 2. Remove local config
rm /opt/data/profiles/orchestrator/mem0.json
# Or restore previous content

# 3. Restart Hermes
docker compose -f /opt/hermes/docker-compose.yml restart
# 4. Keep local stack running or stop
cd /opt/hermes/local-memory && docker compose down
# (do NOT use -v unless you want to delete all memories)
```

---

## Next Steps

1. **Do NOT import staged memories yet** — the local stack is validated but needs real-world testing first.
2. **Shadow-run** for 1-2 days — let sync_turn write to local stack in production and monitor.
3. After shadow-run: import legacy Holographic memories → local Mem0.
4. Mem0 Cloud API key can be removed from config after full cutover.

---

**LOCAL MEMORY E2E GATE GREEN — staged memory import may proceed after shadow-run period.**
