# Codex Cloud C4 Window Scope — Issue #593

**Date:** 2026-07-14
**Execution class:** A1 repository-only
**Branch:** `codex/c4-window-scope2026-07-14`
**Runtime mutation:** NONE

## Goal

Remove the C4 data-scope defect that allowed lifetime-derived metrics to be
presented as a windowed decision. All decision metrics must now be derived from
raw trades selected by one explicit, fail-closed measurement-window contract.

## Root cause

PR #500 added `window_trade_count` metadata to `CanaryMetrics`, but the public
C4 entrypoint still accepted every precomputed metric directly. The count did
not filter win rate, profit factor, Sharpe, drawdown, daily losses, average PnL,
or exposure. A caller could therefore continue to inject 63 lifetime trades as
the 14-day C4 input while reporting a separate count of 12.

## Solution

- Added a pure `C4MeasurementInput` raw-trade contract with explicit,
  timezone-aware start/end boundaries and equity baselines.
- Added canonical selection method
  `close_in_window_or_open_at_window_end/v1` covering realized trades,
  continuation trades, open-at-end trades, and excluded trades.
- Removed the public `metrics=` decision input. C4 now builds metrics before the
  decision engine and blocks on missing, ambiguous, invalid, or reversed scope.
- Made continuation drawdown authoritative while persisting separately named
  lifetime and window-relative audit calculations.
- Persisted measurement start/end, selection method, included/realized/open/
  excluded trade counts and IDs, metrics, and drawdown methods in JSON and the
  human-readable report.
- Replaced the metadata-only PR #500 regression test with raw-trade boundary,
  contamination, fail-closed, historic-value, signature, and artifact tests.

## Historic regression evidence

The synthetic fixture preserves the 2026-07-03 triage relationships without
copying runtime state or rewriting the historical decision:

| Metric/method | Expected |
|---------------|---------:|
| Lifetime max drawdown | 82.79% |
| Window-relative max drawdown | 323.38% |
| Continuation max drawdown (authoritative) | 75.08% |
| Window Sharpe | -0.18 |
| Window win rate | 91.67% |
| Window profit factor | 0.36 |

The authoritative continuation drawdown and window Sharpe remain critical
breaches, so the historic `ROLLBACK_RECOMMENDED` outcome remains valid. No
rollback, restart, deployment, configuration, strategy, or live action is
performed by this change.

## Validation

Fresh validation ran in a temporary VPS virtual environment:

- `pytest` on
  `test_live_canary_measurement_decision.py` and
  `test_c4_window_scope_contract.py`: **52 passed**.
- Ruff check on all four changed Python files: **passed**.
- Ruff format check on all four changed Python files: **passed**.
- MyPy on both changed production modules: **passed**.
- `scripts/secret_scan.py --tracked`: **passed**.
- `git diff --check`: **passed**.
- `compileall` over the repository source/test trees and the changed C4
  tests: **passed**, with one pre-existing `invalid escape sequence '\\|'`
  warning in `orchestrator/scripts/fleetguard_observation_snapshot.py:95`.

The full SI-v2 suite completed with one environment-dependent, out-of-scope
failure:

- `TestImportGuard.test_kill_switch_disabled_fallback` expected the
  ImportError fallback to report `False`, but the real HermesTrader
  kill-switch module was importable and reported the active state as `True`.
  The failure reproduces in isolation. The kill switch was not disabled,
  bypassed, or changed.

The root suite completed with **891 passed, 52 skipped, 2 failed**. Both
failures reproduce outside the C4 change:

- `test_init_db_fails_on_unwritable_path`: the suite runs as root, which can
  create the SQLite file despite a directory mode of `0444`.
- `test_correct_commit_check_passes`: the installer succeeds and prints
  `all precondition checks passed` to stderr, while the assertion checks that
  success text only in stdout.

GitHub searches found no open issue matching these three baseline failures.
They should be handled separately so Issue #593 remains one issue, one branch,
one PR, and one report.

## Rollback

Revert the PR. This restores the precomputed-metrics API, so rollback should be
used only if callers are simultaneously kept blocked from running C4 until a
replacement window-scope guard is available.
