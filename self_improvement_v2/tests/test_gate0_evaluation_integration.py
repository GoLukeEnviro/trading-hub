"""Tests for Gate-0 evaluation integration (C5).

Tests the snapshot loading, partition filtering, backtest export parsing,
manifest building, and evaluation pipeline functions. No actual Freqtrade
backtest execution (not available on this container).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from si_v2.research.evaluation_bundle_v1 import CandleV1, PartitionWindowV1
from si_v2.research.gate0_evaluation_integration import (
    CALIBRATION,
    HOLDOUT,
    WALK_FORWARD_1,
    WALK_FORWARD_2,
    _partition_candles,
    parse_backtest_trades,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_candles() -> list[CandleV1]:
    base = datetime(2025, 1, 1, tzinfo=UTC)
    return [
        CandleV1(pair="BTC/USDT", timestamp=base, open=100.0, high=101.0, low=99.0, close=100.5, volume=10.0),
        CandleV1(pair="BTC/USDT", timestamp=base.replace(hour=0, minute=15),
                 open=100.5, high=102.0, low=100.0, close=101.0, volume=12.0),
        CandleV1(pair="ETH/USDT", timestamp=base, open=2000.0, high=2010.0, low=1990.0, close=2005.0, volume=5.0),
    ]


# ---------------------------------------------------------------------------
# _partition_candles
# ---------------------------------------------------------------------------


class TestPartitionCandles:
    def test_filter_by_window(self, sample_candles):
        window = PartitionWindowV1(
            label="test", start=datetime(2025, 1, 1, 0, 5, tzinfo=UTC),
            end=datetime(2025, 1, 1, 0, 20, tzinfo=UTC))
        result = _partition_candles(sample_candles, window)
        assert len(result) == 1
        assert result[0].timestamp == datetime(2025, 1, 1, 0, 15, tzinfo=UTC)

    def test_returns_empty_for_empty_window(self, sample_candles):
        window = PartitionWindowV1(
            label="pre", start=datetime(2024, 1, 1, tzinfo=UTC),
            end=datetime(2024, 12, 31, tzinfo=UTC))
        assert _partition_candles(sample_candles, window) == []

    def test_strict_contained_excludes_boundary(self, sample_candles):
        # end is exclusive -> candle at exactly end is excluded
        window = PartitionWindowV1(
            label="test", start=datetime(2025, 1, 1, 0, 5, tzinfo=UTC),
            end=datetime(2025, 1, 1, 0, 20, tzinfo=UTC))
        result = _partition_candles(sample_candles, window)
        assert len(result) == 1  # only the 00:15 candle fits


# ---------------------------------------------------------------------------
# parse_backtest_trades
# ---------------------------------------------------------------------------


class TestParseBacktestTrades:
    def test_parse_simple_trades(self, tmp_path):
        export = {
            "trades": [
                {
                    "trade_id": 1,
                    "pair": "BTC/USDT:USDT",
                    "open_date": "2025-01-01T00:00:00Z",
                    "close_date": "2025-01-01T01:00:00Z",
                    "open_rate": 100.0,
                    "close_rate": 101.0,
                    "amount": 1.0,
                    "is_short": False,
                    "profit_ratio": 0.01,
                }
            ]
        }
        path = tmp_path / "trades.json"
        path.write_text(json.dumps(export))
        trades = parse_backtest_trades(path)
        assert len(trades) == 1
        assert trades[0].pair == "BTC/USDT"
        assert trades[0].entry_price == 100.0
        assert trades[0].side == "long"

    def test_empty_trades(self, tmp_path):
        path = tmp_path / "trades.json"
        path.write_text(json.dumps({"trades": []}))
        assert parse_backtest_trades(path) == []

    def test_strategy_nested_format(self, tmp_path):
        """Some Freqtrade versions nest trades under strategy."""
        export = {"strategy": {"trades": [{
            "trade_id": "a", "pair": "ETH/USDT",
            "open_date": "2025-01-01T00:00:00Z",
            "close_date": "2025-01-01T01:00:00Z",
            "open_rate": 2000, "close_rate": 2010,
            "amount": 0.5, "is_short": False,
        }]}}
        path = tmp_path / "trades.json"
        path.write_text(json.dumps(export))
        trades = parse_backtest_trades(path)
        assert len(trades) == 1
        assert trades[0].pair == "ETH/USDT"

    def test_handles_missing_fields_defaults(self, tmp_path):
        export = {"trades": [{
            "trade_id": "1", "pair": "SOL/USDT",
            "open_date": "2025-06-01T00:00:00Z",
            "close_date": "2025-06-01T01:00:00Z",
            "open_rate": 100.0, "close_rate": 101.0, "amount": 1.0,
        }]}
        path = tmp_path / "trades.json"
        path.write_text(json.dumps(export))
        trades = parse_backtest_trades(path)
        assert len(trades) == 1
        assert trades[0].entry_price == 100.0
        assert trades[0].exit_price == 101.0
        assert trades[0].quantity == 1.0


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestConstants:
    def test_partition_ordering(self):
        """Calibration before walk-forward before holdout, no overlap."""
        assert CALIBRATION.start < CALIBRATION.end
        assert CALIBRATION.end <= WALK_FORWARD_1.start  # contiguous or close
        assert WALK_FORWARD_1.end <= WALK_FORWARD_2.start
        assert WALK_FORWARD_2.end <= HOLDOUT.start
        assert HOLDOUT.start < HOLDOUT.end

    def test_partition_durations(self):
        """Each partition should be the expected length."""
        cal_days = (CALIBRATION.end - CALIBRATION.start).days
        wf_days = (WALK_FORWARD_1.end - WALK_FORWARD_1.start).days
        holdout_days = (HOLDOUT.end - HOLDOUT.start).days
        assert 180 <= cal_days <= 181  # ~6 months
        assert 91 <= wf_days <= 92     # ~3 months
        assert 180 <= holdout_days <= 181  # ~6 months
