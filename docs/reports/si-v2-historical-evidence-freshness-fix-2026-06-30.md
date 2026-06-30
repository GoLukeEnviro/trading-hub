# SI-v2 Historical Evidence Freshness Fix — 2026-06-30

## Status

GREEN / HISTORICAL_SUMMARY_REFRESHED

## Scope

- freqtrade_monitor.py read-only bug fix (3 issues)
- historical_trades_summary.json refresh (37 missing trades recovered)
- Mutation status: NONE

## Before

| Source | State |
|---|---|
| historical_trades_summary.json | 2026-06-23, missing 37 trades |
| freqai-rebel monitor open trade details | crash risk via bot_dir=None (TypeError) |
| Docker network mapping | stale "ki-fabrik" (no containers on this network) |
| freqai-rebel bot_dir | None (incorrectly assumed Docker volume) |

## After

| Source | State |
|---|---|
| historical_trades_summary.json | refreshed 2026-06-30T13:03Z |
| freqai-rebel monitor open trade details | fixed — None-guard + container-first read |
| Docker network mapping | corrected to trading_hermes-net / hermes-net |
| freqai-rebel bot_dir | /home/hermes/projects/trading/freqtrade/bots/freqai-rebel/user_data |

## Changes Applied

### 1. freqtrade_monitor.py — freqai-rebel bot_dir

- **Before**: `"bot_dir": None` (comment: "Docker volume: freqai-rebel-data")
- **After**: `"bot_dir": "/home/hermes/projects/trading/freqtrade/bots/freqai-rebel/user_data"`
- **Rationale**: docker inspect confirmed bind-mount, not volume

### 2. freqtrade_monitor.py — get_open_trade_details() None-guard

- **Before**: `os.path.exists(db_path)` crashes with `TypeError` when `db_path=None`
- **After**: `if db_path is not None and (...)` — proceeds to container read regardless
- **Rationale**: Container DB is authoritative; host path is sanity check only

### 3. freqtrade_monitor.py — Docker network mapping

- **Before**: `DOCKER_NETWORK = "ki-fabrik"` (stale), freqai-rebel on `"trading-freqai-rebel-1-net"`
- **After**: `DOCKER_NETWORK = "trading_hermes-net"`, canary on `"hermes-net"`, rebel on `"trading_hermes-net"`
- **Rationale**: docker inspect confirmed network assignments

### 4. freqtrade_monitor.py — get_container_ip() robust fallback

- **Before**: Only tried configured network, then hostname -i
- **After**: Tries configured network → discovers first network from docker inspect → hostname -i
- **Rationale**: Containers may be on multiple networks; don't hardcode

### 5. historical_trades_summary.json — refreshed

| Bot | Before (closed) | After (closed) | Delta | Open | PnL |
|---|---:|---:|---:|---:|---|
| freqtrade-freqforge | 78 | 81 | +3 | 0 | +$3.34 |
| freqtrade-freqforge-canary | 58 | 59 | +1 | 1 (UNI) | +$3.98 |
| freqtrade-regime-hybrid | 55 | 56 | +1 | 0 | -$7.35 |
| freqai-rebel | 18 | 50 | +32 | 0 | -$1.82 |
| **Total** | **209** | **246** | **+37** | **1** | — |

### 6. Tests

- `tests/test_freqtrade_monitor_paths.py` — 15 tests, all pass
- `tests/test_measurement_decision_engine.py` — 37 tests, all pass
- `tests/test_final_measurement_decision_pack.py` — 20 tests, all pass

## Safety

- No apply
- No restart
- No rollback
- No Docker/Compose mutation
- No live trading
- No dry_run=false
- No DB copy/migration
- No secrets

## Validation

```bash
python -m py_compile orchestrator/scripts/freqtrade_monitor.py  # OK
git diff --check                                                  # WHITESPACE_OK
PYTHONPATH=. python -m pytest tests/test_freqtrade_monitor_paths.py -q  # 15 passed
PYTHONPATH=src python -m pytest tests/test_measurement_decision_engine.py tests/test_final_measurement_decision_pack.py -q  # 57 passed
```