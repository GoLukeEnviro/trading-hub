# Hermes Integration Plan — ai-hedge-fund-crypto Signal Consumer

**Prepared:** 12 May 2026
**Status:** Plan only — not yet wired

## Current State

ai-hedge-fund-crypto runs as a persistent Docker container that:
- Runs analysis on startup and every `/trigger` call
- Writes `output/hermes_signal.json` to a shared bind mount
- Exposes /health, /signal, /trigger on port 8410

## Proposed Hermes Integration

### Option A: Cron-based Polling (Recommended for v1)

Hermes cron job polls ai-hedge-fund-crypto on a schedule:

```
Schedule: every 60m or every 4h
Action: curl -s http://localhost:8410/trigger
Verification: Read output/hermes_signal.json, check schema
```

**Pros:** Simple, no new code, matches existing cron pattern
**Cons:** 1h analysis cycle may miss faster moves (30m timeframe)

### Option B: Event-driven (Future)

Hermes calls /trigger after receiving a webhook or on a condition.

### Option C: HTTP Bridge (Not yet needed)

Full bridge like the old hermes-bridge service that validates signals 
before writing to Freqtrade. Can be added in a later phase.

## Signal Schema for Freqtrade

The current `output/hermes_signal.json` has Hermes-compatible fields:

```json
{
  "pairs": {
    "BTC/USDT:USDT": {
      "confidence": 0.42,
      "recommendation": "observe | allow | block",
      "bias": "bullish | bearish | neutral",
      "action": "hold | buy",
      "quantity": 0.0,
      "reason": "..."
    }
  },
  "global_risk_mode": "neutral | risk_on | risk_off"
}
```

## Freqtrade Integration (Future Phase)

The signal file can be consumed by:
1. A new Freqtrade strategy that reads `hermes_signal.json` as an external signal gate
2. A bridge container similar to the old hermes-bridge

**Design principles:**
- Fail closed: no signal file = no new entries
- Confidence < 60 → observe only
- global_risk_mode = "risk_off" → block all new entries
- Signal freshness limit: 90 seconds (default)

## Scheduling Recommendation

Start with **manual /trigger calls** through Hermes during observation phase.
Add cron-based scheduling (every 60m) after 24h stable observation.

## Risk Fields for Hermes Consumption

| Field | Type | Description |
|-------|------|-------------|
| pairs[].recommendation | string | allow / block / observe |
| pairs[].confidence | float | 0.0–1.0 |
| pairs[].bias | string | bullish / bearish / neutral |
| pairs[].risk_multiplier | float | 0.0–1.0 (future) |
| global_risk_mode | string | risk_on / neutral / risk_off |

## Next Step

Keep manual for now. Wire Hermes cron after 24h observation.
No Freqtrade execution wiring until signal quality is proven.
