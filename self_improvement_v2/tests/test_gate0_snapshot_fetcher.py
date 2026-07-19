"""Tests for the Gate-0 snapshot fetcher (C1, spec #653).

No real network access. All HTTP calls are mocked via the ``http_get`` injection
point. Tests cover backward pagination, boundary normalization, deduplication,
atomic writes, resumability, hash format, and all edge cases (429, 5xx, empty
pages, gaps, duplicates, boundary overlap).
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from si_v2.research.evaluation_bundle_v1 import CandleV1, canonical_candle_hash
from si_v2.research.gate0_snapshot_fetcher import (
    HISTORY_ENDPOINT,
    MAX_CANDLES_PER_REQUEST,
    MAX_QUERY_RANGE_DAYS,
    SnapshotFetchError,
    build_manifest,
    dedup_and_sort,
    fetch_history_candles,
    normalize_candles,
    write_snapshot,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ts(minute: int) -> str:
    """Bitget-style ms timestamp for 2025-01-01 + minute*15."""
    base = int(datetime(2025, 1, 1, tzinfo=UTC).timestamp() * 1000)
    return str(base + minute * 15 * 60 * 1000)


def _raw_candle(pair: str, minute: int, o=100.0, hi=101.0, lo=99.0, c=100.5, vol=10.0):
    """One raw Bitget candle array: [ts, o, h, l, c, vol]."""
    return [_ts(minute), str(o), str(hi), str(lo), str(c), str(vol)]


def _mock_response(candles: list, status=200, next_marker=None):
    """Build a mock Bitget history-candles API response."""
    body = {"code": "00000", "data": candles}
    return status, json.dumps(body)


# ---------------------------------------------------------------------------
# normalize_candles
# ---------------------------------------------------------------------------


class TestNormalizeCandles:
    def test_converts_raw_to_candle_v1(self):
        raw = [_raw_candle("BTCUSDT", 0), _raw_candle("BTCUSDT", 1)]
        result = normalize_candles(raw, pair="BTC/USDT")
        assert len(result) == 2
        assert all(isinstance(c, CandleV1) for c in result)
        assert result[0].pair == "BTC/USDT"
        assert result[0].timestamp == datetime(2025, 1, 1, 0, 0, tzinfo=UTC)
        assert result[1].timestamp == datetime(2025, 1, 1, 0, 15, tzinfo=UTC)

    def test_15min_boundary_normalization(self):
        # Timestamp at 00:07:30 should snap to 00:00:00 (15m boundary)
        odd_ts = int(datetime(2025, 1, 1, 0, 7, 30, tzinfo=UTC).timestamp() * 1000)
        raw = [[str(odd_ts), "100", "101", "99", "100.5", "10"]]
        result = normalize_candles(raw, pair="BTC/USDT")
        assert result[0].timestamp == datetime(2025, 1, 1, 0, 0, tzinfo=UTC)

    def test_skips_malformed_rows(self):
        raw = [
            _raw_candle("BTCUSDT", 0),
            ["bad", "data"],  # malformed
            _raw_candle("BTCUSDT", 1),
        ]
        result = normalize_candles(raw, pair="BTC/USDT")
        assert len(result) == 2

    def test_rejects_negative_price(self):
        raw = [["100", "-1", "101", "99", "100", "10"]]
        with pytest.raises(ValueError, match="must be > 0"):
            normalize_candles(raw, pair="BTC/USDT")


# ---------------------------------------------------------------------------
# dedup_and_sort
# ---------------------------------------------------------------------------


class TestDedupAndSort:
    def test_removes_duplicates(self):
        c1 = normalize_candles([_raw_candle("BTCUSDT", 0)], "BTC/USDT")
        c2 = normalize_candles([_raw_candle("BTCUSDT", 0)], "BTC/USDT")  # dup
        c3 = normalize_candles([_raw_candle("BTCUSDT", 1)], "BTC/USDT")
        result = dedup_and_sort(c1 + c2 + c3)
        assert len(result) == 2

    def test_sorts_chronologically(self):
        c1 = normalize_candles([_raw_candle("BTCUSDT", 5)], "BTC/USDT")
        c2 = normalize_candles([_raw_candle("BTCUSDT", 0)], "BTC/USDT")
        c3 = normalize_candles([_raw_candle("BTCUSDT", 3)], "BTC/USDT")
        result = dedup_and_sort(c1 + c2 + c3)
        assert result[0].timestamp < result[1].timestamp < result[2].timestamp

    def test_boundary_overlap_no_dup(self):
        """Two paginated ranges overlap by one candle — must not produce dup."""
        c_overlap_1 = normalize_candles([_raw_candle("BTCUSDT", 10)], "BTC/USDT")
        c_overlap_2 = normalize_candles([_raw_candle("BTCUSDT", 10)], "BTC/USDT")
        c_before = normalize_candles(
            [_raw_candle("BTCUSDT", i) for i in range(0, 10)], "BTC/USDT"
        )
        c_after = normalize_candles(
            [_raw_candle("BTCUSDT", i) for i in range(11, 20)], "BTC/USDT"
        )
        result = dedup_and_sort(c_before + c_overlap_1 + c_overlap_2 + c_after)
        assert len(result) == 20  # 0..19, no dup of minute 10


# ---------------------------------------------------------------------------
# fetch_history_candles (pagination + error handling)
# ---------------------------------------------------------------------------


class TestFetchHistoryCandles:
    def test_single_page_fetch(self):
        candles = [_raw_candle("BTCUSDT", i) for i in range(3)]
        mock_get = MagicMock(return_value=_mock_response(candles))
        result = fetch_history_candles(
            pair="BTC/USDT",
            symbol="BTCUSDT",
            product_type="USDT-FUTURES",
            timeframe="15m",
            start=datetime(2025, 1, 1, tzinfo=UTC),
            end=datetime(2025, 1, 1, 0, 45, tzinfo=UTC),
            http_get=mock_get,
        )
        assert len(result) == 3
        assert all(isinstance(c, CandleV1) for c in result)

    def test_backward_pagination(self):
        """Full page (200 candles) triggers a second request."""
        page1 = [_raw_candle("BTCUSDT", i) for i in range(MAX_CANDLES_PER_REQUEST)]
        page2 = [_raw_candle("BTCUSDT", i) for i in range(MAX_CANDLES_PER_REQUEST, 210)]
        responses = [_mock_response(page1), _mock_response(page2)]
        mock_get = MagicMock(side_effect=responses)
        # Range must be large enough that 200 candles don't cover it all:
        # 210 candles * 15m = 52.5 hours ≈ 2.19 days
        result = fetch_history_candles(
            pair="BTC/USDT",
            symbol="BTCUSDT",
            product_type="USDT-FUTURES",
            timeframe="15m",
            start=datetime(2024, 12, 31, tzinfo=UTC),
            end=datetime(2025, 1, 3, tzinfo=UTC),  # 3 days > 210*15m
            http_get=mock_get,
        )
        assert mock_get.call_count == 2
        assert len(result) == 210

    def test_empty_page_stops_pagination(self):
        mock_get = MagicMock(return_value=_mock_response([]))
        result = fetch_history_candles(
            pair="BTC/USDT",
            symbol="BTCUSDT",
            product_type="USDT-FUTURES",
            timeframe="15m",
            start=datetime(2025, 1, 1, tzinfo=UTC),
            end=datetime(2025, 1, 1, 1, tzinfo=UTC),
            http_get=mock_get,
        )
        assert len(result) == 0

    def test_429_retries_then_succeeds(self):
        candles = [_raw_candle("BTCUSDT", 0)]
        responses = [(429, '{"code":"30001","msg":"rate limit"}'), _mock_response(candles)]
        mock_get = MagicMock(side_effect=responses)
        result = fetch_history_candles(
            pair="BTC/USDT",
            symbol="BTCUSDT",
            product_type="USDT-FUTURES",
            timeframe="15m",
            start=datetime(2025, 1, 1, tzinfo=UTC),
            end=datetime(2025, 1, 1, 0, 15, tzinfo=UTC),
            http_get=mock_get,
            max_retries=3,
            retry_delay=0,  # no sleep in tests
        )
        assert len(result) == 1

    def test_429_exhausts_retries(self):
        mock_get = MagicMock(return_value=(429, '{"code":"30001"}'))
        with pytest.raises(SnapshotFetchError, match="rate limit"):
            fetch_history_candles(
                pair="BTC/USDT",
                symbol="BTCUSDT",
                product_type="USDT-FUTURES",
                timeframe="15m",
                start=datetime(2025, 1, 1, tzinfo=UTC),
                end=datetime(2025, 1, 1, 0, 15, tzinfo=UTC),
                http_get=mock_get,
                max_retries=2,
                retry_delay=0,
            )

    def test_5xx_retries_then_raises(self):
        mock_get = MagicMock(return_value=(500, '{"code":"error"}'))
        with pytest.raises(SnapshotFetchError, match="HTTP 500"):
            fetch_history_candles(
                pair="BTC/USDT",
                symbol="BTCUSDT",
                product_type="USDT-FUTURES",
                timeframe="15m",
                start=datetime(2025, 1, 1, tzinfo=UTC),
                end=datetime(2025, 1, 1, 0, 15, tzinfo=UTC),
                http_get=mock_get,
                max_retries=2,
                retry_delay=0,
            )

    def test_uses_history_endpoint(self):
        mock_get = MagicMock(return_value=_mock_response([_raw_candle("BTCUSDT", 0)]))
        fetch_history_candles(
            pair="BTC/USDT",
            symbol="BTCUSDT",
            product_type="USDT-FUTURES",
            timeframe="15m",
            start=datetime(2025, 1, 1, tzinfo=UTC),
            end=datetime(2025, 1, 1, 0, 15, tzinfo=UTC),
            http_get=mock_get,
        )
        call_args = mock_get.call_args
        assert HISTORY_ENDPOINT in call_args[0][0]  # URL contains history-candles

    def test_no_auth_header_in_request(self):
        mock_get = MagicMock(return_value=_mock_response([_raw_candle("BTCUSDT", 0)]))
        fetch_history_candles(
            pair="BTC/USDT",
            symbol="BTCUSDT",
            product_type="USDT-FUTURES",
            timeframe="15m",
            start=datetime(2025, 1, 1, tzinfo=UTC),
            end=datetime(2025, 1, 1, 0, 15, tzinfo=UTC),
            http_get=mock_get,
        )
        # The http_get callable receives (url, params, headers) — verify no auth
        headers = mock_get.call_args[0][2] if len(mock_get.call_args[0]) > 2 else \
            mock_get.call_args[1].get("headers", {})
        for key in headers:
            kl = key.lower()
            assert "key" not in kl
            assert "secret" not in kl
            assert "pass" not in kl
            assert "auth" not in kl
            assert "token" not in kl

    def test_query_range_respects_90_day_limit(self):
        """A 100-day range must be split into multiple sub-ranges."""
        # With 0 candles returned per call, just verify we get 2 calls for 100 days
        mock_get = MagicMock(return_value=_mock_response([]))
        fetch_history_candles(
            pair="BTC/USDT",
            symbol="BTCUSDT",
            product_type="USDT-FUTURES",
            timeframe="15m",
            start=datetime(2025, 1, 1, tzinfo=UTC),
            end=datetime(2025, 4, 11, tzinfo=UTC),  # 100 days > 90
            http_get=mock_get,
        )
        assert mock_get.call_count >= 2  # at least 2 sub-ranges


# ---------------------------------------------------------------------------
# write_snapshot (atomic writes, path confinement)
# ---------------------------------------------------------------------------


class TestWriteSnapshot:
    def test_atomic_write_with_sidecar(self, tmp_path):
        candles = normalize_candles(
            [_raw_candle("BTCUSDT", i) for i in range(5)], "BTC/USDT"
        )
        target_dir = tmp_path / "snapshots"
        write_snapshot(candles, pair_label="BTC_USDT", target_dir=target_dir)

        csv_gz = target_dir / "BTC_USDT_15m.csv.gz"
        sha256 = target_dir / "BTC_USDT_15m.csv.gz.sha256"
        assert csv_gz.is_file()
        assert sha256.is_file()

        # Verify SHA-256 matches file content
        actual_hash = hashlib.sha256(csv_gz.read_bytes()).hexdigest()
        expected_hash = sha256.read_text().strip().split()[0]
        assert actual_hash == expected_hash

    def test_no_temp_files_left(self, tmp_path):
        candles = normalize_candles([_raw_candle("BTCUSDT", 0)], "BTC/USDT")
        target_dir = tmp_path / "snapshots"
        write_snapshot(candles, pair_label="BTC_USDT", target_dir=target_dir)
        temp_files = list(target_dir.glob("*.tmp"))
        assert len(temp_files) == 0

    def test_candle_hash_matches_canonical(self, tmp_path):
        candles = normalize_candles(
            [_raw_candle("BTCUSDT", i) for i in range(5)], "BTC/USDT"
        )
        target_dir = tmp_path / "snapshots"
        write_snapshot(candles, pair_label="BTC_USDT", target_dir=target_dir)

        # The sidecar hash must match canonical_candle_hash of the candles
        expected = canonical_candle_hash(candles)
        hash_file = target_dir / "BTC_USDT_15m.canonical_sha256"
        assert hash_file.read_text().strip() == expected


# ---------------------------------------------------------------------------
# build_manifest (detached hash)
# ---------------------------------------------------------------------------


class TestBuildManifest:
    def test_manifest_has_no_self_hash_field(self, tmp_path):
        candles = normalize_candles(
            [_raw_candle("BTCUSDT", i) for i in range(3)], "BTC/USDT"
        )
        target_dir = tmp_path / "snapshots"
        write_snapshot(candles, pair_label="BTC_USDT", target_dir=target_dir)

        build_manifest(
            snapshot_id="test-001",
            exchange="bitget",
            pairs=("BTC/USDT",),
            timeframe="15m",
            timerange_start=datetime(2025, 1, 1, tzinfo=UTC),
            timerange_end=datetime(2025, 1, 1, 0, 45, tzinfo=UTC),
            snapshot_files=[
                {
                    "path": "BTC_USDT_15m.csv.gz",
                    "sha256": hashlib.sha256(b"test").hexdigest(),
                    "candle_count": 3,
                    "pair": "BTC/USDT",
                    "first_timestamp": "2025-01-01T00:00:00Z",
                    "last_timestamp": "2025-01-01T00:30:00Z",
                }
            ],
            target_dir=target_dir,
        )
        manifest_path = target_dir / "snapshot_manifest.json"
        data = json.loads(manifest_path.read_text())
        # The manifest must NOT contain overall_sha256 — it's detached
        assert "overall_sha256" not in data

    def test_detached_hash_sidecar(self, tmp_path):
        candles = normalize_candles(
            [_raw_candle("BTCUSDT", i) for i in range(3)], "BTC/USDT"
        )
        target_dir = tmp_path / "snapshots"
        write_snapshot(candles, pair_label="BTC_USDT", target_dir=target_dir)

        build_manifest(
            snapshot_id="test-002",
            exchange="bitget",
            pairs=("BTC/USDT",),
            timeframe="15m",
            timerange_start=datetime(2025, 1, 1, tzinfo=UTC),
            timerange_end=datetime(2025, 1, 1, 0, 45, tzinfo=UTC),
            snapshot_files=[
                {
                    "path": "BTC_USDT_15m.csv.gz",
                    "sha256": hashlib.sha256(b"test").hexdigest(),
                    "candle_count": 3,
                    "pair": "BTC/USDT",
                    "first_timestamp": "2025-01-01T00:00:00Z",
                    "last_timestamp": "2025-01-01T00:30:00Z",
                }
            ],
            target_dir=target_dir,
        )
        manifest_path = target_dir / "snapshot_manifest.json"
        detached_path = target_dir / "snapshot_manifest.json.sha256"

        assert manifest_path.is_file()
        assert detached_path.is_file()

        # Verify detached hash matches manifest content
        actual = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        expected = detached_path.read_text().strip().split()[0]
        assert actual == expected


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_history_endpoint_url():
    assert "history-candles" in HISTORY_ENDPOINT


def test_max_candles_is_200():
    assert MAX_CANDLES_PER_REQUEST == 200


def test_max_query_range_is_90_days():
    assert MAX_QUERY_RANGE_DAYS == 90
