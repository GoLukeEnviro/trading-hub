# Phase 10.4 — Post-Fleet Measurement Watcher

> **Date:** 2026-07-01
> **PR:** #425 — `feat(si-v2): add post-fleet measurement watcher`
> **Builds on:** PR #424 (Phase 10.3 — Controlled Dry-Run Fleet Runtime Executor)

## Summary

This PR adds the Phase 10.4 post-fleet measurement watcher. It measures whether a promoted dry-run overlay on a fleet target (regime-hybrid or freqai-rebel) helped or harmed that target compared with its pre-apply baseline and/or the control bot.

## Watcher Module

**Module:** `self_improvement_v2/src/si_v2/rollout/fleet_post_fleet_measurement_watcher.py`

**Entry point:** `run_post_fleet_measurement_watcher()`

The watcher:
1. Reads the measurement start record from Phase 10.3 executor
2. Reads a fleet evidence snapshot (target + control comparison)
3. Validates evidence schema and measurement readiness
4. Checks measurement age (stale detection)
5. Determines final decision: KEEP / EXTEND / ROLLBACK
6. Writes decision pack with full evidence trail

## Acceptance Criteria

- [x] Reads measurement start record
- [x] Reads post-apply evidence snapshots
- [x] Emits KEEP / EXTEND / ROLLBACK decision
- [x] Uses statistical evidence when enough data exists
- [x] Blocks on insufficient evidence unless EXTEND_MEASUREMENT is valid
- [x] Writes final decision pack
- [x] No runtime mutation

## Decision Logic

| Condition | Decision |
|-----------|----------|
| Target profit >= control profit AND target PF >= control PF | KEEP_FLEET_OVERLAY |
| Target profit < control profit - 0.01 AND target PF < control PF | ROLLBACK_FLEET_OVERLAY |
| Target profit < control profit - 0.01 (PF OK) | EXTEND (or ROLLBACK if no extend) |
| Target PF < control PF (profit OK) | EXTEND (or KEEP if no extend) |
| Ambiguous | EXTEND (or ROLLBACK if no extend) |

## Validation

```text
$ python -m pytest self_improvement_v2/tests/test_fleet_post_fleet_measurement_watcher.py -q
20 passed

$ python -m pytest self_improvement_v2/tests/test_fleet_rollout_input_resolver.py \
  self_improvement_v2/tests/test_fleet_rollout_chain_runner.py \
  self_improvement_v2/tests/test_fleet_rollout_ready_evidence_runner.py \
  self_improvement_v2/tests/test_fleet_dry_run_runtime_executor.py -q
72 passed

$ python -m ruff check self_improvement_v2/src/si_v2/rollout/fleet_post_fleet_measurement_watcher.py \
  self_improvement_v2/tests/test_fleet_post_fleet_measurement_watcher.py
All checks passed!
```

## Safety

- No live trading
- No `dry_run=false`
- No Docker/Cron/Scheduler changes
- No Freqtrade config mutation
- `runtime_mutation=NONE` in all artifacts
- All tests use `tmp_path`, fake start records, fake evidence snapshots
