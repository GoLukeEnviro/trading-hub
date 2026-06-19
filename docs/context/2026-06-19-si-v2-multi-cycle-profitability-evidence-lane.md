# SI v2 Multi-Cycle Profitability Evidence Lane

## Purpose

Turn the first `#279` outcome (`INCONCLUSIVE_MORE_DATA_REQUIRED`) into a repeatable, read-only evidence lane that can be rerun after each natural scheduled cycle without changing runtime, Docker, Freqtrade config, strategy logic, or live-trading state.

## Input Artifacts

Primary inputs:

- telemetry history JSONL
  - `self_improvement_v2/state/telemetry_history/telemetry_20260619.jsonl`
- active-cycle evidence JSON
  - `self_improvement_v2/reports/phase2/evidence/active_cycle_20260619T121720Z.json`
- cycle-state JSON
  - `self_improvement_v2/reports/phase2/cycle_state/active_cycle_20260619T121720Z.state.json`
- prior `#279` report
  - `docs/context/2026-06-19-si-v2-four-bot-profitability-evidence-gate.md`

Supporting post-fix artifacts currently present after `2026-06-19 11:31:25 UTC`:

- `self_improvement_v2/reports/phase2/active_cycle_runner_report.md`
- `self_improvement_v2/reports/phase2/cycle_state/active_cycle_20260619T121720Z.state.json`
- `self_improvement_v2/reports/phase2/evidence/active_cycle_20260619T121720Z.json`
- `self_improvement_v2/reports/phase2/measurement/attribution_report.md`
- `self_improvement_v2/reports/phase2/measurement/measurement_ledger.jsonl`
- `self_improvement_v2/reports/phase2/measurement/measurement_summary.json`
- `self_improvement_v2/state/telemetry_history/telemetry_20260619.jsonl`

## Aggregation Window

Baseline window for `#284`:

- all post-`#274` / post-auth-fix natural scheduled cycles
- initial cutoff for the current lane: `2026-06-19T11:31:25Z`
- only cycles whose artifact timestamps are at or after that cutoff count toward the multi-cycle lane

Window variants to support later:

1. **since-fix cumulative window**
   - all natural scheduled cycles after the auth-fix cutoff
2. **rolling 5-cycle window**
   - latest five natural scheduled cycles
3. **rolling 10-cycle window**
   - latest ten natural scheduled cycles

Current reality:

- only **one** qualifying post-fix scheduled cycle is currently available:
  - `2026-06-19T12:17:20.448720+00:00`
- therefore `#284` starts as a **lane definition + baseline snapshot**, not as a candidate-selection closeout

## Per-Bot Aggregation Fields

For each bot, the lane should aggregate and persist:

- `net_pnl_total`
  - sum of `walk_forward_net_metrics.total_net_pnl` across qualifying cycles where `metrics_source=real`
- `profit_factor_latest`
  - latest available `walk_forward_net_metrics.profit_factor`
- `profit_factor_weighted` if possible
  - weighted mean of `profit_factor` across qualifying `metrics_source=real` cycles
  - weighting key: `walk_forward_net_metrics.total_trades`
  - fallback: `profit_factor_latest` when fewer than two real-metrics cycles exist
- `trade_count_total`
  - sum of qualifying trade counts from telemetry snapshots
- `max_drawdown_pct_max`
  - maximum observed `walk_forward_net_metrics.max_drawdown_pct` across qualifying real-metrics cycles
- `read_success_rate`
  - successful `/api/v1/profit` reads divided by expected natural scheduled cycles in the window
- `real_metrics_count`
  - count of cycles where `walk_forward_net_metrics.metrics_source=real`
- `no_proposal_count`
  - count of cycles where `decision_type=NO_PROPOSAL` or `reason_codes` include `no_proposal`
- `negative_metrics_count`
  - count of cycles where `evaluation_status=NEGATIVE_NET_METRICS`
- `candidate_score`
  - deterministic score for ranking only; never sufficient for live enablement by itself

## Candidate Score Model

Use a deterministic 0-100 score only for ranking, with hard safety vetoes applied before ranking:

```text
candidate_score = 100 * (
  0.30 * real_metrics_score
+ 0.20 * trade_count_score
+ 0.20 * read_success_score
+ 0.15 * profit_factor_score
+ 0.10 * drawdown_score
+ 0.05 * no_proposal_score
)
```

Suggested normalized components:

- `real_metrics_score = min(real_metrics_count / 2, 1.0)`
- `trade_count_score = min(trade_count_total / 10, 1.0)`
- `read_success_score = clamp(read_success_rate, 0.0, 1.0)`
- `profit_factor_score = clamp(profit_factor_weighted / 1.20, 0.0, 1.0)`
- `drawdown_score = clamp(1.0 - (max_drawdown_pct_max / 5.0), 0.0, 1.0)`
- `no_proposal_score = clamp(1.0 - (no_proposal_count / max(window_cycle_count, 1)), 0.0, 1.0)`

Hard vetoes override score:

- auth regression in any cycle
- missing profit telemetry across the window
- `max_drawdown_pct_max > 10.0`
- `net_pnl_total <= 0` with enough real-metrics evidence

## Classification Model

### candidate

A bot is `candidate` only if all are true:

- `real_metrics_count >= 2`
- `trade_count_total >= 10`
- `net_pnl_total > 0`
- `max_drawdown_pct_max <= 5`
- `read_success_rate = 1.0` across the evaluated window
- no auth regressions
- no telemetry gaps for the same window

### watch

A bot is `watch` if:

- positive read-path telemetry exists
- `/api/v1/profit` reads are healthy
- but `real_metrics_count < 2` or `no_proposal_count` remains too high
- therefore the bot is promising but not yet evidence-complete

This is the intended bucket for positive telemetry without real walk-forward metrics.

### blocked

A bot is `blocked` if any are true:

- auth or profit telemetry is broken
- `max_drawdown_pct_max > 10`
- enough real metrics exist and `net_pnl_total <= 0`
- enough real metrics exist and `profit_factor_weighted < 1.0`

For this lane, “enough real metrics exist” should be interpreted as either:

- `real_metrics_count >= 2`, or
- `real_metrics_count >= 1` and `trade_count_total >= 10`

This prevents a single tiny sample from becoming a permanent block, while still allowing clearly negative evidence to block quickly when trade volume is already meaningful.

### inconclusive

A bot is `inconclusive` if:

- too few qualifying cycles exist overall, or
- metrics are incomplete, or
- the window is not yet large enough to place the bot confidently into `candidate`, `watch`, or `blocked`

## Current Baseline Snapshot

Current qualifying post-fix cycle count:

- `1`
- timestamp: `2026-06-19T12:17:20.448720+00:00`

Controller / safety baseline:

- controller: `PAUSED / L3_REPOSITORY_ONLY`
- fleet verdict: `GREEN`
- runtime mutations: `0`
- config mutations: `0`
- docker mutations: `0`
- live-trading mutations: `0`
- strategy mutations: `0`

Initial per-bot baseline from the single qualifying cycle:

| Bot | net_pnl_total | profit_factor_latest | trade_count_total | max_drawdown_pct_max | read_success_rate | real_metrics_count | no_proposal_count | negative_metrics_count | initial lane status |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| freqtrade-freqforge | 0.00000000 | 0.0000 | 5 | 0.0000 | 1.00 | 0 | 1 | 0 | watch |
| freqtrade-regime-hybrid | -7.12849201 | 0.5801 | 5 | 0.7656 | 1.00 | 1 | 0 | 1 | inconclusive |
| freqtrade-freqforge-canary | 0.00000000 | 0.0000 | 6 | 0.0000 | 1.00 | 0 | 1 | 0 | watch |
| freqai-rebel | -0.31948744 | 0.2057 | 10 | 0.0379 | 1.00 | 1 | 0 | 1 | blocked |

Interpretation:

- `freqtrade-freqforge` and `freqtrade-freqforge-canary` move from generic `inconclusive` into a clearer `watch` bucket because positive read-path telemetry exists but real metrics are still absent.
- `freqai-rebel` is already strong enough for `blocked` under the lane rule because it has real negative metrics plus `trade_count_total >= 10`.
- `freqtrade-regime-hybrid` remains `inconclusive` for the multi-cycle lane because only one real-metrics cycle exists so far and cumulative evidence is still thin, even though the first real sample is negative.

## Reusable Multi-Cycle Process

For every new natural scheduled cycle:

1. discover the latest evidence JSON, cycle-state JSON, and telemetry-history line
2. filter to natural scheduled cycles only
3. include only artifacts at or after the auth-fix cutoff for the since-fix lane
4. update per-bot aggregates
5. recompute `candidate_score`
6. apply the hard classification rules
7. append a fresh report or refresh a rolling scoreboard artifact
8. keep all outputs repo-only and read-only

## Minimal Future Implementation Plan

A future pure helper can be added without runtime impact:

- suggested path: `self_improvement_v2/src/si_v2/proofs/multi_cycle_profitability_gate.py`
- suggested test path: `self_improvement_v2/tests/test_multi_cycle_profitability_gate.py`

Recommended pure-function surface:

- `load_telemetry_history(paths: list[Path], cutoff: datetime) -> list[TelemetryCycle]`
- `load_evidence_bundles(paths: list[Path], cutoff: datetime) -> list[EvidenceCycle]`
- `aggregate_bot_metrics(...) -> dict[str, BotAggregate]`
- `classify_bot(...) -> Literal["candidate", "watch", "blocked", "inconclusive"]`
- `render_table(...) -> list[dict[str, str | int | float]]`

Recommended first test matrix:

- candidate
- watch
- blocked negative metrics
- inconclusive insufficient data
- four-bot mixed case

No runtime calls, no Freqtrade mutation, no Docker dependency, deterministic input/output only.

## Current Trading Decision

- pilot candidate: none
- watch list:
  - `freqtrade-freqforge`
  - `freqtrade-freqforge-canary`
- blocked now:
  - `freqai-rebel`
- needs one more real-metrics cycle before hard classification:
  - `freqtrade-regime-hybrid`

## Safety Invariants

- Live trading: forbidden
- Dry-run: unchanged; no `dry_run=false` introduced
- Runtime mutation: none
- Docker / Compose / services: untouched
- Freqtrade config / strategy: untouched
- Apply path: none
- Auto-apply: disabled
- Auto-promotion: disabled
- Secret exposure: none
