"""Test strategy with rsi_period but missing cooldown_candles."""

from __future__ import annotations

rsi_period = 14


class TestStrategy:
    """A minimal strategy class missing the cooldown_candles parameter."""

    def __init__(self) -> None:
        self.rsi_period = rsi_period

    def should_buy(self) -> bool:
        """Dummy buy signal."""
        return False

    def should_sell(self) -> bool:
        """Dummy sell signal."""
        return False
