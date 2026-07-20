# Gate-0 C5.2 Preflight Failure Report

**Date:** 2026-07-20
**Execution class:** A0 (read-only)
**Result:** `GATE0_C52_PREFLIGHT_FAIL` / `CORRECTIVE_REQUIRED`

## Summary

A read-only preflight inspection of the C5.2 merge (PR #662, `2875b67`) revealed
that `FreqForge_Gate0_Core_v1` — despite being committed as a "stripped"
strategy — still contains AI, Shadow, and FleetRisk references, uses uninitialized
runtime objects, references undefined functions, and fails Ruff lint checks.
No valid manifest v3 artifact exists. The C5.2 merge status of `✅ MERGED` in
the operational state is incorrect; the correct status is A0-FAIL with a
corrective required (C5.3).

## Detailed findings

### 1. Residual Primo/FleetRisk/AI/Shadow references

`FreqForge_Gate0_Core_v1` still imports or references:
- `self_improvement_v2.src.si_v2.components.risk_manager`
- `self_improvement_v2.src.si_v2.components._fleet_source`
- AI/Shadow signal paths from Primo signal chain
- FleetRisk delegation hooks

These were supposed to be fully stripped per the C5.2 design.

### 2. Uninitialized runtime objects

- `risk_manager` is used in strategy logic but never initialized.
- `_fleet_source` is referenced but never constructed.

### 3. Undefined function references

Three F821 (undefined name) errors in Ruff:
- `normalize_pair` — used but not defined or imported
- `long_risk_allowed` — used but not defined or imported
- `short_risk_allowed` — used but not defined or imported

### 4. Ruff lint failures

Ruff reports **14 total errors** including 3× F821, plus additional
F811 (redefinition), F841 (unused variables), and other issues.

### 5. Tests do not validate strategy in Freqtrade context

The 31 C5.2 tests are predominantly text-based (checking docstrings, class
existence, metadata fields). They do not import `FreqForge_Gate0_Core_v1`
inside a Freqtrade strategy loading context, so the F821 undefined-name
errors are never caught at test time.

### 6. No manifest v3 artifact exists

`build_manifest_v2()` still produces:
- `evaluation-manifest/v1` (not v3)
- `gate0-manifest-v2` (not v3)

No serialized manifest v3 exists on disk or in the repository.

### 7. Default provenance points to wrong strategy

`gate0_strategy_provenance` defaults to `FreqForge_Override`, not
`FreqForge_Gate0_Core_v1`. Any consumer that does not explicitly override
the provenance will use the wrong strategy identity.

### 8. Regime classification has lookahead

The regime classification logic uses post-entry candles for threshold
computation, violating the entry-time-only requirement.

### 9. Selection runner evaluates holdout state

The `SelectionRunner` currently evaluates holdout partition state, which
should remain sealed until the C6 marker.

### 10. Threshold limits out of specification

Current threshold configuration does not match the required guards:
- Min trades: current default ≤ 100 (spec requires > 100)
- OOS max drawdown: no enforcement (spec requires < 25%)
- Profit factor: no enforcement (spec requires > 1.3)

### 11. PR #660 is closed with stale markers

PR #660 (closed) contains `FreqForge_Override` hash and a manifest
placeholder. These stale markers must not be used as evidence.

### 12. No A2 marker is present

No `APPROVED_A2_SELECTION_BACKTEST` or equivalent marker exists.

### 13. No runtime mutation permitted

None of the C5.2 artifacts authorize any runtime change.

## Remediation

A corrective PR (C5.3) must:
- Remove all residual Primo/FleetRisk/AI/Shadow imports and references
- Initialize `risk_manager` and `_fleet_source` or replace with gate0 noop stubs
- Define or stub `normalize_pair`, `long_risk_allowed`, `short_risk_allowed`
- Resolve all 14 Ruff errors (0 remaining)
- Add at least one test that imports `FreqForge_Gate0_Core_v1` in a Freqtrade-compatible context
- Generate a real manifest v3 artifact
- Fix default provenance to `FreqForge_Gate0_Core_v1`
- Fix regime classification to use entry-time-only data
- Remove holdout evaluation from SelectionRunner
- Enforce threshold guards (>100 trades, <25% drawdown, >1.3 profit factor)

## Gate status

| Check | Status |
|---|---|
| Strategy code self-consistent | ❌ FAIL (14 Ruff errors, 3× F821) |
| Primo/FleetRisk/AI/Shadow stripped | ❌ FAIL (residual references) |
| Runtime objects initialized | ❌ FAIL (`risk_manager`, `_fleet_source`) |
| Undefined functions resolved | ❌ FAIL (`normalize_pair`, `long_risk_allowed`, `short_risk_allowed`) |
| Manifest v3 artifact exists | ❌ FAIL (still produces v1/v2) |
| Default provenance correct | ❌ FAIL (still `FreqForge_Override`) |
| Regime classification entry-time | ❌ FAIL (post-entry lookahead) |
| Holdout sealed | ❌ FAIL (evaluated by SelectionRunner) |
| Threshold guards enforced | ❌ FAIL |
| Tests validate in Freqtrade context | ❌ FAIL (text-only) |
| A2 marker present | ❌ FAIL |

**Overall:** `GATE0_C52_PREFLIGHT_FAIL`

**Next:** C5.3 corrective PR required before any A0 re-run or A2 selection backtest.
No A2 marker is valid until C5.3 is merged and A0 re-validated.
