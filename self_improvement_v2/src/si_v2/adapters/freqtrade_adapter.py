"""Read-only Freqtrade adapter protocol.

Defines the interface for Freqtrade interactions. Only read-only methods
are permitted — no write_config, place_order, or other write operations.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from si_v2.state.schemas import MutationOverlay


@runtime_checkable
class FreqtradeAdapter(Protocol):
    """Protocol for read-only Freqtrade operations."""

    def read_config(self, bot_id: str) -> dict[str, str | int | float | bool]:
        """Read the current Freqtrade configuration for a bot.

        Args:
            bot_id: Bot identifier.

        Returns:
            Configuration dictionary (read-only copy).
        """
        ...

    def get_trade_history(self, bot_id: str, limit: int = 100) -> list[dict[str, str | int | float]]:
        """Get recent trade history for a bot.

        Args:
            bot_id: Bot identifier.
            limit: Maximum number of trades to return.

        Returns:
            List of trade record dictionaries.
        """
        ...

    def run_backtest(self, bot_id: str, overlay: MutationOverlay) -> dict[str, str | int | float]:
        """Run a backtest with the given overlay parameters.

        Args:
            bot_id: Bot identifier.
            overlay: Mutation overlay parameters to backtest.

        Returns:
            Backtest result dictionary.
        """
        ...
