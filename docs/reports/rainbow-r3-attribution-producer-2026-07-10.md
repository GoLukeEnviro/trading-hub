# Rainbow R3 — Signal-to-Trade Attribution Producer Report

**Issue:** #492
**Parent Tracker:** #489
**Canonical Roadmap:** #423
**Branch:** `feat/rainbow-r3-attribution-producer`
**Base SHA:** `dc15f6dbc4039103cfc7c5a79754ed00df1c4342`
**Head SHA:** *(set on commit)*
**Date:** 2026-07-10

## Observation

The attribution pipeline existed (`AttributionInput`, `SignalContribution`, `PerformanceAttributionEngine`) but had no Rainbow-specific producer. Rainbow signals were not being converted into attribution inputs for closed dry-run trades.

## Cause

R1 reconciled the contract, R2 enabled the read-only client. R3 bridges the gap between validated Rainbow signals and the existing attribution engine.

## Implementation

### New file: `si_v2/rainbow/attribution_producer.py`

| Component | Description |
|-----------|-------------|
| `RainbowAttributionProducerConfig` | Config: max_signal_age_seconds (default 3600), default_contribution_weight (1.0), default_source_confidence |
| `RainbowAttributionResult` | Result: inputs, skipped_trades, errors, matched_count |
| `RainbowAttributionProducer` | Core producer with `produce(signals, trades, now)` method |

### Behavior

- Indexes signals by pair for efficient lookup
- For each closed trade, finds the freshest valid signal for the same pair within the decision window
- Creates `AttributionInput` with `SignalContribution(source_id="rainbow:*")`
- Direction-to-regime mapping: long→BULLISH, short→BEARISH, flat→NEUTRAL, no_signal→NEUTRAL, unknown→UNKNOWN
- No fake/default credit when no valid signal exists
- Contribution weights sum to 1.0

### Safety Invariants

- Attribution is evidence only, never execution authority
- No fake/default credit when no valid signal existed
- Read-only regarding live trading gates
- No Autonomy/RiskGuard gate bypass

## Tests

| Test Suite | Result |
|------------|--------|
| `test_rainbow_attribution_producer.py` (new, 10 tests) | PASS |
| All 9 Rainbow test suites | PASS |
| Ruff (all changed Python files) | PASS |

## CI

*(to be filled after PR)*

## Next Gate

`R3_ATTRIBUTION_PRODUCER_MERGED_R4_SELECTED`
