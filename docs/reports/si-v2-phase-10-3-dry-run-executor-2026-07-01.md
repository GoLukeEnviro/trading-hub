# Phase 10.3 — Controlled Dry-Run Fleet Runtime Executor

> **Date:** 2026-07-01
> **PR:** #423 — `feat(si-v2): add controlled dry-run fleet runtime executor`
> **Builds on:** PR #422 (Phase 10.2 — READY-only Fleet Chain Evidence Runner)

## Summary

This PR adds the Phase 10.3 controlled dry-run fleet runtime executor. It wraps the Phase 9C ceremony with additional safety guards and executes the Fleet Rollout Chain in dry-run runtime mode for exactly one allowlisted target bot.

## Executor Module

**Module:** `self_improvement_v2/src/si_v2/rollout/fleet_dry_run_runtime_executor.py`

**Entry point:** `run_dry_run_fleet_runtime_executor()`

The executor:
1. Applies 4 safety guards before any execution
2. Overrides `execute_fleet_runtime=True` on the chain input
3. Delegates to `run_fleet_rollout_chain()` with a runtime executor
4. Writes executor audit artifact
5. Returns `DRY_RUN_EXECUTED_GREEN`, `DRY_RUN_EXECUTED_YELLOW`, or `DRY_RUN_EXECUTOR_BLOCKED`

## Safety Guards

| Guard | Implementation | Test |
|-------|---------------|------|
| Refuses `dry_run=false` | `_validate_dry_run()` checks all fleet bots | `test_refuses_dry_run_false` |
| Refuses non-allowlisted target | `_validate_allowlist()` checks against `DEFAULT_ALLOWED_DRY_RUN_TARGETS` | `test_refuses_non_allowlisted_target` |
| Refuses multiple targets (default) | `_validate_single_target()` enforces single target | `test_refuses_multiple_targets_by_default` |
| Blocks without rollback plan | `_validate_rollback_plan()` checks decision_pack_path | `test_blocks_without_rollback_plan` |

## Acceptance Criteria

- [x] Executor refuses `dry_run=false`
- [x] Executor refuses non-allowlisted target
- [x] Executor refuses multiple targets unless explicitly configured
- [x] Executor writes pre-apply snapshot
- [x] Executor writes runtime apply audit
- [x] Executor writes RuntimeEffectProof
- [x] Executor writes measurement start record
- [x] Executor blocks without rollback plan
- [x] Chain can produce `FLEET_CHAIN_EXECUTED_GREEN` in dry-run fixture
- [x] Partial target failure yields YELLOW, not silent GREEN

## Artifacts Written

| Artifact | Path (relative to executor output dir) |
|----------|----------------------------------------|
| Executor audit | `executor_audit.json` |
| Pre-apply snapshot | `chain/<change_id>/ceremony/<change_id>/targets/<bot>/pre_apply_snapshot.json` |
| Runtime apply audit | `chain/<change_id>/ceremony/<change_id>/targets/<bot>/runtime_apply_audit.json` |
| RuntimeEffectProof | `chain/<change_id>/ceremony/<change_id>/targets/<bot>/runtime_effect_proof.json` |
| Measurement start record | `chain/<change_id>/ceremony/<change_id>/targets/<bot>/measurement_start_record.json` |
| Chain audit | `chain/<change_id>/chain_audit.json` |

## Validation

```text
$ python -m pytest self_improvement_v2/tests/test_fleet_dry_run_runtime_executor.py -q
18 passed

$ python -m pytest self_improvement_v2/tests/test_fleet_rollout_input_resolver.py \
  self_improvement_v2/tests/test_fleet_rollout_chain_runner.py \
  self_improvement_v2/tests/test_fleet_rollout_ready_evidence_runner.py -q
54 passed

$ python -m ruff check self_improvement_v2/src/si_v2/rollout/fleet_dry_run_runtime_executor.py \
  self_improvement_v2/tests/test_fleet_dry_run_runtime_executor.py
All checks passed!
```

## Safety

- No live trading
- No `dry_run=false`
- No Docker/Cron/Scheduler changes
- No Freqtrade config mutation
- `runtime_mutation=NONE` in all artifacts
- All tests use `tmp_path`, fake decision packs, fake overlays, fake runtime executors
