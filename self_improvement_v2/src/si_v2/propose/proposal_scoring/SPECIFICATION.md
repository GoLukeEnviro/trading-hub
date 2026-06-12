# Issue #35 — Proposal Scoring & Promotion Policy Specification

> **Versioned contract:** `policy_version = "scoring_policy_v1"`
> **Module path:** `self_improvement_v2/src/si_v2/propose/proposal_scoring/`
> **Status:** AC for issue #35.

## 1. Purpose

This document is the versioned, normative specification for the
proposal scoring and promotion policy that the SI v2 Weight Proposal
Engine (issue #63) consumes.

The policy is **advisory only**:

- It is a typed, deterministic, side-effect-free library.
- It never reads or writes live strategy / Freqtrade configuration.
- It never starts shadow, dry-run, or live execution.
- It never marks a proposal as approved.
- Human approval is mandatory after every automated gate.

## 2. Policy inputs

`ProposalScoreInput` carries all the data the engine needs:

| Field | Type | Description |
|---|---|---|
| `evidence_id` | `str` | Deterministic identifier of the evidence record. |
| `source_id` | `str` | The signal source (e.g. `"rainbow:ta"`). |
| `regime` | `str` | Market regime (e.g. `"bullish"`, `"bearish"`, `"neutral"`, `"unknown"`). |
| `evidence_schema_version` | `int` | Schema version of the upstream evidence record. |
| `unique_trade_count` | `int` | Number of unique trades behind the metric. |
| `expectancy` | `Decimal` | Per-trade edge in fractional units (e.g. `0.012` = 1.2%). |
| `drawdown_proxy` | `Decimal` | Evidence-level drawdown proxy in `[0, 1]`. |
| `average_source_confidence` | `Decimal \| None` | `[0, 1]`. |
| `average_regime_confidence` | `Decimal \| None` | `[0, 1]`. |
| `evidence_age_days` | `Decimal` | Age of the evidence, in days. |
| `data_quality_verdict` | `DataQualityVerdict` | `accepted` / `rejected` / `deduplicated`. |
| `is_actionable` | `bool` | Whether the upstream evidence is actionable. |
| `direction_hint` | `DirectionHint` | `increase` / `decrease` / `neutral` (caller-supplied). |
| `has_conflict` | `bool` | Whether conflicting evidence was detected. |
| `human_approval_available` | `bool` | Whether a human approval pathway is available (non-bypassable). |
| `backtest_metrics` | `BacktestMetrics \| None` | Narrow view of a `BacktestResult`. |
| `walk_forward_metrics` | `WalkForwardMetrics \| None` | Narrow view of a `WalkForwardResult`. |

All `Decimal` values are quantized to `SCORING_QUANTUM = 0.000001` with
`ROUND_HALF_EVEN` at the `decimal_safe` module boundary. `NaN`,
`±Infinity`, malformed strings, and unsupported types are rejected at
the `to_decimal` helper.

## 3. Policy thresholds

| Field | Type | Default | Units | Rationale |
|---|---|---|---|---|
| `policy_version` | `Literal["scoring_policy_v1"]` | `"scoring_policy_v1"` | – | Schema identifier; mismatch rejects. |
| `minimum_sample_count` | `int` | `30` | unique trades | At least 30 trades are needed for a stable sample. |
| `maximum_evidence_age_days` | `Decimal` | `30` | days | Stale evidence cannot be the basis of a proposal. |
| `minimum_expectancy` | `Decimal` | `0.0` | fractional | Non-negative per-trade edge is required for any proposal; increase candidates require strictly positive. |
| `maximum_drawdown_proxy` | `Decimal` | `0.25` | fractional | A drawdown proxy above 25% is a hard ceiling. |
| `minimum_confidence` | `Decimal` | `0.30` | `[0, 1]` | Source/regime confidence below 30% is heavily penalised. |
| `accept_threshold` | `Decimal` | `0.65` | `[0, 1]` | Total score ≥ 0.65 → ACCEPT (subject to gates). |
| `defer_threshold` | `Decimal` | `0.40` | `[0, 1]` | Total score ≥ 0.40 and < 0.65 → DEFER. |
| `maximum_proposal_delta` | `Decimal` | `0.10` | `[0, 1]` | Issue #63 enforces a per-proposal delta cap of 10%. |
| `require_backtest_for_promotion` | `bool` | `True` | – | Missing backtest → REJECT with stage `BACKTEST_REQUIRED`. |
| `require_walk_forward_for_promotion` | `bool` | `True` | – | Missing walk-forward → REJECT with stage `WALK_FORWARD_REQUIRED`. |
| `accepted_evidence_schema_versions` | `tuple[int, ...]` | `(1,)` | – | Unknown schema → REJECT. |

### 3.1 Backtest minimum thresholds (`minimum_backtest_thresholds`)

| Field | Default | Rationale |
|---|---|---|
| `minimum_profit_total_pct` | `0.0` | Backtest must at least break even. |
| `minimum_profit_factor` | `1.0` | Backtest profit factor must be ≥ 1. |
| `maximum_drawdown_pct` | `0.20` | Backtest drawdown ≤ 20%. |
| `minimum_win_rate_pct` | `0.0` | No win-rate floor; we rely on profit factor + drawdown. |
| `minimum_total_trades` | `10` | Backtest must have at least 10 trades. |

### 3.2 Walk-forward stability thresholds (`minimum_walk_forward_stability`)

| Field | Default | Rationale |
|---|---|---|
| `minimum_stability_score` | `0.50` | Walk-forward stability in `[0, 1]`. |
| `minimum_out_of_sample_profit_total_pct` | `0.0` | Out-of-sample profit must be non-negative. |

### 3.3 Component weights (default, must sum to 1.0)

| Component | Default | Rationale |
|---|---|---|
| `sample` | `0.10` | Sample size — log-saturating. |
| `expectancy` | `0.20` | Per-trade edge is the primary signal. |
| `drawdown` | `0.20` | Drawdown is the primary risk signal. |
| `confidence` | `0.10` | Source + regime confidence. |
| `recency` | `0.05` | Fresh evidence is better than stale. |
| `backtest` | `0.15` | Backtest metrics. |
| `walk_forward` | `0.15` | Walk-forward stability. |
| `quality` | `0.05` | Pipeline data-quality verdict. |
| **Sum** | **`1.00`** | Enforced within `1e-9`. |

## 4. Hard rejection gates

The engine runs every gate below in a documented order; the first gate
to fire determines the `ProposalRejectionReason` and (for backtest /
walk-forward) the `PromotionStage`. All other gates still report in
`hard_gate_results` so reviewers can see the full picture.

| Gate | Reason | Promotion stage |
|---|---|---|
| Policy version mismatch | `UNSUPPORTED_POLICY_SCHEMA` | `PROPOSAL_ONLY` |
| Evidence schema not accepted | `UNSUPPORTED_EVIDENCE_SCHEMA` | `PROPOSAL_ONLY` |
| Data quality not accepted | `MISSING_DATA_QUALITY_VERDICT` | `PROPOSAL_ONLY` |
| Numeric input not finite | `INVALID_NUMERICS` | `PROPOSAL_ONLY` |
| Sample count below minimum | `INSUFFICIENT_EVIDENCE_SAMPLE` | `PROPOSAL_ONLY` |
| Evidence older than maximum | `STALE_EVIDENCE` | `PROPOSAL_ONLY` |
| Conflicting evidence | `CONFLICTING_EVIDENCE` | `PROPOSAL_ONLY` |
| Drawdown above policy max | `DRAWDOWN_ABOVE_POLICY_MAX` | `PROPOSAL_ONLY` |
| Direction increase, negative expectancy | `NEGATIVE_EXPECTANCY_FOR_INCREASE` | `PROPOSAL_ONLY` |
| Backtest required, missing | `MISSING_MANDATORY_BACKTEST` | `BACKTEST_REQUIRED` |
| Walk-forward required, missing | `MISSING_MANDATORY_WALK_FORWARD` | `WALK_FORWARD_REQUIRED` |
| Human approval unavailable | `HUMAN_APPROVAL_UNAVAILABLE` | `PROPOSAL_ONLY` |

The human-approval gate is **non-bypassable**: even a perfect
proposal with `ACCEPT` would be REJECTed with
`HUMAN_APPROVAL_UNAVAILABLE` if the caller did not set
`human_approval_available=True`.

## 5. Scoring components

Eight bounded, dimensionless, `Decimal` components. Each is
`quantize_score`d to 6 decimals with `ROUND_HALF_EVEN`.

| Component | Formula (clipped to `[0, 1]`) |
|---|---|
| `sample_score` | `(unique_trade_count - minimum) / (2*minimum - minimum)`, clipped. |
| `expectancy_score` | `(expectancy - minimum_expectancy) / 0.05`, clipped. |
| `drawdown_score` | `1 - (drawdown_proxy / maximum_drawdown_proxy)`, clipped. |
| `confidence_score` | `min(source, regime)` (default `0` if both missing), soft-penalised if below `minimum_confidence`. |
| `recency_score` | `(maximum_age - age) / maximum_age`, clipped. |
| `backtest_score` | additive 0.05–0.4 buckets, clipped to 1.0. |
| `walk_forward_score` | additive 0.2–0.5 buckets, clipped to 1.0. |
| `quality_score` | `1.0` iff `data_quality_verdict == accepted and is_actionable` else `0.0`. |

The `total_score` is the weighted sum, clipped to `[0, 1]`, quantized.

## 6. Promotion stages

```
PROPOSAL_ONLY
   │
   ├── gate: BACKTEST_REQUIRED         (REJECT)
   ├── gate: WALK_FORWARD_REQUIRED    (REJECT)
   │
APPROVAL_REQUEST_READY  (ACCEPT, all gates passed)
   │
SHADOW_REVIEW_REQUIRED  (advisory metadata only — never starts a shadow run)
```

- `LIVE_APPROVED` is **not** a member of the `PromotionStage` enum.
- No code path starts shadow, dry-run, or live execution.
- `SHADOW_REVIEW_REQUIRED` is a metadata flag for downstream human
  reviewers; a separate approval-gated issue must act on it.
- Human approval is always required after every automated gate.

## 7. Decision policy

```
if any hard gate failed:
    decision = REJECT
    promotion_stage = stage_for_gate(first_failed_gate)
elif total_score >= accept_threshold:
    decision = ACCEPT
    promotion_stage = APPROVAL_REQUEST_READY
elif total_score >= defer_threshold:
    decision = DEFER
    promotion_stage = PROPOSAL_ONLY
else:
    decision = REJECT
    promotion_stage = PROPOSAL_ONLY
```

`human_approval_required = True` is hard-coded into the
`ProposalDecision` model (Pydantic `Literal[True]`) — there is no
construction path that produces anything else.

## 8. Determinism guarantee

For any fixed `(input, policy)` pair, `score_proposal` returns a
`ProposalDecision` whose `canonical_serialize()` is **byte-identical**
across reruns. This is enforced by:

- `Decimal` arithmetic (no float drift).
- `ROUND_HALF_EVEN` quantization to 6 decimals.
- Pydantic v2 `ConfigDict(strict=True)`.
- A SHA-256 `decision_fingerprint` field on every `ProposalDecision`.

A regression test (`test_determinism.py` in
`tests/test_proposal_scoring.py`) runs `score_proposal` twice and
asserts byte-identical JSON output.

## 9. Explicit statement: no automatic promotion, no application

This policy **does not**:

- Apply any weight.
- Mark any proposal as approved.
- Persist any runtime state.
- Read or write Freqtrade configs.
- Start shadow, dry-run, or live execution.

Every `ProposalDecision` is advisory metadata with
`human_approval_required=True`. A separate, human-approval-gated
issue must act on it. The Weight Proposal Engine (issue #63) builds
on this contract and inherits all of these invariants.

## 10. Versioning

The `policy_version` is a `Literal` in the `ScoringPolicy` model.
Future versions will be introduced under a new `Literal` value (e.g.
`"scoring_policy_v2"`), and the engine will reject any policy whose
version is not the currently supported one with
`UNSUPPORTED_POLICY_SCHEMA`.
