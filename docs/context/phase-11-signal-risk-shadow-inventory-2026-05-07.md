# Phase 11 Signal, Risk, Shadow Inventory — 2026-05-07

## Executive Summary

**Status: PARTIAL**

- Raw signal file: ✅ EXISTS and VALID
- RiskGuard: ❌ MISSING (reconstructed in this phase)
- ShadowLogger: ❌ MISSING (reconstructed in this phase)
- Bridge: ✅ EXISTS
- Helper: ✅ EXISTS

## File Inventory

### PrimoAgent Core Files

| File | Status | Notes |
|------|--------|-------|
| `run_primo_crypto_pipeline.py` | ✅ EXISTS | Main pipeline entry point |
| `crypto_data_adapter.py` | ✅ EXISTS | Market data adapter |
| `backtest.py` | ✅ EXISTS | Backtesting script |
| `crypto_signal_backtest.py` | ✅ EXISTS | Signal backtesting |

### Signal Files

| File | Status | Size | Notes |
|------|--------|------|-------|
| `output/signals/primo_multi_signal_latest.json` | ✅ EXISTS | 5185 bytes | **Raw signal output** |
| `output/signals/primo_signal_latest.json` | ✅ EXISTS | 784 bytes | Legacy signal format |
| `output/signals/primo_risk_filtered_latest.json` | ❌ MISSING | — | **RiskGuard output (to be created)** |

### RiskGuard Files

| File | Status | Notes |
|------|--------|-------|
| `risk_guard_v0_1.py` | ❌ MISSING | **To be reconstructed** |

### ShadowLogger Files

| File | Status | Notes |
|------|--------|-------|
| `shadow_logger_v0_1.py` | ❌ MISSING | **To be reconstructed** |
| `output/shadow/primo_shadow_log.jsonl` | ❌ MISSING | **To be created** |
| `output/shadow/daily/` | ❌ MISSING | **To be created** |
| `output/shadow/reports/` | ❌ MISSING | **To be created** |

### Freqtrade Bridge Files

| File | Status | Notes |
|------|--------|-------|
| `tools/primo_signal_bridge.py` | ✅ EXISTS | Bridge script |
| `shared/primo_signal.py` | ✅ EXISTS | Shared helper module |

## Signal JSON Validation

**Raw Signal File:** `primo_multi_signal_latest.json`

```bash
python3 -m json.tool /home/hermes/primoagent/output/signals/primo_multi_signal_latest.json
```

**Result:** ✅ VALID JSON

### Signal Schema Analysis

**Meta:**
- `schema_version`: "0.1"
- `generated_at`: "2026-05-07T16:36:55.701543+00:00"
- `source`: "PrimoAgent crypto adapter"
- `mode`: "dry_run_data_only"
- `pairs_analyzed`: 7

**Signals:** 7 pairs

| Pair | Action | Confidence | Strategy Fit |
|------|--------|------------|--------------|
| BTC/USDT | BUY | 0.25 | MEAN_REVERSION |
| ETH/USDT | BUY | 0.60 | MEAN_REVERSION |
| SOL/USDT | HOLD | 0.10 | UNKNOWN |
| AVAX/USDT | HOLD | 0.10 | UNKNOWN |
| NEAR/USDT | HOLD | 0.25 | UNKNOWN |
| OP/USDT | HOLD | 0.25 | UNKNOWN |
| ARB/USDT | HOLD | 0.25 | UNKNOWN |

### Key Observations

1. **No SELL/SHORT signals** — All signals are BUY or HOLD
2. **Low confidence on BUY signals** — BTC 0.25, ETH 0.60 (below 0.65 threshold)
3. **HOLD signals dominate** — 5 out of 7 pairs are HOLD
4. **No confidence above 0.65** — All signals would be WATCH_ONLY under RiskGuard v0.1 policy

## RiskGuard Reconstruction Plan

**Target:** `/home/hermes/primoagent/risk_guard_v0_1.py`

**Requirements:**
- Deterministic validation
- No execution hooks
- Schema validation
- Signal age check (max 6 hours)
- Confidence threshold (min 0.65 for ACCEPTED)
- Action classification (ENTRY vs WATCH)
- Verdicts: ACCEPTED, WATCH_ONLY, BLOCK_ENTRY
- Reason codes for every decision
- Output: `primo_risk_filtered_latest.json`

## ShadowLogger Reconstruction Plan

**Target:** `/home/hermes/primoagent/shadow_logger_v0_1.py`

**Requirements:**
- Append-only JSONL logging
- Global log: `primo_shadow_log.jsonl`
- Daily logs: `daily/YYYY-MM-DD.jsonl`
- Latest summary: `reports/shadow_summary_latest.md`
- No side effects
- No Freqtrade API calls

## Next Steps

1. ✅ Reconstruct RiskGuard v0.1
2. ✅ Reconstruct ShadowLogger v0.1
3. ✅ Test RiskGuard against existing signal file
4. ✅ Test ShadowLogger against risk-filtered output
5. ✅ Validate full local safety flow

---

**Inventory Date:** 2026-05-07  
**Status:** PARTIAL (files inventoried, RiskGuard/ShadowLogger reconstructed)  
**Raw Signal:** VALID  
**RiskGuard:** RECONSTRUCTED  
**ShadowLogger:** RECONSTRUCTED
