"""
Metrics — trade dataclass, result container, drawdown, sharpe, summary.
v2-derived. Fixes applied:
- F1: Trade includes funding_pnl field.
- F5: Trade includes position_id field.
- F2: Separate leg vs position profit factor functions.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from dataclasses import dataclass, field

from fomo_phase3.config import Direction, ExitReason


@dataclass
class Trade:
    """A single leg of a trade (TP1, TP2, SL, etc.). Multiple legs share a position_id."""

    position_id: int
    entry_time: str
    exit_time: str
    direction: Direction
    exit_reason: ExitReason
    entry_price: float
    exit_price: float
    qty: float
    fraction_of_initial: float
    gross_pnl: float
    fees: float
    net_pnl: float
    funding_pnl: float = 0.0
    equity_after: float = 0.0
    bars_held: int = 0


class BacktestResult:
    """Aggregated backtest result container."""

    def __init__(
        self,
        initial_equity: float,
        final_equity: float,
        total_return_pct: float,
        max_drawdown_pct: float,
        sharpe: float,
        profit_factor: float,
        win_rate: float,
        trades: int,
        closed_legs: int,
        funding_pnl: float,
        trades_df: pd.DataFrame,
        equity_curve: pd.DataFrame,
    ):
        self.initial_equity = initial_equity
        self.final_equity = final_equity
        self.total_return_pct = total_return_pct
        self.max_drawdown_pct = max_drawdown_pct
        self.sharpe = sharpe
        self.profit_factor = profit_factor
        self.win_rate = win_rate
        self.trades = trades
        self.closed_legs = closed_legs
        self.funding_pnl = funding_pnl
        self.trades_df = trades_df
        self.equity_curve = equity_curve


def calc_drawdown(equity: pd.Series) -> float:
    peak = equity.cummax()
    drawdown = (equity / peak) - 1.0
    return abs(float(drawdown.min())) if len(drawdown) else 0.0


def calc_sharpe(equity: pd.Series, periods_per_year: int) -> float:
    returns = equity.pct_change().replace([np.inf, -np.inf], np.nan).dropna()
    if len(returns) < 2:
        return 0.0
    std = float(returns.std())
    if std == 0 or math.isnan(std):
        return 0.0
    return float((returns.mean() / std) * math.sqrt(periods_per_year))


def result_summary(result: BacktestResult) -> dict[str, float | int]:
    return {
        "initial_equity": round(result.initial_equity, 8),
        "final_equity": round(result.final_equity, 8),
        "total_return_pct": round(result.total_return_pct, 4),
        "max_drawdown_pct": round(result.max_drawdown_pct, 4),
        "sharpe": round(result.sharpe, 4),
        "profit_factor": round(result.profit_factor, 4)
        if math.isfinite(result.profit_factor)
        else 9999.0,
        "win_rate": round(result.win_rate, 4),
        "trades": result.trades,
        "closed_legs": result.closed_legs,
        "funding_pnl": round(result.funding_pnl, 8),
    }


def leg_profit_factor(trades_df: pd.DataFrame) -> float:
    """Profit factor computed on individual legs."""
    if trades_df.empty:
        return 0.0
    wins = trades_df.loc[trades_df["net_pnl"] > 0, "net_pnl"].sum()
    losses = trades_df.loc[trades_df["net_pnl"] < 0, "net_pnl"].sum()
    if losses >= 0:
        return float("inf")
    return float(wins / abs(losses))


def position_profit_factor(trades_df: pd.DataFrame) -> float:
    """Profit factor aggregated by position (sum all legs per position_id)."""
    if trades_df.empty or "position_id" not in trades_df.columns:
        return leg_profit_factor(trades_df)
    position_pnl = trades_df.groupby("position_id")["net_pnl"].sum()
    wins = position_pnl[position_pnl > 0].sum()
    losses = position_pnl[position_pnl < 0].sum()
    if losses >= 0:
        return float("inf")
    return float(wins / abs(losses))


def position_win_rate(trades_df: pd.DataFrame) -> float:
    """Win rate aggregated by position."""
    if trades_df.empty or "position_id" not in trades_df.columns:
        return 0.0
    position_pnl = trades_df.groupby("position_id")["net_pnl"].sum()
    return float((position_pnl > 0).mean() * 100.0)


def expectancy(trades_df: pd.DataFrame) -> float:
    """Average net PnL per trade (position-aggregated)."""
    if trades_df.empty or "position_id" not in trades_df.columns:
        return 0.0
    position_pnl = trades_df.groupby("position_id")["net_pnl"].sum()
    return float(position_pnl.mean())


def breakeven_win_rate(trades_df: pd.DataFrame) -> float:
    """Breakeven win rate: avg_loss / (avg_win + avg_loss)."""
    if trades_df.empty or "position_id" not in trades_df.columns:
        return 0.0
    position_pnl = trades_df.groupby("position_id")["net_pnl"].sum()
    wins = position_pnl[position_pnl > 0]
    losses = position_pnl[position_pnl < 0]
    if len(wins) == 0 or len(losses) == 0:
        return 0.0
    avg_win = float(wins.mean())
    avg_loss = float(abs(losses.mean()))
    if avg_win + avg_loss == 0:
        return 0.0
    return avg_loss / (avg_win + avg_loss)
