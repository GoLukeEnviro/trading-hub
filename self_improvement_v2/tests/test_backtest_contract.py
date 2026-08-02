"""Tests for the reproducible Gate-0 backtest contract (A1)."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from si_v2.research.backtest_contract import (
    BACKTEST_COMMAND,
    BACKTEST_RESULTS_DIR,
    CONFIG_FILE_SHA256,
    FREQTRADE_NATIVE_DATA_DIR,
    PINNED_FREQTRADE_IMAGE,
    RESEARCH_SNAPSHOT_DIR,
    SELECTION_END_UTC,
    SELECTION_START_UTC,
    STRATEGY_FILE_SHA256,
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


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _candle(pair: str, ts: datetime) -> CandleV1:
    return CandleV1(
        pair=pair, timestamp=ts, open=100.0, high=101.0,
        low=99.0, close=100.5, volume=10.0,
    )


class TestImagePin:
    def test_image_has_digest_and_no_moving_tag(self):
        assert PINNED_FREQTRADE_IMAGE.startswith(
            "freqtradeorg/freqtrade@sha256:"
        )
        assert ":stable" not in PINNED_FREQTRADE_IMAGE
        assert ":latest" not in PINNED_FREQTRADE_IMAGE

    def test_contract_validate_accepts_pinned_image(self):
        BacktestContract().validate()

    def test_contract_rejects_moving_tag(self):
        with pytest.raises(RuntimeError, match="IMAGE_NOT_PINNED"):
            BacktestContract(image="freqtradeorg/freqtrade:stable").validate()

    def test_contract_rejects_holdout_in_timerange(self):
        with pytest.raises(RuntimeError, match="HOLDOUT_IN_TIMERANGE"):
            BacktestContract(timerange="20250101-20260701").validate()

    def test_contract_rejects_missing_warmup(self):
        with pytest.raises(RuntimeError, match="WARMUP_MISSING"):
            BacktestContract(timerange="20250101-20260101").validate()


class TestInputProvenance:
    def test_strategy_hash_matches_repo(self, repo_root):
        path = (
            repo_root / "freqforge" / "user_data" / "strategies"
            / "FreqForge_Gate0_Core_v1.py"
        )
        assert hashlib.sha256(path.read_bytes()).hexdigest() == STRATEGY_FILE_SHA256

    def test_config_hash_matches_repo(self, repo_root):
        path = repo_root / "freqforge" / "user_data" / "config.example.json"
        assert hashlib.sha256(path.read_bytes()).hexdigest() == CONFIG_FILE_SHA256


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
        # Download contract covers the full dataset; backtest view excludes
        # holdout separately.
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

    def test_path_constants(self):
        assert Path("/opt/data/gate0-freqtrade-native-r1") == FREQTRADE_NATIVE_DATA_DIR
        assert Path("/opt/data/gate0-snapshot-v2-r1") == RESEARCH_SNAPSHOT_DIR
        assert Path("/opt/data/gate0-backtest-results") == BACKTEST_RESULTS_DIR

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


class TestMountValidation:
    def _tree(self, tmp_path):
        data = tmp_path / "data"
        results = tmp_path / "results"
        project = tmp_path / "project"
        strategies = project / "strategies"
        strategies.mkdir(parents=True)
        results.mkdir()
        # native freqtrade layout: data/bitget/futures/{mark,funding_rate}/<pair>
        for ct in ("mark", "funding_rate"):
            for key in ("btc_usdt:usdt", "eth_usdt:usdt", "sol_usdt:usdt"):
                (data / "bitget" / "futures" / ct / key).mkdir(parents=True)
        return data, results, project

    def test_mount_contract_passes(self, tmp_path):
        data, results, project = self._tree(tmp_path)
        validate_mount_contract(
            project_dir=project, data_dir=data, results_dir=results,
            strategy_path=project / "strategies",
        )

    def test_results_not_persistent_fails_closed(self, tmp_path):
        data, _, project = self._tree(tmp_path)
        with pytest.raises(RuntimeError, match="RESULTS_NOT_PERSISTENT"):
            validate_mount_contract(
                project_dir=project, data_dir=data,
                results_dir=tmp_path / "missing-results",
                strategy_path=project / "strategies",
            )

    def test_strategy_path_missing_fails_closed(self, tmp_path):
        data, results, project = self._tree(tmp_path)
        with pytest.raises(RuntimeError, match="STRATEGY_PATH_MISSING"):
            validate_mount_contract(
                project_dir=project, data_dir=data, results_dir=results,
                strategy_path=project / "no-strategies",
            )

    def test_holdout_in_datadir_fails_closed(self, tmp_path):
        data, results, project = self._tree(tmp_path)
        (data / "holdout-sealed").mkdir()
        with pytest.raises(RuntimeError, match="HOLDOUT_IN_DATADIR"):
            validate_mount_contract(
                project_dir=project, data_dir=data, results_dir=results,
                strategy_path=project / "strategies",
            )

    def test_missing_funding_fails_closed(self, tmp_path):
        data, results, project = self._tree(tmp_path)
        import shutil

        shutil.rmtree(data / "bitget" / "futures" / "funding_rate")
        with pytest.raises(RuntimeError, match="MARK_OR_FUNDING_MISSING"):
            validate_mount_contract(
                project_dir=project, data_dir=data, results_dir=results,
                strategy_path=project / "strategies",
            )


class TestExcludeHoldout:
    def test_drops_holdout_candles(self):
        candles = [
            _candle("BTC/USDT:USDT", datetime(2025, 6, 1, tzinfo=UTC)),
            _candle("BTC/USDT:USDT", datetime(2026, 3, 1, tzinfo=UTC)),
        ]
        kept = exclude_holdout(candles)
        assert len(kept) == 1
        assert kept[0].timestamp.year == 2025

    def test_empty_input(self):
        assert exclude_holdout([]) == []


class TestAggregate1h:
    def test_aggregates_four_15m_to_one_1h(self):
        base = datetime(2025, 1, 1, 0, 0, tzinfo=UTC)
        candles = [
            _candle("BTC/USDT:USDT", base.replace(minute=0)),
            _candle("BTC/USDT:USDT", base.replace(minute=15)),
            _candle("BTC/USDT:USDT", base.replace(minute=30)),
            _candle("BTC/USDT:USDT", base.replace(minute=45)),
        ]
        out = aggregate_1h_dataset(candles)
        assert len(out) == 1
        assert out[0].timestamp == base
        assert out[0].open == 100.0

    def test_drops_incomplete_hour(self):
        base = datetime(2025, 1, 1, 0, 0, tzinfo=UTC)
        candles = [_candle("BTC/USDT:USDT", base.replace(minute=0))]
        assert aggregate_1h_dataset(candles) == []


class TestMaterializeSelection:
    def test_output_excludes_holdout_physically(self, tmp_path):
        sel = _candle("BTC/USDT:USDT", datetime(2025, 6, 1, tzinfo=UTC))
        hold = _candle("BTC/USDT:USDT", datetime(2026, 3, 1, tzinfo=UTC))
        paths = materialize_selection_dataset({"BTC_USDT": [sel, hold]}, tmp_path)
        (pair_path,) = paths.values()
        rows = json.loads(pair_path.read_text())
        assert len(rows) == 1
        assert rows[0][0] < int(HOLDOUT.start.timestamp() * 1000)

    def test_freqtrade_directory_layout(self, tmp_path):
        c = _candle("BTC/USDT:USDT", datetime(2025, 6, 1, tzinfo=UTC))
        paths = materialize_selection_dataset({"BTC_USDT": [c]}, tmp_path)
        out = next(iter(paths.values()))
        assert out.parent.name == "btc_usdt:usdt"
        assert out.name == "15m.json"


class TestFundingAdapter:
    def test_deterministic_sorted_dedup(self, tmp_path):
        base = datetime(2025, 1, 1, 0, 0, tzinfo=UTC)
        rows = [
            (base.replace(hour=2), 0.0001),
            (base.replace(hour=1), 0.0002),
            (base.replace(hour=1), 0.0002),
        ]
        out = convert_funding_to_freqtrade(rows, tmp_path)
        data = json.loads(out.read_text())
        assert data == sorted(data)
        assert len(data) == 2
        assert data[0][1] == 0.0002

    def test_funding_filename(self, tmp_path):
        out = convert_funding_to_freqtrade([], tmp_path)
        assert out.name == "BTC_USDT_USDT.json"
        assert out.parent.name == "futures_funding_rate"


class TestWarmupValidator:
    def test_rejects_warmup_leak(self):
        leak = _candle("BTC/USDT:USDT", datetime(2025, 1, 1, 0, 15, tzinfo=UTC))
        with pytest.raises(RuntimeError, match="WARMUP_LEAKS_INTO_SELECTION"):
            validate_warmup_excluded_from_metrics([leak])

    def test_accepts_pure_warmup(self):
        ok = _candle("BTC/USDT:USDT", datetime(2024, 12, 15, tzinfo=UTC))
        validate_warmup_excluded_from_metrics([ok])
