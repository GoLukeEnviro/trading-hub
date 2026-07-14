# Phase 0A Corrective Completion Report

**Date:** 2026-07-14
**Issue:** #594
**Execution class:** A1 — repository-only
**Runtime mutation:** None

## Purpose

PR #613 established a useful scaffold but did not complete the Phase-0A
acceptance contract. This corrective implementation preserves that history and
makes the evaluation path manifest-bound, physically validated, deterministic,
and fail closed. It does not run Gate 0, select a strategy, or authorize any
runtime or live-capital action.

## Completed contract

- `EvaluationManifestV1` declares the strategy identity, complete Freqtrade
  provenance, canonical candle and benchmark hashes, exact pair/timeframe/time
  range, contiguous calibration/walk-forward/holdout windows, cost assumptions,
  deterministic bootstrap parameters, and every decision threshold.
- `EvaluationBundleV1` holds one canonical candle source, benchmark series, and
  raw trade set. Partition views are derived only from the manifest.
- Strict containment is the authoritative trade-to-partition policy. A trade
  crossing a boundary is either invalid or report-only under the explicitly
  declared continuation policy; it never contributes to authoritative metrics.
- Candle completeness, ordering, uniqueness, pair coverage, finite prices,
  physical OHLC bounds, snapshot hashes, benchmark coverage, trade identity,
  pair membership, timestamps, prices, quantities, sides, and regimes are
  validated before evaluation.
- The shared backtest cost engine now preserves signed funding, rejects
  non-physical/non-finite inputs, and exposes canonical mark-to-market PnL.
- Drawdown and returns use a candle-close mark-to-market equity curve rather
  than closed-trade-only equity.
- The deterministic block bootstrap produces explicit mean/lower/upper/width
  evidence. Outcomes are derived from predeclared OOS and holdout rules:
  `PASS_CANDIDATE`, `EXTEND`, `REJECT`, or `INVALID`.
- Profit-factor edge cases use finite JSON state instead of serializing
  infinity. JSON, Markdown, and artifact hashes are timestamp-free and stable
  for identical inputs.
- `FreqtradeExportAdapterV1` is import-only and rejects any provenance mismatch.
- The legacy `evaluate(list[dict], ...)` API raises a dedicated migration error
  so callers cannot bypass the manifest/bundle contract.

## TDD and validation evidence

Baseline before corrective edits:

- 55 targeted scaffold/cost tests passed.

RED evidence:

- The new contract tests initially failed during collection because
  `LegacyEvaluationAPIError` and canonical mark-to-market PnL did not exist.
- After the first implementation pass, 17 manifest tests exposed one adjacent
  window iteration defect while 20 tests already passed.

GREEN evidence after correction and lint formatting:

- Corrective harness and cost suites: **69 passed**.
- Repository root suite: **914 passed, 52 skipped**; warnings were pre-existing
  deprecations outside this scope.
- Ruff 0.15.16 over all changed Python targets: **clean**.
- Python `compileall` over both changed packages: **clean**.
- The full SI-v2 suite has one pre-existing environment-sensitive failure in
  `test_kill_switch_disabled_fallback`. The same isolated test fails unchanged
  in the clean canonical checkout, proving it is not introduced by this patch.

## Safety and sequencing

- No VPS runtime, Docker, Cron, scheduler, exchange, secret, bot, or strategy
  configuration was changed.
- No Gate-0 evaluation was executed and no profitability claim was produced.
- No approval marker, autonomous apply, restart, rollback, or live-capital
  authorization was created.
- Issue #604 remains blocked until this corrective change merges. Gate 0 and
  Phase 1 remain downstream of #604.
