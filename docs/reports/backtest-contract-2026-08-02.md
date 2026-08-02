# Reproducible Gate-0 Backtest Contract

**Date:** 2026-08-02
**Author:** Hermes (trading-hub-orchestrator)
**Issue:** #686
**Branch:** `fix/backtest-contract-2026-08-02`
**Base:** `92da91e6768c3c8746b1f45f7f2e5b23e2f26f7b` (origin/main)

## Contract (pinned)

| Field | Value |
|---|---|
| Image | `freqtradeorg/freqtrade@sha256:50720a4af314a812be2cfbf5cc6331c63e9332b06f3f4372241f54bc61a35486` (verified 2026-08-02 via Docker Hub tag metadata, last_updated 2026-07-31) |
| Freqtrade version | `2026.6` |
| Strategy SHA-256 | `112ff28ef7bd1fdc28341b4e53516b48fe7c94278c747691077d4d2e6e7916c0` (`freqforge/user_data/strategies/FreqForge_Gate0_Core_v1.py`) |
| Config SHA-256 | `7647ed03a88e49a63c9916e9e8137ce84d5e12a90f461785a694591e5e70345d` (`freqforge/user_data/config.example.json`) |
| Timerange | `20241201-20260101` (warm-up 2024-12-01 → selection end 2026-01-01; holdout excluded) |
| Cache policy | `none` (deterministic, no indicator cache) |
| Export format | `freqtrade-trades-json` (`--export trades`) |
| Results dir | `freqforge/user_data/backtest_results/gate0-selection/` |
| Backtest command | pinned `BACKTEST_COMMAND` in `backtest_contract.py` |

## Deliverables implemented

1. **Image digest pin** — `docker-compose.yml` (4 services): `freqtradeorg/freqtrade:stable` → pinned digest; no moving tag remains.
2. **`backtest_contract.py`** — `BacktestContract` frozen dataclass with fail-closed `validate()` (rejects moving tags `IMAGE_NOT_PINNED`, invalid pin `IMAGE_PIN_INVALID`, holdout in timerange `HOLDOUT_IN_TIMERANGE`, missing warm-up `WARMUP_MISSING`); pinned command/cache/export/results constants.
3. **15m→1h resampling** — `aggregate_1h_dataset()` wraps the existing deterministic `aggregate_to_1h()`; tests cover full-hour aggregation and incomplete-hour drop.
4. **Warm-up without metrics** — `validate_warmup_excluded_from_metrics()` fail-closed (`WARMUP_LEAKS_INTO_SELECTION`); timerange validation requires warm-up start before selection.
5. **Freqtrade dataset materialization** — `materialize_selection_dataset()` wraps `convert_to_freqtrade_format()` after physical holdout exclusion.
6. **Funding dataset adapter** — `convert_funding_to_freqtrade()`: `(timestamp, rate)` rows → `futures_funding_rate/<pair_key>.json` (`[[ts_ms, rate], ...]`, sorted, deduplicated).
7. **Physical holdout exclusion** — `exclude_holdout()` drops all candles at/after `HOLDOUT.start`; verified on materialized output (no holdout timestamps in JSON).

## Validation

- `test_backtest_contract.py`: all green (image pin 5, provenance 2, timerange 3, exclusion 2, resampling 2, materialization 2, funding 2, warm-up 2)
- Combined Gate-0 suite from repo root: green (incl. existing suites)
- Ruff clean on changed files; `git diff --check` clean
- CI: main-gate ✅, offline-smoke ✅, governance-consistency ✅

## Safety

```
holdout_inspected=NO
backtest_executed=NO
network_data_download=NO
runtime_mutation=NO
live_trading=NO
docker_pull_build_start=NO
```

## Changed Files

- `self_improvement_v2/src/si_v2/research/backtest_contract.py` — new contract module
- `self_improvement_v2/tests/test_backtest_contract.py` — new contract tests
- `docker-compose.yml` — image digest pins (4 services)
