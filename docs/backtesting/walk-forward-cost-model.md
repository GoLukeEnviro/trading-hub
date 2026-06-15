# Walk-Forward Backtest Cost Model

Date: 2026-06-15
Issues: #249

## Purpose

This module adds realistic cost modeling to backtest evaluation.  It is a
**deterministic, fixture-based calculation scaffold** — not an optimizer,
not a live-trading gateway, and not a strategy promoter.

## What the model includes

- **Entry fee** — fraction of notional paid when opening a position.
- **Exit fee** — fraction of notional paid when closing a position.
- **Slippage** — estimated market-impact cost on entry and exit.
- **Funding** — perpetual futures funding rate (long pays, short receives).
- **Gross PnL** — before costs.
- **Net PnL** — after all costs.
- **Aggregate metrics** — win rate, max drawdown, profit factor, average return.
- **Walk-forward windows** — sequential train/test splits with per-window metrics.

## What it deliberately does not include

- No live exchange calls.
- No Docker or runtime dependency.
- No strategy optimisation or parameter search.
- No live-readiness assessment.
- No position sizing or risk management advice.
- No historical data fetching.

## Assumptions

### Fee rates (default: 0.05 % per leg)

Fees are modelled as a fraction of notional value (entry * quantity for entry,
exit * quantity for exit).  The default 0.05 % approximates a taker fee on
Bitget futures.  Users can override via ``CostConfig``.

### Slippage (default: 0.05 % per leg)

Slippage is modelled as an additional cost applied on both entry and exit,
as a fraction of average notional.  This is a simplification — real slippage
depends on order book depth, volatility, and order type.

### Funding (default: 0.01 % per 8h)

Funding is modelled as a linear accrual over hold time.  Long trades pay
funding (cost), short trades receive funding (credit).  The rate is
configurable.  This does not model variable funding rates or premium
index dynamics.

### Walk-forward window split

Trades are split into *n_splits* sequential windows.  Each window is divided
into a training portion (70 %) and a testing portion (30 %).  Non-overlapping.
At least 5 trades per window are required for meaningful statistics.

## How to run tests

```bash
# Cost model unit tests
python3 -m pytest tests/test_backtest_cost_model.py -q

# Walk-forward evaluator tests
python3 -m pytest tests/test_walk_forward_evaluator.py -q

# Both
python3 -m pytest tests/test_backtest_cost_model.py tests/test_walk_forward_evaluator.py -q
```

## How to interpret net metrics

- **Net PnL < Gross PnL** — costs reduce returns.  Always compare net, not gross.
- **Win rate drops after costs** — a strategy that appears profitable on gross
  may be a net loser.
- **Max drawdown on net equity** — the real-world drawdown an operator would
  experience, not a paper simulation.
- **Walk-forward windows** — show whether performance is consistent across time
  periods or driven by a favourable single window.

## Safety statement

- **No live trading enabled.**
- **No exchange API calls.**
- **No Docker or runtime mutation.**
- **No strategy promotion.**  Passing these tests is necessary but not
  sufficient for live readiness.
