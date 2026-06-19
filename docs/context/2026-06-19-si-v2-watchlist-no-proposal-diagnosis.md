# SI v2 Watchlist NO_PROPOSAL Diagnosis

**Date:** 2026-06-19
**Author:** Hermes (orchestrator), Senior Trading Systems Engineer mode
**Refs:** #284 (WATCH_LIST_ONLY result), #286 (merged ff52299)
**Scope:** read-only diagnosis of why `freqtrade-freqforge` and
`freqtrade-freqforge-canary` emit `NO_PROPOSAL` /
`metrics_source=not_applicable` despite positive read-path telemetry.
No runtime, config, strategy, Docker, or cron mutation performed.

## Verdict

```
ROOT_CAUSE_FOUND
```

The watchlist bots are **profitable, anomaly-free, and flat at cycle-read
time**, so they fall into the *idle* branch of the proposal generator and
emit `NO_PROPOSAL`. Because every `NO_PROPOSAL` is structurally skipped by
the walk-forward metrics enricher, the bots' real closed-trade profit never
enters the metrics ledger (`real_metrics_count=0`). The reason string
`insufficient_signal_depth` is a **misnomer** — actual `signal_depth` is
`1.0` (maximum) for all four bots.

## Source Artifacts

Post-cutoff cycles (cutoff `2026-06-19 11:31:25 UTC`):

| Artifact | Cycle | Commit |
|---|---|---|
| `self_improvement_v2/reports/phase2/evidence/active_cycle_20260619T121720Z.json` | 20260619T121720Z | 29f5a63 |
| `self_improvement_v2/reports/phase2/evidence/active_cycle_20260619T181720Z.json` | 20260619T181720Z | 592c3a8 |
| `self_improvement_v2/reports/phase2/cycle_state/active_cycle_20260619T121720Z.state.json` | 20260619T121720Z | 29f5a63 |
| `self_improvement_v2/reports/phase2/cycle_state/active_cycle_20260619T181720Z.state.json` | 20260619T181720Z | 592c3a8 |
| `self_improvement_v2/state/telemetry_history/telemetry_20260619.jsonl` | 06:17 / 12:17 / 18:17Z | — |

Code (read-only, `main` @ ff52299):

| File | Lines | Role |
|---|---|---|
| `self_improvement_v2/src/si_v2/loop/fleet_analyzer.py` | 246-418 (`_decide_one`) | proposal decision/gate |
| `self_improvement_v2/src/si_v2/loop/active_cycle_runner.py` | 1202-1246 | walk-forward metrics enrichment |

## Watchlist Bots

Decision input traced from `evidence_summary` (the values the code reads):

| Bot | cycles | no_proposal_count | metrics_source | reason_codes | profit_all_% | evidence.status.open_trades | anomaly_flags | root_cause |
|---|---:|---:|---|---|---:|---:|---|---|
| freqtrade-freqforge | 2 | 2 | not_applicable | insufficient_signal_depth | +2.6 (12Z), +2.6 (18Z) | 0 | [] | profitable + flat + no anomaly → idle branch |
| freqtrade-freqforge-canary | 2 | 2 | not_applicable | insufficient_signal_depth | +1.18 (12Z), +1.18 (18Z) | 0 | [] | profitable + flat + no anomaly → idle branch |

Both watchlist bots: `signal_depth=1.0`, `signal_count_total=8`,
`signal_count_available=8`, `auth_outcome=AUTHENTICATED`, `ping_ok=true`,
`daily_trade_count_recent=5-7`, `hypothesis=no_action_insufficient_evidence_v1`,
`metadata_only_candidates={"signal_depth_observed": 1}`.

## Comparator Bots

| Bot | cycles | real_metrics_count | net_pnl | reason | profit_all_% | anomaly_flags |
|---|---:|---:|---:|---|---:|---|
| freqtrade-regime-hybrid | 2 | 2 | -7.128 USDT | walk_forward_net_metrics_negative | -0.72 | ['negative_closed_profit'] |
| freqai-rebel | 2 | 2 | -0.319 USDT | walk_forward_net_metrics_negative | -0.03 | ['negative_closed_profit'] |

Both comparators: `metrics_source=real`, `total_trades=54` / `10`,
`hypothesis=observe_underperforming_pair_cluster_v1`,
`promotion_blocked=true`.

**Key contrast:** the comparators reach `SHADOW_PROPOSAL` (and therefore
real walk-forward metrics) *only because they are losing money* and carry
the `negative_closed_profit` anomaly. The watchlist bots are profitable,
carry no anomaly, and are therefore invisible to the metrics ledger.

## Root Cause

The proposal generator `_decide_one` is **problem/anomaly-driven**. For an
authenticated bot with rich signal evidence (`signal_depth>=0.5`), it chooses
a hypothesis in this order (fleet_analyzer.py:298-322):

```python
if "negative_closed_profit" in anomalies or profit_pct < -5.0:
    hypothesis = UNDERPERFORMING_PAIR          # -> SHADOW_PROPOSAL
elif open_trades > 0 and profit_pct > 5.0:
    hypothesis = PROFIT_DISPERSION              # -> SHADOW_PROPOSAL
elif open_trades == 0:
    # Idle — insufficient evidence for actionable proposal
    return NO_PROPOSAL(reason="insufficient_signal_depth")  # <- WATCHLIST
else:
    hypothesis = STATUS_OBSERVABLE              # -> SHADOW_PROPOSAL
```

The watchlist bots satisfy *none* of the proposal-producing branches:

- no `negative_closed_profit` anomaly and `profit_pct` not `< -5.0` (they are
  positive);
- `profit_pct` not `> 5.0` (they are +2.6% / +1.18%, moderate);
- `evidence.status_open_trades == 0` at the read instant → they hit the
  `elif open_trades == 0` *idle* branch → `NO_PROPOSAL`.

So a profitable, currently-flat bot is classified as "insufficient evidence",
even though it has real closed-trade history
(`profit_closed_percent=2.6`, `daily_trade_count_recent=5-6`).

Two distinct `signal_depth` notions exist and must not be conflated:

- `evidence.signal_depth` = `1.0` (REST-derived 0..1 ratio) — **identical for
  all four bots**, passes the `>=0.5` gate.
- `metadata_only_candidates` = `{"signal_depth_observed": 1}` (watchlist) vs
  `{"signal_depth": 100, ...}` (comparators). The `100` is just
  `int(signal_depth * 100)` written only on the SHADOW_PROPOSAL path; the `1`
  is a hardcoded placeholder on the NO_PROPOSAL path. **Neither gates the
  decision** — the decision is gated by `open_trades == 0`.

### Misnomer

`no_proposal_reason="insufficient_signal_depth"` (line 317) does **not**
describe the actual condition. The in-code comment on the branch reads
*"Idle — insufficient evidence for actionable proposal"*. The true predicate
is `open_trades == 0` (flat at read time) combined with no anomaly and
non-explosive profit. The label should be `idle_no_open_trades_no_anomaly`.

### Downstream effect (why real_metrics_count=0)

`active_cycle_runner.py:1221-1223` assigns metrics unconditionally by
decision type:

```python
if sr.get("decision_type") == "NO_PROPOSAL":
    sr[wf_key] = default_no_proposal_evaluation().to_dict()
    sr[wf_key]["metrics_source"] = METRICS_SOURCE_NOT_APPLICABLE   # SKIP
else:  # SHADOW_PROPOSAL
    agg_metrics, source_tag = derive_aggregate_metrics(snap)       # REAL
```

Because the watchlist bots are branded `NO_PROPOSAL` upstream, the
walk-forward evaluator is **structurally skipped** for them. Their real
aggregate metrics (`derive_aggregate_metrics`) are never computed, so the
genuine profitability that a promotion decision would want to see is never
written to the ledger. Result: `real_metrics_count=0`,
`no_proposal_count=2`, `metrics_source=not_applicable` — even though the bot
has 5-6 real closed trades and +2.6% closed profit.

### Causal chain

```
fleet_analyzer._decide_one
  outcome==AUTHENTICATED, signal_depth=1.0>=0.5, proposal_evidence present
  branch1 negative anomaly:  False  (profit +2.6%, no negative_closed_profit)
  branch2 profit dispersion: False  (evidence.status_open_trades==0)
  branch3 idle (open==0):    True   -> NO_PROPOSAL(reason="insufficient_signal_depth")
        |
active_cycle_runner metrics enricher (line 1221)
  decision_type=="NO_PROPOSAL" -> metrics_source=NOT_APPLICABLE (skip derive_aggregate_metrics)
        |
artifacts: real_metrics_count=0, no_proposal_count=2, metrics_source=not_applicable
```

## Code Path

1. `fleet_analyzer._decide_one(evidence)` — `fleet_analyzer.py:246-418`.
2. Authenticated + rich-signal block — `fleet_analyzer.py:284-342`.
3. Idle branch returning `NO_PROPOSAL` — `fleet_analyzer.py:302-319`
   (reason string at 317).
4. Hypothesis constants — `fleet_analyzer.py:93-97`
   (`no_action_insufficient_evidence_v1`, `observe_underperforming_pair_cluster_v1`,
   `review_fleet_profitability_dispersion_v1`).
5. Metrics enrichment — `active_cycle_runner.py:1202-1246`
   (NO_PROPOSAL skip at 1221-1223).

## Recommended Fix

> Advisory only. Touches proposal/strategy logic → requires explicit human
> approval (L3). Not applied in this task.

The generator is *loss-observing by construction*: it surfaces underperformers
but hides outperformers. For a profit-focused system this is inverted. Two
independent improvements:

1. **Add a positive-profit branch** before the idle branch so profitable bots
   become candidates and their real trades reach the walk-forward evaluator:

   ```python
   # new constant
   PROPOSAL_HYPOTHESIS_REINFORCE_PROFITABLE = "reinforce_profitable_pair_cluster_v1"

   # in _decide_one, before `elif open_trades == 0:`
   elif profit_pct > 0.0 and _has_closed_trade_history(pe):
       hypothesis = PROPOSAL_HYPOTHESIS_REINFORCE_PROFITABLE
   ```

   This routes freqforge/canary to `SHADOW_PROPOSAL` → `derive_aggregate_metrics`
   runs → their real `+2.6%` / `+1.18%` closed trades populate the ledger.
   `requires_human_approval=True` and `mutation_policy=safe_parameter_overlay_only`
   are unchanged, so promotion still stays fully human-gated.

2. **Fix the misleading reason string** (low-risk, improves ledger accuracy):
   rename `insufficient_signal_depth` → `idle_no_open_trades_no_anomaly` at
   `fleet_analyzer.py:317`, with a matching test update. This stops the
   metrics ledger from recording a non-existent "signal depth" problem.

Either fix unblocks the watchlist bots toward pilot-candidate evidence.
Fix (2) alone improves diagnosability but does not, by itself, produce real
metrics for the watchlist bots; fix (1) is required for that.

## Safety Invariants (verified, unchanged by this read-only task)

- Live trading: **forbidden** (`LIVE_FORBIDDEN`). No `dry_run=false`.
- Dry-run: all 4 bots remain `base_mode=proposal_only` / dry-run.
- Mutation counters: `config_mutations=0`, `docker_mutations=0`,
  `runtime_mutations=0`, `live_trading_mutations=0`, `strategy_mutations=0`
  (both post-cutoff cycles).
- Controller: `PAUSED / L3_REPOSITORY_ONLY` — all mutation counters zero.
- Apply path: no proposals applied; `requires_human_approval=True` on every
  decision.
- Auto-apply: disabled.
- Auto-promotion: disabled; both comparators are `promotion_blocked=true`
  (`walk_forward_net_metrics_negative`).
- Secret exposure: none. This report references env-var *names* only
  (`username_env`, `password_env`); no credential values.

## Next Step

Open a tracked issue/PR for fix (1) — the positive-profit hypothesis branch —
so profitable watchlist bots emit `SHADOW_PROPOSAL` and their real
walk-forward metrics are evaluated. Fix (2) (reason-string rename) can ride
along in the same change.
