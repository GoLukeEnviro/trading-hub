# Hermes Memory System — Frozen State Declaration

**Date:** 2026-05-18 21:21 UTC
**Status:** FROZEN — Audit PASS, Snapshot Created
**Reference:** `hermes-memory-system-full-audit-20260518.md`

---

## Frozen Stack Configuration

| Component | Value | Notes |
|-----------|-------|-------|
| **Embedding model** | `nomic-embed-text:latest` | Local via Ollama |
| **Embedding dimension** | **768** | Cosine distance |
| **LLM extraction** | `gpt-oss:120b` | Ollama Cloud (`https://ollama.com/v1`) |
| **Vector store** | Qdrant | Local, collection `hermes_memories` |
| **Qdrant points** | **481** | 198 curated import + 20 prior + 3 audit + misc |
| **Mem0 Cloud** | **INACTIVE** | Zero calls, zero dependency |
| **Hermes provider** | `_LocalMem0Client` | HTTP to mem0-local-api:8787 |
| **Container network** | `hermes_memory` + `ki-fabrik` | Docker DNS internal |

---

## Audit Result

**FULL AUDIT: PASS — STACK IS OPERATIONAL**

15-phase audit completed 2026-05-18 21:15 UTC. All 14 success criteria met.
See: `hermes-memory-system-full-audit-20260518.md`

---

## Qdrant Snapshot

| Property | Value |
|----------|-------|
| Name | `hermes_memories-1874142023429158-2026-05-18-21-20-48.snapshot` |
| Size | 4,760 KB |
| Created | 2026-05-18T21:20:49 |
| Checksum | `372ec4fa4552e8f9a0c365efbf1a40e651823818cbf624918289d9f26eca5290` |

Previous snapshot also available:
- `hermes_memories-1874142023429158-2026-05-18-20-04-23.snapshot` (4,720 KB)

---

## Performance Baseline (Frozen)

| Operation | Latency | Notes |
|-----------|---------|-------|
| mem0_conclude (write) | ~9s | Cloud LLM extraction |
| mem0_search (read) | ~0.06s | Local embedding + Qdrant |
| mem0_profile (list) | <0.1s | Qdrant scroll |

---

## WARNING: Do NOT Switch Embedding Models Without Migration

The Qdrant collection `hermes_memories` uses **768-dimensional vectors** from
`nomic-embed-text:latest`. Switching to `mxbai-embed-large:latest` (1024d) or
any other model would require:

1. Deleting the existing `hermes_memories` collection
2. Recreating it with new dimensions
3. Re-importing all 198 curated memories from the JSONL shortlist
4. Re-adding the 20 original memories
5. Full re-validation (E2E gate: write + search, score > 0.5)

**The `mxbai-embed-large:latest` model IS pulled locally in Ollama but is NOT active.**

---

## Documentation Corrections Applied

Two reports from the import session incorrectly stated `mxbai-embed-large:latest` (1024d):
- `memory-migration-staging/curated-import-shortlist-report-20260518.md` — superseding note added
- `memory-migration-staging/curated-import-final-report-20260518.md` — superseding note added

JSON manifest/recovery files left unmodified (historical records of what was planned).

---

## Health Check (Post-Snapshot)

```
mem0-local-api: ok (cloud_required: false)
qdrant: green (481 points)
ollama: healthy
hermes-agent: running
```

---

*This document is the authoritative reference for the frozen Hermes memory stack state.*
*Any changes to embedding model, LLM model, or collection structure require a new audit cycle.*
