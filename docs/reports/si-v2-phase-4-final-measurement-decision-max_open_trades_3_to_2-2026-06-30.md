# SI-v2 Phase 4 — Final Measurement Decision

**Candidate:** max_open_trades_3_to_2
**Target Bot:** freqtrade-freqforge-canary
**Final Verdict:** YELLOW
**Final Decision:** EXTEND_MEASUREMENT
**Confidence:** MEDIUM

## Report Overview

| Label | Exists | Official | Smoke |
|-------|--------|----------|-------|
| T0 | ✅ | ✅ | ❌ |
| T1 | ✅ | ✅ | ❌ |
| T2 | ✅ | ✅ | ❌ |
| T3 | ✅ | ✅ | ❌ |

**All required reports present:** ✅
**Official T3 present:** ✅

## Decision Reasons

- T0: YELLOW — YELLOW: 3 warning(s) since last snapshot
- T1: YELLOW — YELLOW: 3 warning(s) since last snapshot
- T2: YELLOW — YELLOW: 12 warning(s) since last snapshot
- T3: YELLOW — YELLOW: 12 warning(s) since last snapshot
- comparison: trade_gap: canary=+0 vs control=+2

## Next Step

Measurement inconclusive. Extend window or investigate root cause.
