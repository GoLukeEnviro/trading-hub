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

## Canonical Measurement Scope

C4 accepts `C4MeasurementInput` raw trade observations, explicit timezone-aware
`measurement_start_utc` / `measurement_end_utc` boundaries, and the lifetime
and continuation equity baselines. The public decision entrypoint does not
accept precomputed `CanaryMetrics`; missing, naive, invalid, or reversed window
boundaries block the decision rather than falling back to lifetime data.

The canonical selector is `close_in_window_or_open_at_window_end/v1`:

- A trade closed inside the inclusive `[start, end]` interval is realized in
  the window, including a trade opened before the window.
- A trade opened by `end` but closed after `end`, or still open at `end`, is
  included as exposure evidence but its future PnL is excluded.
- A trade closed before `start` or opened after `end` is excluded from the
  window.
- Win rate, profit factor, Sharpe, daily loss count, average profit, and the
  decision trade count use only realized window trades.
- Notional exposure uses trades that remain open at the window end.

Max drawdown retains three explicitly named calculations in evidence:

| Method | Scope | Decision authority |
|--------|-------|--------------------|
| `lifetime` | All realized trades through the window end from lifetime starting equity | No — audit only |
| `window_relative` | Realized window PnL rebased to zero | No — audit only |
| `continuation` | Realized window PnL continued from pre-window equity | **Yes** |

The decision JSON embeds `measurement_scope`, including boundaries, selection
method, included/realized/open/excluded counts and IDs, calculated metrics, and
all three drawdown methods. Its `metric_authority` map explicitly assigns
trade count, win rate, profit factor, Sharpe, daily loss count, and average PnL
to realized-window trades; notional exposure to open-at-window-end trades; and
max drawdown to continuation equity. This makes the exact input scope reviewable
without turning historical or lifetime calculations into windowed decision
authority.

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
