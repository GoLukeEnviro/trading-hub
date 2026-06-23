# SI-v2 Apply Actuator

**Issue:** #332
**Status:** In Progress
**Dependency:** PR #333 (merged 2026-06-23)
**Blocks:** Measurement phase, Mutation counter correctness

## Summary

The SI-v2 Self-Improvement Loop has a critical gap: the "apply" phase created
overlay artifacts in repo-inert paths that were never visible to the running
Freqtrade bots. The mutation counter was incremented despite zero runtime effect.

The Apply Actuator fixes this by:
1. Fleet-verified runtime binding (Docker mount paths, not repo paths)
2. Machine-verified runtime proof (file visibility + loaded config check)
3. Fail-closed policy (any uncertainty → BLOCKED)
4. Strict gate: mutation counter only with GREEN proof
5. Strict gate: measurement only with APPLIED_WITH_RUNTIME_PROOF

## Corrected State Machine

```
ShadowProposal ✅ → Approval ✅ → Overlay Artifact ✅ →
  Runtime Binding (this issue) → Runtime Proof → Mutation Counter →
  Measurement
```

## Implementation

- `self_improvement_v2/src/si_v2/apply_actuator/` — Actuator module
- `self_improvement_v2/tests/test_apply_actuator_*.py` — 47 tests
- `self_improvement_v2/scripts/si_v2_apply_actuator_audit.py` — Audit CLI
- `docs/reports/si-v2-apply-actuator-*.md` — Documentation
- `docs/plans/si-v2-apply-actuator-runtime-activation-plan-2026-06-23.md` — L3 activation runbook

## Acceptance Criteria

- [x] All 4 bot mount paths documented and machine-verifiable
- [x] Overlay artifacts resolve to correct runtime path
- [x] Effective config draft generated, validated
- [x] Machine proof: file visibility + loaded config values
- [x] Mutation counter increments only after runtime proof
- [x] No `dry_run=false`
- [x] No live trading
- [x] No strategy changes
- [x] Bot restart only with explicit approval
- [ ] L3 runtime activation (future, requires approval token)
- [ ] End-to-end: ShadowProposal → APPLIED_WITH_RUNTIME_PROOF → Measurement

## Related

- PR #331: Original controlled apply (NO_RUNTIME_EFFECT)
- PR #333: Correction (merged)
- Issue #332: This issue
- PR #334: Apply Actuator implementation (to be opened)
