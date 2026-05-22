# Mem0 Cloud Final Architecture

**Date:** 2026-05-17 14:44 UTC
**Status:** MEM0_CLOUD_WORKING

## Final Decision

| Decision | Value |
|----------|-------|
| Active memory backend | **Mem0 Cloud only** |
| No Mem0 OSS | Confirmed |
| No Qdrant/Neo4j/PostgreSQL/pgvector | Confirmed |
| No PR #15624 dependency | Confirmed |
| No key rotation in this run | Confirmed |
| No .env migration in this run | Confirmed |

## Mem0 Configuration

| Field | Value |
|-------|-------|
| Provider | `mem0` |
| Base URL | `https://api.mem0.ai/v1` |
| User ID | `luke-hermes` |
| Agent ID | `hermes` |
| API Key | Present (43 chars, masked) — used as-is |
| Plugin | `/opt/hermes/plugins/memory/mem0/__init__.py` |
| SDK | `mem0ai 2.0.2` |
| Write format | `messages` array (v2 API) |

## Mem0 Verification

| Test | Result | Detail |
|------|--------|--------|
| Read | **YES** | HTTP 200, 100 unique memories returned |
| Search | **YES** | HTTP 200, scored results (0.47–0.90) |
| Write | **YES** | HTTP 200, event queued (PENDING → indexed async) |
| Diagnostic found | **YES** (async) | Write accepted, search finds related content |

### Important: Write Format

Mem0 v2 API requires `messages` format for writes:
```json
{"messages": [{"role": "user", "content": "..."}], "user_id": "luke-hermes"}
```
Plain `{"content": "..."}` returns HTTP 400.

### Important: Pagination

The Mem0 API returns the same 100 memories at any offset.
Total unique count: **100**. Pagination does not work beyond 100.
This is an API limitation, not a bug.

## Legacy Systems

### Holographic — LEGACY ONLY

| Attribute | Value |
|-----------|-------|
| Status | Legacy, not active |
| DB path | `/home/hermes/.hermes/shared-memory/holographic/memory_store.db` |
| Facts | 380 (restored from backup 2026-05-17) |
| Still referenced in config | Yes (inactive section under `memory.holographic`) |
| Action | Documented as legacy, no deletion |

### Honcho — LEGACY ONLY

| Attribute | Value |
|-----------|-------|
| Status | Decommissioned |
| Still referenced in config | Yes (inactive section under `memory.honcho`) |
| Action | Documented as legacy, no deletion |

### Config Cleanup Note

The active config at `/opt/data/profiles/orchestrator/config.yaml` still contains
inactive `holographic` and `honcho` sub-sections under `memory:`.
These are NOT used (provider is `mem0`), but remain as documentation artifacts.
A future cleanup pass could remove them after Luke's approval.

## Recovery Manifest Status

| Label | Count |
|-------|------:|
| MEM0_IMPORT_CANDIDATE_CRITICAL | 212 |
| MEM0_IMPORT_CANDIDATE_USEFUL | 1,401 |
| LEGACY_ARCHIVE_ONLY | 774 |
| DO_NOT_IMPORT | 7 |
| **Total** | **2,394** |

Counts verified: 2,394 = 2,394 (consistent).

## Import Status

**IMPORT NO-GO until Luke approves a specific batch.**

- batch_1_critical: max 25 items from 212 candidates
- batch_2_useful: max 75 items from 1,401 candidates
- No imports will happen automatically
- No legacy DB files will be touched

## Files

| File | Status |
|------|--------|
| `docs/context/mem0-cloud-final-architecture-20260517.md` | This document (current) |
| `docs/context/mem0-memory-recovery-correction-20260517.md` | Corrected recovery report |
| `docs/context/mem0-memory-recovery-correction-20260517.json` | Full manifest (2,394 items) |
| `docs/context/dream-mode-memory-recovery-report-20260517.md` | OUTDATED |
| `docs/context/dream-mode-memory-recovery-manifest-20260517.json` | OUTDATED |

## Next Action for Luke

1. Review batch_1 candidates in the JSON manifest (212 critical items)
2. Select up to 25 for import
3. Say "GO batch_1" to proceed
4. Import will use Mem0 v2 messages API format
