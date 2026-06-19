# SI v2 Multi-Cycle Profitability Score Rerun

## Verdict

WATCH_LIST_ONLY

## Source Artifacts

- `self_improvement_v2/reports/phase2/evidence/active_cycle_20260619T121720Z.json`
- `self_improvement_v2/reports/phase2/evidence/active_cycle_20260619T181720Z.json`
- `self_improvement_v2/reports/phase2/cycle_state/active_cycle_20260619T121720Z.state.json`
- `self_improvement_v2/reports/phase2/cycle_state/active_cycle_20260619T181720Z.state.json`
- `self_improvement_v2/state/telemetry_history/telemetry_20260619.jsonl`
- `docs/context/2026-06-19-si-v2-multi-cycle-profitability-evidence-lane.md`

Telemetry records analyzed:
- `2026-06-19T12:17:20.448720+00:00`
- `2026-06-19T18:17:20.876189+00:00`

## Four-Bot Multi-Cycle Matrix

| Bot | cycles | read_success_rate | net_pnl_total | profit_factor | trade_count_total | max_drawdown_pct_max | real_metrics_count | no_proposal_count | classification | candidate_score |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|
| freqtrade-freqforge | 2 | 1.00 | 0.00000000 | 0.0000 | 11 | 0.0000 | 0 | 2 | watch | 50.0 |
| freqtrade-regime-hybrid | 2 | 1.00 | -14.25698402 | 0.5801 | 10 | 0.7656 | 2 | 0 | blocked | 90.7 |
| freqtrade-freqforge-canary | 2 | 1.00 | 0.00000000 | 0.0000 | 13 | 0.0000 | 0 | 2 | watch | 50.0 |
| freqai-rebel | 2 | 1.00 | -0.63897488 | 0.2057 | 20 | 0.0379 | 2 | 0 | blocked | 87.5 |

## Ranking

1. **freqtrade-freqforge** — `watch`; candidate_score `50.0`; positive read-path telemetry, but still no real walk-forward metrics.
2. **freqtrade-freqforge-canary** — `watch`; candidate_score `50.0`; positive read-path telemetry, but still no real walk-forward metrics.
3. **freqtrade-regime-hybrid** — `blocked`; candidate_score `90.7`; repeated real metrics remain net-negative.
4. **freqai-rebel** — `blocked`; candidate_score `87.5`; repeated real metrics remain net-negative.

## Candidate Decision

No controlled spot-pilot candidate exists yet.

Operational watch list:

- `freqtrade-freqforge`
- `freqtrade-freqforge-canary`

Blocked from promotion now:

- `freqtrade-regime-hybrid`
- `freqai-rebel`

## Missing Evidence Per Bot

- **freqtrade-freqforge** — healthy positive `/api/v1/profit` telemetry across 2/2 cycles, but `real_metrics_count=0` and `no_proposal_count=2`; still needs two real walk-forward metric cycles.
- **freqtrade-freqforge-canary** — healthy positive `/api/v1/profit` telemetry across 2/2 cycles, but `real_metrics_count=0` and `no_proposal_count=2`; still needs two real walk-forward metric cycles.
- **freqtrade-regime-hybrid** — repeated real metrics now exist (`real_metrics_count=2`), but they remain net-negative (`net_pnl_total=-14.25698402`, `profit_factor=0.5801`).
- **freqai-rebel** — repeated real metrics now exist (`real_metrics_count=2`), but they remain net-negative (`net_pnl_total=-0.63897488`, `profit_factor=0.2057`).

## Live-Pilot Implication

The lane has matured from single-cycle uncertainty into a stable watch-list outcome: two bots are operationally watchable but still evidence-incomplete, and two bots are blocked by repeated negative real metrics. This is not enough to justify `#280`.

## Next Required Action

Wait for one more natural scheduled SI v2 cycle, then rerun `#284` again. The highest-value delta is whether `freqtrade-freqforge` or `freqtrade-freqforge-canary` finally produce real walk-forward metrics instead of `NO_PROPOSAL`.

## Safety Invariants

- Live trading: forbidden; no live enablement performed.
- Dry-run: unchanged; no `dry_run=false` introduced.
- Mutation counters: `runtime=0`, `config=0`, `docker=0`, `live_trading=0`, `strategy=0`.
- Controller: `PAUSED / L3_REPOSITORY_ONLY`.
- Apply path: none; analysis/report only.
- Auto-apply: disabled.
- Auto-promotion: disabled.
- Secret exposure: none.
