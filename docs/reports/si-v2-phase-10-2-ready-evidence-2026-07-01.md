# Phase 10.2 — Real READY-only Fleet Chain Evidence Run

> **Date:** 2026-07-01
> **PR:** #422 — `feat(si-v2): add fleet rollout ready evidence runner`
> **Builds on:** PR #421 (Phase 10.1 — Real Fleet Rollout Chain Input Resolver)

## Summary

This report proves that the Phase 10.1 resolver can feed real validated SI-v2 artifacts into the Fleet Rollout Chain and produce `FLEET_CHAIN_READY` plus `chain_audit.json` without runtime execution.

## Evidence Runner

**Module:** `self_improvement_v2/src/si_v2/rollout/fleet_rollout_ready_evidence_runner.py`

**Entry point:** `run_fleet_rollout_ready_evidence()`

The runner:
1. Resolves chain input from real SI-v2 artifacts via `resolve_fleet_rollout_chain_input()`
2. Runs the Fleet Rollout Chain in READY-only mode via `run_fleet_rollout_chain(..., runtime_executor=None)`
3. Validates `chain_audit.json` exists and `runtime_mutation == "NONE"`
4. Writes a Phase 10.2 evidence report (`phase_10_2_ready_evidence_report.json`)
5. Returns `FLEET_READY_EVIDENCE_GREEN` or `FLEET_READY_EVIDENCE_BLOCKED`

## Safety Guards

| Guard | Implementation |
|-------|---------------|
| `execute_fleet_runtime=False` | Hard-coded in resolver, checked in runner |
| `runtime_executor=None` | Always passed to chain runner |
| `runtime_mutation=NONE` | Verified in chain audit artifact |
| `chain_audit.json` required | Runner blocks if missing or unreadable |
| Resolver block propagation | Runner blocks immediately on resolver failure |
| Chain block propagation | Runner blocks if chain status != `FLEET_CHAIN_READY` |

## Test Results

```
$ python -m pytest self_improvement_v2/tests/test_fleet_rollout_ready_evidence_runner.py -q
............
12 passed

$ python -m pytest self_improvement_v2/tests/test_fleet_rollout_input_resolver.py -q
........................
24 passed

$ python -m pytest self_improvement_v2/tests/test_fleet_rollout_chain_runner.py -q
..................
18 passed

$ python -m ruff check self_improvement_v2/src/si_v2/rollout ...
All checks passed!
```

### Pre-existing Failures (3 tests, confirmed on `main`)

| Test | Error | Cause |
|------|-------|-------|
| `test_primary_verdict_and_windows_helpers` | `GREEN != WAITING_FOR_POST_APPLY_DATA` | Verdict logic changed in earlier phase |
| `test_root_bundle_field_round_trip` | Same | Same root cause |
| `test_post_apply_zero_closed_keeps_waiting_verdict` | Same | Same root cause |

## Test Coverage (12 tests)

1. ✅ Green READY evidence — `FLEET_READY_EVIDENCE_GREEN`, `chain_audit.json` exists, `runtime_mutation=NONE`
2. ✅ Missing decision pack — `FLEET_READY_EVIDENCE_BLOCKED`
3. ✅ Resolver block propagation — unsafe overlay key blocks
4. ✅ Chain block propagation — no eligible targets blocks
5. ✅ Audit required — `chain_audit_path` must exist
6. ✅ Runtime execution forbidden — `execute_fleet_runtime=True` blocked
7. ✅ Report serializable — `json.dumps(result.to_dict())` works
8. ✅ No live fields — no `api_key`, `secret`, `LIVE` in result
9. ✅ Evidence report contains all required fields
10. ✅ Blocked evidence report contains `blocked_reasons`
11. ✅ `runtime_mutation=NONE` in both green and blocked paths
12. ✅ Evidence runner uses resolver internally

## Architecture

```
SI-v2 Artifacts (decision pack, bot registry, candidate overlay)
  → Phase 10.1 Resolver (fleet_rollout_input_resolver.py)
    → FleetRolloutChainInput
      → Phase 10 Fleet Rollout Chain (fleet_rollout_chain_runner.py)
        → Phase 9A Policy → Phase 9B Planner → Phase 9C Ceremony
          → FLEET_CHAIN_READY
            → chain_audit.json
              → Phase 10.2 Evidence Report
```

## Next Step

Phase 10.3 — Controlled Dry-Run Runtime Executor.
