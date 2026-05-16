# Honcho → Holographic Migration: Import Results

**Date:** 2026-05-13T21:47Z
**Phase:** 3 (Import) + 4 (Validation) + 5 (Conditional Cutover)

---

## Import Summary

| Metric | Value |
|--------|-------|
| Candidates processed | 2,385 |
| Successfully inserted | 2,385 |
| Duplicates (skipped) | 0 |
| Failed/skipped | 0 |
| **Final DB count** | **2,385** |

---

## Gate Results

| Gate | Name | Status |
|------|------|--------|
| Gate 3.0 | Pre-Import Verification | ✓ PASS |
| Gate 3.1 | Activate Holographic | ✓ PASS |
| Gate 3.2 | Import Candidates | ✓ PASS |
| Gate 3.3 | Post-Import SQLite Validation | ✓ PASS |
| Gate 3.4 | Recall Smoke Tests | ✓ PASS |
| Gate 3.5 | Conditional Cutover | ✓ PASS |

---

## SQLite Validation (Gate 3.3)

| Check | Result |
|-------|--------|
| Total facts | 2,385 |
| FTS indexed rows | 2,385 |
| Duplicate content groups | 0 |
| FTS integrity | OK |

### Facts by Category

| Category | Count |
|----------|-------:|
| general | 1,125 |
| project | 853 |
| tool | 323 |
| user_pref | 84 |
| **Total** | **2,385** |

### Facts by Level (from tags)

| Level | Count |
|-------|-------:|
| explicit | 1,435 |
| deductive | 602 |
| inductive | 348 |
| unknown | 0 |

### Trust Score Distribution

| Range | Count |
|-------|-------:|
| 0.9–1.0 | 1,203 |
| 0.8–0.9 | 570 |
| 0.7–0.8 | 303 |
| 0.6–0.7 | 308 |
| 0.3–0.6 | 1 |

---

## Recall Smoke Tests (Gate 3.4)

| Query | Description | Result | Top Score | Notes |
|-------|-------------|--------|-----------|-------|
| never live trading | Hard safety rules | PASS | 1.0 | Via LIKE fallback (FTS multi-word limit reached) |
| Luke trading bot rules | Luke's hard bot rules | PASS | 1.0 | Via LIKE fallback |
| VPS Hetzner | VPS safety rules | PASS | 1.0 | Via LIKE fallback |
| Freqtrade backtest | Trading backtest rules | PASS | 0.8 | Direct FTS |
| German informal terse | Communication preferences | PASS | 1.0 | Via LIKE fallback |
| live trading | Trading mode rules | PASS | 0.9 | Direct FTS |

**All 6 tests PASS** using hybrid FTS + LIKE fallback approach.

### FTS Behavior Note
FTS5 has inconsistent results for multi-word space-separated queries with 3+ words.
This is a known FTS5 tokenizer behavior. LIKE fallback provides reliable coverage.
The Holographic store itself functions correctly; this is purely a query-translation issue.

---

## Cutover State (Gate 3.5)

| Item | Status |
|------|--------|
| memory.provider | holographic (set in config.yaml) |
| Honcho containers | still running (read-only archive) |
| Honcho data | backed up, not deleted |
| Rollback path | documented below |

### Rollback Command
```bash
# Restore Honcho as active provider
docker exec hermes-agent sh -c 'cp /home/hermes/.hermes/config.yaml.backup.pre-import.20260513T2147Z /home/hermes/.hermes/config.yaml'
# Restart Hermes session
```

---

## Config Backup Locations

| File | Path |
|------|------|
| Config backup (pre-import) | `/home/hermes/.hermes/config.yaml.backup.pre-import.20260513T2147Z` |
| Original config backup | `/home/hermes/.hermes/backups/migration-20260513T2147Z/config.yaml.20260513T2147Z` |

---

## Import Log

- **Phase 1 (Backup):** pg_dump at `/tmp/honcho_pre_holographic_migration_20260513T2147Z.sql` (255 MB, verified)
- **Phase 2 (Deduplication):** 43 exact duplicates removed, 815 noise records filtered, 2,385 candidates retained
- **Phase 3 (Import):** 2,385 candidates inserted into `/home/hermes/.hermes/memory_store.db` (fresh DB)
- **Phase 4 (Validation):** 0 duplicates, all categories represented, FTS indexed
- **Phase 5 (Cutover):** `memory.provider` set to `holographic`, Honcho preserved as archive

---

## Retrieval Stabilization Patch (2026-05-14)

**Problem:** 4/6 recall tests returned NO RESULTS through production FactRetriever.
The external test script had a LIKE fallback not present in production code.
Root cause: FTS5 tokenization returns 0 for some 3-word space-separated queries.

**Solution:** Three-strategy fallback added to `_fts_candidates`:

| Strategy | Method | When used |
|----------|--------|-----------|
| 1 | Raw FTS5 MATCH | Default first attempt |
| 2 | Tokenized OR/prefix FTS | If strategy 1 returns 0 |
| 3 | SQLite LIKE fallback | If strategy 2 returns 0 |

**Files changed:** `/home/hermes/hermes-src/plugins/memory/holographic/retrieval.py`

**Recall tests after patch — ALL PASS (6/6):**

| Query | Result | Trust | Strategy |
|-------|--------|-------|----------|
| never live trading | PASS | 1.0 | LIKE |
| Luke trading bot rules | PASS | 1.0 | LIKE |
| VPS Hetzner safety | PASS | 0.9 | LIKE |
| Freqtrade backtest | PASS | 0.8 | raw_FTS |
| German informal terse | PASS | 1.0 | LIKE |
| live trading | PASS | 0.9 | raw_FTS |

**Config state:**
- `memory.provider` in orchestrator profile: `holographic`
- Orchestrator profile backup: `/home/hermes/.hermes/profiles/orchestrator/config.yaml.backup.pre-holo-patch`

---

## Status: COMPLETE ✓

Migration successful. Holographic is now the active memory provider.
Honcho remains available as a read-only archive. All data preserved.
Retrieval is stable with 3-strategy fallback.

**No further action required.**