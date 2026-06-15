# Bridge Plan v0.1 — Minimal Signal Bridge

**Date:** 2026-05-16
**Status:** PLAN — awaiting approval
**Scope:** ai-hedge-fund-crypto → primo_signal_state.json (no RiskGuard, no ShadowLogger)

---

## 1. Architecture

```
ai-hedge-fund-crypto                Minimal Bridge (cron 5m)              Freqtrade Bots
┌─────────────────────┐             ┌──────────────────────┐             ┌──────────────────┐
│ /app/output/latest/  │── READ ──→ │ signal_bridge.py      │── WRITE ──→│ primo_signal.py   │
│ hermes_signal.json   │             │                      │             │ reads state file  │
│                      │             │ 1. Read signal        │             │ per bot:          │
│ Format:              │             │ 2. Validate schema    │             │ /freqtrade/       │
│ - schema_version:1.0 │             │ 3. Check freshness    │             │  user_data/       │
│ - pairs → bias,      │             │ 4. Map → state format │             │  primo_signal_    │
│   confidence,action  │             │ 5. Write 4 state files│             │  state.json       │
│ - confidence: 0.0-1.0│             │                      │             │                  │
└─────────────────────┘             └──────────────────────┘             └──────────────────┘
```

## 2. Input Signal Format (ai-hedge-fund-crypto)

```json
{
  "schema_version": "1.0",
  "timestamp_utc": "2026-05-16T22:40:04Z",
  "source": "ai-hedge-fund-crypto",
  "mode": "analysis_only",
  "exchange": "bitget",
  "pairs": {
    "BTC/USDT:USDT": {
      "bias": "neutral|bullish|bearish",
      "confidence": 0.0-1.0,
      "recommendation": "observe|buy|sell",
      "action": "hold|buy|sell",
      "quantity": 0.0,
      "reason": "..."
    }
  },
  "global_risk_mode": "neutral"
}
```

**Key observations:**
- Confidence is 0.0-1.0 (NOT 0-100)
- Only 3 pairs currently (BTC, ETH, SOL)
- Bias maps to long/short direction
- Low confidence → observe/hold → bridge should set allow_long/allow_short = false

## 3. Output State Format (primo_signal_state.json)

Already consumed by `primo_signal.py` → `primo_gate_allows()`:

```json
{
  "schema_version": "0.2",
  "fresh": true,
  "generated_at": "2026-05-16T22:40:04Z",
  "processed_at": "2026-05-16T22:40:05Z",
  "age_minutes": 0.5,
  "source": "signal_bridge_v0.1",
  "pairs": {
    "BTC/USDT": {
      "verdict": "WATCH_ONLY|ACCEPTED",
      "action": "HOLD|LONG|SHORT",
      "confidence": 0.0-1.0,
      "allow_long_bias": false,
      "allow_short_bias": false
    }
  }
}
```

**Key logic in `primo_signal.py`:**
- `fresh == false` → strategy ignores signal, uses own logic (safe fallback)
- `age_minutes > 45` → stale, strategy falls back
- `verdict == WATCH_ONLY` → uses `allow_long_bias` / `allow_short_bias`
- `verdict == ACCEPTED` → uses `allow_long_bias` / `allow_short_bias`
- Pair key format: `BTC/USDT` (not `BTC/USDT:USDT`) — normalize_pair() strips `:USDT`

## 4. Bridge Logic (signal_bridge.py)

```python
# Pseudocode:

1. READ /home/hermes/projects/trading/ai-hedge-fund-crypto/output/latest/hermes_signal.json
2. VALIDATE:
   - schema_version == "1.0"
   - timestamp_utc exists
   - pairs dict exists
   - age < 45 minutes
3. For EACH pair in signal:
   - Strip :USDT from pair name (BTC/USDT:USDT → BTC/USDT)
   - confidence = pair_data["confidence"]
   - bias = pair_data["bias"]
   - action = pair_data["action"]

   # Decision logic:
   if confidence >= 0.60 and bias == "bullish" and action in ("buy", "long"):
     verdict = "ACCEPTED"
     allow_long = True, allow_short = False
   elif confidence >= 0.60 and bias == "bearish" and action in ("sell", "short"):
     verdict = "ACCEPTED"
     allow_long = False, allow_short = True
   else:
     verdict = "WATCH_ONLY"
     allow_long = False, allow_short = False

4. BUILD state dict (schema 0.2 format)
5. WRITE to 4 state files (atomic write: write to .tmp, rename)
6. LOG decision to stdout (for cron capture)
```

## 5. Output Paths (4 state files)

| # | Path | Mount Target |
|---|------|-------------|
| 1 | `/home/hermes/projects/trading/freqtrade/shared/primo_signal_state.json` | shared template |
| 2 | `/home/hermes/projects/trading/freqtrade/bots/regime-hybrid/user_data/primo_signal_state.json` | regime-hybrid bot |
| 3 | `/home/hermes/projects/trading/freqtrade/bots/momentum/user_data/primo_signal_state.json` | momentum bot |
| 4 | `/home/hermes/projects/trading/freqtrade/bots/rsi/user_data/primo_signal_state.json` | rsi dir (canary reads from here?) |

**Note:** FreqAI-Rebel uses its own compose/volume — may NOT read primo_signal_state.json.
Need to verify if Rebel strategy uses the signal gate.

## 6. Deployment Plan

### 6.1 Script Location

```
/home/hermes/projects/trading/orchestrator/scripts/signal_bridge.py
```

### 6.2 Cron Job (Hermes internal)

```
Name: signal-bridge-v0.1
Schedule: every 5 minutes
no_agent: true (script-only, no LLM needed)
script: /home/hermes/projects/trading/orchestrator/scripts/signal_bridge.py
workdir: /home/hermes/projects/trading
```

### 6.3 Fallback Safety

- If signal file missing → write stale state (fresh=false) → strategies fall back to own logic
- If signal > 45 min old → write stale state → strategies fall back
- If signal parse error → log error, DON'T write → old state stays (eventually goes stale)
- If write error to any file → log error, continue with others

## 7. Estimated Size

| Component | Lines |
|-----------|-------|
| signal_bridge.py | ~120-150 |
| Total | ~150 |

## 8. What's NOT in Scope (future extensions)

- RiskGuard validation layer
- ShadowLogger append-only logging
- Per-pair confidence thresholds (configurable)
- Prometheus metrics
- Health check endpoint
- Multi-source signal merging

## 9. Testing Plan

1. **Dry run** — `python3 signal_bridge.py --dry-run` → show what it would write
2. **Manual trigger** — `python3 signal_bridge.py` → write state files
3. **Verify** — cat all 4 state files, check format
4. **Verify strategy reads** — check momentum/regime-hybrid logs for `PrimoGate` output
5. **Cron deploy** — add to Hermes cron, verify 5m cycle
6. **Monitor** — check that momentum bot starts receiving signals within 5m

## 10. Resolved Questions

1. **Canary bot** → reads from `/freqtrade/shared/primo_signal_state.json` via shared mount.
   No separate state file needed.
2. **FreqAI-Rebel** → no primo references in strategies. Uses own volume. No bridge needed.
3. **Pair expansion** → RESOLVED. Bridge reads known pairs from existing state template
   (30 pairs) and fills non-signal pairs with WATCH_ONLY.

## 11. Deployment Status

- **Script:** `/home/hermes/projects/trading/orchestrator/scripts/signal_bridge.py` (11.5 KB)
- **Symlink:** `~/.hermes/scripts/signal_bridge.py` → script
- **Cron Job:** `signal-bridge-cycle` (ID: 1f328ef93d63), every 5m, no_agent=true
- **First run:** 2026-05-16T23:02 UTC
- **Log:** `orchestrator/logs/signal_bridge.log` (JSONL)
- **Output files:** 3 (shared + momentum + regime-hybrid)
