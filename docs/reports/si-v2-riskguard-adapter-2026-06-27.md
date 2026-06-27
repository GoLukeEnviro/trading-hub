# RiskGuard PASS Adapter — SI-v2 Controlled Apply

## Summary

Added a read-only adapter that derives `riskguard_status="PASS"` for the Controlled Apply Actuator from the canonical RiskGuard state file.

## Canonical source

```txt
/home/hermes/projects/trading/orchestrator/state/riskguard/riskguard_state.json
```

## PASS conditions

The adapter returns PASS only when:

- `summary.status == "ACTIVE"`
- at least one pair has `verdict == "ACCEPTED"`
- no pair has `verdict == "BLOCK_ENTRY"`

Otherwise it returns FAIL/BLOCKED (fail-closed).

## Files changed

- `self_improvement_v2/src/si_v2/apply_actuator/controlled_apply_actuator.py`
- `self_improvement_v2/tests/test_controlled_apply_actuator.py`

## Verification

- 52/52 controlled apply tests pass.
- 134/134 combined apply-actuator tests pass.
- ruff clean.

## Related

- Phase 1 PR #371
- Kill-switch fix PR #373
- Canonical kill-switch state initialized at `var/kill_switch.json` in NORMAL mode.

## Notes

This change is read-only and does not affect runtime state, bot configs, or Docker.
