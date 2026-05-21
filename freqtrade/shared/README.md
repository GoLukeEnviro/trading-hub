# FleetRisk Shared State

This directory is the shared, dry-run-only risk and observability layer for the
Freqtrade fleet.

## What lives here

- `fleet_risk_manager.py` — shared risk state manager
- `fleet_risk_state.json` — current portfolio / open-trade / history snapshot
- `fleet_correlation_matrix.json` — correlation inputs for cluster throttling
- `primo_signal.py`, `primo_signal_state.json` — signal gate bridge state
- `fleet_watcher.py` — read-only watcher for state, artifacts, and container logs
- `run_fleet_watcher.sh` — background wrapper for the watcher
- `update_fleet_equity.py` — equity sync helper
- `calculate_correlation_matrix.py` — correlation refresh helper

## Problems the FleetRisk fix solves

1. Temporary file collisions on shared writes
   - The manager now writes via unique temp files instead of shared `.tmp` names.

2. Concurrent writers from multiple containers
   - A shared lock file (`.fleet_risk_state.json.lock`) serializes writers.

3. Incorrect portfolio totals when multiple source writers update equity
   - The manager re-derives portfolio totals from source equities before saving.

## Current manager behavior

The manager is intentionally conservative and dry-run friendly:

- shared state is loaded from `fleet_risk_state.json`
- source equity updates are written under `portfolio.sources`
- global portfolio totals are derived from source equities
- `current_drawdown` is computed from `peak_equity` vs `current_equity`
- open trades and closed trade history are stored in the shared JSON snapshot
- the manager never places orders or changes exchange credentials

Key methods:

- `update_source_equity(source, current_equity)`
- `update_portfolio_equity(current_equity)`
- `register_open_trade(...)`
- `unregister_closed_trade(...)`
- `log_trade_result(...)`
- `sync_trade_state(...)`
- `summarize_state()`

## How bots integrate it

Strategies can import the manager from the mounted shared path:

```python
import sys
sys.path.insert(0, "/freqtrade/shared")
from fleet_risk_manager import FleetRiskManager

risk_manager = FleetRiskManager()
```

Typical patterns:

- call `risk_manager.update_source_equity(...)` from equity updater logic
- call `risk_manager.sync_trade_state(...)` when syncing open / closed trades
- call `risk_manager.summarize_state()` for a compact health snapshot
- keep entry logic advisory-only; no signal should force a live trade

## Watcher usage

Read-only live monitoring:

```bash
python3 /home/hermes/projects/trading/freqtrade/shared/fleet_watcher.py
```

Smoke test:

```bash
python3 /home/hermes/projects/trading/freqtrade/shared/fleet_watcher.py --once --tail-lines 20
```

Background daemon with log file and rotation on start:

```bash
python3 /home/hermes/projects/trading/freqtrade/shared/fleet_watcher.py \
  --daemon \
  --duration-minutes 30 \
  --log-file /home/hermes/projects/trading/freqtrade/shared/logs/fleet_watcher.log \
  --log-max-bytes 1048576 \
  --log-backups 5
```

Convenience wrapper:

```bash
/home/hermes/projects/trading/freqtrade/shared/run_fleet_watcher.sh 30 60 80
```

Useful flags:

- `--interval 60` — poll cadence in seconds
- `--duration-minutes 15` — default run length
- `--once` — single snapshot for smoke tests
- `--tail-lines 250` — how many Docker log lines to inspect per cycle
- `--color auto|always|never` — colored console output
- `--background` / `--daemon` — start in the background and stream to a log file
- `--log-file /path/to/file.log` — background log file path
- `--log-max-bytes 1048576` — rotate the background log on daemon start when it exceeds this size
- `--log-backups 5` — how many rotated log files to keep

Cron example for a 30-minute run every 4 hours:

```cron
0 */4 * * * /home/hermes/projects/trading/freqtrade/shared/run_fleet_watcher.sh 30 60 80 >/dev/null 2>&1
```

## Why historical_signals.jsonl may stay quiet

The signal archiver only appends when the source signal JSON changes.
If `/home/hermes/projects/trading/freqtrade/bots/regime-hybrid/user_data/primo_signal_state.json`
has not changed, `historical_signals.jsonl` will not get a new record.
That is expected and is usually a sign that the bridge is stable rather than broken.

## Known boundaries

- Dry-run only. No live trading.
- No `dry_run=false` changes.
- No exchange credentials belong here.
- The watcher is observational only; it does not mutate state.
- Signal freshness matters: stale signal artifacts may fail open rather than block.
- Docker access depends on the runtime user / socket permissions.

## Notes

- Shared state should remain versioned and append-only where possible.
- Keep new changes minimal, reviewable, and reversible.
- When the FleetRisk design changes, update this README and the context docs.
