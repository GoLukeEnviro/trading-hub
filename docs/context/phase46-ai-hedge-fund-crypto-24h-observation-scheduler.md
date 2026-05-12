# Phase 46 — ai-hedge-fund-crypto 24h Observation Scheduler

**Timestamp:** 2026-05-12T04:23:00Z
**Host:** Hermes Docker Container
**Status:** Observation active, 24 cycles scheduled

## Executive Summary

Set up a safe 24-hour observation system for the ai-hedge-fund-crypto analysis
layer. A runner script triggers one analysis cycle per hour via the container's
`/trigger` endpoint, archives timestamped JSON outputs, validates the schema,
and logs results. No trading, no Freqtrade interaction, no hermes-agent restart.

## Starting State

| Component | Status |
|-----------|--------|
| ai-hedge-fund-crypto | ✅ Up, healthy, port 8410 |
| hermes-agent | ✅ Running (NOT restarted) |
| Freqtrade fleet | ✅ 5 bots, dry-run |
| PrimoAgent references | ✅ Zero |

## Observation Architecture

```
Hermes Cron (every 60m, 24 runs)
  └─> ai_hedge_observation_runner.sh (cron wrapper)
        └─> scripts/run_ai_hedge_analysis_once.sh
              ├─> docker exec ai-hedge-fund-crypto → /trigger
              ├─> Copy signal → output/latest/hermes_signal.json
              ├─> Archive   → output/history/hermes_signal_YYYYMMDD_HHMMSS.json
              ├─> Validate  → scripts/validate_hermes_signal.py
              └─> Log       → output/logs/observation.log
```

## Runner Script

**Path:** `/home/hermes/projects/trading/ai-hedge-fund-crypto/scripts/run_ai_hedge_analysis_once.sh`

**What it does:**
1. Triggers one analysis cycle via `docker exec` → `/trigger` endpoint
2. Copies the resulting signal from the container to `output/latest/`
3. Validates the JSON is parseable
4. Archives a timestamped copy to `output/history/`
5. Runs schema validator
6. Extracts a concise one-line summary to `observation.log`
7. Exits non-zero on any failure (fail-closed)

**What it does NOT do:**
- No trading
- No Freqtrade API calls
- No order placement
- No live trading
- No PrimoAgent interaction

## Schema Validator

**Path:** `/home/hermes/projects/trading/ai-hedge-fund-crypto/scripts/validate_hermes_signal.py`

**Checks performed:**
| Check | Rule |
|-------|------|
| Top-level fields | schema_version, timestamp_utc, source, mode, exchange, pairs |
| schema_version | Must be "1.0" |
| mode | Must be "analysis_only" |
| exchange | Must be "bitget" |
| Pairs | All 3 must exist: BTC/USDT:USDT, ETH/USDT:USDT, SOL/USDT:USDT |
| Pair fields | bias, confidence, recommendation required |
| confidence | Numeric, 0.0–1.0 |
| recommendation | One of: allow, reduce, block, observe |
| bias | One of: bullish, bearish, neutral |
| global_risk_mode | risk_on, risk_off, or neutral |
| Signal age | Warns if >3600s old |

**Output:** `output/validation/schema_validation_latest.json`

## Scheduler Method

| Attribute | Value |
|-----------|-------|
| **Type** | Hermes cron job (no_agent, script-only) |
| **Job ID** | `d01d224792ac` |
| **Name** | ai-hedge-fund-crypto-observation-1h |
| **Schedule** | Every 60 minutes |
| **Repeat** | 24 times (24h observation window) |
| **Script** | `~/.hermes/scripts/ai_hedge_observation_runner.sh` |
| **Workdir** | `/home/hermes/projects/trading/ai-hedge-fund-crypto` |
| **Delivery** | origin (Telegram/Luke) |
| **Agent** | No (script-only, no LLM cost) |

## Smoke Test Result

Two successful cycles completed:

```
Run 1: ts=2026-05-12T04:20:54 risk=neutral llm=True BTC=0.26/observe ETH=0.22/observe SOL=0.20/observe
Run 2: ts=2026-05-12T04:22:32 risk=neutral llm=True BTC=0.26/observe ETH=0.22/observe SOL=0.20/observe
```

**Schema validation: PASS** — 0 errors, 0 warnings on both runs.

**LLM behavior:** Both runs correctly hold (confidence < 60% threshold).
Risk policy is being followed.

## Output Paths

| Path | Purpose |
|------|---------|
| `output/latest/hermes_signal.json` | Latest signal (always overwritten) |
| `output/history/hermes_signal_*.json` | Timestamped archive (one per cycle) |
| `output/logs/observation.log` | Append-only log with START/END markers |
| `output/validation/schema_validation_latest.json` | Latest validation result |

## Disable Scheduler Command

```bash
# Option A: Pause (can resume)
cronjob action=pause job_id=d01d224792ac

# Option B: Remove permanently
cronjob action=remove job_id=d01d224792ac
```

## Freqtrade Safety Confirmation

| Bot | Status | Mode |
|-----|--------|------|
| freqtrade-freqforge | ✅ Up 28h | Dry-run |
| freqtrade-webserver | ✅ Up 5h | — |
| freqtrade-rsi | ✅ Up 5h | Dry-run |
| freqtrade-regime-hybrid | ✅ Up 7h | Dry-run |
| freqtrade-momentum | ✅ Up 11h | Dry-run |

**No Freqtrade bot was touched.** No signal was wired to any strategy.

## Known Limitations

| # | Limitation | Impact |
|---|-----------|--------|
| 1 | Observation is read-only | No Freqtrade execution during observation |
| 2 | 1-hour intervals | May miss intraday moves on 30m timeframe |
| 3 | `docker exec` dependency | Runner requires container to be running |
| 4 | All signals are "observe" | Expected in neutral markets with conf < 60% |
| 5 | `hermes-agent` has stale PrimoAgent bind mount | Cosmetic only, empty directory |

## Next Step After 24h Observation

1. **Review observation log** — `cat output/logs/observation.log`
2. **Count history files** — `ls output/history/ | wc -l` (expect 24+)
3. **Analyze signal variation** — Did any pair reach confidence > 60%?
4. **Check schema pass rate** — `grep VALIDATION output/logs/observation.log`
5. **Decide:** Wire Hermes cron for permanent scheduling, or extend observation

## Files Created

| File | Size |
|------|------|
| `scripts/run_ai_hedge_analysis_once.sh` | 2.9 KB |
| `scripts/validate_hermes_signal.py` | 5.5 KB |
| `~/.hermes/scripts/ai_hedge_observation_runner.sh` | 316 B |

## Final Verdict

**PASS ✅ — Observation scheduler active**

```
ai-hedge-fund-crypto:    ✅ healthy, valid output
hermes-agent:            ✅ NOT restarted
Freqtrade fleet:         ✅ untouched, dry-run
Runner script:           ✅ tested, 2/2 cycles OK
Schema validator:        ✅ 0 errors, 0 warnings
Cron job:                ✅ d01d224792ac, every 60m, 24 runs
No live trading:         ✅ analysis_only mode
No PrimoAgent:           ✅ zero references
```
