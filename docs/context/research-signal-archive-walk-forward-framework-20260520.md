# Research Signal Archive + Walk-Forward Framework — 2026-05-20

## Scope

Research-only infrastructure created for historical external-signal archiving and reusable rolling walk-forward backtests.

No active production/dry-run strategy or config was modified. No container was restarted. No archiver service was started.

## Files Created

Base path:

`freqtrade/bots/regime-hybrid/config/research/signal_tools/`

Files:

- `signal_archiver.py` — polls `primo_signal_state.json` and appends changed signal states to JSONL.
- `signal_loader.py` — `HistoricalSignalLoader` with binary-search lookup by timestamp and pair.
- `walk_forward_backtest.py` — rolling window OOS backtest runner using Freqtrade JSON result ZIPs.
- `README.md` — manual start instructions and strategy integration example.

## Signal Archiver Design

Defaults inside Freqtrade container:

- Source: `/freqtrade/user_data/primo_signal_state.json`
- Archive: `/freqtrade/user_data/signals/historical_signals.jsonl`
- Poll interval: 30 seconds

Robustness features:

- Handles missing, empty, invalid, stale, and pair-empty source files gracefully.
- Hashes canonical JSON payload with SHA256.
- Loads the last archived hash at startup to avoid duplicate writes across restarts.
- Appends only if source content changed.
- Logs timestamp, hash prefix, freshness, staleness, and pair count.
- Supports `--once`, `--skip-stale`, custom source/archive, and custom sleep interval.

## HistoricalSignalLoader Design

Class:

`HistoricalSignalLoader(archive_path, strict=False)`

Primary methods:

- `get_state_at(timestamp)` — returns last known full signal state.
- `get_signal_at(pair, timestamp)` — returns last known pair-specific signal.

Pair handling:

- Supports raw futures keys such as `BTC/USDT:USDT`.
- Supports normalized keys such as `BTC/USDT`.

Performance:

- Loads archive records once and uses binary search (`bisect`) over timestamps.

## Walk-Forward Framework Design

Script:

`walk_forward_backtest.py`

Defaults:

- Train: 30 days
- Test: 7 days
- Step: 7 days
- Rolling, not expanding

Features:

- Requires `--strategy`, `--config`, and preferably `--timerange`.
- Can best-effort auto-detect timerange with `freqtrade list-data --show-timerange` if `--timerange` omitted.
- Runs Freqtrade backtesting per OOS test window.
- Uses `--backtest-directory` and reads JSON reports from Freqtrade result ZIPs.
- Avoids deprecated `--export-filename`.
- Extracts trades, winrate, PF, total profit, max drawdown, expectancy, long/short counts.
- Skips low-trade windows via `--min-trades`.
- Writes terminal table and CSV.
- Optional equity-index CSV.
- Hyperopt is optional and intentionally conservative: runs train-window hyperopt but does not auto-apply params, avoiding hidden shadow-JSON contamination.

## Validation Performed

Host-side tests:

- `python3 -m py_compile` for all three `.py` files: PASS
- Imports for `signal_archiver`, `signal_loader`, `walk_forward_backtest`: PASS
- `signal_archiver.py --help`: PASS
- `walk_forward_backtest.py --help`: PASS
- `HistoricalSignalLoader` smoke test with synthetic JSONL: PASS
- `signal_archiver.py --once` smoke test with synthetic source file: PASS
- Duplicate prevention test: second identical archiver run did not append a second line: PASS
- Walk-forward JSON parser smoke test with synthetic Freqtrade result ZIP: PASS

## Important Caveats

1. The archiver was not started automatically. It must be started manually or later via an approved service/supervisor.
2. The current real bridge state is still stale/empty. This framework records history once the source starts changing, but it does not repair the bridge.
3. Historical walk-forward testing using external signals becomes meaningful only after enough archived signal records exist.
4. Strategy integration should stay research-only until validated with sufficient OOS windows and trade counts.

## Next Recommended Steps

1. Manually start `signal_archiver.py` in screen/tmux after approval and let it collect signal history.
2. Repair or audit the bridge so `/freqtrade/user_data/primo_signal_state.json` contains fresh non-empty `pairs`.
3. Build Regime-Hybrid v3 research strategy to use `HistoricalSignalLoader` rather than static fixtures.
4. Run walk-forward with at least several weeks of archived signals; treat early results as infrastructure smoke tests only.
5. Add a later approved systemd/supervisor unit only after manual archiver behavior is verified.
