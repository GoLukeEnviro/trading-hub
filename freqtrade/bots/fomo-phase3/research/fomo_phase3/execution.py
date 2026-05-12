"""
Execution — position management, funding simulation, trailing stop, slippage.
v2-derived. Fixes applied:
- F1: OpenPosition gains funding_pnl_accumulated field.
- F5: OpenPosition gains position_id field.
"""

from __future__ import annotations

from typing import Callable

import numpy as np
import pandas as pd

from fomo_phase3.config import Direction, ExitReason, StrategyConfig

_position_id_counter: int = 0


def _next_position_id() -> int:
    global _position_id_counter
    _position_id_counter += 1
    return _position_id_counter


def reset_position_counter() -> None:
    global _position_id_counter
    _position_id_counter = 0


# Re-export for type hints
OpenPosition = None  # forward-declared below


from dataclasses import dataclass, field


@dataclass
class OpenPosition:
    direction: Direction
    entry_idx: int
    entry_time: pd.Timestamp
    entry_price: float
    qty: float
    remaining_qty: float
    sl: float
    tp1: float
    tp2: float
    atr: float
    position_id: int = field(default_factory=_next_position_id)
    bars: int = 0
    tp1_done: bool = False
    funding_pnl_accumulated: float = 0.0


def direction_sign(direction: Direction) -> int:
    return 1 if direction == "LONG" else -1


def apply_entry_slippage(price: float, direction: Direction, cfg: StrategyConfig) -> float:
    sign = direction_sign(direction)
    return price * (1 + sign * cfg.slippage_bps)


def apply_exit_slippage(price: float, direction: Direction, cfg: StrategyConfig) -> float:
    sign = direction_sign(direction)
    return price * (1 - sign * cfg.slippage_bps)


def is_funding_timestamp(ts: pd.Timestamp, cfg: StrategyConfig) -> bool:
    if not cfg.simulate_funding:
        return False
    utc_ts = ts.tz_convert("UTC") if ts.tzinfo is not None else ts.tz_localize("UTC")
    return utc_ts.hour in cfg.funding_hours_utc and utc_ts.minute == 0


def process_funding(
    pos: OpenPosition,
    row: pd.Series,
    equity: float,
    cfg: StrategyConfig,
) -> tuple[float, float]:
    ts = pd.Timestamp(row["timestamp"])
    if not is_funding_timestamp(ts, cfg):
        return equity, 0.0

    funding_rate = float(row["funding_rate"])
    notional = abs(float(row["close"]) * pos.remaining_qty)
    sign = direction_sign(pos.direction)

    # Positive funding: longs pay shorts. Negative funding: shorts pay longs.
    funding_pnl = -sign * funding_rate * notional
    pos.funding_pnl_accumulated += funding_pnl
    return equity + funding_pnl, funding_pnl


def update_trailing_stop(pos: OpenPosition, row: pd.Series, cfg: StrategyConfig) -> None:
    if not pos.tp1_done:
        return

    sign = direction_sign(pos.direction)
    close_price = float(row["close"])
    trail_price = close_price - sign * cfg.trail_atr_mult * pos.atr

    if sign * (trail_price - pos.sl) > 0:
        pos.sl = trail_price
