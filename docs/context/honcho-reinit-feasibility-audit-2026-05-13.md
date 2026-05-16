# Honcho Repository Re-Initialization Feasibility Audit

**Date:** 2026-05-13 | **Mode:** Read-Only Planning | **Status:** COMPLETE

---

## Executive Summary

**Recommendation: PATCH CURRENT DEPLOYMENT — do NOT rebuild from upstream yet.**

The current Honcho deployment at `/opt/honcho/` is a **clean git clone of `plastic-labs/honcho` main branch** (commit `ad7c1b3`, 6 May 2026). It is NOT a fork, NOT manually assembled, and NOT image-only. It is the full upstream source tree with local `docker-compose.yml` and `.env` overrides, plus two local patches (deriver prompt + CRUD trigger).

The duplicate regression root cause is **known and fixable** (trigger scope too narrow, upstream bug #557/#444). The upstream does not yet have a definitive fix for cross-observer deduplication. Rebuilding from upstream would not solve the problem and would introduce significant migration risk for no functional gain.

The highest-ROI path: **modify the trigger, tune the quality guard, and track upstream PR #430 / #557 for a proper app-level fix.**

---

## Current Production State

### Container Map

| Container | Image | Upstream Match | Local Modifications |
|-----------|-------|----------------|---------------------|
| `honcho-api-1` | `honcho-api` (built from source) | Exact — Dockerfile + src/ at commit `ad7c1b3` | Source mounted RW at `/app` via bind mount |
| `honcho-deriver-1` | `honcho-deriver` (built from source) | Exact — same Dockerfile | 1 file: `/app/src/deriver/prompts.py` → ro bind mount from `/opt/honcho/patches/deriver/prompts.py` |
| `honcho-database-1` | `pgvector/pgvector:pg15` | Standard upstream image | init.sql + manual trigger `prevent_document_duplicates()` |
| `honcho-redis-1` | `redis:8.2` | Standard upstream image | None |
| `honcho-ollama` | `ollama/ollama:latest` | Local addition (not in upstream compose) | Embedding model `rjmalagon/gte-qwen2-1.5d-instruct-embed-f16` |

### Source Provenance

```
/opt/honcho/  =  git clone of plastic-labs/honcho (main branch)
   HEAD:      ad7c1b3040382d5f1e866d8dfa9d8a9978488768 (6 May 2026)
   Version:   3.0.6 (from pyproject.toml)
   License:   AGPLv3
   Python:    3.11 (specified), 3.13 in Dockerfile
   Build:     Local docker build (Dockerfile present, not prebuilt image)
   Migrations: 25 files, head = e4eba9cfaa6f (matches DB)
   Networks:  ki-fabrik (external, shared with Freqtrade) + honcho-internal (bridge)
```

**Local patches (2 files):**
1. `/opt/honcho/patches/deriver/prompts.py` — MQG v2.0.0 Memory Quality Guard (6-gate reject-by-default, ro bind mount)
2. `/opt/honcho/patches/crud/` — empty directory (placeholder for future CRUD trigger patch)

**Manual DB modifications:**
1. `prevent_document_duplicates()` trigger function — added manually (not in any migration)
2. `document_duplicate_upsert_trigger` trigger on `documents` table

### Data Volume Map

| Volume | Driver | Purpose | Size Risk |
|--------|--------|---------|-----------|
| `honcho_pgdata` | local | PostgreSQL data | 805 MB |
| `honcho_venv` | local | Python venv (cached) | Rebuildable |
| `honcho_redis-data` | local | Redis cache | Ephemeral |
| `honcho_ollama_data` | local | Embedding model files | Rebuildable |

### Hermes Integration

```
Config path:    ~/.hermes/honcho.json (global) + ~/.hermes/profiles/orchestrator/honcho.json (profile-local)
Workspace:      hermes
Base URL:       http://honcho-api-1:8000 (Docker internal)
Auth:           Bearer local
Profiles:       5 profiles connected (orchestrator, trading, mira, weatherbot, default)
Observers:      Luke, hermes-agent, trading-agent, orchestrator, hermes-orchestrator, mira-agent
```

### Database State

| Table | Rows | Notes |
|-------|------|-------|
| workspaces | 4 | hermes + 3 others |
| peers | 13 | Multi-profile peer names |
| sessions | 61 | Per-repo strategy |
| messages | 7,607 | Raw chat messages |
| documents | 3,328 | Active (non-deleted) |
| documents (soft-del) | 0 | All hard-deleted |
| collections | 26 | Observer-observed pairs |
| queue | 541 | Deriver processing queue |
| alembic_version | e4eba9cfaa6f | Current migration head |

---

## Upstream Repository Findings

### Version and Activity

- **Latest version:** 3.0.6 (pyproject.toml in deployed source)
- **Latest upstream activity:** May 11, 2026 (5 days newer than deployed commit)
- **Stars:** 3,500+ | **Forks:** 404
- **Active contributors:** ~10+ (Plastic Labs team + community)

### Key Upstream Changes Since Deploy (May 6 → May 11)

| Date | PR | Impact |
|------|-----|--------|
| May 11 | #609 | **Deriver custom instructions** — allows user-defined deriver prompts (replaces our MQG patch) |
| May 11 | #647 | Fix: model-aware tokenizer, skip empty messages |
| May 11 | #656 | Fix: dialectic level defaults merging |
| May 6 | #652 | Fix: N+1 query in dialectic agent calls (performance) |

### Upstream Deduplication Status (CRITICAL FINDING)

**The upstream has NO built-in deduplication for documents.** There is no `prevent_document_duplicates()` trigger in any migration or source file.

The duplicate problem is a **known upstream issue**:

1. **Issue #557** (Apr 12, 2026 — OPEN): "Duplicate conclusions (~14% of total). 54 unique strings appear multiple times across 762 conclusions, totaling 110 duplicate entries." Same pattern as our 47% duplicate ratio.

2. **Issue #444** (Mar 23, 2026 — OPEN): "Deriver creates ephemeral session events as permanent conclusions." The deriver does not distinguish durable facts from session noise. Recursive bloat (observations about the cleanup itself).

3. **PR #430** (in development): Deriver custom instructions — will allow operator-tunable filtering at extraction time. **This is the upstream fix for our MQG patch.**

4. **PR #445** (merged): Changed deriver prompt from "extract all observations" to "extract only durable observations" — but deduplication itself is not addressed.

5. **PR #573** (Apr 30): Major dreamer subsystem overhaul — fixes feedback loops in the dreaming/consolidation system that could cause document count inflation.

**Maintainer stance (from #444):** "We take a maximalist approach to storing explicit conclusions and use the dreaming agent for consolidation. We aren't interested in deleting old conclusions." This means **upstream will not add a dedup trigger** — they expect the dreamer to handle it.

### Upstream Service Topology vs Production

| Component | Upstream | Production | Delta |
|-----------|----------|------------|-------|
| API | build from source | build from source (mounted) | Development mode (RW mount) |
| Deriver | build from source | build from source | 1 file patched (prompts.py) |
| Database | pgvector/pgvector:pg15 | pgvector/pgvector:pg15 | Identical + manual trigger |
| Redis | redis:8.2 | redis:8.2 | Identical |
| Ollama | Not in compose | ollama/ollama:latest | **Local addition** for embeddings |
| Networks | honcho-internal only | ki-fabrik + honcho-internal | **Local addition** for cross-service DNS |

---

## Gap Analysis

### What We Have That Upstream Doesn't

1. **Ollama embedding service** — upstream expects external embedding APIs (OpenAI, etc.). We run local embeddings via Ollama with `rjmalagon/gte-qwen2-1.5d-instruct-embed-f16`.

2. **ki-fabrik network integration** — upstream compose only has `honcho-internal`. We added `ki-fabrik` (external) so Hermes containers can resolve `honcho-api-1` by DNS.

3. **`prevent_document_duplicates()` trigger** — manually added, not in any migration. This is a local fix for a known upstream bug.

4. **MQG deriver prompt patch** — ro bind mount replacing the entire deriver prompt with a 6-gate reject-by-default system. Upstream PR #430 (custom instructions) will make this cleaner.

5. **Docker compose override** — `docker-compose.override.yml` adds model config env vars, Ollama service, network aliases, and the patches bind mount.

6. **Honcho watchdog** — `/opt/honcho/scripts/honcho_watchdog.sh` + host cron. Not upstream.

7. **Memory quality scripts** — `/opt/honcho/scripts/memory_quality_check.sh`. Not upstream.

### What Upstream Has That We're Missing (5 days of commits)

| Change | Risk of Not Having It | Action Needed |
|--------|----------------------|---------------|
| PR #609 (custom instructions) | LOW — our MQG patch covers this | Track for integration |
| PR #647 (skip empty messages) | LOW — edge case fix | Git pull when convenient |
| PR #656 (dialectic level defaults) | LOW — config fix | Git pull when convenient |
| PR #652 (N+1 query fix) | MEDIUM — performance under load | Git pull when convenient |

### Schema Compatibility

Our DB migration head (`e4eba9cfaa6f`) matches the latest upstream migration. **No schema drift.** The only DB modification is the manual trigger, which is not in any migration file and would survive a `git pull` + rebuild.

---

## License / AGPL Notes

| Aspect | Assessment |
|--------|------------|
| License | GNU AGPLv3 |
| Internal-only deployment | Permitted — no source distribution obligation for private use |
| Modified source obligation | If the service is accessible over a network to users, source must be offered |
| Our situation | Honcho is accessible only within the Docker network and via localhost. External access is through Hermes (which is our own code). **No source-availability obligation triggered** unless we expose the Honcho API to external users. |
| Fork strategy | **Recommended: GitHub fork** — best for tracking upstream, clean PR flow, patch management |
| Private fork | Acceptable under AGPL — the fork itself can be private since we're not distributing the software to third parties |

**Legal review flag:** If the Honcho API were ever exposed publicly (e.g., via Tailscale Funnel), AGPL §13 would require offering source code to users. Current architecture (internal Docker network only) is safe.

---

## Migration Feasibility

### Option A: Full DB Restore (Easiest)

| Aspect | Assessment |
|--------|------------|
| Schema compatibility | **Exact match** — same Alembic head `e4eba9cfaa6f` |
| pg_dump/pg_restore | **Compatible** — same PostgreSQL 15 + pgvector |
| Data integrity | Carries all 3,328 docs, 7,607 messages, 61 sessions |
| Duplicate risk | Carries current clean state (0 dupes as of last dedup) |
| Embedding preservation | **Yes** — embeddings stored in documents table, survive restore |
| Workspace/peer stability | **Yes** — workspace `hermes`, all peer names, session IDs preserved |
| Hermes config impact | **None** — same base_url, workspace_id, peer names |
| Effort | ~30 minutes |
| Risk | **LOW** |

### Option B: Selective Export/Import (Cleanest)

| Aspect | Assessment |
|--------|------------|
| Effort | ~4 hours (custom scripts) |
| Clean result | Yes — only canonical docs, no legacy noise |
| Risk | **MEDIUM** — custom scripts need testing, FK ordering is complex |

### Option C: Fresh Start (Fastest)

| Aspect | Assessment |
|--------|------------|
| Data loss | **ALL** memory — 3,328 documents, peer cards, inductive/deductive layers |
| Rehydration | Manual — would need to re-conclude core facts |
| Effort | ~1 hour for stack setup, ~4 hours for memory rehydration |
| Risk | **HIGH** — loses months of accumulated inductive/deductive reasoning |

### Recommended Migration Method

**Option A (Full DB Restore)** — schema is identical, data is clean, embeddings preserved. Only needed if switching to a rebuilt stack.

---

## Staging Stack Plan

If a source-controlled rebuild is eventually desired:

```
Directory:     /home/hermes/projects/honcho-deploy/
Git remote:    github.com/GoLukeEnviro/honcho (private fork of plastic-labs/honcho)
Branch:        luke/production (tracks main + local patches)

Staging services:
  honcho-staging-api      127.0.0.1:8010  (no ki-fabrik, isolated)
  honcho-staging-deriver  (internal only)
  honcho-staging-db       127.0.0.1:5433  (separate volume: honcho_staging_pgdata)
  honcho-staging-redis    127.0.0.1:6380  (separate volume: honcho_staging_redis)

Staging volumes:
  honcho_staging_pgdata
  honcho_staging_redis

Staging env:
  Isolated .env.staging with separate API key
  No Hermes profile points to staging

Smoke-test checklist:
  1. API health check (GET /v3/workspaces)
  2. Workspace creation
  3. Peer creation
  4. Message ingestion
  5. Deriver cycle (wait 5 min)
  6. Document count > 0
  7. Semantic search returns ranked results
  8. Embedding coverage 100%

Rollback:
  Simply stop staging containers. Production untouched.
```

---

## Effort and Risk Estimation

| Bucket | Time | Downtime | Risk | Recommendation |
|--------|------|----------|------|----------------|
| **Quick current repair** (trigger fix + quality guard tuning) | 1h | 0 min | LOW | **DO NOW** |
| **Git pull to latest upstream** (May 6 → May 11, 5 days) | 2h | ~5 min (rebuild) | LOW | **DO THIS WEEK** |
| **Integrate PR #609 (custom instructions)** (replace MQG patch) | 3h | ~5 min (rebuild) | LOW | **TRACK, do after upstream stabilizes** |
| **GitHub fork + deployment repo** | 2h | 0 min | LOW | **DO THIS WEEK** |
| **Clean staging from fork** | 4h | 0 min | LOW | **NICE TO HAVE** |
| **Full rebuild with DB restore** | 4h | ~15 min | MEDIUM | **NOT NEEDED NOW** |
| **Fresh start, no migration** | 1h stack + 4h rehydration | 0 min (parallel) | HIGH | **DO NOT DO** |

---

## Recommended Path

### DO NOW (this session or next)

1. **Fix the trigger** — modify `prevent_document_duplicates()` to exclude `observer` from the dedup WHERE clause. This is the permanent fix for cross-observer duplication.

2. **Keep quality guard cron** — `honcho-memory-quality-guard` at 06:00/18:00 UTC as belt-and-suspenders.

3. **Document the trigger in a migration** — create a proper Alembic migration file so the trigger survives future schema upgrades.

### DO THIS WEEK

4. **Create a GitHub fork** — `GoLukeEnviro/honcho` (private), add as remote to `/opt/honcho/`.

5. **Branch strategy** — `luke/production` branch with local patches (trigger migration, MQG prompt, watchdog script, compose overrides).

6. **Git pull to latest** — update from commit `ad7c1b3` (May 6) to latest (May 11+). Rebuild API + deriver images.

### TRACK (upstream)

7. **PR #430 / #609** — custom deriver instructions. When merged, replace our MQG bind mount with proper custom_instructions config.

8. **Issue #557** — upstream duplicate conclusions fix. When resolved, evaluate if our trigger is still needed.

9. **PR #573** — dreamer feedback loop fix. May improve document count stability.

### DO NOT DO

- **Do NOT rebuild from scratch** — current deployment IS the upstream source, cleanly cloned.
- **Do NOT start fresh without migration** — loses 3,328 documents including 950 deductive+inductive gold facts.
- **Do NOT add a DB unique index** on content — Honcho's ORM doesn't handle constraint violations gracefully.
- **Do NOT switch to prebuilt images** — we need source-mount development mode for the MQG patch.
- **Do NOT modify Hermes architecture** to work around Honcho issues.

---

## Next Agent Prompt Needed

If Luke approves the trigger fix, the next prompt would be:

> "Modify the `prevent_document_duplicates()` trigger function in the Honcho database to exclude `observer` from the dedup WHERE clause. Create a proper Alembic migration file at `/opt/honcho/migrations/versions/` that creates this trigger. Test with a harmless duplicate write. Do not restart production services — the trigger change takes effect immediately for new INSERTs."

---

## Rollback Notes

Current state is fully backed up:
- `pre_dedup_20260513T2024Z.sql` — 64 MB, SHA256 `4d3434fb...`
- `/opt/honcho/` is a git repo — any file change is revertable via `git checkout`
- Docker volumes are independent of container lifecycle

No production changes were made during this audit.
