# Live Canary Activation Ceremony — C3

**Status:** `LIVE_CANARY_CEREMONY_READY` or `LIVE_CANARY_CEREMONY_BLOCKED`

**Target:** `freqtrade-freqforge-canary`

**Prerequisite marker:** `APPROVED_EXECUTE_LIVE_CANARY`

---

## Purpose

The C3 ceremony is the final pre-flight gate before live canary activation. It
validates all preconditions, creates pre-activation snapshots, documents the
rollback plan, initialises the measurement window, and explicitly does **not**
perform execution.

---

## Verification Criteria

| # | Check | Source |
|---|-------|--------|
| 1 | C3 approval marker document exists and is valid | `docs/decisions/APPROVED_EXECUTE_LIVE_CANARY.md` |
| 2 | C3 approval is fresh (≤ 7 days) | File mtime vs. current time |
| 3 | C2 config plan was READY | `var/si_v2/live_canary_config_plan/live_canary_config_plan.json` |
| 4 | C1 approval gate evidence exists and was READY | `var/si_v2/live_canary_approval_gate/live_canary_approval_gate.json` |
| 5 | B2 risk limits document exists | `docs/specs/production-risk-limits-spec.md` |
| 6 | B4 alerting gate document exists | `docs/reports/production-alerting-readiness-gate.md` |
| 7 | Kill switch is NORMAL | `freqtrade/shared/kill_switch.py` (`MODE = "NORMAL"`) |
| 8 | Canary target config exists and is valid dry-run | `freqforge-canary/config/config_canary_dryrun.json` |

---

## Artifacts Created

| Artifact | Path | Description |
|----------|------|-------------|
| Ceremony JSON | `var/si_v2/live_canary_activation_ceremony/live_canary_activation_ceremony.json` | Structured ceremony result |
| Ceremony Report | `var/si_v2/live_canary_activation_ceremony/live_canary_activation_ceremony.md` | Human-readable ceremony summary |
| Config Snapshot | `var/si_v2/live_canary_activation_ceremony/pre_activation_config_snapshot.json` | Pre-activation canary config |
| Kill Switch Snapshot | `var/si_v2/live_canary_activation_ceremony/pre_activation_kill_switch_snapshot.txt` | Pre-activation kill switch state |
| Approval Marker Snapshot | `var/si_v2/live_canary_activation_ceremony/c3_approval_marker_snapshot.md` | C3 approval document copy |

---

## Safety Guarantees

1. **No execution:** The ceremony does NOT apply any config, toggle dry_run,
   modify exchange keys, execute Docker/Cron actions, or perform fleet rollout.
2. **Fail-closed:** Calling `run` with `execute=True` raises `RuntimeError`.
3. **Snapshot-backed:** Pre-activation state is captured before any action.
4. **Rollback-capable:** Rollback plan is documented in every ceremony output.
5. **Measurement-initialised:** Measurement window duration and metrics are
   documented in the ceremony output for subsequent evaluation.

---

## Execution (after ceremony passes)

The ceremony itself does **not** execute the live canary activation. After the
ceremony reports `LIVE_CANARY_CEREMONY_READY`, the dedicated runtime executor
module (C4) must be used for actual activation.

---

## Track C Dependencies

```
C1 — Human Approval Gate  ──────────────────────┐
                                                 │
C2 — Live Canary Config Plan ───────────────────┤
                                                 │
C3 — Live Canary Activation Ceremony (this) ────┤
                                                 │
C4 — Live Canary Execution (separate module) ────┘
```

---

## References

- [Issue #423 — Phase 10.6](https://github.com/GoLukeEnviro/trading-hub/issues/423)
- [PR #433 — C1: Live Canary Approval Gate](https://github.com/GoLukeEnviro/trading-hub/pull/433)
- [PR #434 — C2: Live Canary Config Plan](https://github.com/GoLukeEnviro/trading-hub/pull/434)
- [PR #435 — APPROVED_EXECUTE_LIVE_CANARY Marker](https://github.com/GoLukeEnviro/trading-hub/pull/435)
- [C2 Config Plan Report](live-canary-config-plan.md)
