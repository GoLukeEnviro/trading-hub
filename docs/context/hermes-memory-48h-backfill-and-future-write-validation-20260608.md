# Hermes Memory 48h Backfill + Future Persistence Validation

**Date:** 2026-06-08 UTC
**Window:** 2026-06-06T12:23:06Z → 2026-06-08T12:23:06Z
**Verdict:** YELLOW — write/recall path works, but one expected legacy smoke memory was not found exactly and one Dream Mode candidate no-op'd.
**Healthscore:** 84/100

## 1. Endpoint Baseline

- `/health`: HTTP 200
- `/memories/all`: HTTP 200
- `/memories/search`: HTTP 200
- `/memories/add`: HTTP 200 on productive writes in this run
- Runtime from `/health`: `backend=local-mem0`, `llm_model=gpt-oss:20b`, `embedder_model=qwen3-embedding:4b`, `cloud_required=false`
- Memory count before run: **64**
- Memory count after strict backfill phase: **66**
- Memory count after explicit future-write validation: **67**
- Final memory count after refinement pass: **70**

## 2. Source Discovery

Scanned meaningful sources modified in the last 48h, plus the live session DB:

- `/home/hermes/.hermes/state.db` — real Hermes sessions
- `/home/hermes/projects/trading/docs/context/hermes-memory-v2-curation-audit-20260607-103359.md`
- `/home/hermes/projects/trading/docs/context/mem0-final-memory-cleanup-20260607-045622.md`
- `/home/hermes/projects/trading/docs/context/mem0-dream-mode-20260607-043959.md`
- `/opt/data/profiles/orchestrator/skills/trading/local-memory-ops/references/mem0-openaiconfig-policy-repair-20260608.md`
- `/opt/data/profiles/orchestrator/skills/trading/local-memory-ops/references/mem0-extractor-rebuild-validation-20260608.md`
- `/opt/data/profiles/orchestrator/sessions/request_dump_20260607_184023_8c5a95_20260607_194244_152994.json`
- `/opt/data/profiles/orchestrator/sessions/request_dump_20260607_132544_9dfd93_20260607_153435_860146.json`
- additional context reports / request dumps under the same roots

Counts:
- meaningful sources included: **61**
- recent-but-excluded files: **1929**
- full machine-readable inventory: `/tmp/memory_backfill_20260608_report.json`

## 3. Candidate Curation Summary

### Strict phase
- durable backfill candidates extracted: **4**
- duplicates skipped: **1**
- uncertain deferred: **0**
- secret/sensitive candidates rejected: **0**
- write attempts accepted by API: **3**
- confirmed persisted + recalled from strict backfill: **2**
- one Dream Mode candidate returned `results: []` and did not persist

### Refinement phase
- extra durable candidates reviewed after initial underfill: **5**
- duplicates skipped in refinement: **1**
- additional confirmed persisted memories: **4**

### Rejected / non-durable examples
- `This is a temporary endpoint ping during memory verification.` → temporary smoke noise
- assistant-action facts (`Assistant created ...`) → rejected as non-user durable facts
- run-specific counters (`expected memory count before this operation: 65`) → transient
- historical cleanup counts (`66 -> 52`) → superseded report metrics, not canonical memory

## 4. Confirmed Written Memories

1. `883f6193-446c-4d31-adbe-1fb02c516846`
   - **Memory:** User performed a minimal repair on Hermes Local Mem0 on 2026-06-08, removing the invalid `response_format` field from OpenAIConfig and making the extraction policy schema-neutral.
   - **Source:** `mem0-openaiconfig-policy-repair-20260608.md`

2. `6f4af327-0370-4ee0-885b-7978c30cf148`
   - **Memory:** User wants Hermes session backfills to store only durable, deduplicated facts, explicitly excluding logs, assistant actions, temporary smoke facts, corrected assumptions, and duplicate memories.
   - **Source:** current 2026-06-08 session

3. `063860bd-a4fd-480d-a4be-4432f8867e41`
   - **Memory:** User requires Hermes memory fixes to be validated by proving that new memories can be written and recalled, not only by health endpoint checks.
   - **Source:** current 2026-06-08 session

4. `300dec7b-ad7f-4a69-8524-0941481837bd`
   - **Memory:** User's active local Mem0 extraction model is `gpt-oss:20b`.
   - **Source:** live `/health` on 2026-06-08

5. `431ad3db-6402-4a5c-ac9c-bfc6d2162f99`
   - **Memory:** User's minimal repair on Hermes Local Mem0 on 2026-06-08 restored `/memories/all`, `/memories/search`, and `/memories/add` from HTTP 500 to HTTP 200.
   - **Source:** `mem0-openaiconfig-policy-repair-20260608.md`

6. `3ea7bac4-0bd2-4e2e-a064-7dc852b35079`
   - **Memory:** User wants recent Hermes sessions backfilled into memory when extraction was broken, but only after durable-fact filtering and deduplication against existing memories.
   - **Source:** current 2026-06-08 session

## 5. Duplicate / No-op Findings

### Duplicates skipped
- active runtime stack fact (`green-mem0` + `green-qdrant` + `hermes_memories_v2` + `2560d`) was skipped as a near-duplicate of existing memory `c175b126-7e27-4ad5-b3e6-402d4f246b73`
- one endpoint-validation phrasing was skipped as a near-duplicate of the stronger new validation-rule memory `063860bd-a4fd-480d-a4be-4432f8867e41`

### No-op / partial failures
- Dream Mode dry-run candidate phrasing returned HTTP 200 but `result.results=[]` and did **not** become retrievable durable memory
- known legacy smoke-memory lookup did **not** find the exact expected phrase; only semantically related memories were returned

## 6. Validation Results

### Required checks
- `/health` → **200 PASS**
- `/memories/all` → **200 PASS**
- `/memories/search` → **200 PASS**
- `/memories/add` → **200 PASS**
- future write → **PASS** (`063860bd-a4fd-480d-a4be-4432f8867e41`)
- future recall → **PASS** (same memory recalled with score **1.0**)
- negative noise (`temporary endpoint ping`) → **PASS** by policy rejection / no durable write

### Known smoke-memory recall
- Query: `User prefers Hermes memory validation reports to include healthscore, rollback status, exact changed files, and Qdrant vector size.`
- Exact phrase recall: **FAIL**
- Semantic recall: **PARTIAL** — top hit was `063860bd-a4fd-480d-a4be-4432f8867e41` with score `0.7956`

## 7. Final Metrics Table

| Metric | Value |
|---|---:|
| Count vorher | 64 |
| Quellen gescannt | 61 |
| Kandidaten gefunden (strict backfill) | 4 |
| Kandidaten geprüft gesamt inkl. refinement | 9 |
| geschrieben, final bestätigt | 6 |
| Duplicates geskippt | 2 |
| rejected noise examples | 4 |
| Count nach strict backfill | 66 |
| Count nach future-write Test | 67 |
| Final Count nach Refinement | 70 |
| Recall-Test neue Facts | 6/6 bestätigt |
| `/memories/all` | 200 |
| `/memories/search` | 200 |
| `/memories/add` | 200 |

## 8. Remaining Risks

- The expected older smoke memory is not exactly recallable by phrase anymore.
- One Dream Mode fact phrasing still no-op'd despite HTTP 200.
- Two newly written backfill memories are semantically close and should be watched in future curation to avoid overlap growth.
- Net result is clearly better than pre-run, but not clean enough for a GREEN closure.

## 9. Artifacts

- Full structured evidence: `/tmp/memory_backfill_20260608_report.json`
- Human report: `/home/hermes/projects/trading/docs/context/hermes-memory-48h-backfill-and-future-write-validation-20260608.md`
