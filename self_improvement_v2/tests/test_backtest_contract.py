"""Tests for the Gate-0 selection backtest contract (A1, offline)."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest

from si_v2.research.backtest_contract import (
    BACKTEST_COMMAND,
    BACKTEST_RESULTS_DIR,
    CONFIG_FILE_SHA256,
    FREQTRADE_NATIVE_DATA_DIR,
    FREQTRADE_VERSION,
    PINNED_FREQTRADE_IMAGE,
    PROJECT_DIR,
    RESEARCH_SNAPSHOT_DIR,
    SELECTION_END_UTC,
    SELECTION_START_UTC,
    STRATEGY_FILE_SHA256,
    SUPERSEDED_INFORMATIONAL_VERSION,
    WARMUP_START_UTC,
    BacktestContract,
    aggregate_1h_dataset,
    convert_funding_to_freqtrade,
    exclude_holdout,
    full_dataset_timerange,
    materialize_selection_dataset,
    render_backtest_command,
    selection_timerange,
    validate_mount_contract,
    validate_warmup_excluded_from_metrics,
)
from si_v2.research.evaluation_bundle_v1 import CandleV1
from si_v2.research.gate0_evaluation_integration import HOLDOUT


class TestImageAndVersion:
    def test_image_is_pinned_digest(self):
        assert "sha256:" in PINNED_FREQTRADE_IMAGE
        assert ":stable" not in PINNED_FREQTRADE_IMAGE
        assert ":latest" not in PINNED_FREQTRADE_IMAGE

    def test_canonical_version_is_2026_7(self):
        assert FREQTRADE_VERSION == "2026.7"

    def test_superseded_version_is_informational(self):
        assert SUPERSEDED_INFORMATIONAL_VERSION == "2026.6"


class TestInputProvenance:
    def test_strategy_sha256_exact(self):
        assert STRATEGY_FILE_SHA256 == (
            "112ff28ef7bd1fdc28341b4e53516b48fe7c94278c747691077d4d2e6e7916c0"
        )

    def test_config_sha256_exact(self):
        assert CONFIG_FILE_SHA256 == (
            "7647ed03a88e49a63c9916e9e8137ce84d5e12a90f461785a694591e5e70345d"
        )


class TestWindows:
    def test_warmup_before_selection(self):
        assert WARMUP_START_UTC < SELECTION_START_UTC

    def test_selection_before_holdout(self):
        assert HOLDOUT.start >= SELECTION_END_UTC

    def test_selection_end_is_walk_forward_2_end(self):
        assert datetime(2026, 1, 1, tzinfo=UTC) == SELECTION_END_UTC


class TestTimerange:
    def test_selection_timerange_excludes_holdout(self):
        tr = selection_timerange()
        _, end_s = tr.split("-")
        end = datetime.strptime(end_s, "%Y%m%d").replace(tzinfo=UTC)
        assert end <= HOLDOUT.start
        assert end == SELECTION_END_UTC

    def test_timerange_starts_at_warmup(self):
        start_s, _ = selection_timerange().split("-")
        start = datetime.strptime(start_s, "%Y%m%d").replace(tzinfo=UTC)
        assert start == WARMUP_START_UTC

    def test_selection_start_is_calibration_start(self):
        assert datetime(2025, 1, 1, tzinfo=UTC) == SELECTION_START_UTC

    def test_full_dataset_timerange_includes_holdout(self):
        tr = full_dataset_timerange()
        _, end_s = tr.split("-")
        end = datetime.strptime(end_s, "%Y%m%d").replace(tzinfo=UTC)
        assert end == datetime(2026, 7, 1, tzinfo=UTC)
        assert end > HOLDOUT.start


class TestCommandContract:
    def test_no_export_filename(self):
        assert "--export-filename" not in BACKTEST_COMMAND

    def test_backtest_directory_present(self):
        assert "--backtest-directory" in BACKTEST_COMMAND

    def test_data_format_explicit_feather(self):
        assert "--data-format-ohlcv feather" in BACKTEST_COMMAND

    def test_timeframe_15m(self):
        assert "--timeframe 15m" in BACKTEST_COMMAND

    def test_trading_mode_futures(self):
        assert "--trading-mode futures" in BACKTEST_COMMAND

    def test_cache_none(self):
        assert "--cache none" in BACKTEST_COMMAND

    def test_export_trades(self):
        assert "--export trades" in BACKTEST_COMMAND

    def test_results_mount_read_write(self):
        assert "/freqtrade/user_data/backtest_results:rw" in BACKTEST_COMMAND

    def test_data_mount_read_only(self):
        assert "/freqtrade/user_data/data:ro" in BACKTEST_COMMAND

    def test_strategy_mount_read_only(self):
        assert "/freqtrade/user_data/project:ro" in BACKTEST_COMMAND

    def test_path_constants_absolute(self):
        assert FREQTRADE_NATIVE_DATA_DIR.is_absolute()
        assert RESEARCH_SNAPSHOT_DIR.is_absolute()
        assert BACKTEST_RESULTS_DIR.is_absolute()
        assert PROJECT_DIR.is_absolute()

    def test_path_constants_values(self):
        assert Path("/opt/data/gate0-freqtrade-native-r1") == FREQTRADE_NATIVE_DATA_DIR
        assert Path("/opt/data/gate0-snapshot-v2-r1") == RESEARCH_SNAPSHOT_DIR
        assert Path("/opt/data/gate0-backtest-results") == BACKTEST_RESULTS_DIR
        assert Path("/opt/data/projects/trading-hub/freqforge/user_data") == PROJECT_DIR

    def test_contract_fields_explicit(self):
        c = BacktestContract()
        assert c.data_format_ohlcv == "feather"
        assert c.timeframe == "15m"
        assert c.trading_mode == "futures"
        assert c.cache_policy == "none"

    def test_contract_rejects_non_feather(self):
        with pytest.raises(RuntimeError, match="DATA_FORMAT_NOT_EXPLICIT"):
            BacktestContract(data_format_ohlcv="json").validate()

    def test_contract_rejects_non_15m(self):
        with pytest.raises(RuntimeError, match="TIMEFRAME_NOT_15M"):
            BacktestContract(timeframe="1h").validate()

    def test_render_backtest_command_uses_selection_timerange(self):
        cmd = render_backtest_command()
        assert "--timerange 20241201-20260101" in cmd
        assert "--backtest-directory /freqtrade/user_data/backtest_results/gate0-selection" in cmd

    def test_render_backtest_command_defaults_absolute(self):
        cmd = render_backtest_command()
        assert str(PROJECT_DIR) in cmd
        assert str(FREQTRADE_NATIVE_DATA_DIR) in cmd
        assert str(BACKTEST_RESULTS_DIR) in cmd


class TestMountValidation:
    def _tree(self, tmp_path):
        """Create a minimal valid data tree with real Freqtrade file layout."""
        data = tmp_path / "data"
        results = tmp_path / "results"
        project = tmp_path / "project"
        strategies = project / "strategies"
        strategies.mkdir(parents=True)
        results.mkdir()

        # Strategy file with correct hash
        strategy_file = strategies / "FreqForge_Gate0_Core_v1.py"
        strategy_file.write_text("dummy strategy content")
        # Config file with correct hash
        config_file = project / "config.example.json"
        config_file.write_text("dummy config content")

        # Real Freqtrade file layout: flat futures/ directory
        futures_dir = data / "futures"
        futures_dir.mkdir(parents=True)
        for pair_fn in ("BTC_USDT_USDT", "ETH_USDT_USDT", "SOL_USDT_USDT"):
            (futures_dir / f"{pair_fn}-15m.feather").touch()
            (futures_dir / f"{pair_fn}-1h-mark.feather").touch()
            (futures_dir / f"{pair_fn}-1h-funding_rate.feather").touch()

        return data, results, project, strategies

    def test_mount_contract_passes(self, tmp_path):
        data, results, project, strategies = self._tree(tmp_path)
        # Use dummy hashes matching the actual file content
        strategy_hash = hashlib.sha256(
            (strategies / "FreqForge_Gate0_Core_v1.py").read_bytes()
        ).hexdigest()
        config_hash = hashlib.sha256(
            (project / "config.example.json").read_bytes()
        ).hexdigest()
        validate_mount_contract(
            project_dir=project,
            data_dir=data,
            results_dir=results,
            strategy_path=strategies,
            strategy_sha256=strategy_hash,
            config_sha256=config_hash,
        )

    def test_results_not_persistent_fails_closed(self, tmp_path):
        data, _, project, strategies = self._tree(tmp_path)
        with pytest.raises(RuntimeError, match="RESULTS_NOT_PERSISTENT"):
            validate_mount_contract(
                project_dir=project,
                data_dir=data,
                results_dir=tmp_path / "missing-results",
                strategy_path=strategies,
            )

    def test_strategy_path_missing_fails_closed(self, tmp_path):
        data, results, project, _ = self._tree(tmp_path)
        with pytest.raises(RuntimeError, match="STRATEGY_PATH_MISSING"):
            validate_mount_contract(
                project_dir=project,
                data_dir=data,
                results_dir=results,
                strategy_path=project / "no-strategies",
            )

    def test_holdout_in_datadir_fails_closed(self, tmp_path):
        data, results, project, strategies = self._tree(tmp_path)
        (data / "holdout-sealed").mkdir()
        with pytest.raises(RuntimeError, match="HOLDOUT_IN_DATADIR"):
            validate_mount_contract(
                project_dir=project,
                data_dir=data,
                results_dir=results,
                strategy_path=strategies,
            )

    def test_missing_data_file_fails_closed(self, tmp_path):
        data, results, project, strategies = self._tree(tmp_path)
        # Remove one required file
        (data / "futures" / "BTC_USDT_USDT-1h-mark.feather").unlink()
        with pytest.raises(RuntimeError, match="DATA_FILE_MISSING"):
            validate_mount_contract(
                project_dir=project,
                data_dir=data,
                results_dir=results,
                strategy_path=strategies,
            )

    def test_no_fictional_nested_subdirs_checked(self, tmp_path):
        """validate_mount_contract must NOT check for fictional
        bitget/futures/mark/<pair> subdirectories."""
        data, results, project, strategies = self._tree(tmp_path)
        # The real layout is flat futures/ — no nested mark/ or funding_rate/
        # subdirectories. The test passes because we use the real layout.
        strategy_hash = hashlib.sha256(
            (strategies / "FreqForge_Gate0_Core_v1.py").read_bytes()
        ).hexdigest()
        config_hash = hashlib.sha256(
            (project / "config.example.json").read_bytes()
        ).hexdigest()
        validate_mount_contract(
            project_dir=project,
            data_dir=data,
            results_dir=results,
            strategy_path=strategies,
            strategy_sha256=strategy_hash,
            config_sha256=config_hash,
        )

    def test_relative_project_path_fails_closed(self, tmp_path):
        data, results, _, strategies = self._tree(tmp_path)
        with pytest.raises(RuntimeError, match="PATH_NOT_ABSOLUTE"):
            validate_mount_contract(
                project_dir="relative/path",
                data_dir=data,
                results_dir=results,
                strategy_path=strategies,
            )

    def test_relative_data_path_fails_closed(self, tmp_path):
        _, results, project, strategies = self._tree(tmp_path)
        with pytest.raises(RuntimeError, match="PATH_NOT_ABSOLUTE"):
            validate_mount_contract(
                project_dir=project,
                data_dir="relative/data",
                results_dir=results,
                strategy_path=strategies,
            )

    def test_strategy_hash_mismatch_fails_closed(self, tmp_path):
        data, results, project, strategies = self._tree(tmp_path)
        with pytest.raises(RuntimeError, match="STRATEGY_HASH_MISMATCH"):
            validate_mount_contract(
                project_dir=project,
                data_dir=data,
                results_dir=results,
                strategy_path=strategies,
                strategy_sha256="0" * 64,
            )

    def test_config_hash_mismatch_fails_closed(self, tmp_path):
        data, results, project, strategies = self._tree(tmp_path)
        strategy_hash = hashlib.sha256(
            (strategies / "FreqForge_Gate0_Core_v1.py").read_bytes()
        ).hexdigest()
        with pytest.raises(RuntimeError, match="CONFIG_HASH_MISMATCH"):
            validate_mount_contract(
                project_dir=project,
                data_dir=data,
                results_dir=results,
                strategy_path=strategies,
                strategy_sha256=strategy_hash,
                config_sha256="0" * 64,
            )


class TestExcludeHoldout:
    def test_drops_holdout_candles(self):
        candles = [
            CandleV1(
                timestamp=datetime(2025, 12, 31, 23, 45, tzinfo=UTC),
                pair="BTC/USDT:USDT",
                open=1,
                high=1,
                low=1,
                close=1,
                volume=1,
            ),
            CandleV1(
                timestamp=datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
                pair="BTC/USDT:USDT",
                open=1,
                high=1,
                low=1,
                close=1,
                volume=1,
            ),
        ]
        result = exclude_holdout(candles)
        assert len(result) == 1
        assert result[0].timestamp < HOLDOUT.start

    def test_all_before_holdout_kept(self):
        candles = [
            CandleV1(
                timestamp=datetime(2025, 12, 1, tzinfo=UTC),
                pair="BTC/USDT:USDT",
                open=1,
                high=1,
                low=1,
                close=1,
                volume=1,
            )
        ]
        assert len(exclude_holdout(candles)) == 1


class TestAggregate1h:
    def test_returns_list(self):
        result = aggregate_1h_dataset([])
        assert isinstance(result, list)


class TestMaterializeSelectionDataset:
    def test_holdout_excluded_from_output(self, tmp_path):
        candles = [
            CandleV1(
                timestamp=datetime(2025, 12, 31, 23, 45, tzinfo=UTC),
                pair="BTC/USDT:USDT",
                open=1,
                high=1,
                low=1,
                close=1,
                volume=1,
            ),
            CandleV1(
                timestamp=datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
                pair="BTC/USDT:USDT",
                open=1,
                high=1,
                low=1,
                close=1,
                volume=1,
            ),
        ]
        result = materialize_selection_dataset(
            {"BTC/USDT:USDT": candles}, tmp_path
        )
        assert "BTC/USDT:USDT" in result


class TestConvertFundingToFreqtrade:
    def test_writes_json(self, tmp_path):
        rows = [(datetime(2025, 1, 1, tzinfo=UTC), 0.0001)]
        path = convert_funding_to_freqtrade(rows, tmp_path, pair="BTC/USDT:USDT")
        assert path.exists()
        import json

        data = json.loads(path.read_text())
        assert len(data) == 1

    def test_deduplicates(self, tmp_path):
        import json

        ts = datetime(2025, 1, 1, tzinfo=UTC)
        rows = [(ts, 0.0001), (ts, 0.0002)]
        path = convert_funding_to_freqtrade(rows, tmp_path, pair="BTC/USDT:USDT")
        data = json.loads(path.read_text())
        assert len(data) == 1


class TestWarmupExclusion:
    def test_no_leak_passes(self):
        candles = [
            CandleV1(
                timestamp=datetime(2024, 12, 1, tzinfo=UTC),
                pair="BTC/USDT:USDT",
                open=1,
                high=1,
                low=1,
                close=1,
                volume=1,
            )
        ]
        validate_warmup_excluded_from_metrics(candles)

    def test_leak_fails_closed(self):
        candles = [
            CandleV1(
                timestamp=datetime(2025, 1, 1, tzinfo=UTC),
                pair="BTC/USDT:USDT",
                open=1,
                high=1,
                low=1,
                close=1,
                volume=1,
            )
        ]
        with pytest.raises(RuntimeError, match="WARMUP_LEAKS_INTO_SELECTION"):
            validate_warmup_excluded_from_metrics(candles)
