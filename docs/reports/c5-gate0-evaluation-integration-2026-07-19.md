# C5 — Gate-0 Evaluation Integration Report

**Date:** 2026-07-19
**Phase:** C (Gate-0 Strategy Evidence) — evaluation integration (C5)
**PR class:** A1 (repository code + tests)
**Issue:** #656

## Goal

Wire the complete Gate-0 execution pipeline: Snapshot → CandleV1 → EvaluationBundleV1 → EvaluationRunnerV1 for calibration + walk-forward. No holdout evaluation.

## Delivered

### `gate0_evaluation_integration.py`

| Function | Purpose |
|---|---|
| `load_snapshot_manifest()` | Load `snapshot_manifest.json` |
| `load_snapshot_candles(pair_label)` | Load gzipped CSV → deduplicated `list[CandleV1]` |
| `run_backtest_cli(...)` | HermesTrader CLI wrapper for `freqtrade backtesting` |
| `parse_backtest_trades(json_path)` | Freqtrade trade export → `list[RawTradeV1]` |
| `build_frozen_manifest(...)` | Build `EvaluationManifestV1` from Luke's ratified values |
| `run_calibration_and_walkforward(...)` | Pipeline: bundle → runner for 3 eval windows |
| `format_results(...)` | Markdown result summary |

### Frozen `EvaluationManifestV1`

All values per Luke's ratification on #604/#651:
- Strategy: `FreqForge_Override`
- Pairs: BTC/USDT, ETH/USDT, SOL/USDT
- Timeframe: 15m
- Partitions: Calibration (2025-01 to 2025-06), WF1 (2025-07 to 2025-09), WF2 (2025-10 to 2025-12), Holdout (2026-01 to 2026-06)
- Cost: entry/exit fee 0.05%, slippage 0.02%, funding 0.01%/8h
- Thresholds: PF > 1.3, DD < 25%, trades > 100, regimes ≥ 2, CI width 0.05
- Bootstrap: 1000 samples, block size 4, seed 42, CL 0.95
- Boundary: STRICT_CONTAINED, Continuation: REPORT_ONLY

## Tests (9 passed)

| Test | Cases |
|---|---|
| `TestPartitionCandles` | 3 — filter by window, empty window, boundary exclusion |
| `TestParseBacktestTrades` | 4 — standard export, empty, nested format, missing fields |
| `TestConstants` | 2 — partition ordering, partition durations |

## Scope

- A1 only. No Freqtrade backtest executed (requires HermesTrader host).
- No holdout evaluation. No strategy mutation. No runtime changes.

## Next steps

1. Run Freqtrade backtest on HermesTrader for calibration + walk-forward
2. `run_calibration_and_walkforward()` → results
3. Luke issues `APPROVED_GATE0_HOLDOUT_EVALUATION` marker
4. C6: Holdout ceremony → Phase C complete

Alles OK. No holdout inspected. No credentials. No strategy mutation.
