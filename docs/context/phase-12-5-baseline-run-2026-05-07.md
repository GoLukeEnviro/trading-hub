# Phase 12.5 Baseline Run — 2026-05-07

## Executive Summary

**Status: PASS**

Baseline manual run executed successfully.

## Run Details

**Run ID:** `20260507T201616Z`  
**Start:** 2026-05-07T20:16:16Z  
**End:** 2026-05-07T20:18:58Z  
**Duration:** ~162s (PrimoAgent pipeline: ~160s)  
**Exit Code:** 0 (success)

## Step Results

| Step | Description | Status | Duration |
|------|-------------|--------|----------|
| 1 | PrimoAgent pipeline | ✅ COMPLETE | ~160s |
| 1b | Signal file exists | ✅ PASS | <1s |
| 2 | Raw JSON valid | ✅ PASS | <1s |
| 3 | RiskGuard | ✅ 7 WATCH_ONLY | <1s |
| 4 | Risk JSON valid | ✅ PASS | <1s |
| 5 | ShadowLogger | ✅ 7 signals logged | <1s |
| 6 | Shadow log non-empty | ✅ PASS | <1s |
| 7 | Risk-Aware Bridge | ✅ 3 state files | <1s |
| 8 | State files validated | ✅ PASS | <1s |
| 9 | Fleet Healthcheck | ✅ GREEN | <1s |

## Component Results

### PrimoAgent Pipeline

- **Mode:** dry_run_advisory_only
- **Symbols:** 7 (BTC, ETH, SOL, AVAX, NEAR, ARB, OP)
- **Timeframe:** 1h
- **Signals:** All HOLD/WATCH with low confidence (0.1-0.3)

### RiskGuard

- **Total:** 7 signals
- **ACCEPTED:** 0
- **WATCH_ONLY:** 7
- **BLOCK_ENTRY:** 0
- **Stale:** 0

### ShadowLogger

- **Run ID:** `run_20260507T201858Z_1aab7ca0`
- **Signals Logged:** 7
- **Global Log:** 28 lines total
- **Daily Log:** `2026-05-07.jsonl` created

### Bridge

- **Version:** 0.2.0-risk-aware
- **Source Type:** riskguard
- **State Files Written:** 3
- **Schema:** 0.2

### Fleet Healthcheck

- **Verdict:** GREEN
- **Bots Checked:** 3
- **All Bots:** running, dry_run, no credentials

## Log File

**Path:** `/home/hermes/projects/trading/orchestrator/logs/trading_cycle_20260507T201616Z.log`

## Acceptance Criteria Met

- ✅ Wrapper exits 0
- ✅ RiskGuard output valid JSON
- ✅ ShadowLogger appended entries
- ✅ Bridge wrote 3 valid state files
- ✅ Fleet Healthcheck GREEN
- ✅ Validator reports written

---

**Baseline Run Date:** 2026-05-07T20:16:16Z  
**Status:** PASS  
**Next:** Continue manual runs every 4h
