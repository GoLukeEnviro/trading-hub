# Phase 46B — ai-hedge-fund-crypto Rapid 2h Observation Test

**Timestamp:** 2026-05-12T04:31:00Z
**Duration:** 2 hours (12 runs x 10 minutes)

## Executive Summary

Created a temporary rapid observation schedule to collect 12 signal samples
over 2 hours. Uses the same runner and validator from Phase 46 with a
separate output directory. The existing 24h observation job is untouched.

## Purpose of Rapid Test

Collect more signal samples in shorter time to assess:
- Signal stability across consecutive 10m intervals
- Whether confidence values vary with fresh candle data
- LLM output consistency over multiple runs

## Schedule

| Attribute | Value |
|-----------|-------|
| **Job ID** | `515a6ad31dc3` |
| **Name** | ai-hedge-fund-crypto-rapid-2h-test |
| **Interval** | Every 10 minutes |
| **Total runs** | 12 (auto-expires after) |
| **Started** | ~04:39 UTC |
| **Ends** | ~06:39 UTC |
| **Agent** | None (script-only) |

## Runner Wrapper

**Path:** `~/.hermes/scripts/ai_hedge_rapid_observation_runner.sh`

Calls the existing `run_ai_hedge_analysis_once.sh`, then copies the result
to `output/rapid_test/history/` and appends to `rapid_observation.log`.

## Immediate Smoke Test Result

```
RAPID OK: ts=2026-05-12T04:30:51 risk=neutral BTC=0.26/observe ETH=0.22/observe SOL=0.20/observe
Exit: 0
History: hermes_signal_20260512_043003.json (1.1KB)
Container: healthy
```

## Output Paths

| Path | Purpose |
|------|---------|
| `output/rapid_test/rapid_observation.log` | Append-only rapid log |
| `output/rapid_test/history/hermes_signal_*.json` | Timestamped archive |
| `output/latest/hermes_signal.json` | Latest (shared with 24h job) |
| `output/logs/observation.log` | Main log (also appended) |

## Disable / Remove Command

```bash
# Remove the rapid test job:
cronjob action=remove job_id=515a6ad31dc3

# Or pause it:
cronjob action=pause job_id=515a6ad31dc3
```

The job auto-expires after 12 runs (~06:39 UTC).

## Known Limitation

10-minute intervals will often produce identical signals because:
- OHLCV candles update on 30m/1h/4h/1d timeframes
- LLM may return the same reasoning for unchanged market data
- This is expected — the rapid test measures consistency, not variety

## Final Verdict

**PASS ✅**

```
ai-hedge-fund-crypto:    ✅ healthy
Existing 24h job:        ✅ untouched
Rapid job:               ✅ 515a6ad31dc3, 12 runs x 10m
Smoke test:              ✅ 1/1 passed
hermes-agent:            ✅ NOT restarted
Freqtrade:               ✅ untouched
```
