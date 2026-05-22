# Mem0 Unified Memory Restore Report

**Date:** 2026-05-17
**Status:** UNIFIED_MEM0_RESTORE_COMPLETE

## Decision

One active memory backend: **Mem0 Cloud**.
No separate databases. No per-project stores. No Holographic. No Honcho.
Context preserved via metadata tags only.

## Import Summary

| Metric | Count |
|--------|------:|
| Original manifest items | 2,394 |
| Import candidates (CRITICAL + USEFUL + useful ARCHIVE) | 1,784 |
| Blocked (DO_NOT_IMPORT label) | 7 |
| Blocked (secrets detected) | 0 |
| Blocked (garbage detected) | 2 |
| Skipped (duplicate of existing Mem0) | 1 |
| Skipped (internal dedup) | 33 |
| **Final import set** | **1,750** |
| **Successfully imported** | **1,750** |
| **Errors** | **0** |

## Import Method

- Format: Mem0 v2 messages API
- Endpoint: `POST https://api.mem0.ai/v1/memories/`
- Payload: `{"messages": [{"role": "user", "content": "..."}], "user_id": "luke-hermes", "agent_id": "hermes", "metadata": {...}}`
- Chunk size: 25 items with 0.3s pause
- Duration: ~18 minutes total (2 batches)

## Metadata Standard

Each imported memory includes:
- `project_scope`: trading, hermes, infrastructure, global
- `memory_source`: recovery_import
- `source_type`: legacy_db
- `confidence`: medium
- `import_batch`: unified_restore_20260517
- `legacy_origin`: holographic, honcho, hermes_legacy

## Project Scopes

| Scope | Description |
|-------|-------------|
| trading | FreqForge, Freqtrade, RiskGuard, Signal Bridge, Bitget |
| hermes | Mem0, Holographic legacy, Honcho, Dream Mode |
| infrastructure | Docker, Caddy, Tailscale, Hetzner, ki-fabrik |
| global | Cross-cutting facts, user preferences, decisions |

## Retrieval Verification (8/8 PASS)

| Topic | Score | Result |
|-------|-------|--------|
| Mem0 architecture | 0.90 | PASS |
| Holographic legacy | 0.90 | PASS |
| Trading/RiskGuard | 0.90 | PASS |
| Infrastructure | 0.90 | PASS |
| Dry-run safety | 0.90 | PASS |
| FreqForge shadow | 0.90 | PASS |
| Exchange/Bitget | 0.90 | PASS |
| Confidence threshold | 0.90 | PASS |

## Architecture

```
Active:    Mem0 Cloud (api.mem0.ai, ~1,850+ memories)
Legacy:    Holographic memory_store.db (LEGACY_ONLY, not active)
Legacy:    Honcho (DECOMMISSIONED)
Local:     MEMORY.md / USER.md (session injection, supplementary)
```

## Files

- `docs/context/mem0-unified-memory-restore-20260517.md` — This report
- `docs/context/mem0-unified-import-log-20260517.json` — Import log
- `docs/context/mem0-cloud-final-architecture-20260517.md` — Architecture doc
- `docs/context/mem0-recovery-top25-review-20260517.md` — Top-25 review (superseded by full import)
