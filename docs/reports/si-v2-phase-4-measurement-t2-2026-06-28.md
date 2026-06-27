# SI-v2 Phase 4 — T2 Measurement Snapshot

**Date:** 2026-06-27T21:10:51Z (early trigger — not waiting for 00:27Z)
**Scheduled:** 2026-06-28T00:27Z
**Candidate:** `max_open_trades_3_to_2`
**Target Bot:** `freqtrade-freqforge-canary`

## Verdict: 🟡 YELLOW / CONTINUE_MEASUREMENT

## RuntimeEffectProof

| Check | Result |
|-------|--------|
| Process command | `--config config.json --config overlay_max_open_trades_.json` ✅ |
| max_open_trades | **2** ✅ |
| dry_run | **true** ✅ |
| Strategy | `FreqForge_Override` ✅ |
| Container | Up 3h, healthy ✅ |
| Overlay SHA | `922510976aa0d28324e88b52f6d0e92d51a3c858b2c4ce7c9b081b2efe29d99d` ✅ unchanged |

## T2 Metrics

| Metric | T0 (18:27Z) | T1 (19:27Z) | **T2 (21:10Z)** |
|--------|-------------|-------------|-----------------|
| max_open_trades | 2 ✅ | 2 ✅ | **2** ✅ |
| dry_run | true ✅ | true ✅ | **true** ✅ |
| Container | Up 36min | Up 1h36min | **Up 3h** ✅ |
| Open trades | 0 | 0 | **0** |
| Closed trades | 59 | 59 | **59** |
| Profit | +3.98 USD | +3.98 USD | **+3.98 USD** |
| Wins | 53 (89.8%) | 53 (89.8%) | **53 (89.8%)** |
| Losses | 6 (10.2%) | 6 (10.2%) | **6 (10.2%)** |
| Errors since last | 0 | 0 | **0** ✅ |
| Warnings since last | 0 | 3 (Bitget 429) | **12 (Bitget 429)** |
| New trades since T0 | — | 0 | **0** |
| Kill Switch | NORMAL | HALT_NEW | **NORMAL** |
| RiskGuard | PASS | — | **PASS (3 ACCEPTED)** |

## Control Bot (freqtrade-freqforge)

| Metric | T0 | T1 | **T2** |
|--------|----|----|--------|
| max_open_trades | 3 | 3 | **3** |
| dry_run | true | true | **true** |
| Closed trades | 78 | 78 | **78** |
| Profit | +24.78 USD | +24.78 USD | **+24.78 USD** |
| New trades since T0 | — | 0 | **0** |

## Fleet Context

| Bot | Status | Trades | Profit |
|-----|--------|--------|--------|
| freqtrade-freqforge-canary | ✅ Up 3h | 59 | +3.98 USD |
| freqtrade-freqforge | ✅ Up 16h (healthy) | 78 | +24.78 USD |
| freqtrade-regime-hybrid | ✅ Up 16h | — | — |
| freqai-rebel | ✅ Up 10min | — | — |

## Decision Engine Output

| Field | Value |
|-------|-------|
| `evaluate_measurement_safety()` | **YELLOW** — 12 warnings (Bitget 429) |
| `decide_measurement_point("T2")` | **YELLOW / CONTINUE_MEASUREMENT** |
| Confidence | MEDIUM |
| Key reason | 12 Bitget 429 warnings (rate limiting, non-critical) |
| Next step | Proceed to T3 |

## Analysis

1. **RuntimeProof GREEN** — overlay intact, process command correct, `max_open_trades=2`, `dry_run=true`
2. **Kill Switch now NORMAL** — was HALT_NEW at T1, but still 0 new trades. Market may not be triggering entries, or the `max_open_trades=2` limit is being respected.
3. **12 Bitget 429 warnings** — rate limiting, same pattern as T1 but accumulated over longer runtime. Non-critical.
4. **No new trades** — 0 trades since T0 on both canary and control. The `max_open_trades=2` effect cannot be measured until trades occur.
5. **Control bot identical** — also 0 new trades. No divergence.
