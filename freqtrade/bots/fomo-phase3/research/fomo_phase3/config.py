"""
StrategyConfig — frozen dataclass for all FOMO strategy parameters.

v2-derived. Fixes applied:
- F3: volume_fill_method added to control forward-fill vs drop policy.
- F5: position_id support added.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Literal

import pandas as pd


Direction = Literal["LONG", "SHORT"]
ExitReason = Literal[
    "SL_HIT",
    "TP1_HIT",
    "TP2_HIT",
    "FOMO_DECAY",
    "TIME_EXIT",
    "END_OF_DATA",
]


@dataclass
class WalkForwardFold:
    fold: int
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp


@dataclass(frozen=True)
class StrategyConfig:
    # Signal thresholds
    fomo_entry: float = 2.2
    fomo_exit: float = 0.3
    roc_long: float = 0.0012
    roc_short: float = -0.0012
    trend_min: float = 0.1
    noise_atr_pct: float = 0.55
    oi_price_alignment_thresh: float = 0.15
    funding_residual_thresh_long: float = 0.0004
    funding_residual_thresh_short: float = -0.0004

    # Signal windows
    z_window: int = 20
    atr_period: int = 14
    ema_fast: int = 21
    ema_slow: int = 55
    oi_alignment_window: int = 288
    funding_residual_window: int = 288

    # Risk and execution
    risk_per_trade: float = 0.01
    max_notional_pct: float = 1.0
    sl_atr_mult: float = 1.5
    tp1_atr_mult: float = 2.0
    tp2_atr_mult: float = 4.0
    tp1_fraction: float = 0.60
    trail_atr_mult: float = 0.8
    max_bars: int = 24
    taker_fee: float = 0.0006
    slippage_bps: float = 0.001
    latency_candles: int = 1

    # Funding simulation
    simulate_funding: bool = True
    funding_hours_utc: tuple[int, ...] = (0, 8, 16)

    # Data policy (F3 fix: explicit volume fill method)
    volume_fill_method: str = "drop"  # "ffill" or "drop"

    # Backtest safety
    conservative_intrabar: bool = True
    min_trades_per_test: int = 10
    max_drawdown_constraint: float = 0.12

    # Annualization for 5m bars: 365 * 24 * 12
    periods_per_year: int = 105_120
