# Live Canary Measurement and Decision — C4

**Status:** `LIVE_CANARY_MEASUREMENT_READY` or `LIVE_CANARY_MEASUREMENT_BLOCKED`

**Decision:** `KEEP` | `EXTEND` | `ROLLBACK_RECOMMENDED` | `INSUFFICIENT_DATA`

**Target:** `freqtrade-freqforge-canary`

---

## Purpose

C4 is the post-activation measurement and decision watcher. It consumes C3
ceremony artifacts, evaluates live canary metrics against the defined C2/C3
measurement window, and produces an explicit decision.

---

## Verification Criteria

| # | Check | Source |
|---|-------|--------|
| 1 | C3 ceremony artifacts exist and are READY | `var/si_v2/live_canary_activation_ceremony/live_canary_activation_ceremony.json` |
| 2 | C3 measurement-start reference exists | `measurement_window` field in C3 ceremony JSON |

---

## Metrics Evaluated

| Metric | Min Threshold | Critical Threshold (Breach) |
|--------|:------------:|:--------------------------:|
| Win rate | ≥ 0.40 (40%) | < 0.25 (25%) |
| Profit factor | ≥ 1.0 | < 0.8 |
| Sharpe ratio | ≥ 0.5 | < 0.0 |
| Max drawdown | ≤ 15% | > 20% |
| Daily loss count | ≤ 3 | > 5 |

---

## Decision Outcomes

| Decision | Condition | Action |
|----------|-----------|--------|
| **KEEP** | All metrics within thresholds, enough data | Continue live canary operation |
| **EXTEND** | One or more metrics borderline | Extend measurement window, re-run |
| **ROLLBACK_RECOMMENDED** | One or more metrics in critical breach | Roll back to dry-run immediately |
| **INSUFFICIENT_DATA** | < 5 trades AND < 3 data points | Wait for more data |

---

## Artifacts Created

| Artifact | Path | Description |
|----------|------|-------------|
| Decision JSON | `var/si_v2/live_canary_measurement_decision/live_canary_measurement_decision.json` | Structured decision result |
| Decision Report | `var/si_v2/live_canary_measurement_decision/live_canary_measurement_decision.md` | Human-readable decision summary |

---

## Safety Guarantees

1. **No rollback execution:** C4 emits `ROLLBACK_RECOMMENDED` but does NOT
   execute the rollback.
2. **No fleet rollout:** C4 does not modify any other bot.
3. **No runtime mutation:** All outputs are advisory JSON/report artifacts.

---

## Track C Flow

```
C1 → C2 → C3 → C4 → Decision → D1 (Fleet Rollout Gate)
                       │
                       ├── KEEP → D1
                       ├── EXTEND → re-run C4 later
                       ├── ROLLBACK_RECOMMENDED → execute rollback (separate module)
                       └── INSUFFICIENT_DATA → wait for more data
```

---

## References

- [Issue #423 — Phase 10.6](https://github.com/GoLukeEnviro/trading-hub/issues/423)
- [PR #436 — C3: Live Canary Activation Ceremony](https://github.com/GoLukeEnviro/trading-hub/pull/436)
- [C3 Ceremony Report](live-canary-activation-ceremony.md)
- [C2 Config Plan Report](live-canary-config-plan.md)
- [Production Risk Limits Spec](../specs/production-risk-limits-spec.md)
