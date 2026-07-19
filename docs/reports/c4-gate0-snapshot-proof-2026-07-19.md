# C4 — Gate-0 Snapshot Proof

**Date:** 2026-07-19
**Phase:** C (Gate-0 Strategy Evidence) — snapshot acquisition (C3)
**PR class:** A1 (proof report, no runtime mutation)
**A2 marker:** `APPROVED_A2_GATE0_SNAPSHOT_FETCH` on #651

## Snapshot overview

| Property | Value |
|---|---|
| Snapshot ID | `gate0-snapshot-20260719T212841Z` |
| Created | 2026-07-19T21:28:41Z |
| Exchange | bitget |
| Pairs | BTC/USDT, ETH/USDT, SOL/USDT |
| Timeframe | 15m |
| Date range | 2025-01-01T00:00:00Z to 2026-06-30T23:59:59Z |
| Fetcher commit | `992bfab66fa3e291c17c5b8e07862eeb1d1966de` |
| Manifest SHA-256 | `4013c49a35adfd7017a2f0161e65bbfae938f8dead8269566d99edc1af450c29` |

## File evidence

| Pair | Candles | Size | Canonical hash |
|---|---|---|---|
| BTC/USDT | 52,163 | 1,052 KB | `ce9415cc6ac5dab0c3664520...` |
| ETH/USDT | 52,163 | 992 KB | `6753a262f8fa1cbfc5329933...` |
| SOL/USDT | 52,163 | 939 KB | `35733d6a83f43ff77d842504...` |
| **Total** | **156,489** | **~3 MB** | — |

## Partition coverage (per pair)

| Partition | Candles |
|---|---|
| Calibration (2025-01 to 2025-06) | 17,294 |
| Walk-forward 1 (2025-07 to 2025-09) | 8,789 |
| Walk-forward 2 (2025-10 to 2025-12) | 8,789 |
| Holdout (2026-01 to 2026-06) | 17,291 |

## Data quality

All 3 pairs identical quality:
- **Total gaps:** 254 (single-candle, max 30 min gap)
- **Missing candles:** 254 (0.49%)
- **Duplicates:** 0
- **CandleV1 validation failures:** 0
- Well within `max_missing_candles = 100` threshold

## Scope

- ✅ Public read-only Bitget API only
- ✅ No credentials, no strategy execution, no holdout inspection
- ✅ Atomic writes, detached hash, per-file SHA-256
- ✅ Rollback: only `/opt/data/gate0-snapshot/`

## Next

C5: Evaluation integration (FreqForge_Override → RawTradeV1 → EvaluationBundleV1)
C6: Holdout ceremony → edge decision → Phase C complete
