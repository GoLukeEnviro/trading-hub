# SI-v2 Freqtrade SQLite Source-of-Truth Audit — 2026-06-30

## Status

**YELLOW / SOURCE_OF_TRUTH_IDENTIFIED_FIX_REQUIRED**

## Executive Summary

The Freqtrade containers and host filesystem are correctly aligned via
bind-mounts — the active SQLite DBs are NOT stale. Each container's `db_url`
points to a bot-specific named DB file (e.g. `tradesv3.freqforge_canary.dryrun.sqlite`),
NOT to the generic `tradesv3.sqlite`. The generic `tradesv3.sqlite` in each
host directory is an empty artifact (0 trades, last modified in May) that is
never used by the running Freqtrade process.

However, two issues were found that affect SI-v2 evidence reliability:

1. **`freqtrade_monitor.py` has a `None`-path crash bug** in
   `get_open_trade_details()` for `freqai-rebel` (whose `bot_dir=None`).
   This causes a `TypeError` when checking `os.path.exists(None)`.

2. **`historical_trades_summary.json` is stale** — last generated at
   2026-06-23T20:08Z, missing all trades from June 24–30. SI-v2 reads this
   summary for historical evidence, meaning recent trade data is absent from
   the evidence pipeline until a backfill re-run is performed.

## Scope

- Bots audited:
  - freqtrade-freqforge
  - freqtrade-freqforge-canary
  - freqtrade-regime-hybrid
  - freqai-rebel
- Mutation status: NONE

---

## Observation

### Docker Mount State

| Bot | Container | /freqtrade/user_data Source | RW | Matches Expected Compose Path |
|---|---|---|---|---|
| freqtrade-freqforge | trading-freqtrade-freqforge-1 | /home/hermes/projects/trading/freqforge/user_data | rw | ✅ Yes |
| freqtrade-freqforge-canary | trading-freqtrade-freqforge-canary-1 | /home/hermes/projects/trading/freqforge-canary/user_data | rw | ✅ Yes |
| freqtrade-regime-hybrid | trading-freqtrade-regime-hybrid-1 | /home/hermes/projects/trading/freqtrade/bots/regime-hybrid/user_data | rw | ✅ Yes |
| freqai-rebel | trading-freqai-rebel-1 | /home/hermes/projects/trading/freqtrade/bots/freqai-rebel/user_data | rw | ✅ Yes |

**Finding**: All 4 containers use bind-mounts to the expected host paths.
The `docker-compose.yml` definition matches runtime. No volume-only mounts.
The `freqtrade/docker-compose.fleet.yml` is historical (last modified
2026-05-07) and is NOT the active compose file.

**Note**: Container images are custom (`freqtrade-hermes1337:*`), not
`freqtradeorg/freqtrade:stable` as specified in compose. However, the image
difference does not affect DB path behavior — `db_url` in config.json
overrides any image-default.

### Config DB-URL State

| Bot | Config Path | dry_run | db_url | Strategy | max_open_trades |
|---|---|---|---|---|---|
| freqtrade-freqforge | /freqtrade/user_data/config.json | true | sqlite:////freqtrade/user_data/tradesv3.freqforge.dryrun.sqlite | FreqForge_Override (via CLI) | 5 (config) + 3 (overlay) = 3 |
| freqtrade-freqforge-canary | /freqtrade/user_data/config.json | true | sqlite:////freqtrade/user_data/tradesv3.freqforge_canary.dryrun.sqlite | FreqForge_Override (via CLI) | 3 (config) + 2 (overlay) = 2 |
| freqtrade-regime-hybrid | /freqtrade/user_data/config.json | true | sqlite:////freqtrade/user_data/tradesv3.regime_hybrid.dryrun.sqlite | RegimeSwitchingHybrid_v7_v04_Integration (via CLI) | 5 |
| freqai-rebel | /freqtrade/user_data/config.json | true | sqlite:////freqtrade/user_data/tradesv3.freqai_rebel.dryrun.sqlite | RebelLiquidation (via CLI) | 2 |

**Finding**: Every bot's `db_url` points to a bot-specific named DB file, NOT
to `tradesv3.sqlite`. Container logs confirm Freqtrade startup uses the correct
DB: `INFO - Using DB: "sqlite:////freqtrade/user_data/tradesv3.<bot>.dryrun.sqlite"`.

### Container SQLite State (Active DB)

| Bot | Container DB Path | Size | MTime | Total | Open | Latest Open | Latest Close | Contains UNI/USDT | Fresh? |
|---|---|---:|---|---:|---:|---|---|---|---|
| freqtrade-freqforge | tradesv3.freqforge.dryrun.sqlite | 208K | 2026-06-28T15:08 | 81 | 0 | 2026-06-29 04:45:04 | 2026-06-30 12:24:02 | No | ✅ Fresh |
| freqtrade-freqforge-canary | tradesv3.freqforge_canary.dryrun.sqlite | 172K | 2026-06-28T15:09 | 60 | 1 | 2026-06-29 21:15:03 | 2026-06-24 16:51:12 | ✅ Yes (open) | ✅ Fresh |
| freqtrade-regime-hybrid | tradesv3.regime_hybrid.dryrun.sqlite | 168K | 2026-06-28T15:08 | 56 | 0 | 2026-06-30 08:45:02 | 2026-06-30 09:31:42 | No | ✅ Fresh |
| freqai-rebel | tradesv3.freqai_rebel.dryrun.sqlite | 140K | 2026-06-28T15:09 | 50 | 0 | 2026-06-30 08:00:02 | 2026-06-30 09:00:03 | No | ✅ Fresh |

**Note**: All active DBs have WAL files (write-ahead log) that are being
actively written to. WAL mtimes are 2026-06-30T12:24–12:49, confirming live
DB activity. The main `.sqlite` file mtime reflects the last checkpoint, not
the last write — the WAL contains the newest data.

### Host SQLite State (Active DB — Same File via Bind-Mount)

| Bot | Host DB Path | Exists | Size | MTime | Total | Open | Fresh? |
|---|---|---|---:|---|---:|---:|---|
| freqtrade-freqforge | freqforge/user_data/tradesv3.freqforge.dryrun.sqlite | ✅ | 208K | 2026-06-28 | 81 | 0 | ✅ Fresh |
| freqtrade-freqforge-canary | freqforge-canary/user_data/tradesv3.freqforge_canary.dryrun.sqlite | ✅ | 172K | 2026-06-28 | 60 | 1 | ✅ Fresh |
| freqtrade-regime-hybrid | freqtrade/bots/regime-hybrid/user_data/tradesv3.regime_hybrid.dryrun.sqlite | ✅ | 168K | 2026-06-28 | 56 | 0 | ✅ Fresh |
| freqai-rebel | freqtrade/bots/freqai-rebel/user_data/tradesv3.freqai_rebel.dryrun.sqlite | ✅ | 140K | 2026-06-28 | 50 | 0 | ✅ Fresh |

**Finding**: Host and container DBs are the same file (bind-mount). Host WAL
files are also present and fresh. **No host/container DB mismatch exists.**

### Host SQLite State (Stale `tradesv3.sqlite` — NOT Used)

| Bot | Host Path | Exists | Size | MTime | Total | Fresh? |
|---|---|---|---:|---|---:|---|
| freqtrade-freqforge | freqforge/user_data/tradesv3.sqlite | ✅ | 80K | 2026-05-12 | 0 | ❌ Stale/Empty |
| freqtrade-freqforge-canary | freqforge-canary/user_data/tradesv3.sqlite | ✅ | 80K | 2026-05-21 | 0 | ❌ Stale/Empty |
| freqtrade-regime-hybrid | freqtrade/bots/regime-hybrid/user_data/tradesv3.sqlite | ✅ | 80K | 2026-05-10 | 0 | ❌ Stale/Empty |
| freqai-rebel | freqtrade/bots/freqai-rebel/user_data/tradesv3.sqlite | ✅ | 80K | 2026-05-21 | 0 | ❌ Stale/Empty |

**Finding**: The `tradesv3.sqlite` files are Freqtrade default-DB artifacts
that were created on first run but never used (because `db_url` in config.json
overrides to the bot-specific name). They contain 0 trades and are harmless
but misleading — an agent or script that discovers `tradesv3.sqlite` without
checking `db_url` would see stale data.

### SI-v2 Reader State

| Component | File | Reads Host DB | Reads Container DB | Risk |
|---|---|---|---|---|
| freqtrade_monitor.py | orchestrator/scripts/freqtrade_monitor.py | ✅ (host path via `bot_dir`) | ✅ (docker exec sqlite3) | YELLOW — `get_open_trade_details()` crashes for freqai-rebel (`bot_dir=None`) |
| SI-v2 Backfill | self_improvement_v2/src/si_v2/backfill/historical_trade_backfill.py | ✅ (host path via `DEFAULT_BOT_DBS`) | No | LOW — correct paths, but summary is stale |
| SI-v2 Evidence Pipeline | self_improvement_v2/src/si_v2/evidence/input_pipeline.py | No (reads source_regime_stats cache DB) | No | LOW — reads from cache, not source |
| SI-v2 Active Cycle | self_improvement_v2/src/si_v2/loop/active_cycle_runner.py | No (reads historical_trades_summary + REST API) | No (REST `/api/v1/status`) | MEDIUM — depends on stale summary + REST availability |

### `freqtrade_monitor.py` Issues Found

1. **`get_open_trade_details()` line 229**: `os.path.exists(db_path)` crashes
   with `TypeError` when `db_path=None` (freqai-rebel has `bot_dir=None`).
   This means open trade details for freqai-rebel are never returned.

2. **`get_trade_stats()` lines 122-124**: Correctly handles `db_path=None`
   by skipping the host-existence check and proceeding to `docker exec`.
   This path works correctly.

3. **Docker network mismatch**: `DOCKER_NETWORK = "ki-fabrik"` is stale.
   The running containers are on `trading_hermes-net` (freqforge, regime,
   rebel) and `hermes-net` (canary). `get_container_ip()` may fail when
   querying `ki-fabrik` for these containers.

4. **freqai-rebel `bot_dir=None` comment is wrong**: The comment says
   "Docker volume: freqai-rebel-data" but the container actually uses a
   bind-mount to `./freqtrade/bots/freqai-rebel/user_data`. This should
   be `bot_dir: "/home/hermes/projects/trading/freqtrade/bots/freqai-rebel/user_data"`.

### `historical_trades_summary.json` Staleness

- **Last generated**: 2026-06-23T20:08:00Z (7 days ago)
- **Missing trades**:
  - freqforge: 78→81 closed (3 new trades: ETH, SOL, BTC — since June 23)
  - freqforge-canary: 58→59 closed + UNI/USDT open (1 new open trade since June 23)
  - regime-hybrid: 55→56 closed (1 new trade since June 23)
  - freqai-rebel: 18→50 closed (32 new trades since June 23!)

**Impact**: SI-v2 evidence pipeline uses this summary for historical context.
Any walk-forward evaluation or profitability gate that reads this summary is
working with data that is 7 days old — missing 37 new closed trades and 1
open trade across the fleet.

---

## Root Cause

```
D) freqtrade_monitor.py static mapping is stale/wrong
   (freqai-rebel bot_dir=None despite bind-mount existing)
   +
E) SI-v2 reads stale generated summaries instead of current SQLite/REST
   (historical_trades_summary.json last generated 2026-06-23, missing 37 trades)
```

Primary: **E** — the `historical_trades_summary.json` is 7 days stale and
missing 37 closed trades fleet-wide. This directly affects SI-v2 measurement
evidence quality.

Secondary: **D** — `freqtrade_monitor.py` has a crash bug for freqai-rebel
and a stale network mapping, but this does NOT affect the active SI-v2 loop
(which uses REST `/api/v1/status` and the historical summary, not
`freqtrade_monitor.py` directly).

**Important clarification**: The host SQLite files are NOT stale. The active
DBs (`tradesv3.<bot>.dryrun.sqlite`) are live and fresh via bind-mount. The
stale `tradesv3.sqlite` files are unused default-DB artifacts. The real
data freshness issue is in the SI-v2 generated summary, not the source DBs.

---

## Impact on SI-v2

| Area | Impact | Severity |
|---|---|---|
| T4 official validity | LOW — T4 uses direct container SQLite queries (docker exec), not the stale summary | ✅ Not affected |
| Active Cycle evidence validity | MEDIUM — `historical_trade_summary` field in cycle state is stale (June 23 data) | YELLOW |
| Fleet underperformance diagnosis (PR #398) | LOW — diagnosis used direct container SQLite queries, not the stale summary | ✅ Not affected |
| Measurement Ledger validity | LOW — ledger uses measurement points, not historical summary | ✅ Not affected |
| ShadowProposal scoring validity | MEDIUM — walk-forward evaluation may use stale historical context | YELLOW |

---

## Recommendation

**One concrete next task**: Fix `freqtrade_monitor.py` `freqai-rebel` mapping
(`bot_dir=None` → correct host path) and add a `None`-guard in
`get_open_trade_details()`, then re-run the historical trade backfill to
refresh `historical_trades_summary.json` with current data. This is a read-only
fix + data refresh — no runtime mutation, no restart, no apply.

Do not execute the fix in this PR unless explicitly approved.

---

## Safety Confirmation

- No apply
- No restart
- No rollback
- No Docker/Compose mutation
- No live trading
- No dry_run=false
- No DB copy/migration
- No secrets