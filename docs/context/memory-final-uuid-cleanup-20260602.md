# Memory Final UUID-Based Cleanup Report

**Date:** 2026-06-02T14:20Z
**Task:** Safe deletion of 61 quarantine DELETE_CANDIDATE memories via UUID-only method.

## Executive Verdict: GREEN

61 DELETE_CANDIDATE memories removed via explicit UUID allowlist.
0 semantic-search-based mutations performed.
0 UNCERTAIN memories affected.
0 KEEP memories affected.
0 genuine durable facts lost.

## Phase 1: Preflight

| Check | Status |
|-------|--------|
| Backup manifest exists (52KB) | PASS |
| Backup reject IDs (107 UUIDs) | PASS |
| Backup quarantine IDs (77 UUIDs) | PASS |
| Mem0 API health | PASS (local-mem0, qdrant, ollama) |
| Current memory count before deletion | 1039 |
| DELETE_CANDIDATE UUID count | 61 (matches expected) |
| UUID uniqueness | PASS (0 duplicates) |
| No KEEP IDs in DELETE list | PASS |
| No UNCERTAIN IDs in DELETE list | PASS |
| Backup readable | PASS |

## Phase 2: UUID-Only Guardrail

Added `MEMORY_MUTATION_UUID_ONLY_GUARD_ACTIVE` marker and docstring rule to:
- `/opt/data/profiles/orchestrator/scripts/memory_hygiene_monitor.py`
- `/opt/data/profiles/orchestrator/scripts/memory_backfill.py`

Rule: Memory mutations (delete, rewrite, quarantine) MUST use explicit UUID
allowlists only. Semantic search results MUST NEVER be accepted as deletion
targets. If a deletion function receives a search query instead of UUIDs,
it MUST raise a hard error.

## Phase 3: Dry Run

| Metric | Value |
|--------|-------|
| Before count | 1039 |
| Target UUIDs | 61 |
| Expected after | 978 |
| Risk assessment | LOW (1 item has "confirmed" keyword but is stale nomic-embed ref) |

### Classification Distribution of 61 DELETE_CANDIDATE

| Reason | Count |
|--------|-------|
| cron_job_with_id | 32 |
| docker_network_detail | 5 |
| ip_address | 4 |
| stale_embedding_model | 4 |
| healthcheck | 4 |
| stale_mem0_cloud_ref | 4 |
| bind_mount_detail | 2 |
| port_number | 2 |
| mem0_cloud_quota_note | 2 |
| operational_quota_note | 1 |
| permission_error | 1 |

### Note on c5164fb6
Contains "confirmed" (a decision keyword) but references nomic-embed-text,
a stale embedding model. The canonical fact ("local Mem0 stack with Qdrant +
Ollama") was already stored as a separate memory. No data loss.

## Phase 4: UUID Deletion

| Metric | Value |
|--------|-------|
| Method | `DELETE /memories/{uuid}?user_id=luke-hermes` |
| Total targets | 61 |
| Deleted | 61 |
| Already gone | 0 |
| Failed | 0 |
| Errors | 0 |
| Before | 1039 |
| After | 978 |
| Match | YES (978 = 978) |
| Semantic search used | NEVER |

All 61 UUIDs deleted successfully via direct UUID API call. No search queries
were used at any point during this operation.

## Phase 5: Post-Validation

| Check | Status |
|-------|--------|
| Final memory count | 978 (expected 978) |
| Deleted UUIDs gone | 61/61 (0 still present) |
| UNCERTAIN memories untouched | 14/14 |
| KEEP memories untouched | Present in remaining set |
| Hygiene monitor | WARNING (19 hits — expected, from User-states pattern) |
| Backfill regression | CLEAN (43 sessions, 0 noise stored) |
| Semantic mutations | 0 |

### Hygiene Monitor Note
19 hits are from "User states/reports/notes" memories containing operational
terms ("cron job", "bind mount"). These are NOT new contamination — they are
the 56 UNCERTAIN items from the Phase 4 review of the User-states pattern.
No action needed; they will be reviewed separately.

## Deleted UUIDs

All 61 UUIDs are documented in:
```
/opt/data/profiles/orchestrator/skills/maintenance/dream-mode/backups/20260602T-phase7-delete-candidate-uuids.txt
```

## Failed UUIDs

None.

## Remaining Open Items

| Priority | Item | Status |
|----------|------|--------|
| P3 | 14 remaining quarantine items (KEEP + UNCERTAIN) | Untouched, documented |
| P3 | 56 UNCERTAIN "User states/reports/notes" memories | No action this phase |
| P3 | 19 REWRITE_AS_CANONICAL memories | No action this phase |
| P4 | DeprecationWarning: datetime.utcfromtimestamp in backfill | Low priority |

## Memory Quality Trajectory

| Phase | Count | Active Quality | Notes |
|-------|-------|---------------|-------|
| Initial | 1166 | ~84% | Before any cleanup |
| After Phase 7 (reject) | 1058 | ~93% | 107 noise deleted |
| After incident recovery | 1039 | ~94% | 5 genuine restored |
| After Phase 7b (quarantine) | 978 | ~96% | 61 operational deleted |

## Permanent Rules Established

1. MEMORY_MUTATION_UUID_ONLY_GUARD_ACTIVE — all memory mutations use UUID allowlists only.
2. Semantic search is for READ-ONLY operations (search, classify, audit).
3. Any function that deletes memories MUST require explicit UUIDs as input.
4. Restore tests MUST use unique markers that don't semantically overlap with existing memories.
