# Edge-Evidence Evaluation Harness — Phase 0A Implementation Report

**Date:** 2026-07-14
**Issue:** #594 — [Phase 0A] Build reproducible edge-evidence evaluation harness
**PR:** #613
**Execution class:** A1 — Repository-only (no runtime mutation)

## Corrective status

The #613 scaffold was accepted as a useful repository foundation, but its
Phase-0A acceptance was incomplete. Issue #594 was reopened without reverting
the scaffold. The corrective completion replaces the list-of-dicts evaluation
entry point with the manifest-bound `EvaluationBundleV1` contract and records
the full acceptance evidence in
`docs/reports/phase-0a-corrective-completion-2026-07-14.md`.

Until that corrective change is merged, #604 and all downstream Gate-0/Phase-1
work remain blocked.

## Summary

Implemented a reproducible, repository-only edge-evidence evaluation harness
for testing Freqtrade strategies against historical data. The harness supports
out-of-sample, walk-forward, and untouched-holdout evaluation with explicit
cost and data-quality assumptions.

## Deliverables

### New module: `self_improvement_v2/src/si_v2/research/`

- **`__init__.py`** — Package exports
- **`edge_evidence_harness.py`** — Core harness implementation

### Key components

| Component | Description |
|-----------|-------------|
| `HarnessProvenance` | Immutable provenance record (strategy SHA, data snapshot, time periods, cost assumptions) |
| `EvaluationConfig` | Predeclared thresholds (min_trades, max_drawdown, min_profit_factor) |
| `DataQualityReport` | Data quality detection (missing candles, duplicates, gaps, unsupported pairs) |
| `EvaluationResult` | Complete result with outcome, metrics, provenance, and JSON serialization |
| `StrategyEvaluationHarness` | Main harness class — pure data processor, no side effects |
| `Gate0Outcome` | Four output states: PASS_CANDIDATE, EXTEND, REJECT, INVALID |

### Gate-0 output states

| State | Meaning |
|-------|---------|
| `PASS_CANDIDATE` | Predeclared evidence criteria met |
| `EXTEND` | Insufficient trades, duration, regimes, or uncertainty width |
| `REJECT` | Material guardrail failure or negative edge evidence |
| `INVALID` | Data, leakage, or reproducibility defect |

### Tests: `self_improvement_v2/tests/test_edge_evidence_harness.py`

- **26 tests**, all passing
- Coverage: PASS_CANDIDATE (4), EXTEND (2), REJECT (3), INVALID (3),
  Reproducibility (3), Safety invariants (3), Edge cases (8)
- Deterministic: same inputs produce identical outputs
- Safety: no live trading fields, no auto-approve, no proven-profitability claims

### Validation

| Check | Status |
|-------|--------|
| Targeted tests (26) | ✅ All passed |
| Ruff lint | ✅ Clean |
| `compileall` | ✅ Clean |
| `git diff --check` | ✅ Clean |

## Safety boundary

- **No runtime mutation** — harness is a pure data processor
- **No strategy mutation** — strategy is supplied as an input identifier
- **No live trading fields** — EvaluationResult explicitly excludes dry_run,
  live_trading, api_key, exchange credentials
- **No auto-approve** — PASS_CANDIDATE is not proven profitability or live
  authorization
- **No exchange, Docker, or runtime dependency**

## Dependencies

- Issue #592 (Codex Cloud writer contract) — CLOSED
- Issue #606 (reproducible environment) — CLOSED
- Issue #593 (C4 window-scoped measurement) — CLOSED (PR #612 merged)
- Issue #604 (core strategy selection) — OPEN, depends on this harness

## Next steps

- Complete corrective issue #594 before any downstream research work
- Issue #604 — Select one core strategy and freeze evaluation inputs
- Issue #595 — Fleet HWM and daily drawdown guard
- Issue #596 — Bot-level HALT_BOT circuit breaker
