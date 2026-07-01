# SI-v2 Official T4 Final Measurement Decision — Post Policy Calibration

- **Timestamp (UTC):** 2026-07-01T07:41:52Z
- **Candidate:** `max_open_trades_3_to_2`
- **Target Bot:** `freqtrade-freqforge-canary`
- **Decision mode:** read-only only
- **Policy version:** post PR #406 / merge `599df69`
- **Previous official outcome (pre-policy calibration):** YELLOW / EXTEND_MEASUREMENT / MEDIUM

## Status

- **Final Verdict:** GREEN
- **Final Decision:** KEEP_CANARY_OVERLAY
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
- Latest watcher alert: `/opt/data/logs/si-v2-t4-watcher/alerts/measurement_ready-20260701T073326Z.log`
- Latest watcher run log: `/opt/data/logs/si-v2-t4-watcher/runs/t4-watcher-20260701T073326Z.log`

## Measurement-Point Construction

- T0/T1/T2 are preserved from the official historical point bundle published on `main` and sourced from:
  - `docs/reports/si-v2-phase-4-measurement-t0-2026-06-27.md`
  - `docs/reports/si-v2-phase-4-measurement-t1-2026-06-27.md`
  - `docs/reports/si-v2-phase-4-measurement-t2-2026-06-28.md`
- The official T3 guard remains `docs/reports/si-v2-phase-4-measurement-t3-official-2026-06-30.md`.
- The **current live follow-up point** is mapped into the engine's final slot (`label="T3"`) because the shipped decision engine accepts only `T0..T3` labels.
- The stale pre-policy final-slot live point from the earlier official T4 report was replaced with fresh live SQLite data.
- Control `max_open_trades=5` follows the audited correction in `docs/reports/si-v2-phase-4l-control-baseline-drift-audit-2026-06-29.md`.

## Official T3 Guard Status

- Official T3 report present: **true**
- Runtime proof status from official T3 report: **GREEN**
- Guard interpretation: **present and GREEN**; used only as the required official guard artifact
- Reused stale live figures from the old T3/T4 report: **no**

## Fresh Live DB Evidence

### Canary (`freqtrade-freqforge-canary`)

- DB: `freqforge-canary/user_data/tradesv3.freqforge_canary.dryrun.sqlite`
- `dry_run`: **true**
- effective `max_open_trades`: **2**
- total closed trades: **61**
- total open trades: **1**
- closed since T3: **2**
- realized profit total: **3.98311161 USDT**
- realized profit since T3: **0.00332847 USDT**
- win/loss: **55/6** (win rate 0.901639)
- last close: **2026-07-01 05:31:52.210000 UTC**

**Closed since T3:**
- trade `61` `DOT/USDT:USDT` — open `2026-06-30 14:15:03.965332` → close `2026-07-01 01:11:02.473000`; realized `0.00213071` USDT; close_profit `8.730504477952947e-05`
- trade `62` `ATOM/USDT:USDT` — open `2026-07-01 02:30:03.966736` → close `2026-07-01 05:31:52.210000`; realized `0.00119776` USDT; close_profit `4.921804518416418e-05`

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
- trade `82` `SOL/USDT:USDT` — open `2026-06-29 04:45:04.616904` → close `2026-06-29 17:05:22.642000`; realized `-13.87612577` USDT; close_profit `-0.04110507693142605`
- trade `81` `ETH/USDT:USDT` — open `2026-06-29 04:45:03.443484` → close `2026-06-29 17:46:12.289000`; realized `-12.69750678` USDT; close_profit `-0.03837629851445447`
- trade `80` `BTC/USDT:USDT` — open `2026-06-29 04:45:02.286032` → close `2026-06-30 12:24:02.014000`; realized `5.12554424` USDT; close_profit `0.015312422186754129`

## Canary vs Control Delta Since T3

- closed trades delta: canary **+2** vs control **+3**
- realized PnL delta since T3: canary **+0.00332847 USDT** vs control **-21.44808831 USDT**
- current open trades: canary **1** vs control **0**

## Decision Engine Output

- `build_final_measurement_decision_pack(...)` → **GREEN / KEEP_CANARY_OVERLAY**
- confidence: **MEDIUM**
- reasons:
- T0: GREEN_WITH_SOFT_WARNINGS
- T1: GREEN_WITH_SOFT_WARNINGS
- T2: GREEN_WITH_SOFT_WARNINGS
- T3: GREEN_WITH_SOFT_WARNINGS
- T0: SOFT_WARNING — 3 warning(s) since last snapshot
- T1: SOFT_WARNING — 3 warning(s) since last snapshot
- T2: SOFT_WARNING — 12 warning(s) since last snapshot
- T3: UNKNOWN — container health not collected in read-only mode
- comparison: profit_gap: canary=+0.00 vs control=-21.44
- comparison: trade_gap: canary=+2 vs control=+3
- blocked reasons:
- none

## Interpretation

- The watcher stop condition remains satisfied: the system is at `MEASUREMENT_READY` with live DB evidence (`canary_closed_since_t3=2`, `control_closed_since_t3=3`, kill switch `NORMAL`).
- The post-PR-406 policy now keeps **historical warning-only points** (`T0/T1/T2`) and **read-only `container_healthy=None`** in the soft-evidence lane instead of treating them as automatic final blockers.
- Hard blockers remain untouched: `dry_run=false`, `rollback_required=True`, non-GREEN runtime proof, unhealthy container, or missing official T3 would still prevent KEEP.
- The current live follow-up point is non-RED and the comparison remains favorable versus control, so the recomputed official outcome is **KEEP_CANARY_OVERLAY**.

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

- Preserve this as a docs-only decision artifact and review the PR; do not apply, restart, or enable any watcher job from this report.

## Evidence References

- `docs/reports/si-v2-phase-4-measurement-t0-2026-06-27.md`
- `docs/reports/si-v2-phase-4-measurement-t1-2026-06-27.md`
- `docs/reports/si-v2-phase-4-measurement-t2-2026-06-28.md`
- `docs/reports/si-v2-phase-4-measurement-t3-official-2026-06-30.md`
- `docs/reports/si-v2-phase-4l-control-baseline-drift-audit-2026-06-29.md`
- `/opt/data/logs/si-v2-t4-watcher/alerts/measurement_ready-20260701T073326Z.log`
- `/opt/data/logs/si-v2-t4-watcher/runs/t4-watcher-20260701T073326Z.log`
