# SI-v2 Phase 6C — Runtime Ceremony Runner

## Summary

Adds the runtime ceremony runner that verifies Phase-6B artifacts, builds the canary restart plan, and supports autonomous dry-run runtime execution with mocked tests.

## Scope

- Artifact verification
- RestartPlan integration
- Restart gate evaluation (G1-G10, with G10 bypass for AUTONOMOUS_DRY_RUN)
- Runtime execution wrapper via runtime_executor.apply_mode=AUTONOMOUS_DRY_RUN
- RuntimeEffectProof handling
- T0 activation record (only after GREEN proof)
- No scheduler enablement
- No live trading
- No fleet rollout

## Safety

- Canary-only
- dry_run=true required
- Kill Switch NORMAL required
- RiskGuard PASS required
- overlay hash match required
- rollback plan required
- audit required
- measurement plan required
- missing evidence blocks
- LIVE_CAPITAL_MODE blocks
- MANUAL_L3 still requires token (via runtime_executor)

## Files

- `self_improvement_v2/src/si_v2/pipeline/runtime_ceremony_runner.py` — ceremony runner
- `self_improvement_v2/src/si_v2/apply_actuator/runtime_executor.py` — apply_mode support (AUTONOMOUS_DRY_RUN bypasses token gate)
- `self_improvement_v2/src/si_v2/apply_actuator/restart_gate.py` — G10 bypass for AUTONOMOUS_DRY_RUN
- `self_improvement_v2/tests/test_runtime_ceremony_runner.py` — 18 tests