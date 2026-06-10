"""Test strategy with rsi_period declared twice (ambiguous)."""

from __future__ import annotations

rsi_period = 14
rsi_period = 7  # Second declaration — ambiguous


class TestStrategy:
    """A minimal strategy class with duplicate rsi_period assignment."""

    def __init__(self) -> None:
        self.rsi_period = rsi_period

    def should_buy(self) -> bool:
        """Dummy buy signal."""
        return False

    def should_sell(self) -> bool:
        """Dummy sell signal."""
        return False
