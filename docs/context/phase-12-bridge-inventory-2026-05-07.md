# Phase 12 Bridge Inventory — 2026-05-07

## Executive Summary

**Status: PARTIAL — Bridge needs RiskGuard upgrade**

Current bridge reads raw PrimoAgent signals only. Does NOT know about RiskGuard verdicts.

---

## Files Audited

| File | Status | Purpose |
|------|--------|---------|
| `tools/primo_signal_bridge.py` | ✅ EXISTS | Bridge script |
| `shared/primo_signal.py` | ✅ EXISTS | Shared helper |
| `output/signals/primo_multi_signal_latest.json` | ✅ VALID | Raw signal |
| `output/signals/primo_risk_filtered_latest.json` | ✅ VALID | Risk-filtered signal |

---

## Current Bridge Behavior

### Input

```
/home/hermes/primoagent/output/signals/primo_multi_signal_latest.json
```

**Schema:**
```json
{
  "meta": { "generated_at": "...", "schema_version": "0.1", ... },
  "signals": [
    {
      "pair": "BTC/USDT",
      "price": 79773.02,
      "signal": {
        "action": "BUY",
        "confidence": 0.25,
        "strategy_fit": "MEAN_REVERSION",
        "reasons": [...]
      },
      "indicators": {...}
    }
  ]
}
```

### Output

```
/home/hermes/projects/trading/freqtrade/bots/<bot>/user_data/primo_signal_state.json
```

**Current Schema:**
```json
{
  "schema_version": "0.1",
  "fresh": true/false,
  "reason": null or "stale_source",
  "source_file": "...",
  "source_generated_at": "...",
  "collected_at": "...",
  "age_minutes": N.N,
  "max_age_minutes": 45.0,
  "pairs": {
    "BTC/USDT": {
      "pair": "BTC/USDT",
      "action": "BUY",
      "confidence": 0.25,
      "strategy_fit": "MEAN_REVERSION",
      "reasons": [...],
      "indicators": {...},
      "price": 79773.02,
      "allow_long": true,
      "allow_short": false
    }
  }
}
```

### Key Limitations

| Issue | Status | Impact |
|-------|--------|--------|
| Reads raw signal only | ❌ YES | No RiskGuard verdict |
| Knows about verdict field | ❌ NO | Cannot distinguish ACCEPTED vs WATCH_ONLY |
| Uses verdict for bias | ❌ NO | All BUY/SELL actions create bias |
| Fail-open on missing risk file | ❌ NO | No risk file path configured |

---

## Current Helper Behavior

### Function: `primo_gate_allows(pair, side, state_file, max_age_minutes)`

**Logic:**
1. Missing state → return `True` (fallback to normal strategy)
2. Stale state (`fresh=false`) → return `True`
3. Age > max → return `True`
4. Pair not found → return `True`
5. Action = BUY/LONG → block short, allow long
6. Action = SELL/SHORT → block long, allow short
7. Other (HOLD/WATCH) → return `True`

**Key Limitations:**

| Issue | Status | Impact |
|-------|--------|--------|
| Knows about verdict field | ❌ NO | Cannot check ACCEPTED vs WATCH_ONLY |
| Checks verdict for bias | ❌ NO | All actions treated equally |
| Fail-open on WATCH_ONLY | ❌ NO | WATCH_ONLY should be neutral |

---

## Audit Questions Answered

| Question | Answer |
|----------|--------|
| Does the bridge currently read raw PrimoAgent signals only? | ✅ **YES** — reads `primo_multi_signal_latest.json` |
| Does the bridge know about RiskGuard verdicts? | ❌ **NO** — no verdict field in state |
| Where does the bridge write per-bot signal state files? | `bots/<bot>/user_data/primo_signal_state.json` |
| Which strategies import the shared helper? | RSI, Momentum, Regime-Hybrid (all three) |
| Does the shared helper fail open on missing or stale signal? | ✅ **YES** — returns `True` (normal strategy) |
| Can the bridge be upgraded without touching strategy logic? | ✅ **YES** — helper can check new fields with backward compatibility |

---

## State Files Found

```bash
find /home/hermes/projects/trading/freqtrade -name 'primo_signal_state.json'
```

**Status:** No state files found yet (bridge hasn't run in this session)

---

## Config/Strategy File Timestamps

| File | Modified | Notes |
|------|----------|-------|
| `bots/rsi/config/config.json` | 2026-05-06 15:14 | Before Phase 11 |
| `bots/momentum/config/config.json` | 2026-05-02 12:51 | Before Phase 11 |
| `bots/regime-hybrid/config/config_regime_hybrid_dryrun.json` | 2026-05-07 09:15 | Before Phase 11 |
| `shared/primo_signal.py` | 2026-05-07 10:13 | Before Phase 11 |
| `tools/primo_signal_bridge.py` | 2026-05-07 10:13 | Before Phase 11 |

**Verdict:** ✅ No config or strategy files changed in Phase 11

---

## Upgrade Plan

### Bridge Changes Required

1. Add `--risk-input` CLI option for RiskGuard output path
2. Prefer RiskGuard output as primary source
3. Include verdict field in per-pair state
4. Include riskguard metadata (version, available)
5. Fail-open when RiskGuard output is missing/invalid
6. Use atomic write pattern (already exists ✅)

### Helper Changes Required

1. Check `verdict` field if present
2. WATCH_ONLY → return `True` (neutral, no bias)
3. BLOCK_ENTRY → return `True` (neutral, no bias)
4. ACCEPTED → use action for directional bias
5. Missing verdict → backward compatible (use action)

### State Contract

New state schema must include:
- `source_type`: "riskguard" or "raw_fallback" or "fail_open_no_riskguard"
- `riskguard_available`: bool
- `riskguard_version`: string
- `pairs[].verdict`: "ACCEPTED" / "WATCH_ONLY" / "BLOCK_ENTRY"
- `pairs[].watch_only`: bool
- `pairs[].block_entry`: bool
- `pairs[].allow_long_bias`: bool (derived from verdict + action)
- `pairs[].allow_short_bias`: bool (derived from verdict + action)

---

## Next Steps

1. ✅ Bridge inventoried
2. → Define risk-aware bridge contract (Phase 2)
3. → Patch bridge for RiskGuard preference (Phase 3)
4. → Patch helper minimally if needed (Phase 4)

---

**Inventory Date:** 2026-05-07  
**Status:** PARTIAL — Bridge needs RiskGuard upgrade  
**Current Behavior:** Raw signal → state (no verdict)  
**Target Behavior:** RiskGuard verdict → state (verdict-aware)
