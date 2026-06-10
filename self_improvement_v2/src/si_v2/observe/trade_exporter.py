"""Trade exporter using dependency-injected FreqtradeAdapter.

Exports trade data through the adapter protocol, never via direct DB access.
"""

from __future__ import annotations

from si_v2.adapters.freqtrade_adapter import FreqtradeAdapter


class TradeExporter:
    """Exports trade history using a FreqtradeAdapter instance."""

    def __init__(self, adapter: FreqtradeAdapter) -> None:
        """Initialize with a FreqtradeAdapter protocol instance.

        Args:
            adapter: FreqtradeAdapter implementation to use for data access.
        """
        self._adapter = adapter

    def export_trades(self, bot_id: str, limit: int = 100) -> list[dict[str, str | int | float]]:
        """Export recent trades for a bot through the adapter.

        Args:
            bot_id: Bot identifier.
            limit: Maximum number of trades to export.

        Returns:
            List of trade record dictionaries.
        """
        return self._adapter.get_trade_history(bot_id, limit=limit)
