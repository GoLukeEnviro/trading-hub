"""Market data feed stub for OHLCV data.

Phase C scope — this module provides a placeholder for future market data
integration.
"""

from __future__ import annotations


class MarketDataFeed:
    """Placeholder for OHLCV market data feed (Phase C scope)."""

    def get_ohlcv(self, pair: str, timeframe: str, limit: int = 500) -> list[dict[str, str | int | float]]:
        """Get OHLCV candle data for a pair.

        Args:
            pair: Trading pair (e.g. 'BTC/USDT').
            timeframe: Candle timeframe (e.g. '5m', '1h').
            limit: Number of candles to return.

        Returns:
            List of OHLCV candle dictionaries (empty in stub).
        """
        return []
