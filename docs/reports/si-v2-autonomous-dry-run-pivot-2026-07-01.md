# SI-v2 Autonomous Dry-Run Pivot — 2026-07-01

## Summary

Pivoted SI-v2 from per-apply human-gated dry-run operation to policy-gated
autonomous dry-run architecture.

## Changes

1. **ADR-2026-07-01** — Architecture decision record for autonomous dry-run loop
   with live-target architecture.
2. **AGENTS.md** — Updated to reflect policy-gated autonomous dry-run, not
   human-gated by default.
3. **current-operational-state.md** — Updated to reflect new mode target,
   KEEP_CANARY_OVERLAY decision, and live as target architecture.
4. **PR #409** — Body patched to remove token example, merged.
5. **Autonomy Policy Module** — `self_improvement_v2/src/si_v2/autonomy/__init__.py`
   — pure policy-as-code decision layer.
6. **Candidate Pipeline** — Updated with autonomy mode support, new status values.
7. **Controlled Apply Actuator** — Added `ApplyMode` class, autonomous dry-run
   gate bypass, LIVE_CAPITAL_MODE blocker.
8. **Tests** — 3 new test files covering autonomy policy, candidate pipeline,
   and controlled actuator modes.

## Safety

- No live trading enabled
- No `dry_run=false`
- No exchange secrets touched
- No Docker/Compose mutation
- No runtime apply in this PR
- No restart
- No rollback
- No jobs.json change
- No watcher enablement

## Architecture State

| Property | Value |
|----------|-------|
| Current mode target | AUTONOMOUS_DRY_RUN |
| Live target | SUPERVISED_LIVE_READY → LIVE_CAPITAL_MODE later |
| Runtime mutation | NONE in this PR |
| Dry-run apply gating | policy-gated |
| Human approval | mode transitions/live only |
