"""Test strategy with invalid Python syntax."""

from __future__ import annotations

rsi_period = 14
cooldown_candles = 6
this_line_has_a_syntax_error = = = = =


class TestStrategy:
    """This class will never be reached due to syntax error above."""

    def __init__(self) -> None:
        self.rsi_period = rsi_period

    def should_buy(self) -> bool:
        """Dummy buy signal."""
        return False