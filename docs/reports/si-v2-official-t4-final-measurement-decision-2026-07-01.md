# SI-v2 Official T4 Final Measurement Decision

- **Timestamp (UTC):** 2026-07-01T06:04:52Z
- **Candidate:** `max_open_trades_3_to_2`
- **Target Bot:** `freqtrade-freqforge-canary`
- **Decision mode:** read-only only
- **Fresh live input:** current SQLite dry-run DBs + official T0/T1/T2 reports + official T3 report guard

## Status

- **Final Verdict:** YELLOW
- **Final Decision:** EXTEND_MEASUREMENT
- **Confidence:** MEDIUM
- **Blocked Reasons:** none

## Watcher Reconfirm

- `SI_V2_T4_ALERT=MEASUREMENT_READY`
- `MEASUREMENT_DECISION_ENGINE_ALLOWED=True`
- `WRAPPER_EXIT=0`
- `T3_REFERENCE_UTC=2026-06-28T18:27:00Z`
- Canary closed since T3: **2**
- Control closed since T3: **3**
- Canary open trades: **1**
- `DRY_RUN_ALL_TRUE=True`
- Kill Switch: **NORMAL**
- Latest watcher alert: `/opt/data/logs/si-v2-t4-watcher/alerts/measurement_ready-20260701T055939Z.log`
- Latest watcher run log: `/opt/data/logs/si-v2-t4-watcher/runs/t4-watcher-20260701T055939Z.log`

## Measurement-Point Construction

- T0/T1/T2 are taken from the official published reports under `docs/reports/`.
- The current live follow-up point is mapped into the engine's final slot (`label="T3"`) because the shipped decision engine only accepts `T0..T3` labels.
- The official T3 guard is still satisfied by `docs/reports/si-v2-phase-4-measurement-t3-official-2026-06-30.md`, but its stale 2026-06-30 live figures were **not** reused for the current live point.
- Control `max_open_trades=5` follows the audited correction in `docs/reports/si-v2-phase-4l-control-baseline-drift-audit-2026-06-29.md`.

## Fresh Live DB Evidence

### Canary (`freqtrade-freqforge-canary`)

- DB: `freqforge-canary/user_data/tradesv3.freqforge_canary.dryrun.sqlite`
- `dry_run`: **true**
- effective `max_open_trades`: **2** (overlay file `freqforge-canary/user_data/overlay_max_open_trades_.json`)
- total closed trades: **61**
- total open trades: **1**
- closed since T3: **2**
- realized profit total: **3.98311161 USDT**
- realized profit since T3: **0.00332847 USDT**
- win/loss: **55/6** (win rate 0.901639)
- last close: **2026-07-01 05:31:52.210000 UTC**

**Closed since T3:**
- trade `61` `DOT/USDT:USDT` — open `2026-06-30 14:15:03.965332` → close `2026-07-01 01:11:02.473000`; realized `0.00213071` USDT; close_profit `0.000087305045`
- trade `62` `ATOM/USDT:USDT` — open `2026-07-01 02:30:03.966736` → close `2026-07-01 05:31:52.210000`; realized `0.00119776` USDT; close_profit `0.000049218045`

**Open canary trades:**
- trade `60` `UNI/USDT:USDT` — open `2026-06-29 21:15:03.825896` UTC

### Control (`freqtrade-freqforge`)

- DB: `freqforge/user_data/tradesv3.freqforge.dryrun.sqlite`
- `dry_run`: **true**
- configured `max_open_trades`: **5**
- total closed trades: **81**
- total open trades: **0**
- closed since T3: **3**
- realized profit total: **3.33600672 USDT**
- realized profit since T3: **-21.44808831 USDT**
- win/loss: **63/18** (win rate 0.777778)
- last close: **2026-06-30 12:24:02.014000 UTC**

**Closed since T3:**
- trade `82` `SOL/USDT:USDT` — open `2026-06-29 04:45:04.616904` → close `2026-06-29 17:05:22.642000`; realized `-13.87612577` USDT; close_profit `-0.041105076931`
- trade `81` `ETH/USDT:USDT` — open `2026-06-29 04:45:03.443484` → close `2026-06-29 17:46:12.289000`; realized `-12.69750678` USDT; close_profit `-0.038376298514`
- trade `80` `BTC/USDT:USDT` — open `2026-06-29 04:45:02.286032` → close `2026-06-30 12:24:02.014000`; realized `5.12554424` USDT; close_profit `0.015312422187`

## Canary vs Control Delta Since T3

- closed trades delta: canary **+2** vs control **+3**
- realized PnL delta since T3: canary **+0.00332847 USDT** vs control **-21.44808831 USDT**
- current open trades: canary **1** vs control **0**

## Decision Engine Output

- `build_final_measurement_decision_pack(...)` → **YELLOW / EXTEND_MEASUREMENT**
- confidence: **MEDIUM**
- reasons:
  - T0: YELLOW — YELLOW: 3 warning(s) since last snapshot
  - T1: YELLOW — YELLOW: 3 warning(s) since last snapshot
  - T2: YELLOW — YELLOW: 12 warning(s) since last snapshot
  - T3: YELLOW — YELLOW: container health unknown
  - comparison: profit_gap: canary=+0.00 vs control=-21.44
  - comparison: trade_gap: canary=+2 vs control=+3

## Interpretation

- The watcher's stop condition is satisfied: the system is at `MEASUREMENT_READY` with live DB evidence (`canary_closed_since_t3=2`, `control_closed_since_t3=3`, kill switch `NORMAL`).
- The shipped final-decision engine remains conservative because the historical official measurement points still carry YELLOW warning states (`T0=3`, `T1=3`, `T2=12` Bitget 429 warnings).
- The fresh live point itself is non-RED: dry-run remains true, rollback is not required, and the DB shows organic trade progression without any apply/restart/rollback action.
- Result: the official read-only engine output is **EXTEND_MEASUREMENT**, not because the watcher is still waiting, but because the current engine treats inherited historical YELLOW points as sufficient to block a GREEN final pack.

## Safety / Mutation Status

- Kill Switch: **NORMAL**
- dry_run preserved on both bots: **true**
- Runtime mutation status: **none**
- No apply
- No restart
- No rollback
- No Docker/Compose mutation
- No jobs.json mutation
- No watcher enablement
- No live trading

## Next Step

- Preserve the watcher as disabled and review, in a separate L1/L2 follow-up, whether the official final-decision policy should continue to let inherited non-critical Bitget-429 YELLOW points dominate the post-`MEASUREMENT_READY` final outcome.

## Evidence References

- `docs/reports/si-v2-phase-4-measurement-t0-2026-06-27.md`
- `docs/reports/si-v2-phase-4-measurement-t1-2026-06-27.md`
- `docs/reports/si-v2-phase-4-measurement-t2-2026-06-28.md`
- `docs/reports/si-v2-phase-4-measurement-t3-official-2026-06-30.md`
- `docs/reports/si-v2-phase-4l-control-baseline-drift-audit-2026-06-29.md`
- `/opt/data/logs/si-v2-t4-watcher/alerts/measurement_ready-20260701T055939Z.log`
- `/opt/data/logs/si-v2-t4-watcher/runs/t4-watcher-20260701T055939Z.log`
