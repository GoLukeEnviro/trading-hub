# SI-v2 Phase 9A — Controlled Fleet Rollout Policy

## Summary

Adds a read-only fleet rollout policy evaluator. It consumes Measurement Watcher decision packs with statistical evidence and emits promotion eligibility plus selected target bots.

## Scope

- Decision pack reader
- Promotion eligibility checks:
  - KEEP_CANARY_OVERLAY required
  - Statistical KEEP required by default
  - Min statistical evidence grade required (default MODERATE)
  - HARD conflicts block promotion
  - Runtime mutation must be NONE
- Fleet target selection:
  - Canary never a target
  - Dry-run required
  - Allowlisted by bot ID
  - Control only when explicitly allowed
  - Max targets configurable (default 1)
- Rollout policy artifact writer
- No runtime mutation
- No fleet apply
- No scheduler enablement
- No live trading

## Artifact

Output: `var/si_v2/fleet_rollout_policy/<change_id>/rollout_policy_<change_id>.json`

Schema includes: event, change_id, candidate_id, source_bot, status, selected_targets, simple_decision, statistical_evidence, statistical_conflict, allowed_target_bots, runtime_mutation=NONE, next_required_component.

## Files

- `self_improvement_v2/src/si_v2/rollout/__init__.py` — package init
- `self_improvement_v2/src/si_v2/rollout/fleet_rollout_policy.py` — policy evaluator
- `self_improvement_v2/tests/test_fleet_rollout_policy.py` — 24 tests