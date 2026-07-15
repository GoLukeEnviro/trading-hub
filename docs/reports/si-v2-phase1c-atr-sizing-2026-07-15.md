# SI-v2 Phase 1C — ATR-distance risk-based position sizing contract

**Issue:** #597
**Branch:** `feat/si-v2-phase1c-atr-sizing-2026-07-15`
**Date:** 2026-07-15
**Scope:** A1 (repository-only)
**Runtime mutation:** NONE

## Goal

Implement a canonical position-sizing contract where ATR determines the technical
stop distance and the approved capital-risk budget determines position size.

## Deliverables

| Path | Purpose |
|------|---------|
| `self_improvement_v2/src/si_v2/risk/atr_position_sizing.py` | `SizingDecision`, `PositionSizingInput`, `calculate_position_size()` |
| `self_improvement_v2/tests/test_atr_position_sizing.py` | 33 tests |
| `docs/reports/si-v2-phase1c-atr-sizing-2026-07-15.md` | This report |

## Formula

```
position_size = allowed_capital_risk / effective_stop_distance
effective_stop_distance = ATR * atr_multiplier
```

## Decision model

| Status | Meaning |
|--------|---------|
| `OK` | Within all limits |
| `CAPPED_NOTIONAL` | Capped by max notional |
| `CAPPED_RISK` | Effective risk > budget (conservatively capped) |
| `MIN_NOTIONAL_FAIL` | Cannot meet min notional within risk budget → `REJECTED` |
| `INVALID_INPUT` | Zero/negative/stale/non-finite input → `REJECTED` |

## Required behaviour coverage

| Requirement (from #597) | Test class |
|---|---|
| Normal sizing (standard, low-vol, high-vol) | `TestNormalSizing` (3) |
| Reject zero/negative/nan/inf inputs | `TestInputValidation` (15 param cases) |
| Max-notional cap and min-notional constraints | `TestCaps` (3) |
| Precision rounding (never round up) | `TestPrecision` (2) |
| Fee/slippage buffer | `TestFeeBuffer` (2) |
| Leverage | `TestLeverage` (2) |
| Structured decision output | `TestSizingDecision` (2) |
| Conservative rounding across scenarios | `TestConservativeRounding` (1) |

## Key invariants

- **Never round up** — `_floor_to_precision()` always truncates
- **Min-notional never forces oversizing** — if risk budget can't meet
  min notional, returns `REJECTED`
- **Fee/slippage buffer** applied as `max(0, 1.0 - fee_pct/100)` factor
- **Caps applied in notional terms** (contracts × entry_price), most
  restrictive wins
- **Rounding BEFORE cap checks** — output reflects exchange precision
- **ATR never treated as accepted loss** — explicitly documented

## Tests

```
33 passed in 0.12s
```

## Validation

- `pytest -v` for `test_atr_position_sizing.py`: **33 / 33 passed**
- `python3 -m py_compile`: clean
- `ruff check`: no findings (6 auto-fixes applied)
- `git diff --check`: no whitespace issues

## Explicit non-goals

- No strategy rollout
- No Freqtrade config mutation
- No runtime restart
- No live-capital use
- No Docker/Compose/Cron mutation

## Follow-up

- Wire into strategy entry logic (separate A1 PR)
- Contract coordination with #595 (fleet HWM) and #596 (HALT_BOT)
- Runtime activation requires separate A2 approval

## Human merge required

Autonomous merge is disabled. Only Luke merges at `READY_FOR_HUMAN_MERGE`.
