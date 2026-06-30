# SI-v2 Phase 4 — Extended Measurement T4 Readiness

**Date:** 2026-06-30T08:45:00Z
**Status:** ⏳ **NOT_ENOUGH_DATA**
**Candidate:** `max_open_trades_3_to_2`
**Target Bot:** `freqtrade-freqforge-canary`
**Control Bot:** `freqtrade-freqforge`

## T4 Readiness Check

| Check | Required | Actual | Verdict |
|-------|----------|--------|---------|
| Kill Switch NORMAL | ✅ | **NORMAL** (since 2026-06-29T04:15Z) | ✅ PASS |
| Canary dry_run=true | ✅ | **true** | ✅ PASS |
| Canary max_open_trades=2 | ✅ | **2** (overlay loaded) | ✅ PASS |
| Canary RuntimeProof GREEN | ✅ | **GREEN** | ✅ PASS |
| Canary container healthy | ✅ | **Up 42h, running** | ✅ PASS |
| Canary new closed trades since T3 | ≥1 | **0** | ❌ FAIL |
| Control new closed trades since T3 | ≥1 | **2** (ETH, SOL — both losses) | ✅ PASS |
| No safety RED triggers | ✅ | **No RED** | ✅ PASS |

**Verdict: NOT_ENOUGH_DATA** — Canary has 0 new closed trades since T3. The single new canary trade (UNI/USDT, opened 2026-06-29T21:15Z) is still open. An official T4 measurement point requires at least 1 closed trade on the canary for a meaningful profit/outcome comparison.

## RuntimeEffectProof

| Check | Result |
|-------|--------|
| Runtime proof status | **GREEN** ✅ |
| Process command | `--config config.json --config overlay_max_open_trades_.json` ✅ |
| max_open_trades | **2** ✅ |
| dry_run | **true** ✅ |
| Container | Up 42h, running ✅ |
| Overlay SHA | `922510976aa0d28324e88b52f6d0e92d51a3c858b2c4ce7c9b081b2efe29d99d` ✅ unchanged |
| Strategy | `FreqForge_Override` ✅ |
| Kill Switch | **NORMAL** ✅ |
| RiskGuard | Not available as state file |

## T4 Metrics (as of 2026-06-30T08:45Z)

| Metric | T3 (2026-06-30) | **T4 Readiness** |
|--------|-----------------|-------------------|
| Canary max_open_trades | 2 ✅ | **2** ✅ |
| Canary dry_run | true ✅ | **true** ✅ |
| Canary container | Up 41h | **Up 42h** ✅ |
| Canary open trades | 1 (UNI/USDT) | **1** (UNI/USDT, still open) |
| Canary closed trades | 59 | **59** (no change) |
| Canary profit | +3.98 USD | **+3.98 USD** (no change) |
| Canary new trades since T3 | — | **1** (UNI, opened 2026-06-29T21:15Z, still open) |
| Canary new closed since T3 | — | **0** ❌ |
| Control max_open_trades | 5 | **5** |
| Control dry_run | true | **true** |
| Control container | Up 41h | **Up 42h (healthy)** |
| Control open trades | 1 (BTC/USDT) | **1** (BTC/USDT, still open) |
| Control closed trades | 80 | **80** (no change since T3) |
| Control profit | +24.78 USD | **-1.79 USD** (2 new losses: ETH -12.70, SOL -13.88) |
| Control new trades since T3 | 3 | **3** (BTC open, ETH/SOL closed with losses) |
| Control new closed since T3 | 2 | **2** (ETH, SOL — both losses) |
| Warnings since T3 | — | **0 new** (Bitget 429 pattern stable) |
| Errors since T3 | — | **0** ✅ |
| Unexpected restart | — | **false** ✅ |
| Rollback required | — | **false** ✅ |

## Fleet Context

| Bot | Status | Trades | Profit |
|-----|--------|--------|--------|
| freqtrade-freqforge-canary | ✅ Up 42h | 60 (59 closed, 1 open) | +3.98 USD |
| freqtrade-freqforge | ✅ Up 42h (healthy) | 81 (80 closed, 1 open) | -1.79 USD |
| freqtrade-regime-hybrid | ✅ Up 42h | — | — |
| freqai-rebel | ✅ Up 42h | — | — |

## Analysis

1. **RuntimeProof GREEN** — overlay intact, `max_open_trades=2`, `dry_run=true`, container healthy. No drift since T3.
2. **Kill Switch NORMAL** — confirmed. No longer blocking trades.
3. **Canary has 0 new closed trades** since T3. The UNI/USDT trade opened 2026-06-29T21:15Z is still open after ~11.5h. This is the only new canary trade since T0.
4. **Control has 2 new closed trades** (ETH -12.70 USD, SOL -13.88 USD) and 1 open trade (BTC/USDT). Control profit dropped from +24.78 to -1.79 USD due to these losses.
5. **Canary-vs-Control comparison not yet possible** — 0 closed canary trades vs 2 closed control trades. The canary's single open trade (UNI) needs to close before any profit/outcome comparison is meaningful.
6. **No safety RED triggers** — no errors, no unexpected restarts, no rollback required.

## Next Check Condition

Re-check after the canary's UNI/USDT trade closes. Minimum requirement for official T4:
- At least **1 new closed canary trade** since T3
- At least **1 new closed control trade** since T3 (already met: 2)

## Safety

- rollback_required: False
- No apply, restart, or rollback executed
- dry_run preserved on both bots
- Kill Switch NORMAL (fleet-wide)
