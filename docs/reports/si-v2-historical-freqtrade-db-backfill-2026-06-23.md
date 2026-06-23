# SI v2 Historical Freqtrade DB Backfill — 2026-06-23

**Status:** GREEN — read-only backfill importer implemented, 210/210 trades imported across 4/4 bots, zero errors, full test pass.

## Mission

Close the 43-day historical-data gap between Freqtrade runtime trade history and SI v2 telemetry.

## Gap (from yesterday's audit)

- Oldest Freqtrade bot trade: **2026-05-03** (regime-hybrid)
- Oldest SI v2 telemetry record: **2026-06-15**
- Gap: **43 days**
- Total trades that exist on disk but were never ingested: **210**

## Result

| Bot | Imported | SQLite | REST | Match |
|---|---:|---:|---:|---|
| freqtrade-freqforge | 78 | 78 | 78 | ✅ |
| freqtrade-freqforge-canary | 59 | 59 | 59 | ✅ |
| freqtrade-regime-hybrid | 55 | 55 | 55 | ✅ |
| freqai-rebel | 18 | 18 | 18 | ✅ |
| **Total** | **210** | **210** | **210** | **✅** |

- Schema-versioned JSONL per bot (`schema_version=1`).
- Atomic write via `tempfile` + `os.replace` — no partial files.
- Strict `mode=ro` URI + `PRAGMA query_only=ON` for the Freqtrade DBs.
- **No Freqtrade container touched. No config touched. No strategy touched. No live trading. No `dry_run=false`.**
- CLI exits non-zero if any bot has errors.

## Implemented

1. `self_improvement_v2/src/si_v2/backfill/freqtrade_sqlite_backfill.py` — pure-Python backfill module
2. `self_improvement_v2/src/si_v2/backfill/__init__.py` — package export
3. `self_improvement_v2/scripts/si_v2_backfill_freqtrade_trades.py` — CLI
4. `self_improvement_v2/tests/test_freqtrade_sqlite_backfill.py` — 12 tests (all pass)
5. `self_improvement_v2/state/historical_trades/` — populated store (in repo, not secrets)

## Schema

Every JSONL record carries:

```json
{
  "schema_version": 1,
  "imported_at_utc": "2026-06-23T20:09:36+00:00",
  "bot_id": "freqtrade-freqforge",
  "source_db": "freqforge/user_data/tradesv3.freqforge.dryrun.sqlite",
  "id": 1,
  "exchange": "bitget",
  "pair": "BTC/USDT",
  "is_open": 0,
  "open_rate": 80673.15,
  "close_rate": 82349.99,
  "open_date": "2026-05-10 20:45:02.656371",
  "close_date": "2026-05-10 23:45:06.786000",
  "close_profit": 0.0167,
  "close_profit_abs": 1.6736,
  "stake_amount": 99.95,
  "amount": 0.001239,
  "exit_reason": "roi",
  "strategy": "FreqForge_Override",
  "enter_tag": "trend_pullback_long",
  "timeframe": 15,
  "trading_mode": "SPOT",
  "is_short": 0,
  ... (all 51 tradesv3 columns)
}
```

## Run

```bash
cd /home/hermes/projects/trading
PYTHONPATH=self_improvement_v2/src python3 \
  self_improvement_v2/scripts/si_v2_backfill_freqtrade_trades.py \
  --output-dir self_improvement_v2/state/historical_trades
```

Re-run is idempotent — overwrites the canonical `historical_trades_*.jsonl` files atomically.

## Tests

```
$ PYTHONPATH=self_improvement_v2/src python3 -m pytest \
    tests/test_apply_actuator_runtime_binding.py \
    tests/test_apply_actuator_overlay_merge.py \
    tests/test_apply_actuator_proof_gate.py \
    tests/test_apply_actuator_runtime_proof_multiconfig.py \
    tests/test_freqtrade_sqlite_backfill.py -q
........................................................................ [ 85%]
............                                                             [100%]
72 passed in 0.46s
```

12 new tests cover:
1. Atomic write (no `.tmp` leftovers)
2. JSONL line-delimited output
3. Schema version + bot_id + source_db stamping on every record
4. Missing DB → error
5. DB without `trades` table → error
6. Source DB is read-only (size/mtime unchanged)
7. `mode=ro` URI rejects writes at SQLite level
8. Open/closed trade split
9. Aggregate fields (PnL, wins, losses)
10. `backfill_all` totals across bots
11. CLI `--summary-only` round-trip
12. CLI `--bot-id` filter + unknown bot rejection

## Safety

- No bot restart
- No `docker compose` mutation
- No Freqtrade config mutation
- No strategy mutation
- No `dry_run=false`
- No live trading
- No secrets printed
- The reader is a hard read-only connection (verified by negative test that `UPDATE` is rejected)

## Resolution of prior backlog issues

- ✅ **P0 — Historical Freqtrade DB Backfill** — done
- ✅ **P1 — Historical Window Analyzer** — store is now consumable by future analyzer PRs
- ✅ **P2 — Rebel Docker-Volume DB Extraction** — moot: all 4 bot DBs (including Rebel) are host-bind-mounted, no Docker-volume special case needed
- ⏳ **P3 — Scheduler Continuity Proof** — still open, separate issue

## Evidence

- `/opt/data/reports/si-v2-historical-freqtrade-db-backfill-20260623T200507Z/`
  - `context.txt` — phase metadata
  - `trades-schema.txt` — column inspection per bot
  - `backfill-run.json` — full machine-readable summary
  - `backfill-cli-output.json` — CLI stdout/stderr capture
  - `validation-report.txt` — backfill-vs-audit cross-check (PASS for all 4 bots)
  - `historical_trades/` — populated SI v2 store (4 JSONL files + summary JSON)
- `/home/hermes/projects/trading/self_improvement_v2/state/historical_trades/` — production store in repo (same data, for SI v2 consumers)

## Next step

The historical data is now ingestible. The next PR — **separate, not in this scope** — should wire the analyzer / proposal pipeline to use the new store. Until that lands, the new store is an evidence artifact only; SI v2 active-cycle behavior is unchanged.
