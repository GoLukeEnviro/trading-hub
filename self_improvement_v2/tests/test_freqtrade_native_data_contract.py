"""Tests for the Freqtrade-native Bitget data contract (A1, offline)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from si_v2.research.freqtrade_native_data_contract import (
    AUX_CANDLE_TYPES,
    AUX_TIMEFRAMES,
    CONTAINER_REPORTED_VERSION,
    DATA_FORMAT_OHLCV,
    EXCHANGE,
    FULL_TIMERANGE_END,
    FULL_TIMERANGE_START,
    IMAGE_DIGEST,
    MAIN_CANDLE_TYPES,
    MAIN_TIMEFRAME,
    MARGIN_MODE,
    PAIR_DIR_KEYS,
    PAIRS,
    PINNED_IMAGE,
    REQUIRED_COVERAGE,
    SELECTION_TIMERANGE_END,
    TRADING_MODE,
    NativeDataFile,
    coverage_line,
    full_timerange,
    pair_dir_key,
    parse_coverage_line,
    render_download_command,
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

    def test_container_version_informational(self):
        assert CONTAINER_REPORTED_VERSION == "2026.7"


class TestTimeranges:
    def test_full_timerange(self):
        assert full_timerange() == "20241201-20260701"

    def test_selection_timerange_ends_before_holdout(self):
        assert selection_timerange() == "20241201-20260101"

    def test_selection_view_before_holdout(self):
        end = datetime(2026, 1, 1, tzinfo=UTC)
        assert end == SELECTION_TIMERANGE_END
        assert FULL_TIMERANGE_START < SELECTION_TIMERANGE_END < FULL_TIMERANGE_END


class TestPairKeys:
    def test_pair_dir_key(self):
        assert pair_dir_key("BTC/USDT:USDT") == "btc_usdt:usdt"
        assert pair_dir_key("ETH/USDT:USDT") == "eth_usdt:usdt"
        assert pair_dir_key("SOL/USDT:USDT") == "sol_usdt:usdt"

    def test_pair_dir_keys_tuple(self):
        assert PAIR_DIR_KEYS == (
            "btc_usdt:usdt",
            "eth_usdt:usdt",
            "sol_usdt:usdt",
        )


class TestRenderDownloadCommand:
    def test_contains_exact_image_digest(self):
        cmd = render_download_command()
        assert "freqtradeorg/freqtrade@sha256:50720a4af314a812be2cfbf5cc6331c63e9332b06f3f4372241f54bc61a35486" in cmd

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
        assert "15m" not in cmd
        assert "futures" not in cmd.split("--candle-types")[1].split("\\")[0]

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


class TestCoverageParser:
    def test_parse_valid_line(self):
        line = coverage_line("btc_usdt:usdt", "15m", "futures",
                             "2024-12-01T00:00:00Z", "2026-06-30T23:45:00Z")
        parsed = parse_coverage_line(line)
        assert parsed == {
            "pair": "btc_usdt:usdt",
            "timeframe": "15m",
            "candle_type": "futures",
            "first": "2024-12-01T00:00:00Z",
            "last": "2026-06-30T23:45:00Z",
        }

    def test_parse_ignores_non_coverage(self):
        assert parse_coverage_line("freqtrade INFO - some log") is None

    def test_parse_rejects_malformed(self):
        with pytest.raises(ValueError, match="MALFORMED_COVERAGE_LINE"):
            parse_coverage_line(
                "freqtrade_native_coverage btc_usdt:usdt 15m futures "
                "2024-12-01T00:00:00Z"
            )


class TestCoverageValidation:
    def _full_coverage(self) -> dict:
        coverage: dict[str, dict[str, dict[str, dict[str, str]]]] = {}
        for ct, tf_map in REQUIRED_COVERAGE.items():
            coverage[ct] = {}
            for tf, window in tf_map.items():
                coverage[ct][tf] = {}
                for key in PAIR_DIR_KEYS:
                    coverage[ct][tf][key] = {
                        "first": window["from"],
                        "last": window["to"],
                    }
        return coverage

    def test_full_coverage_passes(self):
        validate_coverage(self._full_coverage())

    def test_missing_pair_fails_closed(self):
        cov = self._full_coverage()
        del cov["futures"]["15m"]["btc_usdt:usdt"]
        with pytest.raises(RuntimeError, match="COVERAGE_MISSING"):
            validate_coverage(cov)

    def test_late_start_fails_closed(self):
        cov = self._full_coverage()
        cov["futures"]["15m"]["btc_usdt:usdt"]["first"] = "2024-12-02T00:00:00Z"
        with pytest.raises(RuntimeError, match="COVERAGE_START_LATE"):
            validate_coverage(cov)

    def test_early_end_fails_closed(self):
        cov = self._full_coverage()
        cov["futures"]["15m"]["btc_usdt:usdt"]["last"] = "2026-06-01T00:00:00Z"
        with pytest.raises(RuntimeError, match="COVERAGE_END_EARLY"):
            validate_coverage(cov)

    def test_funding_incomplete_fails_closed(self):
        cov = self._full_coverage()
        # funding_rate starts 1 day late — beyond one funding period grace
        cov["funding_rate"]["1h"]["eth_usdt:usdt"]["first"] = "2024-12-02T00:00:00Z"
        with pytest.raises(RuntimeError, match="COVERAGE_START_LATE"):
            validate_coverage(cov)

    def test_100_rows_cannot_pass_full_range_gate(self):
        # A dataset covering only ~100 funding rows (~33 days) can never
        # satisfy the 19-month coverage window.
        cov = self._full_coverage()
        cov["funding_rate"]["1h"] = {
            key: {
                "first": "2026-05-28T00:00:00Z",
                "last": "2026-06-30T23:00:00Z",
            }
            for key in PAIR_DIR_KEYS
        }
        with pytest.raises(
            RuntimeError,
            match=r"COVERAGE_START_LATE|COVERAGE_END_EARLY",
        ):
            validate_coverage(cov)


class TestNativeFileHash:
    def test_missing_file_fails_closed(self, tmp_path):
        f = NativeDataFile("bitget/futures/btc_usdt:usdt/15m.feather")
        with pytest.raises(RuntimeError, match="DATA_FILE_MISSING"):
            f.validate_hash(tmp_path)

    def test_hash_match_passes(self, tmp_path):
        import hashlib

        rel = "bitget/futures/btc_usdt:usdt/15m.feather"
        full = tmp_path / rel
        full.parent.mkdir(parents=True)
        full.write_bytes(b"payload")
        digest = hashlib.sha256(b"payload").hexdigest()
        NativeDataFile(rel, digest).validate_hash(tmp_path)

    def test_hash_mismatch_fails_closed(self, tmp_path):
        rel = "bitget/futures/btc_usdt:usdt/15m.feather"
        full = tmp_path / rel
        full.parent.mkdir(parents=True)
        full.write_bytes(b"payload")
        with pytest.raises(RuntimeError, match="HASH_MISMATCH"):
            NativeDataFile(rel, "0" * 64).validate_hash(tmp_path)
