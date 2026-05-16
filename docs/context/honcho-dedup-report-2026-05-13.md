# Honcho Safe Exact-Deduplication Report — 2026-05-13

## Executive Summary

Phase-gated exact deduplication of Honcho `documents` table. 21 cross-observer duplicate records removed. All validation gates passed. Root cause identified: `prevent_document_duplicates()` trigger includes `observer` in dedup key, allowing identical content from different observers to bypass dedup.

## Actions Taken

1. **Phase 0** — Preflight metrics captured, timestamped pg_dump created
2. **Phase 1** — Schema discovery: identified trigger function `prevent_document_duplicates()` as the dedup mechanism
3. **Phase 2** — Dry-run: 21 rows to purge, 0 unique content at risk
4. **Phase 3** — Controlled DELETE in transaction: 21 rows purged (match), VACUUM ANALYZE
5. **Phase 4** — Post-dedup validation: search/embeddings/persistence all PASS
6. **Phase 5** — honcho_conclude tool-surface was stale at health-check time, resolved during session
7. **Phase 6** — Root cause: cross-observer duplication from multi-profile workspace

## Backup Location and Checksum

| Property | Value |
|----------|-------|
| Path | `/home/hermes/honcho-backups/pre_dedup_20260513T2024Z.sql` |
| Size | 64 MB |
| SHA256 | `4d3434fb471ffa3dcd151e5a7e2b84be6d2ac533ebf6855b022a4c223c22bf8a` |
| Format | pg_dump (documents table only) |
| Header/Footer | Valid |

## Before/After Counts

| Metric | Before (16:32 UTC) | After Quality Guard (18:00) | After Dedup (20:27 UTC) |
|--------|-------------------:|----------------------------:|------------------------:|
| Total docs | 5,592 | ~3,296 | 3,305 |
| Unique content | 2,882 | ~3,290 | 3,305 |
| Exact dupes | 2,573 (47.3%) | 6 (0.2%) | 0 (0.0%) |
| Embedding coverage | 100% | 100% | 100% |
| DB size | 805 MB | — | — |

Note: Quality guard (`honcho-memory-quality-guard` cron at 18:00 UTC) removed the bulk of duplicates (~2,296). This operation handled the residual 21 cross-observer dupes the guard missed.

## Deleted Duplicate Count

**21 exact duplicates** — all cross-observer:
- 19/21: `Luke` ↔ `hermes-agent` (identical content, different observer)
- 1/21: `hermes-agent` ↔ `mira-agent` (also different level: explicit vs deductive)
- 1/21: `orchestrator` ↔ `trading-agent` (also different level: explicit vs deductive)

## Validation Results

| Dimension | Result |
|-----------|--------|
| Container status (5/5) | PASS |
| Exact duplicates | 0 |
| Embedding coverage | 3,305/3,305 = 100% |
| Level breakdown | explicit 2,355 / deductive 602 / inductive 348 |
| Semantic search (FreqForge) | PASS — ranked results returned |
| Semantic search (Hard-Limits) | PASS — confidence 0.60 + 60 paper trades retrievable |
| Cross-session persistence | PASS — deployment rule correctly recalled |
| API health | PASS — HTTP 200 responses |
| Deriver | PASS — sync_vectors cycling every 5 min |
| VACUUM ANALYZE | Complete |

## honcho_conclude Status

- **Health check (16:32 UTC):** FAIL — "Failed to save conclusion" (stale provider/session)
- **Post-dedup (20:27 UTC):** PASS — conclusion saved and searchable
- **Classification:** Stale Hermes provider instance in the control-plane session, not a Honcho backend failure
- **Resolution:** Self-healed during session (provider re-initialized)

## Root Cause Findings

### Primary Cause: Trigger Dedup Scope Too Narrow

```sql
-- Current trigger function (prevent_document_duplicates):
WHERE workspace_name = NEW.workspace_name
  AND observer = NEW.observer          -- ← THIS IS THE PROBLEM
  AND observed = NEW.observed
  AND level = NEW.level
  AND content = NEW.content
  AND deleted_at IS NULL;
```

**Impact:** Same factual content written by different observers (e.g., "Luke" vs "hermes-agent" from different Hermes profiles) bypasses the trigger entirely. With 6+ active profiles sharing workspace `hermes`, this produces systematic cross-observer duplicates.

**Evidence:**
- `times_derived = 1` for ALL 3,303 docs — trigger has NEVER incremented the counter
- 19/21 duplicates were `Luke` ↔ `hermes-agent` with identical content
- ~1,062 new docs/24h across 6 observers

### Contributing Factors

1. Multi-profile workspace architecture (6 profiles → 6+ observer names)
2. Deriver processes shared conversation context from all profiles
3. MQG patch controls procedural noise but can't prevent cross-observer duplication

### Recommended Permanent Fix

**Option 1 (Recommended): Modify trigger to exclude `observer`**

```sql
CREATE OR REPLACE FUNCTION prevent_document_duplicates()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE documents
    SET times_derived = COALESCE(times_derived, 1) + 1,
        created_at = NOW()
    WHERE workspace_name = NEW.workspace_name
      AND observed = NEW.observed
      AND level = NEW.level
      AND content = NEW.content
      AND deleted_at IS NULL;

    IF FOUND THEN
        RETURN NULL;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
```

**Risk:** Low. Factual observations don't need per-observer identity. The content itself is the dedup key.

**Option 2 (Belt-and-suspenders): Add partial unique index**

```sql
CREATE UNIQUE INDEX idx_documents_content_unique
ON documents (content, workspace_name, level, observed)
WHERE deleted_at IS NULL;
```

**Risk:** Medium. Requires Honcho's ORM to handle constraint violations gracefully.

## Rollback Notes

```bash
# Restore from backup if needed:
docker exec -i honcho-database-1 psql -U postgres postgres < \
  /home/hermes/honcho-backups/pre_dedup_20260513T2024Z.sql
```

Backup contains only the `documents` table (pg_dump --table=documents). If a full restore is needed, use the 12-May full backup instead.

## Active Mitigations

| Mitigation | Schedule | Last Run | Status |
|------------|----------|----------|--------|
| `honcho-memory-quality-guard` cron | 06:00, 18:00 UTC | 2026-05-13 18:00 UTC | OK |
| `honcho-weekly-dedupe` cron | Mondays 03:00 UTC | Not yet run | Scheduled |
| MQG deriver patch | Persistent bind mount | Active | Mounted, ro |
| Hourly watchdog | Every hour | 2026-05-13 20:00 UTC | OK |
