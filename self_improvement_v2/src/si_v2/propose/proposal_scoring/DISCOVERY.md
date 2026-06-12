# Issue #35 — Proposal Scoring & Promotion Policy Discovery

## Reusable existing modules

| Module | Role | Reuse |
|---|---|---|
| `si_v2.evidence.input_pipeline.ProposalEvidenceRecord` | Typed per-(source, regime, confidence) evidence record produced by issue #62 | **input contract** for scoring |
| `si_v2.evidence.input_pipeline.run_evidence_pipeline` | Deterministic, fail-closed pipeline that reads `source_regime_stats` (SQLite, mode=ro) | **evidence provider** for scoring |
| `si_v2.evidence.input_pipeline.RejectionReason` | Typed rejection taxonomy (`SPARSE_DATA`, `STALE_EVIDENCE`, `CONFLICTING_EVIDENCE`, `UNSUPPORTED_SCHEMA`, `INTEGRITY_FAILURE`, `INVALID_NUMERICS`, …) | **shared rejection taxonomy** |
| `si_v2.backtest.walk_forward.WalkForwardResult.stability_score` | Walk-forward stability in `[0.0, 1.0]` | **input** for `walk_forward_score` |
| `si_v2.backtest.backtest_runner.BacktestResult` | Typed backtest result (`passed`, `profit_total_pct`, `max_drawdown_pct`, `win_rate_pct`, `sharpe`, `profit_factor`) | **input** for `backtest_score` |
| `si_v2.propose.safe_parameters` | Safe parameter mutability + ranges | orthogonal — strategy mutation, not proposal scoring |
| `si_v2.approve.approval_gate.ApprovalGateManager` | Auto-reject guardrails + Telegram pending | orthogonal — mutation approval, not proposal scoring |
| `si_v2.analyze.performance_analyzer.PerformanceAnalyzer` | Per-bot window stats | orthogonal — different aggregation unit (per-bot, not per-source/regime) |
| `si_v2.deploy.shadow_logger.ShadowLogger` | Append-only audit | **downstream consumer** (out of scope for #35; issue #63 may log proposal metadata) |

No existing `proposal_score` / `promotion_policy` module exists. No conflicting vocabulary was found. Therefore the canonical path is **new** but located inside the existing `propose` subpackage and typed to the existing `ProposalEvidenceRecord` contract.

## Selected canonical package path

```
self_improvement_v2/src/si_v2/propose/proposal_scoring/
  __init__.py
  models.py            # Pydantic v2 typed contracts (zero Any)
  policy.py            # ScoringPolicy definition + validation
  scoring.py           # ScoreProposer: deterministic per-record scoring
  promotion.py         # PromotionStage, PromotionGateResult, transitions
  rejection.py         # ProposalRejectionReason enum
  decimal_safe.py      # Decimal helpers, rounding, normalization
  DISCOVERY.md
  tests/
    __init__.py
    test_proposal_scoring.py
    test_promotion_policy.py
    test_decimal_safe.py
    fixtures/
      positive_evidence.json
      sparse_evidence.json
      stale_evidence.json
      conflicting_evidence.json
      high_drawdown_evidence.json
      negative_expectancy_evidence.json
      policies/
        default_v1.json
        invalid_weights.json
```

## Policy inputs

- `ProposalScoreInput` (typed)
  - `evidence_id: str`
  - `source_id: str`
  - `regime: str`  (must be in canonical regimes from `input_pipeline.KNOWN_REGIMES`)
  - `unique_trade_count: int`
  - `expectancy: Decimal`  (e.g. `Decimal("0.012")` = 1.2% per-trade edge)
  - `drawdown_proxy: Decimal`  (e.g. `Decimal("0.18")` = 18%)
  - `average_source_confidence: Decimal | None`  (`Decimal("0.0")`–`Decimal("1.0")` or `None`)
  - `average_regime_confidence: Decimal | None`
  - `evidence_age_days: Decimal`
  - `data_quality_verdict: Literal["accepted", "rejected", "deduplicated"]`
  - `backtest_metrics: BacktestMetrics | None`
  - `walk_forward_metrics: WalkForwardMetrics | None`
  - `direction_hint: Literal["increase", "decrease", "neutral"]`  (caller-supplied; cannot be inferred from live config)

`BacktestMetrics` and `WalkForwardMetrics` are typed narrow views of `BacktestResult` / `WalkForwardResult`, restricted to the fields required for scoring.

## Hard rejection gates (any one triggers REJECT)

| Gate | Condition |
|---|---|
| `INSUFFICIENT_EVIDENCE_SAMPLE` | `unique_trade_count < policy.minimum_sample_count` |
| `STALE_EVIDENCE` | `evidence_age_days > policy.maximum_evidence_age_days` |
| `CONFLICTING_EVIDENCE` | Conflicting evidence surfaced (see `DirectionConflictDetector`) |
| `UNSUPPORTED_EVIDENCE_SCHEMA` | `evidence_schema_version` not in `policy.accepted_evidence_schema_versions` |
| `UNSUPPORTED_POLICY_SCHEMA` | `policy_version` not parseable / unknown |
| `INVALID_NUMERICS` | Any input is `NaN`, `±Infinity`, malformed Decimal, or out-of-range |
| `NEGATIVE_EXPECTANCY_FOR_INCREASE` | `direction_hint == "increase"` AND `expectancy < 0` |
| `DRAWDOWN_ABOVE_POLICY_MAX` | `drawdown_proxy > policy.maximum_drawdown_proxy` |
| `MISSING_MANDATORY_BACKTEST` | `policy.require_backtest_for_promotion == True` AND `backtest_metrics is None` |
| `MISSING_MANDATORY_WALK_FORWARD` | `policy.require_walk_forward_for_promotion == True` AND `walk_forward_metrics is None` |
| `MISSING_DATA_QUALITY_VERDICT` | `data_quality_verdict != "accepted"` |
| `HUMAN_APPROVAL_UNAVAILABLE` | `human_approval_available == False`  (REJECT — non-bypassable) |

If the gate is **`MISSING_MANDATORY_BACKTEST`** or **`MISSING_MANDATORY_WALK_FORWARD`**, the proposal is **REJECTED with promotion stage `BACKTEST_REQUIRED` / `WALK_FORWARD_REQUIRED`** so the report explicitly states which validation must be produced. This satisfies the "blocks promotion" semantics without introducing any automatic code path.

## Scoring components

Eight bounded, dimensionless, `Decimal` components. Each is `0.0` when the corresponding input is missing. The total score is the **sum of the eight component scores** (bounded in `[0.0, 1.0]`). Quantization is to 6 decimal places using `ROUND_HALF_EVEN`.

| Component | Weight (default) | Inputs |
|---|---|---|
| `sample_score` | 0.10 | `unique_trade_count` vs `minimum_sample_count` (saturating ramp) |
| `expectancy_score` | 0.20 | `expectancy` vs `minimum_expectancy` (clipped) |
| `drawdown_score` | 0.20 | `drawdown_proxy` vs `maximum_drawdown_proxy` (inverse, clipped) |
| `confidence_score` | 0.10 | `average_source_confidence` and `average_regime_confidence` (min) |
| `recency_score` | 0.05 | `evidence_age_days` vs `maximum_evidence_age_days` (inverse) |
| `backtest_score` | 0.15 | `BacktestMetrics` (pass, drawdown, profit factor, win rate) |
| `walk_forward_score` | 0.15 | `WalkForwardMetrics.stability_score` + pass |
| `quality_score` | 0.05 | `data_quality_verdict == "accepted"` and `is_actionable` |

Default weights are exactly:
```
{ "sample": 0.10, "expectancy": 0.20, "drawdown": 0.20,
  "confidence": 0.10, "recency": 0.05, "backtest": 0.15,
  "walk_forward": 0.15, "quality": 0.05 }
```
Sum = **1.00** exactly. Custom policies are accepted only if they sum to **1.00 ± 1e-9**.

Decision policy:
- `total_score >= policy.accept_threshold`  → `ACCEPT` (subject to gates; if any gate fails, gate wins, see above)
- `policy.defer_threshold <= total_score < policy.accept_threshold`  → `DEFER`
- `total_score < policy.defer_threshold`  → `REJECT`

Default thresholds: `accept = 0.65`, `defer = 0.40`.

## Promotion stages

```
PROPOSAL_ONLY           (entry stage for every ACCEPT/REJECT/DEFER decision)
   │
   ├── gate: BACKTEST_REQUIRED         (REJECT with this stage)
   ├── gate: WALK_FORWARD_REQUIRED    (REJECT with this stage)
   │
APPROVAL_REQUEST_READY  (ACCEPT with no missing validation gates)
   │
SHADOW_REVIEW_REQUIRED  (caller may set this advisory stage; never implies
                         any code path actually starts a shadow run)
```

- **No stage = no decision was rendered.** No code path means "approved" simply by absence of a stage.
- **No code path produces `LIVE_APPROVED`.** The enum does not contain `LIVE_APPROVED`.
- **No code path starts shadow, dry-run, or live execution.** `SHADOW_REVIEW_REQUIRED` is metadata that downstream human reviewers may use to schedule a future shadow run via a separate approval-gated issue.
- **Promotion output is advisory metadata only.** Human approval remains mandatory after every automated gate.

## Explicit non-goals

- ❌ No automatic application of any proposal.
- ❌ No automatic approval — `human_approval_required` is always `True` on every emitted decision.
- ❌ No read or write of Freqtrade configs, `dry_run`, runtime weights, or risk parameters.
- ❌ No read of `Freqtrade` REST or SQLite databases.
- ❌ No read or write of Shadowlock source records.
- ❌ No inference of current runtime weights from live config.
- ❌ No use of `Any` types or unjustified `type: ignore`.
- ❌ No cron, systemd, Docker, or scheduler activation.
- ❌ No telemetry side effects beyond returning the typed `ProposalDecision` object.

## Rejected alternatives

- **A second scoring layer on top of `PerformanceAnalyzer`** — rejected: `PerformanceAnalyzer` is per-bot window aggregation; reusing it would conflate two aggregation units (per-bot vs per-source/regime) and would force the scoring input to round-trip through a different boundary.
- **A scoring layer on top of `ApprovalGateManager`** — rejected: `ApprovalGateManager` mutates Telegram + ShadowLogger; coupling scoring to that would import runtime side effects and break the "recommendation output only" invariant.
- **Inference of current weights from Freqtrade `dry_run`/`stake_amount`/`stake_currency` configs** — explicitly rejected: violates the "never read or write live configuration" rule and would couple the policy to runtime data.
- **Scoring against hard-coded thresholds inside the function body** — rejected: the prompt requires `ScoringPolicy` to be a typed, versioned, hashable data structure that the engine consumes. The policy must be passable as a parameter so that issue #63 can adopt it directly.
- **`float` instead of `Decimal`** — rejected: the prompt explicitly requires `Decimal` for thresholds, scores, and proposal deltas, and forbids `NaN`/`±Infinity`. Pydantic v2 + custom `AfterValidator` enforces this.

## Integration contract for issue #63

`WeightProposalEngine` (issue #63) will consume:

1. `ScoringPolicy` — same versioned policy object this issue defines.
2. `ProposalEvidenceRecord` — the same record produced by `run_evidence_pipeline`.
3. `score_proposal(input, policy) -> ProposalDecision` — pure function, no side effects, no I/O.

#35 therefore produces a **library-level typed contract** that #63 imports. It does not produce any proposal files, weight deltas, or audit outputs — those are #63's deliverables.

## Determinism guarantee

For any fixed `(input, policy)` pair, `score_proposal` returns a `ProposalDecision` whose canonical JSON serialization is byte-identical across reruns. This is enforced by:

- `Decimal` arithmetic (no float drift).
- `ROUND_HALF_EVEN` quantization to 6 decimals.
- Pydantic v2 `model_config = ConfigDict(strict=True)`.
- A `decision_fingerprint` field (SHA-256 over canonical serialization) on every `ProposalDecision`.
- A regression test that runs `score_proposal` twice and asserts byte-identical JSON output.
