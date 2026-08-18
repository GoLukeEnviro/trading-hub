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
    FUNDING_CONTRACT_V2_OPTION,
    FUNDING_COST_MODEL,
    FUNDING_COVERAGE_REQUIRED_FROM,
    FUNDING_COVERAGE_REQUIRED_TO,
    FUNDING_ESTIMATE_CAP,
    FUNDING_ESTIMATE_LABEL,
    FUNDING_ESTIMATE_METHOD,
    FUNDING_HISTORY_LIMIT_DAYS,
    FUNDING_SOURCE,
    FUNDING_STATUS,
    PINNED_FREQTRADE_IMAGE,
    PROJECT_DIR,
    RESEARCH_SNAPSHOT_DIR,
    SELECTION_END_UTC,
    SELECTION_START_UTC,
    STRATEGY_FILE_SHA256,
    SUPERSEDED_INFORMATIONAL_VERSION,
    WARMUP_START_UTC,
    BacktestContract,
    FundingCoverage,
    aggregate_1h_dataset,
    compute_funding_coverage,
    convert_funding_to_freqtrade,
    convert_funding_to_freqtrade_with_coverage,
    convert_funding_to_freqtrade_with_gap_estimate,
    estimate_funding_gap,
    exclude_holdout,
    full_dataset_timerange,
    funding_coverage_report,
    funding_gap_estimate_report,
    materialize_selection_dataset,
    render_backtest_command,
    selection_timerange,
    validate_funding_coverage,
    validate_mount_contract,
    validate_warmup_excluded_from_metrics,
)
from si_v2.research.evaluation_bundle_v1 import CandleV1
from si_v2.research.freqtrade_native_data_contract import REQUIRED_COVERAGE
from si_v2.research.gate0_evaluation_integration import HOLDOUT


def _parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


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


class TestFundingContractConstants:
    """Canonical funding data contract constants (issue #705)."""

    def test_funding_status_documented(self):
        assert FUNDING_STATUS == "INCOMPLETE_CONFIRMED_NATIVE_LIMIT"

    def test_funding_source_is_bitget_rest(self):
        assert FUNDING_SOURCE == "bitget_rest"

    def test_funding_history_limit_days(self):
        assert FUNDING_HISTORY_LIMIT_DAYS == 90

    def test_required_window_matches_contract(self):
        assert datetime(2024, 12, 1, tzinfo=UTC) == FUNDING_COVERAGE_REQUIRED_FROM
        assert datetime(2026, 6, 30, tzinfo=UTC) == FUNDING_COVERAGE_REQUIRED_TO

    def test_required_window_aligned_with_native_contract(self):
        funding_required = REQUIRED_COVERAGE["funding_rate"]["1h"]
        # Native contract uses last-candle timestamps: "from" must equal the
        # midnight boundary; "to" (2026-06-30T23:00:00Z) must cover the day
        # boundary required here (2026-06-30T00:00:00Z).
        assert funding_required["from"] == FUNDING_COVERAGE_REQUIRED_FROM.isoformat().replace("+00:00", "Z")
        assert _parse_ts(funding_required["to"]) >= FUNDING_COVERAGE_REQUIRED_TO

    def test_limit_matches_empirically_confirmed_native_cap(self):
        # #697 A2 run: native CCXT fetch_funding_rate_history returned ~90 days.
        assert FUNDING_HISTORY_LIMIT_DAYS == 90


class TestFundingCoverage:
    def test_full_coverage_passes(self):
        cov = FundingCoverage(
            pair="BTC/USDT:USDT",
            first=datetime(2024, 12, 1, tzinfo=UTC),
            last=datetime(2026, 6, 30, tzinfo=UTC),
            rate_count=13888,
        )
        validate_funding_coverage(cov)

    def test_partial_coverage_fails_closed(self):
        cov = FundingCoverage(
            pair="BTC/USDT:USDT",
            first=datetime(2026, 5, 5, tzinfo=UTC),
            last=datetime(2026, 8, 3, tzinfo=UTC),
            rate_count=101,
        )
        with pytest.raises(RuntimeError, match="FUNDING_COVERAGE_START_LATE"):
            validate_funding_coverage(cov)

    def test_missing_window_fails_closed(self):
        cov = FundingCoverage(
            pair="BTC/USDT:USDT",
            first=None,
            last=None,
            rate_count=0,
        )
        with pytest.raises(RuntimeError, match="FUNDING_COVERAGE_EMPTY"):
            validate_funding_coverage(cov)

    def test_compute_full_coverage(self):
        rows = [
            (datetime(2024, 12, 1, tzinfo=UTC), 0.0001),
            (datetime(2026, 6, 30, tzinfo=UTC), 0.0002),
        ]
        cov = compute_funding_coverage(rows, pair="BTC/USDT:USDT")
        assert cov.rate_count == 2
        assert cov.first == datetime(2024, 12, 1, tzinfo=UTC)
        assert cov.last == datetime(2026, 6, 30, tzinfo=UTC)
        validate_funding_coverage(cov)

    def test_compute_empty(self):
        cov = compute_funding_coverage([], pair="BTC/USDT:USDT")
        assert cov.rate_count == 0
        assert cov.first is None
        assert cov.last is None

    def test_report_dict_shape(self):
        rows = [(datetime(2026, 5, 5, tzinfo=UTC), 0.0001)]
        report = funding_coverage_report(rows, pair="BTC/USDT:USDT")
        assert report["pair"] == "BTC/USDT:USDT"
        assert report["status"] == "INCOMPLETE_CONFIRMED_NATIVE_LIMIT"
        assert report["first"] == "2026-05-05T00:00:00+00:00"
        assert report["required_from"] == "2024-12-01T00:00:00+00:00"
        assert report["required_to"] == "2026-06-30T00:00:00+00:00"
        assert report["source"] == "bitget_rest"
        assert report["coverage_ok"] is False

    def test_report_full_coverage_ok(self):
        rows = [
            (datetime(2024, 12, 1, tzinfo=UTC), 0.0001),
            (datetime(2026, 6, 30, tzinfo=UTC), 0.0002),
        ]
        report = funding_coverage_report(rows, pair="ETH/USDT:USDT")
        assert report["coverage_ok"] is True
        # The dataset-level funding status stays at the confirmed native limit
        # even when a single pair's measured window is complete — per Luke's
        # decision (#697) the canonical dataset remains incomplete.
        assert report["status"] == "INCOMPLETE_CONFIRMED_NATIVE_LIMIT"


class TestConvertFundingWithCoverage:
    def test_full_coverage_writes_json_and_report(self, tmp_path):
        rows = [
            (datetime(2024, 12, 1, tzinfo=UTC), 0.0001),
            (datetime(2026, 6, 30, tzinfo=UTC), 0.0002),
        ]
        out, report = convert_funding_to_freqtrade_with_coverage(
            rows, tmp_path, pair="BTC/USDT:USDT"
        )
        assert out.exists()
        assert report["coverage_ok"] is True

    def test_partial_coverage_fails_closed_no_output(self, tmp_path):
        rows = [(datetime(2026, 5, 5, tzinfo=UTC), 0.0001)]
        with pytest.raises(RuntimeError, match="FUNDING_COVERAGE_START_LATE"):
            convert_funding_to_freqtrade_with_coverage(
                rows, tmp_path, pair="BTC/USDT:USDT"
            )
        # Fail-closed: no partial funding file may be materialized.
        assert not (tmp_path / "futures_funding_rate").exists()

    def test_existing_converter_unchanged_default_behavior(self, tmp_path):
        # Backward compatibility: plain converter writes JSON without validation.
        rows = [(datetime(2026, 5, 5, tzinfo=UTC), 0.0001)]
        path = convert_funding_to_freqtrade(rows, tmp_path, pair="BTC/USDT:USDT")
        assert path.exists()


class TestFundingContractV2OptionA:
    """Funding cost model v2 — Option A (issue #708, ESTIMATED_GAP)."""

    def test_option_a_constants(self):
        assert FUNDING_CONTRACT_V2_OPTION == "A"
        assert FUNDING_COST_MODEL == "ESTIMATED_GAP"
        assert FUNDING_ESTIMATE_METHOD == "PER_PAIR_MEDIAN_CAPPED"
        assert FUNDING_ESTIMATE_CAP == 0.001
        assert FUNDING_ESTIMATE_LABEL == "ESTIMATED"
        # The dataset-level status stays fail-closed (no silent gaps).
        assert FUNDING_STATUS == "INCOMPLETE_CONFIRMED_NATIVE_LIMIT"

    def test_full_coverage_no_estimate_needed(self):
        rows = [
            (datetime(2024, 12, 1, tzinfo=UTC), 0.0001),
            (datetime(2026, 6, 30, tzinfo=UTC), 0.0002),
        ]
        est = estimate_funding_gap(rows, pair="BTC/USDT:USDT")
        assert est.gaps == ()
        assert est.estimate_rate is None
        assert est.uncertainty_band is None

    def test_empty_observed_fails_closed(self):
        with pytest.raises(RuntimeError, match="FUNDING_ESTIMATE_EMPTY"):
            estimate_funding_gap([], pair="BTC/USDT:USDT")

    def test_gap_estimate_derived_from_observed_median(self):
        # Observed window: 2026-05-05 .. 2026-05-07 (gaps on both sides).
        rows = [
            (datetime(2026, 5, 5, tzinfo=UTC), 0.0001),
            (datetime(2026, 5, 6, tzinfo=UTC), 0.0003),
            (datetime(2026, 5, 7, tzinfo=UTC), 0.0002),
        ]
        est = estimate_funding_gap(rows, pair="BTC/USDT:USDT")
        assert est.estimate_rate == 0.0002  # median of observed rates
        assert est.gaps == (
            (datetime(2024, 12, 1, tzinfo=UTC), datetime(2026, 5, 5, tzinfo=UTC)),
            (datetime(2026, 5, 7, tzinfo=UTC), datetime(2026, 6, 30, tzinfo=UTC)),
        )
        assert est.label == "ESTIMATED"
        assert est.uncertainty_band is not None

    def test_gap_estimate_capped(self):
        rows = [
            (datetime(2026, 5, 5, tzinfo=UTC), 0.01),
            (datetime(2026, 5, 6, tzinfo=UTC), 0.02),
        ]
        est = estimate_funding_gap(rows, pair="BTC/USDT:USDT")
        assert est.estimate_rate == FUNDING_ESTIMATE_CAP  # clamped to cap

    def test_gap_estimate_negative_capped(self):
        rows = [
            (datetime(2026, 5, 5, tzinfo=UTC), -0.01),
            (datetime(2026, 5, 6, tzinfo=UTC), -0.02),
        ]
        est = estimate_funding_gap(rows, pair="BTC/USDT:USDT")
        assert est.estimate_rate == -FUNDING_ESTIMATE_CAP

    def test_report_shape(self):
        rows = [(datetime(2026, 5, 5, tzinfo=UTC), 0.0001)]
        report = funding_gap_estimate_report(rows, pair="BTC/USDT:USDT")
        assert report["option"] == "A"
        assert report["cost_model"] == "ESTIMATED_GAP"
        assert report["label"] == "ESTIMATED"
        assert report["estimate_rate"] == 0.0001
        assert report["gaps"] == [
            ["2024-12-01T00:00:00+00:00", "2026-05-05T00:00:00+00:00"],
            ["2026-05-05T00:00:00+00:00", "2026-06-30T00:00:00+00:00"],
        ]
        assert report["uncertainty_band"] is not None
        assert report["status"] == "INCOMPLETE_CONFIRMED_NATIVE_LIMIT"

    def test_conversion_writes_json_and_sidecar(self, tmp_path):
        rows = [
            (datetime(2026, 5, 5, tzinfo=UTC), 0.0001),
            (datetime(2026, 5, 6, tzinfo=UTC), 0.0002),
        ]
        out, report, sidecar = convert_funding_to_freqtrade_with_gap_estimate(
            rows, tmp_path, pair="BTC/USDT:USDT"
        )
        assert out.exists()
        assert sidecar.exists()
        assert report["estimate_rate"] == pytest.approx(0.00015)  # median of two observed
        import json

        data = json.loads(out.read_text())
        # Observed rows + deterministic hourly estimate rows across the gaps.
        assert len(data) > 2
        sidecar_data = json.loads(sidecar.read_text())
        assert sidecar_data["label"] == "ESTIMATED"
        assert sidecar_data["cost_model"] == "ESTIMATED_GAP"

    def test_conversion_empty_fails_closed_no_output(self, tmp_path):
        with pytest.raises(RuntimeError, match="FUNDING_ESTIMATE_EMPTY"):
            convert_funding_to_freqtrade_with_gap_estimate(
                [], tmp_path, pair="BTC/USDT:USDT"
            )
        assert not (tmp_path / "futures_funding_rate").exists()

    def test_conversion_full_coverage_no_estimate_rows(self, tmp_path):
        rows = [
            (datetime(2024, 12, 1, tzinfo=UTC), 0.0001),
            (datetime(2026, 6, 30, tzinfo=UTC), 0.0002),
        ]
        out, report, sidecar = convert_funding_to_freqtrade_with_gap_estimate(
            rows, tmp_path, pair="BTC/USDT:USDT"
        )
        assert report["estimate_rate"] is None
        import json

        data = json.loads(out.read_text())
        assert len(data) == 2  # only observed rows, no estimate rows
        sidecar_data = json.loads(sidecar.read_text())
        assert sidecar_data["gaps"] == []

    def test_estimate_rows_never_presented_as_observed(self, tmp_path):
        # The sidecar must always accompany the JSON so estimate rows are
        # distinguishable from fetched data (no silent gap masking).
        rows = [(datetime(2026, 5, 5, tzinfo=UTC), 0.0001)]
        out, report, sidecar = convert_funding_to_freqtrade_with_gap_estimate(
            rows, tmp_path, pair="BTC/USDT:USDT"
        )
        assert out.exists() and sidecar.exists()
        assert report["label"] == "ESTIMATED"
        assert len(report["gaps"]) == 2
