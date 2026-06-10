"""Unit tests for MarketDataFeed (CSV, dict, and optional Feather)."""

from __future__ import annotations

from pathlib import Path

import pytest

from si_v2.observe.market_data import MarketDataDependencyError, MarketDataFeed, OHLCVDataset, OHLCVRow

_SAMPLE_ROW_A: dict[str, str | float] = {
    "timestamp": "2024-01-01T00:00:00",
    "open": 42000.0,
    "high": 42500.0,
    "low": 41800.0,
    "close": 42300.0,
    "volume": 100.0,
}
_SAMPLE_ROW_B: dict[str, str | float] = {
    "timestamp": "2024-01-01T00:05:00",
    "open": 42300.0,
    "high": 42800.0,
    "low": 42200.0,
    "close": 42700.0,
    "volume": 150.0,
}


def _write_csv(path: Path, rows: list[dict[str, str | float]]) -> None:
    """Write a CSV file with OHLCV data."""
    import csv

    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["timestamp", "open", "high", "low", "close", "volume"])
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


class TestMarketDataFeedCSV:
    """Tests for CSV loading."""

    def test_load_csv_basic(self, tmp_path: Path) -> None:
        """Should load OHLCV data from a CSV file."""
        csv_path = tmp_path / "BTC_USDT_5m.csv"
        _write_csv(csv_path, [_SAMPLE_ROW_A, _SAMPLE_ROW_B])

        feed = MarketDataFeed()
        dataset = feed.load_from_csv(csv_path)

        assert len(dataset.rows) == 2
        assert dataset.rows[0].open == 42000.0
        assert dataset.rows[1].close == 42700.0
        assert dataset.rows[0].volume == 100.0

    def test_load_csv_pair_timeframe(self, tmp_path: Path) -> None:
        """Should parse pair and timeframe from filename."""
        csv_path = tmp_path / "BTC_USDT_5m.csv"
        _write_csv(csv_path, [_SAMPLE_ROW_A])

        feed = MarketDataFeed()
        dataset = feed.load_from_csv(csv_path)

        assert dataset.pair == "BTC_USDT"
        assert dataset.timeframe == "5m"

    def test_load_csv_empty_file(self, tmp_path: Path) -> None:
        """Should handle empty CSV (header only)."""
        csv_path = tmp_path / "data.csv"
        _write_csv(csv_path, [])

        feed = MarketDataFeed()
        dataset = feed.load_from_csv(csv_path)

        assert len(dataset.rows) == 0


class TestMarketDataFeedDict:
    """Tests for dict-based loading."""

    def test_load_dict_basic(self) -> None:
        """Should load OHLCV data from a list of dicts."""
        feed = MarketDataFeed()
        data: list[dict[str, str | int | float]] = [_SAMPLE_ROW_A, _SAMPLE_ROW_B]

        dataset = feed.load_from_dict(data, pair="BTC/USDT", timeframe="5m")

        assert dataset.pair == "BTC/USDT"
        assert dataset.timeframe == "5m"
        assert len(dataset.rows) == 2
        assert dataset.rows[0].open == 42000.0

    def test_load_dict_empty(self) -> None:
        """Should handle empty list."""
        feed = MarketDataFeed()
        dataset = feed.load_from_dict([], pair="BTC/USDT", timeframe="5m")

        assert len(dataset.rows) == 0
        assert dataset.pair == "BTC/USDT"

    def test_load_dict_with_numeric_timestamp(self) -> None:
        """Should handle numeric (epoch) timestamps."""
        feed = MarketDataFeed()
        data: list[dict[str, str | int | float]] = [
            {
                "timestamp": 1704067200.0,
                "open": 42000.0,
                "high": 42500.0,
                "low": 41800.0,
                "close": 42300.0,
                "volume": 100.0,
            }
        ]

        dataset = feed.load_from_dict(data, pair="BTC/USDT", timeframe="1h")
        assert len(dataset.rows) == 1


class TestMarketDataFeedFeather:
    """Tests for optional Feather loading."""

    def test_feather_raises_dependency_error_without_pyarrow(self, tmp_path: Path) -> None:
        """Should raise MarketDataDependencyError if pyarrow is not available."""
        try:
            import pyarrow.feather  # noqa: F401

            pytest.skip("pyarrow is installed — cannot test missing-dependency path")
        except ImportError:
            pass

        feed = MarketDataFeed()
        dummy_path = tmp_path / "test.feather"

        with pytest.raises(MarketDataDependencyError, match="pyarrow"):
            feed.load_from_feather(dummy_path)

    def test_feather_dependency_error_is_typed(self) -> None:
        """MarketDataDependencyError should be a distinct exception type."""
        assert issubclass(MarketDataDependencyError, Exception)

    def test_feather_loads_when_available(self, tmp_path: Path) -> None:
        """Should load Feather data when pyarrow is available."""
        try:
            import pyarrow as pa
        except ImportError:
            pytest.skip("pyarrow not installed — cannot test Feather loading")

        feed = MarketDataFeed()

        table = pa.table(
            {
                "timestamp": ["2024-01-01T00:00:00", "2024-01-01T00:05:00"],
                "open": [42000.0, 42300.0],
                "high": [42500.0, 42800.0],
                "low": [41800.0, 42200.0],
                "close": [42300.0, 42700.0],
                "volume": [100.0, 150.0],
            }
        )
        feather_path = tmp_path / "test.feather"
        pa.feather.write_feather(table, feather_path)

        dataset = feed.load_from_feather(feather_path)

        assert len(dataset.rows) == 2
        assert dataset.rows[0].open == 42000.0
        assert dataset.rows[1].close == 42700.0


class TestOHLCVModels:
    """Tests for OHLCV Pydantic models."""

    def test_ohlcv_row_creation(self) -> None:
        """OHLCVRow should be creatable with valid data."""
        from datetime import datetime

        row = OHLCVRow(
            timestamp=datetime(2024, 1, 1, 0, 0),
            open=42000.0,
            high=42500.0,
            low=41800.0,
            close=42300.0,
            volume=100.0,
        )
        assert row.open == 42000.0
        assert row.volume == 100.0

    def test_ohlcv_dataset_creation(self) -> None:
        """OHLCVDataset should be creatable with valid data."""
        from datetime import datetime

        row = OHLCVRow(
            timestamp=datetime(2024, 1, 1),
            open=42000.0,
            high=42500.0,
            low=41800.0,
            close=42300.0,
            volume=100.0,
        )
        dataset = OHLCVDataset(pair="BTC/USDT", timeframe="5m", rows=[row])
        assert dataset.pair == "BTC/USDT"
        assert len(dataset.rows) == 1

    def test_ohlcv_dataset_empty(self) -> None:
        """OHLCVDataset should accept empty rows."""
        dataset = OHLCVDataset(pair="BTC/USDT", timeframe="5m")
        assert len(dataset.rows) == 0
