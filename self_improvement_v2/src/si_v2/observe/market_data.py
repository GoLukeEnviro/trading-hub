"""Market data feed for OHLCV candle data.

Provides loading of OHLCV data from multiple formats: Feather (optional,
requires pyarrow), CSV, and in-memory dict. Feather support is optional —
if pyarrow is not installed, a typed MarketDataDependencyError is raised.
"""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class MarketDataDependencyError(Exception):
    """Raised when an optional dependency (pyarrow/pandas) is not available."""


class OHLCVRow(BaseModel):
    """A single OHLCV candle row."""

    model_config = ConfigDict(strict=True)

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class OHLCVDataset(BaseModel):
    """A dataset of OHLCV candles for a specific pair and timeframe."""

    model_config = ConfigDict(strict=False)

    pair: str
    timeframe: str
    rows: list[OHLCVRow] = Field(default_factory=list)


class MarketDataFeed:
    """Loads OHLCV market data from various formats."""

    def load_from_feather(self, path: Path) -> OHLCVDataset:
        """Load OHLCV data from a Feather file.

        Requires pyarrow to be installed. Raises MarketDataDependencyError
        if pyarrow is not available.

        Args:
            path: Path to the Feather file.

        Returns:
            OHLCVDataset with loaded candle data.

        Raises:
            MarketDataDependencyError: If pyarrow is not installed.
            FileNotFoundError: If the file does not exist.
        """
        try:
            import pyarrow.feather  # noqa: F401 — needed to verify availability
        except ImportError as exc:
            raise MarketDataDependencyError(
                "pyarrow is required for Feather file support. Install it with: pip install pyarrow"
            ) from exc

        import pyarrow.feather as feather_module

        table = feather_module.read_table(path)  # type: ignore[no-untyped-call]
        rows: list[OHLCVRow] = []
        for i in range(table.num_rows):
            raw_ts = table.column("timestamp")[i].as_py()
            if isinstance(raw_ts, str):
                ts = datetime.fromisoformat(raw_ts)
            elif isinstance(raw_ts, (int, float)):
                ts = datetime.fromtimestamp(raw_ts)
            else:
                ts = raw_ts if isinstance(raw_ts, datetime) else datetime.now()
            row = OHLCVRow(
                timestamp=ts,
                open=float(table.column("open")[i].as_py()),
                high=float(table.column("high")[i].as_py()),
                low=float(table.column("low")[i].as_py()),
                close=float(table.column("close")[i].as_py()),
                volume=float(table.column("volume")[i].as_py()),
            )
            rows.append(row)

        # Extract pair and timeframe from metadata or defaults
        pair = ""
        timeframe = ""
        metadata = table.schema.metadata
        if metadata:
            pair = metadata.get(b"pair", b"").decode() if b"pair" in metadata else ""
            timeframe = metadata.get(b"timeframe", b"").decode() if b"timeframe" in metadata else ""

        return OHLCVDataset(pair=pair, timeframe=timeframe, rows=rows)

    def load_from_csv(self, path: Path) -> OHLCVDataset:
        """Load OHLCV data from a CSV file.

        Expects columns: timestamp, open, high, low, close, volume.
        The pair and timeframe are extracted from filename pattern
        {pair}_{timeframe}.csv or left empty.

        Args:
            path: Path to the CSV file.

        Returns:
            OHLCVDataset with loaded candle data.
        """
        rows: list[OHLCVRow] = []
        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            for row_dict in reader:
                ts_str = row_dict.get("timestamp", "")
                ts = datetime.fromisoformat(ts_str) if ts_str else datetime.now()
                rows.append(
                    OHLCVRow(
                        timestamp=ts,
                        open=float(row_dict.get("open", 0.0)),
                        high=float(row_dict.get("high", 0.0)),
                        low=float(row_dict.get("low", 0.0)),
                        close=float(row_dict.get("close", 0.0)),
                        volume=float(row_dict.get("volume", 0.0)),
                    )
                )

        pair, timeframe = self._parse_pair_timeframe(path.stem)
        return OHLCVDataset(pair=pair, timeframe=timeframe, rows=rows)

    def load_from_dict(
        self,
        data: list[dict[str, str | int | float]],
        pair: str = "",
        timeframe: str = "",
    ) -> OHLCVDataset:
        """Load OHLCV data from a list of dictionaries (for testing).

        Args:
            data: List of dicts with keys: timestamp, open, high, low, close, volume.
            pair: Trading pair identifier.
            timeframe: Candle timeframe string.

        Returns:
            OHLCVDataset with loaded candle data.
        """
        rows: list[OHLCVRow] = []
        for item in data:
            ts_val = item.get("timestamp", "")
            if isinstance(ts_val, str):
                ts = datetime.fromisoformat(ts_val)
            elif isinstance(ts_val, (int, float)):
                ts = datetime.fromtimestamp(ts_val)
            else:
                ts = datetime.now()
            rows.append(
                OHLCVRow(
                    timestamp=ts,
                    open=float(item.get("open", 0.0)),
                    high=float(item.get("high", 0.0)),
                    low=float(item.get("low", 0.0)),
                    close=float(item.get("close", 0.0)),
                    volume=float(item.get("volume", 0.0)),
                )
            )
        return OHLCVDataset(pair=pair, timeframe=timeframe, rows=rows)

    def _parse_pair_timeframe(self, stem: str) -> tuple[str, str]:
        """Parse pair and timeframe from a filename stem.

        Expects format: {pair}_{timeframe} (e.g. BTC_USDT_5m or BTCUSDT_1h).

        Args:
            stem: Filename stem without extension.

        Returns:
            Tuple of (pair, timeframe).
        """
        parts = stem.rsplit("_", 1)
        if len(parts) == 2:
            return parts[0], parts[1]
        return stem, ""
