"""Simple test strategy with both mutable parameters."""

from __future__ import annotations

rsi_period = 14
cooldown_candles = 6


class TestStrategy:
    """A minimal strategy class for sandbox mutation testing."""

    def __init__(self) -> None:
        self.rsi_period = rsi_period
        self.cooldown_candles = cooldown_candles

    def should_buy(self) -> bool:
        """Dummy buy signal."""
        return False

    def should_sell(self) -> bool:
        """Dummy sell signal."""
        return False
