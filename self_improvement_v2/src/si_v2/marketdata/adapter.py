"""Read-only market data ingestion adapters.

Provides the ``ReadOnlyMarketDataAdapter`` protocol and two offline-capable
implementations:

- ``FileBasedMarketDataAdapter`` — loads OHLCV data from CSV files.
- ``StubMarketDataAdapter`` — generates synthetic OHLCV data for testing.

No exchange API calls, no credentials, no live trading dependencies.
"""

from __future__ import annotations

import csv
from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta
from pathlib import Path
from random import Random

from si_v2.marketdata.models import OHLCVDataset, OHLCVRow, OHLCVTimeframe

# 10 million candle limit to prevent accidental OOM
_MAX_CANDLES: int = 10_000_000


# ------------------------------------------------------------------
# Abstract adapter
# ------------------------------------------------------------------


class ReadOnlyMarketDataAdapter(ABC):
    """Abstract read-only adapter for fetching OHLCV market data.

    Subclasses must implement ``fetch_ohlcv``. The method signature is
    intentionally simple — no exchange-specific parameters, no secrets.
    """

    @abstractmethod
    def fetch_ohlcv(
        self,
        pair: str,
        timeframe: str,
        *,
        limit: int = 500,
    ) -> OHLCVDataset:
        """Fetch OHLCV candles for the given pair and timeframe.

        Args:
            pair: Trading pair symbol (e.g. ``"BTC/USDT"``).
            timeframe: Candle timeframe (e.g. ``"5m"``, ``"1h"``).
            limit: Maximum number of candles to return (default 500).

        Returns:
            An ``OHLCVDataset`` containing the requested candles.

        Raises:
            ValueError: If ``limit`` exceeds ``_MAX_CANDLES``.
            NotImplementedError: Subclasses must implement this method.
        """
        ...


# ------------------------------------------------------------------
# File-based adapter (CSV)
# ------------------------------------------------------------------


class FileBasedMarketDataAdapter(ReadOnlyMarketDataAdapter):
    """Read-only adapter that loads OHLCV data from local CSV files.

    Files should be named ``{pair}_{timeframe}.csv`` (e.g.
    ``BTC_USDT_5m.csv``) with columns: timestamp, open, high, low,
    close, volume.

    The pair and timeframe are parsed from the filename stem.
    """

    def __init__(self, data_dir: str | Path) -> None:
        """Initialise the adapter with a directory of CSV files.

        Args:
            data_dir: Path to the directory containing CSV files.
        """
        self._data_dir = Path(data_dir)

    def fetch_ohlcv(
        self,
        pair: str,
        timeframe: str,
        *,
        limit: int = 500,
    ) -> OHLCVDataset:
        """Fetch OHLCV data from a CSV file.

        The file ``{data_dir}/{pair}_{timeframe}.csv`` is read. Pair
        separator ``/`` is replaced with ``_`` for the filename.
        """
        self._validate_limit(limit)
        filename = f"{pair.replace('/', '_')}_{timeframe}.csv"
        filepath = self._data_dir / filename

        if not filepath.is_file():
            msg = f"Market data file not found: {filepath}"
            raise FileNotFoundError(msg)

        return self._load_csv(filepath, pair, timeframe, limit)

    def _load_csv(
        self,
        path: Path,
        pair: str,
        timeframe: str,
        limit: int,
    ) -> OHLCVDataset:
        """Load and parse a CSV file into an OHLCVDataset."""
        rows: list[OHLCVRow] = []
        with path.open(newline="") as f:
            reader = csv.DictReader(f)
            for row_dict in reader:
                if len(rows) >= limit:
                    break
                rows.append(self._parse_row(row_dict))

        return OHLCVDataset.from_row_list(pair, timeframe, rows)

    @staticmethod
    def _parse_row(row_dict: dict[str, str]) -> OHLCVRow:
        """Parse a single CSV row dict into an OHLCVRow."""
        return OHLCVRow(
            timestamp=row_dict.get("timestamp", ""),
            open=float(row_dict.get("open", 0.0)),
            high=float(row_dict.get("high", 0.0)),
            low=float(row_dict.get("low", 0.0)),
            close=float(row_dict.get("close", 0.0)),
            volume=float(row_dict.get("volume", 0.0)),
        )

    @staticmethod
    def _validate_limit(limit: int) -> None:
        """Raise ValueError if limit is out of bounds."""
        if limit <= 0:
            msg = f"limit must be positive, got {limit}"
            raise ValueError(msg)
        if limit > _MAX_CANDLES:
            msg = f"limit {limit} exceeds maximum {_MAX_CANDLES}"
            raise ValueError(msg)


# ------------------------------------------------------------------
# Stub adapter (for offline testing)
# ------------------------------------------------------------------


class StubMarketDataAdapter(ReadOnlyMarketDataAdapter):
    """Test-only adapter that generates synthetic OHLCV data.

    No external files or network calls required. Deterministic when
    ``seed`` is fixed.

    This adapter is **not** suitable for production use — candle values
    are purely synthetic.
    """

    _SUPPORTED_TIMEFRAMES: frozenset[str] = frozenset(t.value for t in OHLCVTimeframe)

    def __init__(self, seed: int = 42) -> None:
        """Initialise the stub adapter with a random seed.

        Args:
            seed: Random seed for deterministic candle generation.
        """
        self._rng = Random(seed)
        self._base_price: float = 50000.0

    def fetch_ohlcv(
        self,
        pair: str,
        timeframe: str,
        *,
        limit: int = 500,
    ) -> OHLCVDataset:
        """Generate synthetic OHLCV candles.

        Args:
            pair: Trading pair symbol.
            timeframe: Candle timeframe. Must be in ``OHLCVTimeframe``.
            limit: Number of synthetic candles to generate.

        Returns:
            An ``OHLCVDataset`` with generated candle data.

        Raises:
            ValueError: If ``timeframe`` is not recognised or ``limit`` is
                out of bounds.
        """
        if timeframe not in self._SUPPORTED_TIMEFRAMES:
            msg = f"Unsupported timeframe: {timeframe!r}. Supported: {sorted(self._SUPPORTED_TIMEFRAMES)}"
            raise ValueError(msg)

        self._validate_limit(limit)

        rows: list[OHLCVRow] = []
        price = self._base_price
        now = datetime.now(UTC)

        for i in range(limit):
            ts = (now - timedelta(minutes=int(timeframe.rstrip("mhdw")) * (limit - i))).isoformat()
            price = self._next_price(price)
            candle = self._make_candle(ts, price)
            rows.append(candle)

        self._base_price = price
        return OHLCVDataset.from_row_list(pair, timeframe, rows)

    def _next_price(self, current: float) -> float:
        """Generate the next price with random walk."""
        change = self._rng.gauss(0, current * 0.002)
        return max(current + change, current * 0.5)

    def _make_candle(self, timestamp: str, close_price: float) -> OHLCVRow:
        """Build a single OHLCVRow around a close price."""
        vol = self._rng.uniform(10.0, 1000.0)
        spread = close_price * self._rng.uniform(0.001, 0.005)
        open_price = close_price + self._rng.uniform(-spread, spread)
        high = max(open_price, close_price) + self._rng.uniform(0.0, spread)
        low = min(open_price, close_price) - self._rng.uniform(0.0, spread)
        return OHLCVRow(
            timestamp=timestamp,
            open=round(open_price, 2),
            high=round(high, 2),
            low=round(low, 2),
            close=round(close_price, 2),
            volume=round(vol, 4),
        )

    @staticmethod
    def _validate_limit(limit: int) -> None:
        """Raise ValueError if limit is out of bounds."""
        if limit <= 0:
            msg = f"limit must be positive, got {limit}"
            raise ValueError(msg)
        if limit > _MAX_CANDLES:
            msg = f"limit {limit} exceeds maximum {_MAX_CANDLES}"
            raise ValueError(msg)
