# C1 — Gate-0 Snapshot Fetcher + Contract Repair Evidence Report

**Date:** 2026-07-19
**Issue:** #653
**Branch:** `feat/c1-gate0-snapshot-fetcher-2026-07-19`
**Base:** `origin/main` at `7fad1bf`

## Four gaps addressed

### A. Wrong Bitget endpoint

**Problem:** `/api/v2/mix/market/candles` delivers only ~52 days of history. 18 months of data requires `/api/v2/mix/market/history-candles` (max 200 candles/request, max 90 days/query range).

**Fix:** `HISTORY_ENDPOINT = "/api/v2/mix/market/history-candles"` is the designated endpoint. The fetcher implements backward pagination: walks backward from `end` in chunks of 200 candles, automatically splitting the total date range into sub-ranges of ≤90 days.

### B. Circular manifest self-hash

**Problem:** `overall_sha256` hashing the manifest file that contains it creates a circular dependency.

**Fix:** The manifest JSON (`snapshot_manifest.json`) contains NO `overall_sha256` field. The SHA-256 of the manifest file is written as a detached sidecar: `snapshot_manifest.json.sha256`.

### C. Benchmark dataset undefined

**Problem:** `EvaluationBundleV1` requires `benchmark_candles` and `benchmark_snapshot_sha256`. A spot ticker is insufficient.

**Proposed (for C2 ratification):** BTCUSDT futures 15m as buy-and-hold benchmark — same data series as the primary asset, providing a market-return comparison baseline. This will be formally specified in the full `EvaluationManifestV1` instance during C2.

### D. No tested fetcher

**Problem:** Ad-hoc curl during A2 is risky; no tested, resumable, path-confined fetcher existed.

**Fix:** `self_improvement_v2/src/si_v2/research/gate0_snapshot_fetcher.py` — a complete, tested fetcher module.

## Fetcher module

| Feature | Implementation |
|---|---|
| Endpoint | `/api/v2/mix/market/history-candles` |
| Backward pagination | Chunks of `MAX_CANDLES_PER_REQUEST` (200), walks backward from `end` |
| Sub-range splitting | `_split_into_sub_ranges()` ensures ≤`MAX_QUERY_RANGE_DAYS` (90) per query |
| Boundary normalization | Timestamps snapped to 15m boundaries via `_normalize_timestamp()` |
| Deduplication | `dedup_and_sort()` removes duplicate (pair, timestamp) entries |
| Chronological sort | `dedup_and_sort()` sorts by (pair, timestamp) |
| Atomic writes | `write_snapshot()` writes to temp file, then `os.rename()` |
| Path confinement | All writes confined to `target_dir` only |
| Resumability | Idempotent: re-running fetch + dedup produces same result |
| SHA-256 sidecar | Per-file `.sha256` content hash |
| Canonical candle hash | `.canonical_sha256` compatible with `canonical_candle_hash()` |
| Detached manifest hash | `snapshot_manifest.json.sha256` sidecar (no circular dependency) |
| No credentials | `http_get` headers contain only `Accept: application/json` — verified by test |
| No auth headers | Test explicitly checks no key/secret/pass/auth/token headers |
| Retry with backoff | 429/5xx retried with exponential backoff (2s, 4s, 8s, max 3) |

## Test coverage (24 tests, all passing)

| Test class | Tests | Cases |
|---|---|---|
| `TestNormalizeCandles` | 4 | Raw→CandleV1 conversion, 15m boundary snap, malformed row skip, negative price rejection |
| `TestDedupAndSort` | 3 | Duplicate removal, chronological sort, boundary overlap |
| `TestFetchHistoryCandles` | 9 | Single page, backward pagination, empty page stop, 429 retry success, 429 retry exhaust, 5xx retry exhaust, history endpoint verification, no-auth verification, 90-day sub-range splitting |
| `TestWriteSnapshot` | 3 | Atomic write + sidecar, no temp files left, canonical hash match |
| `TestBuildManifest` | 2 | No self-hash field, detached hash sidecar |
| Constants | 3 | Endpoint URL, max candles 200, max query range 90 days |

## Test results

```
24 passed in 0.23s
```

## Ruff

All checks passed!

## Scope

- A1 only: repository code + tests. No runtime network fetch. No strategy execution. No holdout inspection.
- Fetcher is present and tested but NOT executed in this PR.
- No credentials, no authenticated endpoints, no `.env` mutation.

## Next steps (after merge)

1. **C2:** Luke ratifies full `EvaluationManifestV1` instance (strategy SHA, config SHA, benchmark definition, all thresholds, fetcher commit pin)
2. **A2 marker:** Luke issues `APPROVED_A2_GATE0_SNAPSHOT_FETCH` with pinned fetcher commit
3. **C3:** Snapshot fetch executes using the tested fetcher
4. **C4:** Snapshot proof PR
5. **C5:** Gate-0 evaluation integration
6. **C6:** Holdout ceremony → edge decision → Phase C complete