# RiskGuard Pair Universe Expansion — 2026-06-27

## Executive Summary

The RiskGuard pair universe was expanded from a 3-pair baseline (BTC/ETH/SOL) to a 10-pair active universe with a 7-pair watchlist, all validated against live Bitget futures availability.

## Problem Statement

RiskGuard was evaluating only 3 pairs (BTC/USDT, ETH/USDT, SOL/USDT) because the AI signal generator (`ai-hedge-fund-crypto`) only produced signals for those 3 pairs. The RiskGuard service itself does NOT hardcode any pair list — it evaluates whatever pairs the signal file provides. The bottleneck was upstream in the signal generation pipeline.

The current `riskguard_state.json` showed 0 ACCEPTED pairs, causing the Controlled Apply Actuator to block on Gate 4 (RiskGuard PASS).

## Root Cause Analysis

| Component | Pair Source | Pairs | Hardcoded? |
|-----------|------------|-------|------------|
| `orchestrator/scripts/riskguard_service.py` | AI signal file `pairs` dict | Whatever signal provides | No — evaluates all pairs from signal |
| `ai-hedge-fund-crypto/config.yaml` | `signals.tickers` | 7 tickers (BTC, ETH, SOL, AVAX, NEAR, ARB, OP) | Configurable |
| `ai-hedge-fund-crypto/src/sentiment_collector.py` | `SYMBOL_MAP` / `TICKER_MAP` | 7 entries | **Hardcoded** |
| `ai-hedge-fund-crypto/src/graph/portfolio_management_node.py` | Sentiment loop | 3 pairs (BTC, ETH, SOL) | **Hardcoded at line 236** |
| `freqforge-canary/config/config_canary_dryrun.json` | `pair_whitelist` | 8 pairs | Configurable (L3) |

**Finding**: The signal generator was configured with 7 tickers but only 3 pairs appeared in the output. The sentiment collector and portfolio management node had hardcoded 3-pair and 7-pair limitations.

## Exchange Availability Check

Verified all 18 candidate pairs against live Bitget USDT perpetual futures markets via ccxt:

| Status | Count | Pairs |
|--------|-------|-------|
| AVAILABLE | 17 | BTC, ETH, SOL, XRP, BNB, DOGE, ADA, TRX, LINK, AVAX, SUI, BCH, XLM, DOT, ATOM, UNI, AAVE |
| UNAVAILABLE | 1 | TON/USDT:USDT (market not found on Bitget) |

All available pairs are active, linear, swap-type, USDT-settled.

## Solution: Configurable Pair Universe

### New Files

1. **`orchestrator/config/riskguard-pair-universe.json`** — Tracked config file defining the sanctioned pair universe:
   - `active_universe`: 10 pairs (Tier 0 + Tier 1)
   - `watchlist`: 7 pairs (Tier 2, minus TON which is unavailable)
   - `blacklist`: 6 pairs (stablecoins and delisted assets)
   - `max_active_pairs`: 10
   - `pair_format_regex`: `^[A-Z]+/USDT:USDT$`

2. **`orchestrator/config/riskguard-pair-universe.example.json`** — Example config with minimal 3-pair baseline.

3. **`orchestrator/scripts/pair_universe.py`** — Loader and validator module:
   - `load_pair_universe()` — Loads config, validates all pairs, fails closed to safe baseline on missing/invalid config
   - `validate_pair_format()` — Regex validation for `BASE/USDT:USDT` format
   - `get_verdict_counts()` — Reports ACCEPTED/WATCH_ONLY/BLOCK_ENTRY counts with universe context
   - `PairUniverse` dataclass — Encapsulates active, watchlist, blacklist with helper methods

### Modified Files

4. **`orchestrator/scripts/riskguard_service.py`** — Updated to:
   - Import and load pair universe at startup
   - Include `pair_universe` summary in state output (active_count, watchlist_count, source, outside_universe)
   - Include `block_entry` count in summary
   - Log universe info in RiskGuard summary line

### Test Files

5. **`tests/test_pair_universe.py`** — 22 tests covering all required test cases:
   - RiskGuard loads active universe from config ✓
   - Invalid config fails closed or falls back with warning ✓
   - Unavailable or blacklisted pairs are rejected ✓
   - Stablecoin/stablecoin pairs are rejected ✓
   - At least one ACCEPTED pair yields PASS through existing adapter ✓
   - All WATCH_ONLY yields FAIL ✓
   - Any BLOCK_ENTRY yields FAIL ✓
   - Config schema validates pair format BASE/USDT:USDT ✓
   - Universe count and verdict counts are reported ✓

## Active Universe (10 pairs)

| Pair | Category | Inclusion Rationale |
|------|----------|---------------------|
| BTC/USDT:USDT | Tier 0 — Benchmark | Existing baseline, highest liquidity |
| ETH/USDT:USDT | Tier 0 — Beta | Existing baseline, highest altcoin liquidity |
| SOL/USDT:USDT | Tier 0 — L1 | Existing baseline, high liquidity L1 |
| XRP/USDT:USDT | Tier 1 — Payments | High cap, high liquidity, payment sector |
| BNB/USDT:USDT | Tier 1 — Exchange token | High cap, high liquidity, exchange ecosystem |
| DOGE/USDT:USDT | Tier 1 — Memecoin beta | High cap, high liquidity, sentiment proxy |
| ADA/USDT:USDT | Tier 1 — L1 | High cap, high liquidity, L1 diversity |
| TRX/USDT:USDT | Tier 1 — L1/Payments | High cap, high liquidity, different regime |
| LINK/USDT:USDT | Tier 1 — Oracle | High cap, high liquidity, oracle sector |
| AVAX/USDT:USDT | Tier 1 — L1 | High cap, high liquidity, L1 diversity |

## Watchlist (7 pairs)

| Pair | Category | Watchlist Rationale |
|------|----------|---------------------|
| SUI/USDT:USDT | L1 | Newer high-cap L1, monitor for liquidity stability |
| BCH/USDT:USDT | Payments | Established but lower volume than tier 1 |
| XLM/USDT:USDT | Payments | Similar to BCH, established but moderate volume |
| DOT/USDT:USDT | L0 | Established, already in FT canary config |
| ATOM/USDT:USDT | L0 | Established, already in FT canary config |
| UNI/USDT:USDT | DeFi | Established DeFi, already in FT canary config |
| AAVE/USDT:USDT | DeFi | Established DeFi, already in FT canary config |

## Excluded Pairs

| Pair | Exclusion Reason |
|------|-----------------|
| TON/USDT:USDT | Not available on Bitget futures |
| UST/USDT | Delisted/depegged |
| LUNA/USDT | Delisted/collapsed |
| LUNC/USDT | Delisted |
| TUSD/USDT | Stablecoin pair |
| USDC/USDT | Stablecoin pair |
| DAI/USDT | Stablecoin pair |

## Safety Properties

1. **Fail-closed**: Missing/invalid config → falls back to safe BTC/ETH/SOL baseline with warning
2. **No runtime mutation**: Config is loaded read-only
3. **No live trading**: No `dry_run=false`, no execute_apply, no overlays
4. **Stablecoin rejection**: All stablecoin-base pairs automatically rejected from active/watchlist
5. **Blacklist enforcement**: Blacklisted pairs rejected from active/watchlist
6. **Max cap enforcement**: `max_active_pairs` truncates excess entries
7. **Duplicate removal**: Duplicate pairs in config are deduplicated
8. **Format validation**: All pairs must match `^[A-Z]+/USDT:USDT$`

## Implementation Classification

| Change | Type | Approval Required |
|--------|------|-------------------|
| `orchestrator/config/riskguard-pair-universe.json` | CODE PR (tracked config) | No |
| `orchestrator/scripts/pair_universe.py` | CODE PR (new module) | No |
| `orchestrator/scripts/riskguard_service.py` | CODE PR (modified) | No |
| `tests/test_pair_universe.py` | CODE PR (new tests) | No |
| `freqforge-canary/config/config_canary_dryrun.json` | L3 RUNTIME CONFIG | Yes — explicit approval |
| `ai-hedge-fund-crypto/config.yaml` tickers | L3 RUNTIME CONFIG | Yes — explicit approval |
| `ai-hedge-fund-crypto/src/sentiment_collector.py` SYMBOL_MAP | CODE PR (separate) | No, but separate PR |

## Test Results

```
tests/test_pair_universe.py: 22 passed
Full test suite: 391 passed, 1 skipped, 0 failed
SI-v2 controlled apply tests: 181 passed
Compile check: ALL COMPILE OK
```

## Next Steps

1. **This PR**: Merge configurable pair universe (L2 — safe code + config + tests)
2. **Separate L3 proposal**: Expand `freqforge-canary` pair_whitelist to match active universe (requires explicit L3 approval)
3. **Separate L3 proposal**: Expand `ai-hedge-fund-crypto/config.yaml` tickers and fix hardcoded sentiment collector `SYMBOL_MAP` / `TICKER_MAP` / portfolio_management_node.py line 236 (requires L3 approval for runtime config, code PR for hardcoded source)
4. **Post-merge**: Re-run RiskGuard to verify broader universe yields higher ACCEPTED probability