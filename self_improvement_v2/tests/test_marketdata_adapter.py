"""Unit tests for the read-only market data ingestion adapters.

All tests run offline with no exchange API dependencies.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from si_v2.marketdata.adapter import (
    FileBasedMarketDataAdapter,
    ReadOnlyMarketDataAdapter,
    StubMarketDataAdapter,
)
from si_v2.marketdata.models import OHLCVDataset, OHLCVRow, OHLCVTimeframe

# ======================================================================
# Fixtures
# ======================================================================


@pytest.fixture
def sample_csv_dir(tmp_path: Path) -> Path:
    """Create a temporary directory with sample OHLCV CSV files."""
    data_dir = tmp_path / "marketdata"
    data_dir.mkdir()

    _write_csv(
        data_dir / "BTC_USDT_5m.csv",
        [
            {
                "timestamp": "2024-01-01T00:00:00",
                "open": "42000.0",
                "high": "42500.0",
                "low": "41800.0",
                "close": "42300.0",
                "volume": "100.0",
            },
            {
                "timestamp": "2024-01-01T00:05:00",
                "open": "42300.0",
                "high": "42800.0",
                "low": "42200.0",
                "close": "42700.0",
                "volume": "150.0",
            },
            {
                "timestamp": "2024-01-01T00:10:00",
                "open": "42700.0",
                "high": "43000.0",
                "low": "42600.0",
                "close": "42900.0",
                "volume": "200.0",
            },
        ],
    )
    _write_csv(
        data_dir / "ETH_USDT_1h.csv",
        [
            {
                "timestamp": "2024-01-01T00:00:00",
                "open": "2200.0",
                "high": "2250.0",
                "low": "2180.0",
                "close": "2230.0",
                "volume": "500.0",
            },
        ],
    )
    return data_dir


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    """Write a CSV file with OHLCV data."""
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["timestamp", "open", "high", "low", "close", "volume"])
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


# ======================================================================
# Model tests
# ======================================================================


class TestOHLCVRow:
    """Tests for the OHLCVRow dataclass."""

    def test_create_row(self) -> None:
        """An OHLCVRow should be creatable with valid data."""
        row = OHLCVRow(
            timestamp="2024-01-01T00:00:00",
            open=42000.0,
            high=42500.0,
            low=41800.0,
            close=42300.0,
            volume=100.0,
        )
        assert row.open == 42000.0
        assert row.close == 42300.0
        assert row.volume == 100.0

    def test_row_is_frozen(self) -> None:
        """OHLCVRow should be immutable."""
        row = OHLCVRow(timestamp="t", open=1.0, high=2.0, low=0.5, close=1.5, volume=10.0)
        with pytest.raises(AttributeError):
            row.open = 999.0  # type: ignore[misc]

    def test_row_to_json_safe(self) -> None:
        """to_json_safe should return a JSON-safe dict."""
        row = OHLCVRow(
            timestamp="2024-01-01T00:00:00",
            open=42000.0,
            high=42500.0,
            low=41800.0,
            close=42300.0,
            volume=100.0,
        )
        d = row.to_json_safe()
        assert d["timestamp"] == "2024-01-01T00:00:00"
        assert d["open"] == 42000.0
        assert d["volume"] == 100.0


class TestOHLCVDataset:
    """Tests for the OHLCVDataset dataclass."""

    def test_create_dataset(self) -> None:
        """An OHLCVDataset should be creatable with valid data."""
        row = OHLCVRow(timestamp="t", open=1.0, high=2.0, low=0.5, close=1.5, volume=10.0)
        dataset = OHLCVDataset(pair="BTC/USDT", timeframe="5m", rows=(row,))
        assert dataset.pair == "BTC/USDT"
        assert dataset.timeframe == "5m"
        assert dataset.row_count == 1

    def test_empty_dataset(self) -> None:
        """An OHLCVDataset should accept empty rows."""
        dataset = OHLCVDataset(pair="BTC/USDT", timeframe="5m")
        assert dataset.row_count == 0

    def test_from_row_list(self) -> None:
        """from_row_list should create a dataset from a sequence."""
        rows = [
            OHLCVRow(timestamp="t1", open=1.0, high=2.0, low=0.5, close=1.5, volume=10.0),
            OHLCVRow(timestamp="t2", open=1.5, high=3.0, low=1.0, close=2.5, volume=20.0),
        ]
        dataset = OHLCVDataset.from_row_list("ETH/USDT", "1h", rows)
        assert dataset.pair == "ETH/USDT"
        assert dataset.row_count == 2


class TestOHLCVTimeframe:
    """Tests for the OHLCVTimeframe enum."""

    def test_values(self) -> None:
        """All expected timeframe values should exist."""
        assert OHLCVTimeframe.M5.value == "5m"
        assert OHLCVTimeframe.H1.value == "1h"
        assert OHLCVTimeframe.D1.value == "1d"

    def test_all_values_are_valid(self) -> None:
        """All enum members should be recognised timeframe strings."""
        for tf in OHLCVTimeframe:
            assert tf.value.endswith(("m", "h", "d", "w"))


# ======================================================================
# Adapter base class tests
# ======================================================================


class TestReadOnlyMarketDataAdapter:
    """Tests for the abstract base adapter."""

    def test_cannot_instantiate_abstract(self) -> None:
        """ReadOnlyMarketDataAdapter should not be instantiable directly."""
        with pytest.raises(TypeError):
            ReadOnlyMarketDataAdapter()  # type: ignore[abstract]


# ======================================================================
# File-based adapter tests
# ======================================================================


class TestFileBasedMarketDataAdapter:
    """Tests for the FileBasedMarketDataAdapter."""

    def test_fetch_csv_basic(self, sample_csv_dir: Path) -> None:
        """Should load OHLCV data from a CSV file."""
        adapter = FileBasedMarketDataAdapter(sample_csv_dir)
        dataset = adapter.fetch_ohlcv("BTC/USDT", "5m")

        assert dataset.pair == "BTC/USDT"
        assert dataset.timeframe == "5m"
        assert dataset.row_count == 3
        assert dataset.rows[0].open == 42000.0
        assert dataset.rows[2].close == 42900.0

    def test_fetch_csv_with_limit(self, sample_csv_dir: Path) -> None:
        """Should respect the limit parameter."""
        adapter = FileBasedMarketDataAdapter(sample_csv_dir)
        dataset = adapter.fetch_ohlcv("BTC/USDT", "5m", limit=2)

        assert dataset.row_count == 2

    def test_fetch_missing_file(self, sample_csv_dir: Path) -> None:
        """Should raise FileNotFoundError for missing CSV."""
        adapter = FileBasedMarketDataAdapter(sample_csv_dir)
        with pytest.raises(FileNotFoundError, match="not found"):
            adapter.fetch_ohlcv("DOGE/USDT", "5m")

    def test_fetch_invalid_limit(self, sample_csv_dir: Path) -> None:
        """Should raise ValueError for invalid limit."""
        adapter = FileBasedMarketDataAdapter(sample_csv_dir)
        with pytest.raises(ValueError, match="positive"):
            adapter.fetch_ohlcv("BTC/USDT", "5m", limit=0)

    def test_fetch_eth_pair(self, sample_csv_dir: Path) -> None:
        """Should handle different pairs."""
        adapter = FileBasedMarketDataAdapter(sample_csv_dir)
        dataset = adapter.fetch_ohlcv("ETH/USDT", "1h")

        assert dataset.pair == "ETH/USDT"
        assert dataset.row_count == 1
        assert dataset.rows[0].close == 2230.0

    def test_empty_data_dir(self, tmp_path: Path) -> None:
        """Should raise FileNotFoundError for empty directory."""
        adapter = FileBasedMarketDataAdapter(tmp_path)
        with pytest.raises(FileNotFoundError, match="not found"):
            adapter.fetch_ohlcv("BTC/USDT", "5m")


# ======================================================================
# Stub adapter tests
# ======================================================================


class TestStubMarketDataAdapter:
    """Tests for the StubMarketDataAdapter."""

    def test_fetch_stub_basic(self) -> None:
        """Should generate the requested number of candles."""
        adapter = StubMarketDataAdapter(seed=42)
        dataset = adapter.fetch_ohlcv("BTC/USDT", "5m", limit=10)

        assert dataset.pair == "BTC/USDT"
        assert dataset.timeframe == "5m"
        assert dataset.row_count == 10

    def test_fetch_stub_deterministic(self) -> None:
        """Same seed should produce identical OHLCV values (timestamps differ per call)."""
        a1 = StubMarketDataAdapter(seed=99)
        a2 = StubMarketDataAdapter(seed=99)

        d1 = a1.fetch_ohlcv("BTC/USDT", "5m", limit=5)
        d2 = a2.fetch_ohlcv("BTC/USDT", "5m", limit=5)

        # Compare all fields except timestamp (created with datetime.now)
        for r1, r2 in zip(d1.rows, d2.rows, strict=True):
            assert r1.open == r2.open
            assert r1.high == r2.high
            assert r1.low == r2.low
            assert r1.close == r2.close
            assert r1.volume == r2.volume

    def test_fetch_with_different_seed_produces_different_data(self) -> None:
        """Different seed should produce different data."""
        a1 = StubMarketDataAdapter(seed=1)
        a2 = StubMarketDataAdapter(seed=2)

        d1 = a1.fetch_ohlcv("BTC/USDT", "5m", limit=5)
        d2 = a2.fetch_ohlcv("BTC/USDT", "5m", limit=5)

        assert d1.rows != d2.rows

    def test_candle_values_are_reasonable(self) -> None:
        """Generated candles should have valid price relationships."""
        adapter = StubMarketDataAdapter(seed=42)
        dataset = adapter.fetch_ohlcv("BTC/USDT", "5m", limit=100)

        for row in dataset.rows:
            assert row.high >= row.low, f"high ({row.high}) < low ({row.low})"
            assert row.high >= row.close, f"high ({row.high}) < close ({row.close})"
            assert row.low <= row.open, f"low ({row.low}) > open ({row.open})"
            assert row.volume > 0, "volume must be positive"

    def test_unsupported_timeframe(self) -> None:
        """Should raise ValueError for unsupported timeframe."""
        adapter = StubMarketDataAdapter()
        with pytest.raises(ValueError, match="Unsupported timeframe"):
            adapter.fetch_ohlcv("BTC/USDT", "3m")

    def test_invalid_limit_negative(self) -> None:
        """Should raise ValueError for negative limit."""
        adapter = StubMarketDataAdapter()
        with pytest.raises(ValueError, match="positive"):
            adapter.fetch_ohlcv("BTC/USDT", "5m", limit=-1)

    def test_invalid_limit_zero(self) -> None:
        """Should raise ValueError for zero limit."""
        adapter = StubMarketDataAdapter()
        with pytest.raises(ValueError, match="positive"):
            adapter.fetch_ohlcv("BTC/USDT", "5m", limit=0)

    def test_all_timeframes_supported(self) -> None:
        """All OHLCVTimeframe values should be supported."""
        adapter = StubMarketDataAdapter()
        for tf in OHLCVTimeframe:
            dataset = adapter.fetch_ohlcv("BTC/USDT", tf.value, limit=2)
            assert dataset.row_count == 2
            assert dataset.timeframe == tf.value

    def test_large_limit(self) -> None:
        """Should handle a reasonably large limit."""
        adapter = StubMarketDataAdapter(seed=1)
        dataset = adapter.fetch_ohlcv("BTC/USDT", "5m", limit=5000)
        assert dataset.row_count == 5000

    def test_stub_adapter_implements_protocol(self) -> None:
        """StubMarketDataAdapter should be a ReadOnlyMarketDataAdapter."""
        adapter: ReadOnlyMarketDataAdapter = StubMarketDataAdapter()
        assert isinstance(adapter, StubMarketDataAdapter)
        dataset = adapter.fetch_ohlcv("BTC/USDT", "5m", limit=3)
        assert dataset.row_count == 3
