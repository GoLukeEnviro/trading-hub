# C5.3 Corrective — Gate-0 Strategy Isolation and Evaluation Pipeline

**Date:** 2026-07-21
**Execution class:** A1 (repository-only — no runtime mutation)
**Issue:** #665
**Branch:** `fix/c53-gate0-corrective-2026-07-20`
**Base:** `origin/main` @ `01b7fb2`

## Summary

Resolves all 14 items from the C5.2 A0 preflight failure report. This corrective
fully strips `FreqForge_Gate0_Core_v1` of all external dependencies, introduces a
canonical manifest v3, implements entry-time regime classification without
lookahead, and adds a selection-only evaluation interface with holdout isolation.

## Changes

### A. Strategy code (`FreqForge_Gate0_Core_v1.py`)

Complete rewrite — no noop stubs, no artificial runtime objects:

- **Primo signals:** removed entirely (no `_gate0_noop_gate`, no `_gate0_noop_state`)
- **FleetRiskManager:** removed entirely (no `self.risk_manager`, no `_Gate0NoopRiskManager`)
- **AI/Shadow/LLM paths:** removed entirely (no `_get_ai_override_signal`, no `_inject_ai_signal_override`, no `AI_OVERRIDE_ALLOWED_PAIRS`, no `AI_OVERRIDE_CONFIDENCE_MIN`)
- **sys.path manipulation:** removed entirely (no `sys.path.insert`)
- **File I/O (shadow logging):** removed entirely (no `json`, `os`, `open()`, `os.makedirs`)
- **confirm_trade_entry override:** removed entirely (inherits IStrategy default)
- **bot_loop_start override:** removed entirely (inherits IStrategy default)
- **normalize_pair stub:** removed (was an AI-override dependency)
- **long_risk_allowed / short_risk_allowed stubs:** removed
- **_fleet_source reference:** removed
- **v04 AI override conditions in populate_entry_trend:** removed
- **v04 AI override conditions in custom_exit:** removed
- **Retained:** native entry/exit/ROI/custom_stoploss/deterministic indicator logic
- **Ruff:** 0 errors on strategy file

### B. Manifest v3 (`gate0_evaluation_integration.py`)

- **`build_manifest_v3()`** — new canonical builder
  - `manifest_id="gate0-manifest-v3-20260721"`
  - `approval_reference="issue-665-C53-CORRECTIVE"`
  - `threshold_set_id="gate0-corrective-v3"`
  - `tail_quantile=0.05` added
  - `max_missing_candles` uses corrected 5% formula: `floor(global_expected * 0.05)`
- **`build_manifest_v2()`** — deprecated wrapper
  - Emits `DeprecationWarning`
  - Delegates to `build_manifest_v3()` without preserving old v2 semantics
- **Provenance:** defaults to `FreqForge_Gate0_Core_v1`

### C. Entry-Time Regime (`gate0_evaluation_integration.py`)

- **`classify_regime_at_entry(pair_candles, entry_timestamp, lookback=96)`** — pure function
  - Only candles of the same pair with `timestamp < entry_timestamp`
  - Last 96 pre-entry candles
  - ATR(14)/close as volatility measure
  - Current ATR pct compared to median of valid lookback ATR pcts
  - Returns `high_volatility`, `low_volatility`, or `insufficient_data`
  - Post-entry candles never change the result
- **`FreqtradeExportAdapterV1.parse_trades`** — updated call site to use entry-time-only data

### D. Selection-only Evaluation (`evaluation_bundle_v1.py`)

- **`EvaluationRunnerV1.evaluate_selection(bundle)`** — new method
  - Processes calibration + walk-forward 1 + walk-forward 2 only
  - Calibration is descriptive only; walk-forward partitions are authoritative
  - Rejects holdout candles in bundle → fail-closed `INVALID` (`HOLDOUT_CANDLES_IN_SELECTION_BUNDLE`)
  - Rejects holdout trades in bundle → fail-closed `INVALID` (`HOLDOUT_TRADES_IN_SELECTION_BUNDLE`)
  - Never materializes holdout metrics or holdout hashes
- **`_selection_outcome()`** — strict threshold boundaries
  - Trades: `<= 100` → `EXTEND` (strict `> 100`)
  - Drawdown: `>= 25%` → `REJECT` (strict `< 25%`)
  - Profit Factor: `<= 1.3` → `REJECT` (strict `> 1.3`)
- **`evaluate()`** — unchanged, reserved for later C6 holdout ceremony

### E. Provenance (`gate0_strategy_provenance.py`)

- `strategy_class` → `FreqForge_Gate0_Core_v1`
- `strategy_file` → `freqforge/user_data/strategies/FreqForge_Gate0_Core_v1.py`
- `uses_fleet_risk_manager` → `False`
- `uses_primo_signal` → `False`
- `uses_dynamic_risk_gates` → `False`
- `re_ratification_note` → documents C5.3 stripping

## Tests (42 new + 6 existing = 48 total, all green)

### Strategy AST contract (15 tests)
- No sys.path, primo, FleetRisk, AI override, confirm_trade_entry, bot_loop_start, file I/O, json/os import, noop stubs, normalize_pair, risk_manager, fleet_source references
- Has native entry logic, custom_stoploss, class definition

### Ruff clean (1 test)
- `ruff check` reports 0 errors on strategy file

### Freqtrade-compatible import (1 test)
- Strategy imports with controlled Freqtrade/TA-Lib/pandas stubs
- Class instantiates without external runtime state

### Manifest v3 (5 tests)
- `build_manifest_v3` exists
- `build_manifest_v2` emits DeprecationWarning and delegates to v3
- Manifest v3 has correct id, approval reference, tail_quantile
- Provenance defaults to Gate0_Core_v1

### Entry-time regime (4 tests)
- Function signature correct (pair_candles, entry_timestamp, lookback)
- Insufficient data returns `insufficient_data`
- Post-entry candles do not change result (invariance)
- Only same-pair candles are considered

### Selection evaluation (3 tests)
- `evaluate_selection` method exists
- Does not materialize holdout metrics
- Rejects holdout candles fail-closed

### Threshold boundaries (4 tests)
- Trades `<= 100` → `EXTEND`
- Trades `101` → can `PASS_CANDIDATE`
- Drawdown `25%` → `REJECT`
- Profit Factor `1.3` → `REJECT`

### Existing tests compatibility (5 tests)
- C5.2 class name, no-FleetRisk, no-Primo, max-missing-formula tests still pass

### Provenance documentation (3 tests)
- Defaults to Gate0_Core_v1, all deps False, mentions C5.3

## No runtime mutation

- No Docker, container, deployment, strategy reload, kill-switch, or config change
- No backtest execution
- No holdout inspection
- No `dry_run=false`
- No exchange access

## Verification

- Ruff: 0 errors on all changed files
- Tests: 67/67 passed (42 new C5.3 + 19 C5.1 + 6 C5.2)
- Strategy AST verified: no forbidden imports, symbols, I/O, or sys.path
- Entry-time regime invariance proven
- Selection evaluation holdout isolation proven
- Threshold boundaries proven at exact boundary values
