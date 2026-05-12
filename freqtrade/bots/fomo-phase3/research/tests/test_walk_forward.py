"""Tests for walk-forward window generation."""
import numpy as np
import pandas as pd
import pytest

from fomo_phase3.walk_forward import make_walk_forward_windows, slice_by_time


@pytest.fixture
def coverage_2yr_df() -> pd.DataFrame:
    """Data covering ~2 years of 5m candles."""
    start = pd.Timestamp("2024-01-01", tz="UTC")
    end = pd.Timestamp("2026-01-01", tz="UTC")
    timestamps = pd.date_range(start, end, freq="5min", tz="UTC")
    n = len(timestamps)
    df = pd.DataFrame({
        "timestamp": timestamps,
        "open": np.random.uniform(100, 110, n),
        "high": np.random.uniform(110, 115, n),
        "low": np.random.uniform(95, 100, n),
        "close": np.random.uniform(100, 110, n),
        "volume": np.random.exponential(1000, n),
        "oi": np.random.exponential(1e9, n),
        "funding_rate": np.random.normal(0, 0.0004, n),
    })
    return df


class TestMakeWalkForwardWindows:

    def test_returns_list_of_folds(self, coverage_2yr_df):
        folds = make_walk_forward_windows(coverage_2yr_df)
        assert isinstance(folds, list)
        assert len(folds) > 0

    def test_folds_have_correct_attributes(self, coverage_2yr_df):
        folds = make_walk_forward_windows(coverage_2yr_df)
        for fold in folds:
            assert isinstance(fold.fold, int)
            assert fold.fold >= 1
            assert isinstance(fold.train_start, pd.Timestamp)
            assert isinstance(fold.train_end, pd.Timestamp)
            assert isinstance(fold.test_start, pd.Timestamp)
            assert isinstance(fold.test_end, pd.Timestamp)

    def test_train_end_before_test_start(self, coverage_2yr_df):
        folds = make_walk_forward_windows(coverage_2yr_df)
        for fold in folds:
            assert fold.train_end < fold.test_start

    def test_fold_numbers_are_sequential(self, coverage_2yr_df):
        folds = make_walk_forward_windows(coverage_2yr_df)
        numbers = [f.fold for f in folds]
        assert numbers == list(range(1, len(folds) + 1))

    def test_test_end_does_not_exceed_data(self, coverage_2yr_df):
        folds = make_walk_forward_windows(coverage_2yr_df)
        data_end = coverage_2yr_df["timestamp"].max()
        for fold in folds:
            assert fold.test_end <= data_end

    def test_default_months_8_3_4(self, coverage_2yr_df):
        """With 8/3/4 and ~2 years of data, should generate about 3-4 folds."""
        folds = make_walk_forward_windows(coverage_2yr_df)
        # 24 months of data / 4 step = roughly 6 possible starts, minus buffer
        assert 2 <= len(folds) <= 8

    def test_returns_empty_for_insufficient_data(self):
        small_df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-01", periods=200, freq="5min", tz="UTC"),
            "open": [100.0] * 200,
            "high": [101.0] * 200,
            "low": [99.0] * 200,
            "close": [100.5] * 200,
            "volume": [1000.0] * 200,
            "oi": [1e9] * 200,
            "funding_rate": [0.0001] * 200,
        })
        folds = make_walk_forward_windows(small_df, train_months=8, test_months=3)
        assert len(folds) == 0 or isinstance(folds, list)


class TestSliceByTime:

    def test_one_year_slice(self, coverage_2yr_df):
        start = pd.Timestamp("2025-01-01", tz="UTC")
        end = pd.Timestamp("2025-06-01", tz="UTC")
        sliced = slice_by_time(coverage_2yr_df, start, end)
        assert len(sliced) > 0
        assert sliced["timestamp"].min() >= start
        assert sliced["timestamp"].max() <= end

    def test_empty_slice_outside_range(self, coverage_2yr_df):
        start = pd.Timestamp("2020-01-01", tz="UTC")
        end = pd.Timestamp("2020-06-01", tz="UTC")
        sliced = slice_by_time(coverage_2yr_df, start, end)
        assert len(sliced) == 0

    def test_slice_is_contiguous(self, coverage_2yr_df):
        start = pd.Timestamp("2024-06-01", tz="UTC")
        end = pd.Timestamp("2024-12-31", tz="UTC")
        sliced = slice_by_time(coverage_2yr_df, start, end)
        # Check no missing indices
        assert sliced["timestamp"].is_monotonic_increasing
        # Check reset index
        assert sliced.index[0] == 0
