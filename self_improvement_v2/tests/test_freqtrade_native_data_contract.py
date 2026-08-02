"""Tests for the Freqtrade-native Bitget data contract (A1, offline)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from si_v2.research.freqtrade_native_data_contract import (
    AUX_CANDLE_TYPES,
    AUX_TIMEFRAMES,
    DATA_FORMAT_OHLCV,
    EXCHANGE,
    FULL_TIMERANGE_END,
    FULL_TIMERANGE_START,
    IMAGE_DIGEST,
    MAIN_CANDLE_TYPES,
    MAIN_TIMEFRAME,
    MARGIN_MODE,
    PAIRS,
    PAIR_FILENAMES,
    PINNED_IMAGE,
    REQUIRED_COVERAGE,
    SELECTION_TIMERANGE_END,
    SUPERSEDED_INFORMATIONAL_VERSION,
    TRADING_MODE,
    FREQTRADE_VERSION,
    InventoryEntry,
    NativeDataFile,
    _pair_data_filename,
    full_timerange,
    pair_to_filename,
    parse_inventory,
    rebuild_pair_from_filename,
    render_download_command,
    render_inventory_command,
    render_list_data_command,
    selection_timerange,
    validate_coverage,
)


class TestImmutableConstants:
    def test_image_digest_exact(self):
        assert IMAGE_DIGEST == (
            "sha256:50720a4af314a812be2cfbf5cc6331c63e9332b06f3f4372241f54bc61a35486"
        )
        assert PINNED_IMAGE == (
            "freqtradeorg/freqtrade@sha256:"
            "50720a4af314a812be2cfbf5cc6331c63e9332b06f3f4372241f54bc61a35486"
        )

    def test_canonical_version_is_2026_7(self):
        assert FREQTRADE_VERSION == "2026.7"

    def test_superseded_version_is_informational_only(self):
        assert SUPERSEDED_INFORMATIONAL_VERSION == "2026.6"

    def test_exchange_and_modes(self):
        assert EXCHANGE == "bitget"
        assert TRADING_MODE == "futures"
        assert MARGIN_MODE == "isolated"

    def test_pairs_exact(self):
        assert PAIRS == (
            "BTC/USDT:USDT",
            "ETH/USDT:USDT",
            "SOL/USDT:USDT",
        )

    def test_timeframes_and_candle_types(self):
        assert MAIN_TIMEFRAME == "15m"
        assert AUX_TIMEFRAMES == ("1h",)
        assert MAIN_CANDLE_TYPES == ("futures",)
        assert AUX_CANDLE_TYPES == ("mark", "funding_rate")

    def test_data_format_feather(self):
        assert DATA_FORMAT_OHLCV == "feather"


class TestTimeranges:
    def test_full_timerange(self):
        assert full_timerange() == "20241201-20260701"

    def test_selection_timerange_ends_before_holdout(self):
        assert selection_timerange() == "20241201-20260101"

    def test_selection_view_before_holdout(self):
        end = datetime(2026, 1, 1, tzinfo=UTC)
        assert SELECTION_TIMERANGE_END == end
        assert FULL_TIMERANGE_START < SELECTION_TIMERANGE_END < FULL_TIMERANGE_END


class TestPairFilenameContract:
    """Real Freqtrade upstream pair_to_filename / rebuild_pair_from_filename."""

    def test_pair_to_filename_btc(self):
        assert pair_to_filename("BTC/USDT:USDT") == "BTC_USDT_USDT"

    def test_pair_to_filename_eth(self):
        assert pair_to_filename("ETH/USDT:USDT") == "ETH_USDT_USDT"

    def test_pair_to_filename_sol(self):
        assert pair_to_filename("SOL/USDT:USDT") == "SOL_USDT_USDT"

    def test_pair_filenames_tuple(self):
        assert PAIR_FILENAMES == (
            "BTC_USDT_USDT",
            "ETH_USDT_USDT",
            "SOL_USDT_USDT",
        )

    def test_rebuild_roundtrip(self):
        for pair in PAIRS:
            assert rebuild_pair_from_filename(pair_to_filename(pair)) == pair

    def test_no_colon_in_filename(self):
        for fn in PAIR_FILENAMES:
            assert ":" not in fn

    def test_no_slash_in_filename(self):
        for fn in PAIR_FILENAMES:
            assert "/" not in fn


class TestPairDataFilename:
    """Real Freqtrade _pair_data_filename — flat futures/ layout."""

    def test_futures_15m_filename(self):
        p = _pair_data_filename("BTC/USDT:USDT", "15m", "futures")
        assert p == Path("futures/BTC_USDT_USDT-15m.feather")

    def test_mark_1h_filename(self):
        p = _pair_data_filename("BTC/USDT:USDT", "1h", "mark")
        assert p == Path("futures/BTC_USDT_USDT-1h-mark.feather")

    def test_funding_rate_1h_filename(self):
        p = _pair_data_filename("BTC/USDT:USDT", "1h", "funding_rate")
        assert p == Path("futures/BTC_USDT_USDT-1h-funding_rate.feather")

    def test_flat_layout_no_nested_pair_subdir(self):
        p = _pair_data_filename("ETH/USDT:USDT", "15m", "futures")
        # Must NOT be futures/eth_usdt_usdt/15m.feather or similar
        assert str(p) == "futures/ETH_USDT_USDT-15m.feather"

    def test_no_fictional_mark_subdir(self):
        p = _pair_data_filename("SOL/USDT:USDT", "1h", "mark")
        assert "mark/" not in str(p)
        assert str(p) == "futures/SOL_USDT_USDT-1h-mark.feather"

    def test_no_fictional_funding_subdir(self):
        p = _pair_data_filename("SOL/USDT:USDT", "1h", "funding_rate")
        assert "funding_rate/" not in str(p)
        assert str(p) == "futures/SOL_USDT_USDT-1h-funding_rate.feather"

    def test_timeframe_to_file_1mo(self):
        p = _pair_data_filename("BTC/USDT:USDT", "1M", "futures")
        assert "1Mo" in str(p)


class TestRenderDownloadCommand:
    def test_contains_exact_image_digest(self):
        cmd = render_download_command()
        assert "sha256:50720a4af314a812be2cfbf5cc6331c63e9332b06f3f4372241f54bc61a35486" in cmd

    def test_contains_exact_pairs(self):
        cmd = render_download_command()
        assert "BTC/USDT:USDT" in cmd
        assert "ETH/USDT:USDT" in cmd
        assert "SOL/USDT:USDT" in cmd

    def test_main_command_uses_15m_futures_only(self):
        cmd = render_download_command(
            candle_types=MAIN_CANDLE_TYPES, timeframes=(MAIN_TIMEFRAME,)
        )
        assert "--timeframes 15m" in cmd
        assert "--candle-types futures" in cmd
        assert "mark" not in cmd
        assert "funding_rate" not in cmd
        assert "1h" not in cmd

    def test_aux_command_uses_1h_mark_funding(self):
        cmd = render_download_command(
            candle_types=AUX_CANDLE_TYPES, timeframes=AUX_TIMEFRAMES
        )
        assert "--timeframes 1h" in cmd
        assert "--candle-types mark funding_rate" in cmd

    def test_timerange_full(self):
        cmd = render_download_command()
        assert "--timerange 20241201-20260701" in cmd

    def test_data_format_feather(self):
        cmd = render_download_command()
        assert "--data-format-ohlcv feather" in cmd

    def test_no_erase_no_prepend_no_dl_trades(self):
        cmd = render_download_command()
        assert "--erase" not in cmd
        assert "--prepend" not in cmd
        assert "--dl-trades" not in cmd

    def test_trading_mode_futures(self):
        cmd = render_download_command()
        assert "--trading-mode futures" in cmd

    def test_no_parallel_download(self):
        cmd = render_download_command()
        assert "--no-parallel-download" in cmd


class TestRenderListData:
    def test_list_data_command_readonly_mount(self):
        cmd = render_list_data_command()
        assert "list-data" in cmd
        assert ":ro" in cmd
        assert "--show-timerange" in cmd
        assert "--data-format-ohlcv feather" in cmd
        assert "--trading-mode futures" in cmd

    def test_list_data_has_image_digest(self):
        cmd = render_list_data_command()
        assert "sha256:50720a4af314a812be2cfbf5cc6331c63e9332b06f3f4372241f54bc61a35486" in cmd


class TestRenderInventoryCommand:
    def test_inventory_command_uses_entrypoint_python3(self):
        cmd = render_inventory_command()
        assert "--entrypoint python3" in cmd
        assert "/inventory.py" in cmd

    def test_inventory_command_readonly_mount(self):
        cmd = render_inventory_command()
        assert ":ro" in cmd


class TestInventoryParser:
    def _sample_inventory(self) -> list[dict]:
        return [
            {
                "pair": "BTC/USDT:USDT",
                "timeframe": "15m",
                "candle_type": "futures",
                "first": "2024-12-01T00:00:00+00:00",
                "last": "2026-06-30T23:45:00+00:00",
                "count": 55552,
                "relative_path": "futures/BTC_USDT_USDT-15m.feather",
                "sha256": "a" * 64,
            },
            {
                "pair": "BTC/USDT:USDT",
                "timeframe": "1h",
                "candle_type": "mark",
                "first": "2024-12-01T00:00:00+00:00",
                "last": "2026-06-30T23:00:00+00:00",
                "count": 13888,
                "relative_path": "futures/BTC_USDT_USDT-1h-mark.feather",
                "sha256": "b" * 64,
            },
            {
                "pair": "BTC/USDT:USDT",
                "timeframe": "1h",
                "candle_type": "funding_rate",
                "first": "2024-12-01T00:00:00+00:00",
                "last": "2026-06-30T23:00:00+00:00",
                "count": 13888,
                "relative_path": "futures/BTC_USDT_USDT-1h-funding_rate.feather",
                "sha256": "c" * 64,
            },
        ]

    def _full_inventory(self) -> list[dict]:
        entries = []
        for pair in PAIRS:
            for ct, tf in [("futures", "15m"), ("mark", "1h"), ("funding_rate", "1h")]:
                entries.append({
                    "pair": pair,
                    "timeframe": tf,
                    "candle_type": ct,
                    "first": "2024-12-01T00:00:00+00:00",
                    "last": "2026-06-30T23:45:00+00:00",
                    "count": 55552,
                    "relative_path": str(_pair_data_filename(pair, tf, ct)),
                    "sha256": "d" * 64,
                })
        return entries

    def test_parse_valid_inventory(self):
        entries = parse_inventory(json.dumps(self._sample_inventory()))
        assert len(entries) == 3
        assert entries[0].pair == "BTC/USDT:USDT"
        assert entries[0].timeframe == "15m"
        assert entries[0].candle_type == "futures"
        assert entries[0].count == 55552
        assert entries[0].relative_path == "futures/BTC_USDT_USDT-15m.feather"

    def test_parse_rejects_non_list(self):
        with pytest.raises(ValueError, match="INVENTORY_NOT_LIST"):
            parse_inventory('{"not": "a list"}')

    def test_roundtrip_inventory_entry(self):
        d = self._sample_inventory()[0]
        entry = InventoryEntry.from_dict(d)
        assert entry.pair == d["pair"]
        assert entry.count == d["count"]
        assert entry.sha256 == d["sha256"]


class TestCoverageValidation:
    def _full_inventory(self) -> list[dict]:
        entries = []
        for pair in PAIRS:
            for ct, tf in [("futures", "15m"), ("mark", "1h"), ("funding_rate", "1h")]:
                entries.append({
                    "pair": pair,
                    "timeframe": tf,
                    "candle_type": ct,
                    "first": "2024-12-01T00:00:00+00:00",
                    "last": "2026-06-30T23:45:00+00:00",
                    "count": 55552,
                    "relative_path": str(_pair_data_filename(pair, tf, ct)),
                    "sha256": "d" * 64,
                })
        return entries
    def test_full_coverage_passes(self):
        entries = [
            InventoryEntry.from_dict(d)
            for d in self._full_inventory()
        ]
        validate_coverage(entries)

    def test_missing_pair_fails_closed(self):
        entries = [
            InventoryEntry.from_dict(d)
            for d in self._full_inventory()
            if not (d["pair"] == "BTC/USDT:USDT" and d["candle_type"] == "futures")
        ]
        with pytest.raises(RuntimeError, match="COVERAGE_MISSING"):
            validate_coverage(entries)

    def test_late_start_fails_closed(self):
        entries = [
            InventoryEntry.from_dict(d)
            for d in self._full_inventory()
        ]
        # Shift BTC futures start 2 days late
        for e in entries:
            if e.pair == "BTC/USDT:USDT" and e.candle_type == "futures":
                object.__setattr__(e, "first", "2024-12-03T00:00:00+00:00")
        with pytest.raises(RuntimeError, match="COVERAGE_START_LATE"):
            validate_coverage(entries)

    def test_early_end_fails_closed(self):
        entries = [
            InventoryEntry.from_dict(d)
            for d in self._full_inventory()
        ]
        for e in entries:
            if e.pair == "BTC/USDT:USDT" and e.candle_type == "futures":
                object.__setattr__(e, "last", "2026-06-01T00:00:00+00:00")
        with pytest.raises(RuntimeError, match="COVERAGE_END_EARLY"):
            validate_coverage(entries)

    def test_funding_incomplete_fails_closed(self):
        entries = [
            InventoryEntry.from_dict(d)
            for d in self._full_inventory()
        ]
        for e in entries:
            if e.pair == "ETH/USDT:USDT" and e.candle_type == "funding_rate":
                object.__setattr__(e, "first", "2024-12-02T00:00:00+00:00")
        with pytest.raises(RuntimeError, match="COVERAGE_START_LATE"):
            validate_coverage(entries)

    def test_270_funding_records_cannot_pass_19_month_gate(self):
        """~270 funding records (~90 days) can never satisfy the 19-month
        coverage window. This is a confirmed A0 finding, not a permanent
        Bitget retention contract."""
        entries = [
            InventoryEntry.from_dict(d)
            for d in self._full_inventory()
        ]
        # Simulate Bitget's ~90-day funding cap
        for e in entries:
            if e.candle_type == "funding_rate":
                object.__setattr__(e, "first", "2026-05-28T00:00:00+00:00")
                object.__setattr__(e, "last", "2026-06-30T23:00:00+00:00")
                object.__setattr__(e, "count", 270)
        with pytest.raises(
            RuntimeError,
            match=r"COVERAGE_START_LATE|COVERAGE_END_EARLY",
        ):
            validate_coverage(entries)

    def test_empty_data_fails_closed(self):
        entries = [
            InventoryEntry.from_dict(d)
            for d in self._full_inventory()
        ]
        for e in entries:
            if e.pair == "SOL/USDT:USDT" and e.candle_type == "mark":
                object.__setattr__(e, "first", None)
                object.__setattr__(e, "last", None)
        with pytest.raises(RuntimeError, match="COVERAGE_EMPTY"):
            validate_coverage(entries)


class TestNativeFileHash:
    def test_missing_file_fails_closed(self, tmp_path):
        f = NativeDataFile("futures/BTC_USDT_USDT-15m.feather")
        with pytest.raises(RuntimeError, match="DATA_FILE_MISSING"):
            f.validate_hash(tmp_path)

    def test_hash_match_passes(self, tmp_path):
        import hashlib

        rel = "futures/BTC_USDT_USDT-15m.feather"
        full = tmp_path / rel
        full.parent.mkdir(parents=True)
        full.write_bytes(b"payload")
        digest = hashlib.sha256(b"payload").hexdigest()
        NativeDataFile(rel, digest).validate_hash(tmp_path)

    def test_hash_mismatch_fails_closed(self, tmp_path):
        rel = "futures/BTC_USDT_USDT-15m.feather"
        full = tmp_path / rel
        full.parent.mkdir(parents=True)
        full.write_bytes(b"payload")
        with pytest.raises(RuntimeError, match="HASH_MISMATCH"):
            NativeDataFile(rel, "0" * 64).validate_hash(tmp_path)
