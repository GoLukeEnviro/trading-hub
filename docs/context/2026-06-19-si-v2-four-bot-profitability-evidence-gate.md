# SI v2 Four-Bot Dry-Run Profitability Evidence Gate

## Verdict

INCONCLUSIVE_MORE_DATA_REQUIRED

## Source Artifacts

Primary artifacts:

- `self_improvement_v2/reports/phase2/evidence/active_cycle_20260619T121720Z.json`
- `self_improvement_v2/reports/phase2/cycle_state/active_cycle_20260619T121720Z.state.json`
- `self_improvement_v2/state/telemetry_history/telemetry_20260619.jsonl`

Evidence window embedded in the latest cycle artifact:

- `window_start_utc=2026-06-18T12:17:53.540719+00:00`
- `window_end_utc=2026-06-19T12:17:20.448720+00:00`
- `runs_observed=5`
- evaluated scheduled-cycle timestamps:
  - `2026-06-18T12:17:53.540719+00:00`
  - `2026-06-18T18:17:59.175310+00:00`
  - `2026-06-19T00:17:05.246784+00:00`
  - `2026-06-19T06:17:10.078216+00:00`
  - `2026-06-19T12:17:20.448720+00:00`

Method notes:

- `read_success`, `source_endpoint`, and `trade_count` come from the latest successful `/api/v1/profit` telemetry snapshot in the evidence window.
- `net_pnl`, `profit_factor`, `max_drawdown_pct`, `metrics_source`, `evaluation_status`, and `promotion_blocked` come from `walk_forward_net_metrics` embedded in the latest evidence artifact.
- `stability_score` is computed from successful `/api/v1/profit` `profit_all_percent` observations using the existing SI v2 walk-forward stability formula `1 - (stddev / max_abs)`.
- All four bots only have `2/5` successful profit snapshots inside the 5-cycle window, so stability scores are low-confidence despite numerically high dispersion scores.

## Four-Bot Metrics Matrix

| Bot | read_success | source_endpoint | net_pnl | profit_factor | trade_count | max_drawdown_pct | metrics_source | evaluation_status | classification | stability_score |
|---|---|---|---:|---:|---:|---:|---|---|---|---:|
| freqtrade-freqforge | true | `/api/v1/profit` | 0.00000000 | 0.0000 | 5 | 0.0000 | not_applicable | NOT_APPLICABLE | inconclusive | 0.981 |
| freqtrade-regime-hybrid | true | `/api/v1/profit` | -7.12849201 | 0.5801 | 5 | 0.7656 | real | NEGATIVE_NET_METRICS | blocked | 1.000 |
| freqtrade-freqforge-canary | true | `/api/v1/profit` | 0.00000000 | 0.0000 | 6 | 0.0000 | not_applicable | NOT_APPLICABLE | inconclusive | 1.000 |
| freqai-rebel | true | `/api/v1/profit` | -0.31948744 | 0.2057 | 10 | 0.0379 | real | NEGATIVE_NET_METRICS | blocked | 1.000 |

## Ranking

1. **freqtrade-freqforge** — best positive live telemetry in-window (`profit_all_percent` 2.58 → 2.65) but still `metrics_source=not_applicable`, so not promotable.
2. **freqtrade-freqforge-canary** — positive live telemetry (`profit_all_percent` 1.18 → 1.18) but same `not_applicable` gap.
3. **freqai-rebel** — real profitability metrics exist, but they are net-negative and promotion-blocked.
4. **freqtrade-regime-hybrid** — real profitability metrics exist and are the weakest in the fleet (`net_pnl=-7.12849201`, `profit_factor=0.5801`).

## Candidate Decision

No preferred pilot candidate is technically justifiable from this window.

Why no candidate:

- `freqtrade-freqforge` and `freqtrade-freqforge-canary` have healthy read-path telemetry, but their profitability gate is still `NOT_APPLICABLE` because the latest cycle produced `decision_type=NO_PROPOSAL`, so real `profit_factor` / `max_drawdown_pct` evidence is absent.
- `freqtrade-regime-hybrid` and `freqai-rebel` do have real profitability evidence, but both fail the minimum candidate gate on `net_pnl > 0` and `profit_factor >= 1.05`.
- Coverage is still thin: only `2/5` cycles in the evaluated window yielded successful four-bot `/api/v1/profit` snapshots.

## Blocked / Inconclusive Reasons

- **freqtrade-freqforge** → `inconclusive`
  - latest telemetry healthy: `read_success=true`, `auth_status=AUTHENTICATED`, `source_endpoint=/api/v1/profit`
  - blocked from candidate status by `reason_codes=[no_proposal]`
  - `walk_forward_net_metrics.metrics_source=not_applicable`
  - key profitability gate fields are not real observations for this bot in the latest cycle

- **freqtrade-regime-hybrid** → `blocked`
  - `evaluation_status=NEGATIVE_NET_METRICS`
  - `net_pnl=-7.12849201`
  - `profit_factor=0.580072518214343`
  - `reason_codes=[walk_forward_net_metrics_negative]`

- **freqtrade-freqforge-canary** → `inconclusive`
  - latest telemetry healthy: `read_success=true`, `auth_status=AUTHENTICATED`, `source_endpoint=/api/v1/profit`
  - blocked from candidate status by `reason_codes=[no_proposal]`
  - `walk_forward_net_metrics.metrics_source=not_applicable`
  - key profitability gate fields are not real observations for this bot in the latest cycle

- **freqai-rebel** → `blocked`
  - `evaluation_status=NEGATIVE_NET_METRICS`
  - `net_pnl=-0.31948744`
  - `profit_factor=0.20574061049052306`
  - `reason_codes=[walk_forward_net_metrics_negative]`

## Live-Pilot Implication

No bot is ready for a controlled spot pilot from this evidence window.

The only two bots with positive current `/api/v1/profit` telemetry (`freqtrade-freqforge`, `freqtrade-freqforge-canary`) still lack real profitability-gate metrics in the latest cycle, so promoting either would be evidence-thin and would violate the intended proof-first selection rule.

## Next Required Evidence

1. Accumulate additional natural scheduled cycles with successful four-bot `/api/v1/profit` reads.
2. Wait for `freqtrade-freqforge` or `freqtrade-freqforge-canary` to produce a `SHADOW_PROPOSAL` cycle with `walk_forward_net_metrics.metrics_source=real`.
3. Re-run the gate once a positive bot has real values for all of:
   - `net_pnl`
   - `profit_factor`
   - `max_drawdown_pct`
   - `trade_count`
4. Keep rejecting any pilot candidate with:
   - `read_success != true`
   - `source_endpoint != /api/v1/profit`
   - `trade_count < 5`
   - `net_pnl <= 0`
   - `profit_factor < 1.05`
   - `max_drawdown_pct > 5.0`

## Safety Invariants

- Live trading: forbidden; no live enablement performed.
- Dry-run: unchanged; no `dry_run=false` introduced.
- Mutation counters: `runtime=0`, `config=0`, `docker=0`, `live_trading=0`, `strategy=0`.
- Controller: `PAUSED / L3_REPOSITORY_ONLY`.
- Apply path: none; report is read-only evidence synthesis.
- Auto-apply: disabled.
- Auto-promotion: disabled.
- Secret exposure: none.
