# SI-v2 Candidate Compatibility Gate — 2026-06-27

## Summary

Added a read-only **Candidate Compatibility Gate** (Gate 9) to the Controlled
Apply Actuator readiness layer. This gate blocks candidates whose overlay
parameters are absent from the runtime `pre_apply_config`, have `None` values,
or whose expected baseline does not match the runtime value.

## Problem

Candidate `f68a031923d0` proposed `cooldown_candles: 3 -> 4` for canary bot
`freqtrade-freqforge-canary`. Runtime inspection showed `cooldown_candles` is
`None` in the canary config — the value `3` was never a valid baseline.

`SAFE_PARAMETERS` alone was insufficient: parameter safety does not imply
runtime compatibility. A parameter can be "safe" but not actually present or
proven in the runtime config.

## Solution

Added `check_candidate_compatibility()` as Gate 9 in `check_readiness()`. The
gate checks for each overlay key:

1. **Key exists in `pre_apply_config`** — if absent, BLOCK (no runtime consumer)
2. **Value is not `None`** — if `None`, BLOCK (no proven baseline)
3. **Expected baseline matches** — if `expected_baselines` is supplied and the
   runtime value differs, BLOCK (baseline mismatch)

The gate does NOT infer mappings (e.g. `cooldown_candles` to
`protections[].CooldownPeriod.stop_duration_candles`). Explicit tested mappings
must be implemented separately.

## Files changed

- `self_improvement_v2/src/si_v2/apply_actuator/controlled_apply_actuator.py`
  - Added `compatibility_gate` field to `ReadinessReport`
  - Added `check_candidate_compatibility()` function
  - Added `expected_baselines` parameter to `check_readiness()`,
    `execute_apply()`, and `run_controlled_apply_canary()`
  - Wired Gate 9 into readiness evaluation and `to_dict()` output
- `self_improvement_v2/tests/test_controlled_apply_actuator.py`
  - 11 new tests covering all gate scenarios

## Test results

- 63/63 controlled apply tests pass (52 original + 11 new)
- 181/181 combined apply-actuator tests pass
- ruff clean

## Classification of f68a031923d0

With the compatibility gate active, candidate `f68a031923d0` is classified as
**BASELINE MISMATCH / NOT READY** when the runtime config has
`cooldown_candles=None`. The gate blocks because the value is `None` — no
proven baseline exists.

## Safety

- Read-only gate, no runtime mutation
- No overlay writes
- No bot config changes
- No Docker restarts
- No live trading
- Fail-closed: missing `pre_apply_config` → BLOCKED