# C5.1 — Corrective Evidence Report

**Date:** 2026-07-19
**Issue:** #658
**15 gaps identified and 14 corrected items implemented.**

## Items delivered

| # | Item | File |
|---|---|---|
| 1 | Strategy provenance (actual code, not simplified) | `gate0_strategy_provenance.py` |
| 2 | Pinned strategy path, commit, hashes, image digest | `StrategyProvenance` dataclass |
| 3 | Deterministic isolation doc (Primo/AI/FleetRisk requires runtime hooks) | `re_ratification_note` |
| 4 | 1h aggregation from 15m candles | `aggregate_to_1h()` |
| 5 | CSV→Freqtrade converter | `convert_to_freqtrade_format()` |
| 6 | Partition correction (half-open, no gaps) | Constants |
| 7 | Total multi-pair hash + separate benchmark hash | `compute_total_snapshot_hash()` + `compute_benchmark_hash()` |
| 8 | Manifest v2 with corrected `max_missing_candles=500` | `build_manifest_v2()` |
| 9 | Regime classification (volatility-based, deterministic) | `classify_regime()` + `classify_regime_for_candles()` |
| 10 | Real Freqtrade export format (golden fixture) | `FreqtradeExportAdapterV1` test |
| 11 | `FreqtradeExportAdapterV1` with provenance check | `FreqtradeExportAdapterV1` dataclass |
| 12 | Deterministic trade IDs (SHA-256 fallback) | `parse_trades()` fallback |
| 13 | 19 tests covering all corrected functionality | `test_c51_corrective.py` |
| 14 | State update for C3/C4/C5/C5.1 | `current-operational-state.md` |

## Test results

**19 passed** — partitions, strategy provenance, 1h aggregation, converter,
regime classification, export adapter (with/without IDs, nested format),
E2E manifest v2 construction, constants.

## Ruff

All checks passed.

## Scope

A1 only. No backtest execution. No holdout evaluation. No runtime action.

## Next (after merge)

- **A0 HermesTrader Preflight** (freqtrade version, image digest, mounts, isolation)
- **A2 Selection Backtest** (`APPROVED_A2_GATE0_SELECTION_BACKTEST` marker)
- **C6 Holdout Ceremony** (`APPROVED_GATE0_HOLDOUT_EVALUATION` marker)
