"""Typed OHLCV data models for the canonical market-data contract.

No ``Any``. Only frozen dataclasses, StrEnum, and explicit type aliases.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

# ------------------------------------------------------------------
# JSON-safe type aliases (no Any)
# ------------------------------------------------------------------
JsonScalar = str | int | float | bool | None
JsonValue = JsonScalar | dict[str, "JsonValue"] | list["JsonValue"]
JsonObject = dict[str, JsonValue]


# ------------------------------------------------------------------
# Enumerations
# ------------------------------------------------------------------


class OHLCVTimeframe(StrEnum):
    """Canonical OHLCV timeframes supported by the adapter contract."""

    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    M30 = "30m"
    H1 = "1h"
    H4 = "4h"
    D1 = "1d"
    W1 = "1w"


# ------------------------------------------------------------------
# Data models
# ------------------------------------------------------------------


@dataclass(frozen=True)
class OHLCVRow:
    """A single OHLCV candle.

    Attributes:
        timestamp: ISO 8601 timestamp string (e.g. ``"2024-01-01T00:00:00"``).
        open: Opening price.
        high: Highest price during the period.
        low: Lowest price during the period.
        close: Closing price.
        volume: Trading volume.
    """

    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float

    def to_json_safe(self) -> JsonObject:
        """Return a JSON-safe dict representation."""
        return {
            "timestamp": self.timestamp,
            "open": round(self.open, 8),
            "high": round(self.high, 8),
            "low": round(self.low, 8),
            "close": round(self.close, 8),
            "volume": round(self.volume, 8),
        }


@dataclass(frozen=True)
class OHLCVDataset:
    """A collection of OHLCV candles for a specific trading pair and timeframe.

    Attributes:
        pair: Trading pair symbol (e.g. ``"BTC/USDT"``).
        timeframe: Candle timeframe string (e.g. ``"5m"``).
        rows: Ordered sequence of OHLCV candles.
    """

    pair: str
    timeframe: str
    rows: tuple[OHLCVRow, ...] = ()

    @property
    def row_count(self) -> int:
        """Number of candles in the dataset."""
        return len(self.rows)

    def to_json_safe(self) -> JsonObject:
        """Return a JSON-safe dict representation."""
        return {
            "pair": self.pair,
            "timeframe": self.timeframe,
            "row_count": self.row_count,
            "rows": [r.to_json_safe() for r in self.rows],
        }

    @classmethod
    def from_row_list(
        cls,
        pair: str,
        timeframe: str,
        rows: Sequence[OHLCVRow],
    ) -> OHLCVDataset:
        """Create a dataset from a sequence of rows.

        This is the canonical constructor when building datasets from
        dynamic data (file reads, stub generation, etc.).
        """
        return cls(pair=pair, timeframe=timeframe, rows=tuple(rows))
