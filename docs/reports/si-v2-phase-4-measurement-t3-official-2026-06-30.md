# SI-v2 Phase 4 — T3 Measurement Snapshot (Official)

**Date:** 2026-06-30T08:33:13Z (retrospective — T3 due at 2026-06-28T18:27Z)
**Label:** T3
**Official:** true
**Smoke:** false
**Candidate:** `max_open_trades_3_to_2`
**Target Bot:** `freqtrade-freqforge-canary`
**Control Bot:** `freqtrade-freqforge`

## RuntimeEffectProof

| Check | Result |
|-------|--------|
| Runtime proof status | **GREEN** ✅ |
| Process command | `--config config.json --config overlay_max_open_trades_.json` ✅ |
| max_open_trades | **2** ✅ |
| dry_run | **true** ✅ |
| Container | Up 41h, running ✅ |
| Overlay SHA | `922510976aa0d28324e88b52f6d0e92d51a3c858b2c4ce7c9b081b2efe29d99d` ✅ unchanged |
| Strategy | `FreqForge_Override` ✅ |
| Kill Switch | **NORMAL** (was HALT_NEW during T0-T3 window) |
| RiskGuard | Not available as state file |

## T3 Metrics

| Metric | T0 (18:27Z) | T1 (19:27Z) | T2 (21:10Z) | **T3 (retro)** |
|--------|-------------|-------------|-------------|-----------------|
| max_open_trades | 2 ✅ | 2 ✅ | 2 ✅ | **2** ✅ |
| dry_run | true ✅ | true ✅ | true ✅ | **true** ✅ |
| Container | Up 36min | Up 1h36min | Up 3h | **Up 41h** ✅ |
| Open trades | 0 | 0 | 0 | **1** (UNI/USDT) |
| Closed trades | 59 | 59 | 59 | **59** |
| Profit | +3.98 USD | +3.98 USD | +3.98 USD | **+3.98 USD** |
| Wins | 53 (89.8%) | 53 (89.8%) | 53 (89.8%) | **53 (89.8%)** |
| Losses | 6 (10.2%) | 6 (10.2%) | 6 (10.2%) | **6 (10.2%)** |
| Errors since last | 0 | 0 | 0 | **0** ✅ |
| Warnings since last | 0 | 3 (Bitget 429) | 12 (Bitget 429) | **12 (Bitget 429)** |
| New trades since T0 | — | 0 | 0 | **1** (UNI, still open) |
| Kill Switch | NORMAL | HALT_NEW | NORMAL | **NORMAL** |
| RiskGuard | PASS | — | PASS (3 ACCEPTED) | **N/A** |

## Control Bot (freqtrade-freqforge)

| Metric | T0 | T1 | T2 | **T3** |
|--------|----|----|----|--------|
| max_open_trades | 5 | 5 | 5 | **5** |
| dry_run | true | true | true | **true** |
| Closed trades | 78 | 78 | 78 | **80** |
| Profit | +24.78 USD | +24.78 USD | +24.78 USD | **+24.78 USD** |
| New trades since T0 | — | 0 | 0 | **3** (BTC open, ETH/SOL closed with losses) |
| Open trades | 0 | 0 | 0 | **1** (BTC/USDT) |

## Fleet Context

| Bot | Status | Trades | Profit |
|-----|--------|--------|--------|
| freqtrade-freqforge-canary | ✅ Up 41h | 60 (59 closed, 1 open) | +3.98 USD |
| freqtrade-freqforge | ✅ Up 41h | 81 (80 closed, 1 open) | +24.78 USD |
| freqtrade-regime-hybrid | ✅ Up 41h | — | — |
| freqai-rebel | ✅ Up 41h | — | — |

## Decision Engine Output

| Field | Value |
|-------|-------|
| `evaluate_measurement_safety()` | **YELLOW** — 12 warnings (Bitget 429) |
| `decide_measurement_point("T3")` | **YELLOW / EXTEND_MEASUREMENT** |
| Confidence | MEDIUM |
| Key reason | 12 Bitget 429 warnings + insufficient trade data for comparison |
| Next step | Extend measurement window |

## Analysis

1. **RuntimeProof GREEN** — overlay intact, `max_open_trades=2`, `dry_run=true`, container healthy
2. **Kill Switch was HALT_NEW** during the entire T0-T3 window (2026-06-27T19:27Z to 2026-06-29T04:15Z). This blocked ALL new trades fleet-wide. The measurement window was compromised.
3. **Kill Switch now NORMAL** (since 2026-06-29T04:15Z). New trades are now possible.
4. **1 new canary trade** (UNI/USDT, opened 2026-06-29T21:15Z, still open) — first trade since T0.
5. **3 new control trades** (BTC open, ETH/SOL closed with losses) — control is trading.
6. **12 Bitget 429 warnings** — same pattern, non-critical.
7. **Canary-vs-Control comparison not yet meaningful** — only 1 canary trade vs 3 control trades, insufficient for statistical significance.

## Safety

- rollback_required: False
- No apply, restart, or rollback executed
- dry_run preserved on both bots
- Kill Switch NORMAL (fleet-wide)
