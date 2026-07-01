# SI-v2 Phase 9B — Fleet Rollout Artifact Planner

## Summary

Adds a read-only fleet rollout artifact planner. It consumes Phase-9A rollout policy artifacts and generates per-target rollout plan artifacts: planned overlay, pre-apply snapshot plan, rollback plan, and fleet rollout plan.

## Scope

- Rollout policy reader
- Source overlay validation (path existence + SHA-256 hash match)
- Target runtime spec validation (dry-run, config path, user-data dir, command config reference)
- Per-target overlay plan (planned_overlay.json)
- Pre-apply snapshot plan (pre_apply_snapshot_plan.json)
- Per-target rollback plan (rollback_plan.json)
- Fleet rollout plan artifact (fleet_rollout_plan.json)
- No runtime mutation
- No fleet apply
- No scheduler enablement
- No live trading

## Safety

- Promotion eligibility required (status=PROMOTION_ELIGIBLE)
- Source overlay hash required (SHA-256 verification)
- Target dry-run required
- Target config/user-data paths required
- Target command must contain --config reference
- Runtime mutation remains NONE in all artifacts
- Phase 9C is required for actual controlled runtime ceremony

## Artifact Structure

```
var/si_v2/fleet_rollout_plans/<change_id>/
  fleet_rollout_plan.json
  targets/
    freqtrade-regime-hybrid/
      planned_overlay.json
      pre_apply_snapshot_plan.json
      rollback_plan.json
    freqai-rebel/
      planned_overlay.json
      pre_apply_snapshot_plan.json
      rollback_plan.json
```

## Fail-closed Checks

Blocks when:
- Rollout policy missing or unreadable
- Policy status not PROMOTION_ELIGIBLE
- runtime_mutation not NONE
- Wrong next_required_component
- Empty selected_targets
- Source overlay missing
- Source overlay hash mismatch
- Missing target runtime spec
- Target not dry-run
- Empty config path or user_data_dir
- Empty or config-less command
- Artifact not writable

## Files

- `self_improvement_v2/src/si_v2/rollout/fleet_rollout_artifact_planner.py` — planner module
- `self_improvement_v2/tests/test_fleet_rollout_artifact_planner.py` — 21 tests
