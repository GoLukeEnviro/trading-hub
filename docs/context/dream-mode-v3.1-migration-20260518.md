# Dream Mode v3.1 — Modus-Anpassung Report

**Date:** 2026-05-18 21:38 UTC  
**Status:** SUCCESS  

## Changes Made

### 1. dream_consolidate.py v3.0 -> v3.1

| Change | Before | After |
|--------|--------|-------|
| Mem0 target | `api.mem0.ai` (Cloud) | `mem0-local-api:8787` (Local) |
| Auth | Hardcoded Cloud API key | No auth (local) |
| write format | `POST /v1/memories/` (Cloud) | `POST /memories/add` (Local) |
| search format | `POST /v1/memories/search/` | `POST /memories/search` |
| list format | `GET /v1/memories/?user_id=` | `GET /memories/all?user_id=` |
| State DB path | `/home/hermes/.hermes/state.db` | `/opt/data/state.db` (configurable) |
| Health check | None | Pre-flight mem0-local-api health |
| Docker proxy | None | `DOCKER_EXEC_PROXY=true` fallback |
| LLM mode model | `openai/gpt-4o-mini` via OpenRouter | `gpt-oss:120b` via Ollama Cloud |
| LLM mode auth | DREAM_LLM_KEY (OpenRouter) | OLLAMA_API_KEY (auto from .env) |

### 2. dream_cron_report.sh Updated

- Health check via `docker exec hermes-mem0-local-api python3 -c '...'`
- Sets `DOCKER_EXEC_PROXY=true` for host-side execution
- Sources `.env` for OLLAMA_API_KEY

### 3. Cron Job Updated

| Property | Before | After |
|----------|--------|-------|
| Name | Dream Mode v3.0 Memory Consolidation | Dream Mode v3.1 Memory Consolidation (Local Stack) |
| Script | `dream_cron_report.sh` | `dream_cron_report.sh` (updated content) |
| Workdir | default | `/opt/data/profiles/orchestrator/skills/maintenance/dream-mode/scripts` |

### 4. Docker Exec Proxy Pattern

Since the Docker port proxy for 8787 is broken (host cannot reach 127.0.0.1:8787),
the script uses a `docker exec` proxy pattern:

```
Host cron -> dream_cron_report.sh
  -> python3 dream_consolidate.py (on host, reads state.db)
    -> _docker_exec_rest() -> docker exec hermes-mem0-local-api python3 -c '...'
      -> mem0-local-api:8787 (inside Docker network)
```

This works because `hermes-mem0-local-api` can reach itself at `127.0.0.1:8787`.

### 5. Backup

```
/opt/data/profiles/orchestrator/skills/maintenance/dream-mode/scripts/dream_consolidate.py.20260518T213247Z.bak
```

## Dry-Run Result

```
Messages scanned: 775 (26h)
Raw facts: 41
After local dedup: 38 (3 skipped)
After remote dedup: 38 (0 skipped)
Written: 5 (capped at DREAM_MAX_WRITES=5 for test)
Failed: 0
Status: SUCCESS
```

## Files Modified

| File | Action |
|------|--------|
| `scripts/dream_consolidate.py` | Rewritten v3.1 (local stack + docker exec proxy) |
| `scripts/dream_cron_report.sh` | Updated for local stack + docker exec health check |
| `scripts/dream_consolidate.py.*.bak` | Backup of v3.0 |
| Cron job `b7da1719f272` | Updated name + workdir |
| SKILL.md frontmatter | v3.0 -> v3.1 |
