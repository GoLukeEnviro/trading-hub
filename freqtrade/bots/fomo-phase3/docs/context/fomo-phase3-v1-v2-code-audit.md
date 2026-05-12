# Phase A — Code Audit: FOMO Strategy System v1 vs v2

**Date:** 2026-05-12
**Auditor:** Hermes Orchestrator (DeepSeek v4 Flash)
**Status:** COMPLETE (Phase A — Archive & Audit)
**Next Phase:** B/C — Research Package + Tests (awaiting approval)

---

## 1. Audit Summary

Three artifacts were received during the planning phase:

| # | Artifact | Classification | Action |
|---|---|---|---|
| 1 | FOMO Bot v1 (first Python block, discussed in prior conversation, not preserved as exact file) | **Concept reference only** | Not recoverable as exact source. Marked as UNAVAILABLE. |
| 2 | FOMO Bitget Futures Strategy System v2 (second Python block, ~850 lines) | **Preferred research-lab basis** | Archived verbatim at `research/specs/fomo_bitget_strategy_v2_original.py` |
| 3 | External implementation roadmap (phase structure text) | **Accepted after hardening** | Incorporated into master roadmap |

---

## 2. v1 — Concept Reference (Not Implementation Baseline)

**Status:** NOT recoverable as exact source from active context or session history. Not used as code basis.

### Why v1 is excluded:

| Issue | Severity |
|---|---|
| TP1/TP2 calculated but not executed | HIGH — backtest misleading |
| SL/TP on close only, not high/low | HIGH — intrabar risk understated |
| Funding accounting inconsistent between equity and trade PnL | HIGH — metric distortion |
| Objective penalty only checks final fold's trades | MEDIUM — optimization bias |
| Sharpe annualization on 5m trade returns | MEDIUM — metric noise |
| NaN guards incomplete (correlation/funding/roll can produce NaN in warmup) | MEDIUM — invalid signals possible |
| No multi-pair model | MEDIUM — not fleet-compatible |
| Not a Freqtrade IStrategy | BLOCKER — cannot deploy |

**If exact v1 source is needed later**, it must be re-provided. Placeholder file: `research/specs/fomo_bot_v1_original.UNAVAILABLE.md`

---

## 3. v2 — Preferred Research-Lab Basis

**Status:** Archived. Accepted as code basis for the modular research package after identified fixes.

### 3.1 What v2 does well

| Area | Strength |
|---|---|
| Architecture | Dataclasses (`StrategyConfig`, `OpenPosition`, `Trade`, `BacktestResult`) |
| CLI | argparse with modes: `backtest`, `optimize`, `walk-forward` |
| Data validation | Required columns check, UTC conversion, sorting, dedup, OHLC positivity |
| Signal engine | Vectorized `compute_signals` + `add_entry_signals` |
| NaN guards | `required_signal_cols.notna().all(axis=1)` in entry logic |
| Noise filter | `movement >= noise_atr_pct * atr` |
| Stateful execution | Row-by-row while loop with position tracking |
| Intrabar SL/TP | `high/low` checked, SL wins in same-candle ambiguity |
| Partial exits | TP1 60% → breakeven SL → TP2 remaining |
| Trailing stop | After TP1 only, via `trail_atr_mult` |
| Funding simulation | 0/8/16 UTC settlement points |
| Walk-forward | `DateOffset`-based windows, not fragile exact timestamp match |
| Reporting | summary.json, config.json, trades.csv, equity_curve.csv |
| Optuna integration | `sample_config` + `score_result_for_optimization` + `run_walk_forward` |
| Config isolation | Frozen dataclass, `replace()` for variations |

### 3.2 Identified gaps and required fixes

Each gap is cross-referenced to the master roadmap section.

| # | Gap | Impact | Master Roadmap Ref | Priority |
|---|---|---|---|---|
| F1 | Funding changes equity but not tracked per-position or in Trade | Profit Factor and win rate exclude funding | §7.1-7.3 | HIGH |
| F2 | Profit Factor computed on legs, not positions | TP1/TP2 split inflates or distorts PF | §7.4 | HIGH |
| F3 | Volume is forward-filled by default | Real volume gaps produce artificial signals | §7.7 | HIGH |
| F4 | Entry fee not subtracted at entry (deferred to exit) | Equity during open position is too high | §7.6 | MEDIUM |
| F5 | No position_id for TP1/TP2 leg grouping | Can't aggregate position-level metrics | §7.1 | MEDIUM |
| F6 | No final OOS validation | WFA alone not sufficient for deployment decision | §8.1 | HIGH |
| F7 | No 845d stress test | 30-Day Illusion risk | §8.2 | HIGH |
| F8 | No fold-to-fold parameter drift analysis | Can't detect overfitting vs stability | §7.10 | MEDIUM |
| F9 | Single-pair only | Not fleet-ready; legacy bots are multi-pair | §8.4 | LOW (future) |
| F10 | Trades metric uses `entry_time + direction` unique count — fragile if same time | Trade count can be inaccurate | §3 | LOW |

---

## 4. Safety Gates (from Master Roadmap)

These gates are not yet applied. They become mandatory before each transition.

### 4.1 Data quality gates (pre-backtest)

| Check | Requirement |
|---|---|
| Minimum rows | 500 (smoke); 845d (stress) |
| Timestamp | UTC, monotonic, no duplicates |
| OHLC sanity | 0 errors |
| Missing candles | < 0.5% or documented |
| OI coverage after ffill | > 99% |
| Funding coverage after ffill | > 99% |

### 4.2 Backtest gates (post-implementation)

| Gate | PASS |
|---|---|
| CLI exit | 0 |
| Reports written | summary.json, trades.csv, equity_curve.csv |
| PnL | finite |
| Position size | finite, capped |

### 4.3 Walk-forward gates

| Gate | PASS |
|---|---|
| Folds >= 3 | yes (if data allows) |
| Crashes | 0 |
| Trade count > 0 | across folds |
| Metrics | finite |

### 4.4 Optimization candidate gates

| Gate | PASS |
|---|---|
| Trades >= 80 | preferred |
| PF > 1.0 (min), > 1.15 (candidate) | required |
| MaxDD < 12% | hard |
| Positive folds >= 60% | required |
| Breakeven WR | actual > breakeven |
| Single-fold dependency | none |

### 4.5 Stress + robustness gates

| Gate | PASS |
|---|---|
| Final OOS PF > 1.0 | preferred |
| Final OOS MaxDD < 12% | required |
| 845d PF > 0.9 | minimum |
| 845d MaxDD < 15% | hard |
| Window-shift PF > 0.9 | both shifts |
| Top pair contribution < 50% | multi-pair only |

---

## 5. Implementation Roadmap for Phase B/C

Pre-approved in master roadmap for the user's next signal.

### Phase B — Research Package Skeleton

Create directory structure and empty module files:

```text
research/fomo_phase3/
├── __init__.py            # package marker
├── config.py              # StrategyConfig dataclass
├── data.py                # load/validate/prepare CSV
├── signals.py             # compute_signals, add_entry_signals
├── execution.py           # OpenPosition, funding, trailing
├── backtest.py            # backtest() main loop
├── metrics.py             # calc_sharpe, calc_drawdown, result_summary
├── walk_forward.py        # make_walk_forward_windows, slice_by_time
├── optimization.py        # sample_config, score_result, optimize call
└── cli.py                 # argparse main entry point
```

**Important:** These are implemented FROM v2 source code, not written from scratch. v2 is the basis.

### Phase C — Test Suite (TDD)

Tests written BEFORE implementation code.

```text
research/tests/
├── __init__.py
├── test_data_validation.py
├── test_signals.py
├── test_entry_signals.py
├── test_execution_slippage.py
├── test_partial_exits.py
├── test_funding_accounting.py
├── test_metrics.py
├── test_walk_forward.py
└── test_optimization_scoring.py
```

Test runner:

```bash
cd /home/hermes/projects/trading/freqtrade/bots/fomo-phase3/research
python3 -m pytest tests/ -q
```

Expected initially: `failures` (no implementation yet).

---

## 6. Archive Inventory (Phase A Deliverables)

| File | Status |
|---|---|
| `research/specs/fomo_bitget_strategy_v2_original.py` | ✅ Archived (verbatim source) |
| `research/specs/fomo_bot_v1_original.UNAVAILABLE.md` | ✅ Placeholder note |
| `docs/context/fomo-phase3-strategy-system-master-plan.md` | ✅ Created previously |
| `docs/context/fomo-phase3-master-implementation-roadmap.md` | ✅ Created previously |
| `docs/context/fomo-phase3-v1-v2-code-audit.md` | ✅ THIS FILE |

---

## 7. Verification

All Phase A deliverables checked:

```bash
find /home/hermes/projects/trading/freqtrade/bots/fomo-phase3/research/specs -type f -ls
```

Expected output:

```text
research/specs/fomo_bitget_strategy_v2_original.py
research/specs/fomo_bot_v1_original.UNAVAILABLE.md
```

---

## 8. Next

This Phase A is complete.

To proceed, user must approve Phase B/C with a message containing:
- `start Phase B/C research package with tests`

or the shorter equivalent.
