# FOMO Phase 3 — Master Implementation Roadmap

**Created:** 2026-05-12
**Owner:** Hermes Orchestrator / Luke
**Scope:** Research-to-Dry-Run strategy foundation for FOMO / Open Interest / Funding Rate system
**Status:** PLAN ONLY — no strategy implementation approved yet

---

## 0. Executive Summary

This document consolidates three user-provided inputs into one binding implementation roadmap:

1. **FOMO Bot v1** — conceptual prototype with vectorized signals, filters, backtest, Optuna.
2. **FOMO Bitget Strategy System v2** — stronger research/backtesting system with CLI, partial exits, intrabar execution, walk-forward, reporting.
3. **Implementation Roadmap** — high-level phase structure from data ingestion to potential live deployment.

Decision:

- **v2 is the preferred research basis.**
- **v1 is archived as conceptual reference only.**
- **The external roadmap is accepted only after safety hardening.**
- **No live trading is part of the current implementation.**
- **The next technical build target is a research lab, not a Freqtrade runtime bot.**

Hard line:

```text
Research → Tests → Backtest Engine Validation → Data Quality → Walk-Forward → Optuna → Freqtrade Wrapper → Dry-Run → 60+ Paper Trades → Review → Live remains blocked until explicit approval.
```

---

## 1. Existing Foundation

The scaffold already exists at:

```text
/home/hermes/projects/trading/freqtrade/bots/fomo-phase3/
```

Current foundation files:

```text
config/config_fomo_phase3_dryrun.json
user_data/strategies/FOMO_Phase3_v0.py
docker-compose.fomo.yml
.env.example
scripts/validate_foundation.sh
scripts/healthcheck_foundation.sh
docs/context/fomo-phase3-foundation.md
README.md
```

Important current safety properties:

| Property | State |
|---|---|
| `dry_run` | `true` |
| `initial_state` | `stopped` |
| Exchange credentials | none |
| API bind | `127.0.0.1:8087` |
| Docker network target | `ki-fabrik` |
| Existing fleet | untouched |

---

## 2. Inputs and Classification

### 2.1 Input A — FOMO Bot v1

Classification:

```text
Concept reference only. Not implementation baseline.
```

Strengths:

- Good 3-layer architecture idea: signal, filter, execution.
- Contains OI/price alignment, funding residual, ATR-normalized trend.
- Includes cost assumptions, latency, Optuna, walk-forward concept.

Critical weaknesses:

| Issue | Impact |
|---|---|
| TP1/TP2 calculated but not actually executed | Backtest result misleading |
| SL/TP based on close only, not high/low | Intrabar risk understated |
| Funding accounting inconsistent | Equity and trade PnL diverge |
| Objective low-trade penalty checks only final fold | Optimization can select unstable configs |
| Sharpe on trade returns with 5m annualization | Metric distortion |
| NaN guards incomplete | Invalid warmup signals possible |
| Single dataframe only | No multi-pair fleet behavior |
| Not a Freqtrade IStrategy | Cannot deploy directly |

Verdict:

```text
Archive as design input; do not run as production backtester.
```

---

### 2.2 Input B — FOMO Bitget Strategy System v2

Classification:

```text
Preferred research-lab basis after test-driven hardening.
```

Strengths:

| Area | Improvement |
|---|---|
| Structure | Dataclasses, CLI, reports, typed states |
| Data validation | Required columns, UTC conversion, sorting, duplicates removed |
| Signals | Vectorized signal preparation |
| Entries | Explicit `entry_signal` column with NaN guard |
| Execution | Stateful backtester |
| TP1/TP2 | Real partial exits |
| Intrabar handling | SL/TP checked via high/low |
| Ambiguity | Conservative SL-first mode |
| Funding | 0/8/16 UTC settlement approximation |
| Walk-forward | DateOffset windows rather than fragile exact `get_loc` |
| Reports | summary/config/trades/equity CSV/JSON |

Remaining issues to fix before trusting results:

| Issue | Required fix |
|---|---|
| Funding changes equity but not Trade.net_pnl | Add position-level accumulated funding and include in trade/position metrics |
| Profit Factor computed on legs | Add separate leg-PF and position-PF |
| Entry fee deferred until exit | Either explicitly model entry-fee at open or document delayed accounting; final version should subtract at entry |
| Volume forward-fill | Do not default-fill volume as real activity; mark/drop instead |
| No position IDs | Add `position_id` for grouping TP1/TP2 legs |
| No final OOS gate | Add final unseen period validation |
| No 845d stress gate | Add mandatory stress test if data exists |
| No parameter drift analysis | Add fold-to-fold config stability report |
| Single-pair only | Add multi-pair orchestration later |

Verdict:

```text
Use v2 as initial code basis for research package, not as direct Freqtrade strategy.
```

---

### 2.3 Input C — External Implementation Roadmap

Classification:

```text
Useful phase structure, but unsafe if followed literally.
```

Accepted concepts:

- Data infrastructure first.
- Feature schema: OHLCV + OI + funding.
- Vectorized signal engine.
- Stateful execution backtester.
- Fees, slippage, latency.
- Walk-forward analysis.
- CLI reports.

Corrections required:

| Original idea | Correction |
|---|---|
| Forward-fill volume/OI/funding | Only OI/funding may be forward-filled with gap reporting. Volume should be missing/invalid unless explicitly justified. |
| WFA as ultimate hard test | WFA is necessary but not sufficient; add 845d stress, final OOS, window-shift, pair dependency. |
| WebSocket/order execution next | Not in current scope. Current target is research lab then Freqtrade dry-run. |
| Live order execution via Bitget API | Blocked. No API keys, no real orders. |
| Cloud/server latency optimization | Not relevant now. Existing VPS and Docker network `ki-fabrik` are target. |
| OI via orderbook updates | OI comes from Bitget OI/market data endpoints, not orderbook. |

---

## 3. Target Architecture

The system must be built as a layered research-to-dry-run stack:

```text
fomo-phase3/
├── research/
│   ├── fomo_phase3/
│   │   ├── __init__.py
│   │   ├── config.py
│   │   ├── data.py
│   │   ├── signals.py
│   │   ├── entries.py
│   │   ├── execution.py
│   │   ├── backtest.py
│   │   ├── metrics.py
│   │   ├── walk_forward.py
│   │   ├── optimization.py
│   │   └── cli.py
│   ├── tests/
│   ├── data/
│   │   ├── raw/
│   │   └── validated/
│   ├── reports/
│   └── artifacts/
├── user_data/strategies/
│   └── FOMO_Phase3_v0.py      # placeholder only until wrapper phase
├── config/
│   └── config_fomo_phase3_dryrun.json
└── docs/context/
```

Layer responsibilities:

| Layer | Purpose | Trading side effects |
|---|---|---|
| Data layer | Load, validate, clean OHLCV/OI/Funding | none |
| Signal layer | Compute vectorized indicators | none |
| Entry layer | Generate entry signals | none |
| Execution/backtest layer | Simulate fills, fees, funding, exits | simulated only |
| Optimization layer | Search robust parameters | none |
| Reporting layer | Export evidence | none |
| Freqtrade wrapper | Future dry-run strategy wrapper | dry-run only |

---

## 4. Non-Goals

The following are explicitly out of scope for the next implementation phase:

- No live trading.
- No Bitget API key handling.
- No real order execution.
- No WebSocket live trading engine.
- No changes to `freqtrade-freqforge`.
- No replacement of existing fleet bots.
- No Docker prune or destructive cleanup.
- No migration of RSI or Webserver.
- No direct copy of research code into `user_data/strategies/` as runtime strategy.

---

## 5. Data Quality Requirements

Expected input schema:

```text
timestamp
open
high
low
close
volume
oi
funding_rate
```

### 5.1 Required validation

| Check | Requirement |
|---|---|
| Timestamp parse | UTC, timezone-aware |
| Sort order | monotonically increasing |
| Duplicate timestamps | zero after cleaning |
| OHLC positivity | open/high/low/close > 0 |
| OHLC consistency | high >= max(open, close, low); low <= min(open, close, high) |
| Timeframe | stable 5m cadence |
| Missing candles | report count and percentage |
| Volume | do not blindly forward-fill |
| OI | forward-fill allowed with gap report |
| Funding | forward-fill allowed with gap report |
| Min rows | 500 for smoke only; 845d preferred for stress |

### 5.2 Data pass gates

| Gate | PASS |
|---|---|
| Smoke dataset | >= 500 valid 5m rows |
| Lab dataset | >= 3 months preferred |
| Stress dataset | >= 845 days if available |
| Missing candles | < 0.5% preferred, otherwise documented |
| OI coverage after allowed fill | > 99% |
| Funding coverage after allowed fill | > 99% |
| OHLC sanity errors | 0 |

---

## 6. Test-Driven Development Plan

No production/research implementation should be trusted without tests first.

Minimum test files:

```text
research/tests/test_data_validation.py
research/tests/test_signals.py
research/tests/test_entry_signals.py
research/tests/test_execution_slippage.py
research/tests/test_partial_exits.py
research/tests/test_funding_accounting.py
research/tests/test_metrics.py
research/tests/test_walk_forward.py
research/tests/test_optimization_scoring.py
```

### 6.1 Required test behaviors

| Area | Required tests |
|---|---|
| Data validation | missing columns fail; bad OHLC fails; duplicate timestamps removed/reported |
| Signals | ATR, z-score, fomo, roc3, trend_slope, alignment, funding_residual created correctly |
| Warmup | Rolling-window NaN periods block entries |
| Entry signals | Long/short require FOMO + ROC + trend + OI alignment + funding constraint |
| Noise filter | Tiny movement blocks entry |
| Intrabar execution | SL wins if SL and TP hit same candle in conservative mode |
| Slippage | long/short entry and exit slippage direction correct |
| Partial exits | TP1 closes exactly configured fraction; TP2 closes remaining size |
| Trailing | trailing activates only after TP1 |
| Funding | funding affects equity and position/trade metrics consistently |
| Metrics | leg PF and position PF separated |
| Drawdown | max drawdown computed from equity curve |
| Walk-forward | windows created without exact timestamp dependency |
| Optimization score | too few trades, high DD, invalid PF are penalized |

---

## 7. Backtester Hardening Requirements

Before any Optuna run is considered meaningful, the following fixes are required in the v2-derived research engine:

1. Add `position_id` to `OpenPosition` and each `Trade` leg.
2. Add `funding_pnl_accumulated` to `OpenPosition`.
3. Include funding in final position and leg-level reporting.
4. Add separate metrics:
   - `leg_profit_factor`
   - `position_profit_factor`
   - `leg_win_rate`
   - `position_win_rate`
   - `expectancy`
   - `avg_win`
   - `avg_loss`
   - `breakeven_win_rate`
5. Add position-level aggregation by `position_id`.
6. Explicitly decide entry-fee accounting:
   - preferred: subtract entry fee at entry;
   - alternative: defer but document and test.
7. Change data cleaning policy for volume:
   - no blind forward-fill by default.
8. Add final OOS support.
9. Add 845d stress test support.
10. Add parameter drift reporting between folds.

---

## 8. Backtest and Validation Gates

### 8.1 Smoke backtest gate

Target:

```text
Single pair, e.g. BTC/USDT:USDT
```

PASS:

| Check | PASS |
|---|---|
| CLI exits | code 0 |
| summary.json | exists |
| config.json | exists |
| trades.csv | exists if trades occur |
| equity_curve.csv | exists |
| PnL | finite, no NaN/inf |
| Position size | finite and capped |
| Funding | finite and reported |

### 8.2 Fixed-CFG walk-forward gate

Before Optuna:

| Check | PASS |
|---|---|
| Folds | >= 3 if data allows |
| Crashes | 0 |
| Trade count | not zero in all folds |
| Metrics | finite |
| Drawdown | finite |

### 8.3 Optimization gate

Optuna should run in two stages:

```text
Stage 1: 50-trial smoke optimization
Stage 2: 200-trial full walk-forward optimization
```

Candidate PASS gates:

| Gate | PASS |
|---|---|
| Total trades | >= 80 preferred |
| Trades per test fold | >= 10 minimum |
| Profit Factor | > 1.0 minimum, > 1.15 candidate |
| Max Drawdown | < 12% hard, < 8% preferred |
| Positive folds | >= 60% |
| Parameter drift | no extreme fold-to-fold jumps |
| Breakeven WR | actual win rate > breakeven win rate |
| Single-fold dependency | no single fold explains total result |

---

## 9. Stress and Robustness Gates

### 9.1 Final OOS

A final unseen period must be reserved and not used for optimization.

Example if data exists:

```text
2026-01-01 → latest available date
```

PASS:

| Gate | PASS |
|---|---|
| PF | > 1.0 preferred |
| MaxDD | < 12% |
| Trades | >= 30, otherwise mark insufficient sample |
| Result | not dependent on one trade or one day |

### 9.2 845-day stress test

Mandatory if data exists.

Purpose:

- Prevent the previous “30-Day Illusion”.
- Detect regime blindness.
- Detect crash-period fragility.

PASS:

| Gate | PASS |
|---|---|
| Profit Factor | > 0.9 minimum, > 1.0 preferred |
| MaxDD | < 15% hard |
| Stoploss dominance | no excessive SL-hit cluster |
| Period dependency | no single month/quarter explains all gains |
| Trade sample | >= 80 preferred |

### 9.3 Window-shift robustness

Run shifted train/OOS windows after an apparent PASS.

PASS:

| Gate | PASS |
|---|---|
| Shift A PF | > 0.9 |
| Shift B PF | > 0.9 |
| Shift drawdown | acceptable and finite |
| Trade count | usable |

### 9.4 Pair dependency

Once multi-pair mode exists:

| Gate | PASS |
|---|---|
| Top pair contribution | < 50% of total profit |
| Profitable pair share | >= 30% preferred |
| Loss concentration | no single pair dominates losses |

---

## 10. Freqtrade Wrapper Phase

This phase must not start until the research system passes its gates.

Future target file:

```text
/home/hermes/projects/trading/freqtrade/bots/fomo-phase3/user_data/strategies/FOMO_Phase3_v1.py
```

The Freqtrade wrapper must contain only runtime strategy logic:

- `populate_indicators()`
- `populate_entry_trend()`
- `populate_exit_trend()`
- optional `custom_stoploss()`
- optional `custom_exit()`

It must not include the full research backtester.

### 10.1 OI/Funding integration options

| Option | Description | Initial verdict |
|---|---|---|
| A | Pre-merged informative data files | Preferred first backtest path |
| B | Strategy reads external CSV/Parquet | Fast but fragile |
| C | Custom DataProvider/FreqAI-style integration | Cleaner but higher effort |

Initial recommendation:

```text
Use Option A for Freqtrade backtesting. Reassess B/C for dry-run runtime.
```

---

## 11. Freqtrade Validation Gates

Before any dry-run container is started:

Required checks:

```bash
freqtrade list-strategies
freqtrade backtesting
freqtrade lookahead-analysis
freqtrade recursive-analysis
find /freqtrade/user_data/strategies -name "*.json" -ls
```

PASS gates:

| Gate | PASS |
|---|---|
| Strategy loads | yes |
| Backtest runs | yes |
| Lookahead analysis | clean |
| Recursive analysis | clean |
| Shadow JSON | absent or audited |
| Config | `dry_run=true` |
| Initial state | `stopped` until approved |
| No credentials | no exchange keys |

---

## 12. Dry-Run Deployment Gate

Only after all research and Freqtrade gates pass.

Future container target:

```text
container_name: freqtrade-fomo-phase3
network: ki-fabrik
api: 127.0.0.1:8087
mode: dry-run only
initial_state: stopped
```

Dry-run criteria:

| Gate | Requirement |
|---|---|
| Config | dry_run=true |
| Wallet | dry-run wallet only |
| API bind | local only |
| Existing bots | untouched |
| ShadowLogger | enabled or compatible |
| Monitoring | healthcheck script passes |
| Paper sample | >= 60 trades before any further escalation |

---

## 13. Live Trading Status

Live trading is explicitly blocked.

No live trading may occur until all of the following are true:

```text
Backtest PASS
Walk-forward PASS
845d stress PASS
Final OOS PASS
Freqtrade validation PASS
Dry-run/Paper >= 60 trades PASS
Risk review PASS
Explicit human approval PASS
```

Forbidden in the current phase:

- No `dry_run=false`.
- No exchange API keys.
- No real orders.
- No broker execution implementation.
- No live Bitget WebSocket order engine.

---

## 14. No-Touch List

The following must remain unchanged unless explicitly approved:

| Component | Reason |
|---|---|
| `freqtrade-freqforge` | Gold-standard dry-run baseline |
| `freqtrade-regime-hybrid` | Active comparison bot |
| `freqtrade-momentum` | Existing inactive bot, separate decision |
| `freqtrade-rsi` | Legacy network/mount migration is separate task |
| `freqtrade-webserver` | Separate infra decision |
| `ai-hedge-fund-crypto` | Active signal stack |
| Existing SQLite DBs | Historical evidence |
| Docker networks/volumes | No destructive cleanup |

---

## 15. Suggested Implementation Sequence

### Phase A — Archive & Audit

Create:

```text
research/specs/fomo_bot_v1_original.py
research/specs/fomo_bitget_strategy_v2_original.py
docs/context/fomo-phase3-v1-v2-code-audit.md
```

No execution.

### Phase B — Research Package Skeleton

Create module directories and empty files under:

```text
research/fomo_phase3/
research/tests/
```

No trading.

### Phase C — TDD Test Suite

Write tests before implementation.

Run:

```bash
cd /home/hermes/projects/trading/freqtrade/bots/fomo-phase3/research
python3 -m pytest tests/ -q
```

Expected initially:

```text
failures because implementation is missing
```

### Phase D — Implement v2-derived engine

Implement only enough code to pass tests.

### Phase E — Single-Pair Smoke

Run on one validated CSV.

### Phase F — Fixed-CFG Walk-Forward

No Optuna yet.

### Phase G — Optuna Smoke and Full WFO

Only after baseline engine is proven.

### Phase H — Final OOS / 845d / Robustness

Mandatory hard validation.

### Phase I — Freqtrade Wrapper Plan

Write separate wrapper plan before coding.

### Phase J — Dry-Run Deployment

Only after approval.

---

## 16. Approval Gates

Current status:

```text
APPROVED: foundation scaffold
APPROVED: master roadmap document
NOT APPROVED: research package implementation
NOT APPROVED: strategy logic implementation
NOT APPROVED: Freqtrade wrapper
NOT APPROVED: container start
NOT APPROVED: live trading
```

Next possible approval phrase:

```text
start Phase A archive and audit
```

or:

```text
start Phase B/C research package with tests
```

Until then, stop at planning.

---

## 17. Rollback

This document is planning-only. To remove it:

```bash
rm /home/hermes/projects/trading/freqtrade/bots/fomo-phase3/docs/context/fomo-phase3-master-implementation-roadmap.md
```

No runtime services are affected.
