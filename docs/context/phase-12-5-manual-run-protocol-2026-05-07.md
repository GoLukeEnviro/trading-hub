# Phase 12.5 Manual Run Protocol — 2026-05-07

## Purpose

This document defines the exact protocol for repeated manual validation cycles before Phase 13 cron migration.

## Prerequisites

- ✅ Phase 12 complete (Risk-aware bridge, fleet healthcheck, wrapper v0.2)
- ✅ Phase 12.5 complete (Validator, baseline, audits)
- ✅ Multi-cycle validator operational

## Manual Run Protocol

### Step 1: Run Wrapper

```bash
timeout 600 /home/hermes/projects/trading/orchestrator/scripts/run_trading_cycle.sh
```

**Note:** Use `timeout 600` (10 minutes) because PrimoAgent pipeline needs ~160s.

**Expected Output:**
- Step 1-9 all PASS
- Exit code: 0
- Log file: `orchestrator/logs/trading_cycle_<RUN_ID>.log`

### Step 2: Run Validator

```bash
python3 /home/hermes/projects/trading/orchestrator/scripts/multicycle_validator.py
```

**Expected Output:**
- Status: GREEN
- Wrapper runs found: N+1
- RiskGuard: ✅
- ShadowLogger: N lines
- State Files: ✅
- Fleet Health: GREEN

### Step 3: Review Reports

```bash
cat /home/hermes/projects/trading/orchestrator/reports/multicycle_validation_latest.md
cat /home/hermes/projects/trading/orchestrator/reports/fleet_health_latest.md
```

**Check For:**
- Status: GREEN (or YELLOW with clear cause)
- All state files valid JSON
- Schema stable at 0.2
- ShadowLogger appending correctly
- Fleet health GREEN for all bots

### Step 4: Document Run

**Log File:** `orchestrator/logs/trading_cycle_<RUN_ID>.log`

**Optional:** Copy run ID and timestamp to tracking sheet:

| Run # | Run ID | Timestamp | Status | Notes |
|-------|--------|-----------|--------|-------|
| 1 | 20260507T195314Z | 2026-05-07 19:53 | ✅ | Phase 12 validation |
| 2 | 20260507T201616Z | 2026-05-07 20:16 | ✅ | Phase 12.5 baseline |
| 3 | ... | ... | ... | ... |

## Frequency

**Recommended:** Every 4 hours (aligns with cron schedule)

**Minimum:** 2-3 runs over 24h window

**Target:** 6+ successful runs before Phase 13

## Exit Criteria for Phase 13

- ✅ At least 3 successful manual wrapper runs
- ✅ Preferably 6+ successful runs
- ✅ All state files valid JSON after each run
- ✅ State schema remains stable at 0.2
- ✅ RiskGuard verdicts are explainable
- ✅ ShadowLogger appends without gaps
- ✅ Fleet Healthcheck remains GREEN (or YELLOW with clear explanation)
- ✅ No cronjobs changed
- ✅ No Freqtrade configs or strategies changed
- ✅ No containers restarted
- ✅ No live trading enabled

## Troubleshooting

### Wrapper Timeout (180s)

**Symptom:** Command times out after 180s

**Solution:** Use `timeout 600` wrapper command

```bash
timeout 600 /home/hermes/projects/trading/orchestrator/scripts/run_trading_cycle.sh
```

### RiskGuard ACCEPTED = 0

**Status:** Expected behavior

**Cause:** All signals below confidence threshold (≥0.65) or HOLD/WATCH actions

**Action:** None required — correct RiskGuard behavior

### Fleet Health YELLOW

**Possible Causes:**
- State file missing (but bot otherwise safe)
- RiskGuard output stale
- API ping unavailable but container running

**Action:** Review `fleet_health_latest.md` for specific bot status

### Shadow Logger Gaps

**Check:**
```bash
wc -l /home/hermes/primoagent/output/shadow/primo_shadow_log.jsonl
tail -14 /home/hermes/primoagent/output/shadow/primo_shadow_log.jsonl
```

**Expected:** 7 entries per successful run

## Evidence Locations

| Type | Path |
|------|------|
| Wrapper Logs | `orchestrator/logs/trading_cycle_*.log` |
| Validator Reports | `orchestrator/reports/multicycle_validation_latest.*` |
| Fleet Health | `orchestrator/reports/fleet_health_latest.*` |
| State Files | `freqtrade/bots/*/user_data/primo_signal_state.json` |
| Shadow Log | `primoagent/output/shadow/primo_shadow_log.jsonl` |
| Daily Shadow | `primoagent/output/shadow/daily/YYYY-MM-DD.jsonl` |

---

**Protocol Date:** 2026-05-07  
**Version:** 1.0  
**Next Phase:** Phase 13 Cron Migration (after 6+ successful runs)
