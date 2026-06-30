# SI-v2 Phase 4 — Extended Measurement T4 Follow-up

**Date:** 2026-06-30T09:30:00Z
**Status:** ⏳ **STILL_NOT_ENOUGH_DATA**
**Candidate:** `max_open_trades_3_to_2`
**Target Bot:** `freqtrade-freqforge-canary`
**Control Bot:** `freqtrade-freqforge`

## T4 Re-Check

| Check | T4 Readiness (08:45Z) | **T4 Follow-up (09:30Z)** | Change |
|-------|----------------------|---------------------------|--------|
| Canary UNI/USDT | Open (since 2026-06-29T21:15Z) | **Still open** | ❌ No change |
| Canary new closed trades since T3 | 0 | **0** | ❌ No change |
| Canary total closed | 59 | **59** | ❌ No change |
| Canary profit | +3.98 USD | **+3.98 USD** | ❌ No change |
| Control new closed trades since T3 | 2 | **2** | ❌ No change |
| Control profit | -1.79 USD | **-1.79 USD** | ❌ No change |
| Kill Switch | NORMAL | **NORMAL** | ✅ Stable |
| Container canary | Up 42h | **Up 43h** | ✅ Stable |
| Container control | Up 42h (healthy) | **Up 43h (healthy)** | ✅ Stable |

**Verdict: STILL_NOT_ENOUGH_DATA** — No change since T4 Readiness. The canary's UNI/USDT trade remains open after ~12h. No new trades have been opened on either bot since the T4 Readiness check.

## RuntimeEffectProof

| Check | Result |
|-------|--------|
| Runtime proof status | **GREEN** ✅ |
| max_open_trades | **2** ✅ |
| dry_run | **true** ✅ |
| Container | Up 43h, running ✅ |
| Overlay SHA | `922510976aa0d28324e88b52f6d0e92d51a3c858b2c4ce7c9b081b2efe29d99d` ✅ unchanged |
| Kill Switch | **NORMAL** ✅ |
| Errors since T4 Readiness | **0** ✅ |
| Warnings since T4 Readiness | **0** ✅ |
| Unexpected restart | **false** ✅ |
| Rollback required | **false** ✅ |

## Analysis

1. **No change since T4 Readiness** — zero new trades, zero new closes on both bots in the ~45 minutes since the last check.
2. **Canary UNI/USDT still open** after ~12h. This is a normal trade duration for a trend-following strategy.
3. **Control BTC/USDT still open** — also no change.
4. **No safety RED triggers** — system stable, no drift.
5. **No new Bitget 429 warnings** — rate limiting pattern stable.

## Next Check Condition

Same as T4 Readiness: re-check after the canary's UNI/USDT trade closes. Minimum requirement for official T4:
- At least **1 new closed canary trade** since T3
- At least **1 new closed control trade** since T3 (already met: 2)

## Safety

- rollback_required: False
- No apply, restart, or rollback executed
- dry_run preserved on both bots
- Kill Switch NORMAL (fleet-wide)
