# Freqtrade-Native Bitget Data Contract — A1 corrective

**Date:** 2026-08-03
**Author:** Hermes (trading-hub-orchestrator)
**Issue:** #695
**Branch:** `fix/freqtrade-native-data-contract-2026-08-03`
**Base:** `091f5ad6844bab7e9cbd3b6f365c9aa05d436f83` (origin/main)

## Purpose

Correct the repository data contract so the Gate-0 selection backtest
(`FreqForge_Gate0_Core_v1`, #604) uses a fully reproducible,
Freqtrade-native dataset. The original snapshot v2 (#693) is classified
`SUPERSEDED_FUNDING_INCOMPLETE`; the REST funding endpoint cannot provide
full 19-month history (verified in A0 probes, below).

## A0 upstream probe results (public read-only, 2026-08-02)

| Probe | Result |
|---|---|
| `freqtrade --version` (pinned image `50720a4a…`) | **2026.7** (contract field 2026.6 is informational; digest is the pin) |
| `freqtrade download-data --help` | `--trading-mode`, `--candle-types {spot,futures,mark,index,premiumIndex,funding_rate}`, `--data-format-ohlcv {json,jsongz,feather,parquet}`, `--timerange`, `--prepend`, `--erase`, `--no-parallel-download` ✓ |
| `freqtrade list-data --help` | `--exchange`, `--data-format-ohlcv`, `--trading-mode`, `--show-timerange` ✓ |
| `freqtrade convert-data --help` | `--format-from/--format-to`, `--erase`, `--candle-types` ✓ |
| `freqtrade backtesting --help` | `--backtest-directory/--export-directory`, `--backtest-filename/--export-filename`, `--export {none,trades,signals}`, `--cache {none,day,week,month}`, `--data-format-ohlcv`, `--breakdown` ✓ |
| `freqtrade list-exchanges` | **Bitget (Supported)** — spot, isolated futures |
| `freqtrade list-markets --trading-mode futures --base BTC ETH SOL --quote USDT` | `BTC/USDT:USDT` (lev 150), `ETH/USDT:USDT` (lev 150), `SOL/USDT:USDT` (lev 100) — all active futures ✓ |
| CCXT version (container) | 4.5.68 |

## A0 funding depth probe (public read-only)

| Endpoint | Pages / rows | Oldest reachable |
|---|---|---|
| `/api/v2/mix/market/history-fund-rate` `pageNo=1..3` | 100/100/70 | 2026-05-05 (~90 days) |
| `/api/v2/...` `pageNo>=4` | 0 | — |
| `/api/v3/market/history-fund-rate` `category` + `cursor=1..3` | 100/100/70 | 2026-05-05 (~90 days) |
| `/api/v3/...` `cursor>=4` | 0 | — |
| `/api/mix/v1/market/history-fundRate` | decommissioned (30032) | — |

**Conclusion:** Bitget REST funding history is capped at ~90 days. Native
Freqtrade/CCXT download (`--candle-types futures mark funding_rate`) is the
primary backtest data source (decision B); the raw REST snapshot remains
independent audit evidence.

## Changes (A1)

### `self_improvement_v2/src/si_v2/research/backtest_contract.py`

- Removed `--export-filename`; added `--backtest-directory /freqtrade/user_data/backtest_results/gate0-selection`.
- Explicit `--data-format-ohlcv feather`, `--timeframe 15m`, `--trading-mode futures`, `--cache none`, `--export trades`, `--breakdown month year`.
- Separated mounts: `project:ro` (strategy+config), `data:ro`, `backtest_results:rw`.
- New path constants:
  - `FREQTRADE_NATIVE_DATA_DIR=/opt/data/gate0-freqtrade-native-r1`
  - `RESEARCH_SNAPSHOT_DIR=/opt/data/gate0-snapshot-v2-r1`
  - `BACKTEST_RESULTS_DIR=/opt/data/gate0-backtest-results`
- `full_dataset_timerange()` (download: `20241201-20260701`) vs `selection_timerange()` (backtest: `20241201-20260101`, holdout excluded).
- `BacktestContract.validate()` extended: `DATA_FORMAT_NOT_EXPLICIT`, `TIMEFRAME_NOT_15M`, `TRADING_MODE_NOT_FUTURES`.
- `validate_mount_contract()` fail-closed: `RESULTS_NOT_PERSISTENT`, `STRATEGY_PATH_MISSING`, `HOLDOUT_IN_DATADIR`, `MARK_OR_FUNDING_MISSING`.
- `convert_funding_to_freqtrade()` documented as audit-helper only (not load-compatible until proven; canonical input = native download).

### `self_improvement_v2/src/si_v2/research/freqtrade_native_data_contract.py` (new)

- Immutable constants: image digest, exchange, pairs, timeranges, formats, candle types, timeframes, datadir.
- `render_download_command()` (main 15m futures; auxiliary 1h mark+funding_rate; no `--erase`/`--prepend`/`--dl-trades`).
- `render_list_data_command()` (read-only coverage proof).
- Coverage parser + `validate_coverage()` fail-closed (`COVERAGE_MISSING`, `COVERAGE_START_LATE`, `COVERAGE_END_EARLY`) with per-timeframe grace.
- `NativeDataFile` + hash validation (`DATA_FILE_MISSING`, `HASH_MISMATCH`).
- No network operations; all tests offline.

## Validation

| Check | Result |
|---|---|
| Targeted tests (`test_freqtrade_native_data_contract.py` + `test_backtest_contract.py`) | 75/75 pass |
| Gate-0 suites (backtest_runner, gate0_evaluation_integration, snapshot v1+v2, c52 strategy) | 168/168 pass |
| Ruff (changed files) | clean |
| Type contracts (`test_no_any_types.py`) | pass |
| Forbidden patterns (`test_no_forbidden_patterns.py`) | pass |
| Secret scan (`scripts/secret_scan.py --tracked`) | pass |
| `git diff --check` | clean |

## Safety status

```
BACKTEST_EXECUTED=NO
HOLDOUT_INSPECTED=NO
NETWORK_DATA_DOWNLOAD=NO        (A2 after merge)
CREDENTIALS_USED=NO
PRIVATE_ENDPOINTS_USED=NO
LIVE_TRADING=NO
RUNTIME_MUTATION=NO
```

## Next steps (A2, after human merge + scope-specific A2 marker)

1. Root-provision `/opt/data/gate0-freqtrade-native-r1/` and `/opt/data/gate0-backtest-results/` (`install -d -o 10000 -g 10000 -m 0750`).
2. Native downloads (15m futures; 1h mark + funding_rate; 1h futures oracle).
3. `list-data` coverage proof + file hashes; loader smoke; Research-vs-Native comparison.
4. Full PHASE H report + `#605` tracker update:
   `NEXT_TASK=VERIFY_604_RATIFICATION_THEN_CREATE_SELECTION_BACKTEST_ISSUE`.
