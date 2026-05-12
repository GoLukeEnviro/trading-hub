"""Tests for data validation module."""
import numpy as np
import pandas as pd
import pytest

from fomo_phase3.data import (
    REQUIRED_COLUMNS,
    count_missing_candles,
    load_market_csv,
    validate_and_prepare_dataframe,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def minimal_valid_df() -> pd.DataFrame:
    """Return a small but valid DataFrame (~600 rows of fake OHLCV+OI+Funding)."""
    n = 600
    base = pd.Timestamp("2024-01-01", tz="UTC")
    timestamps = [base + pd.Timedelta(minutes=5 * i) for i in range(n)]

    np.random.seed(42)
    prices = np.linspace(50000, 51000, n) + np.random.normal(0, 100, n)
    vols = np.random.exponential(1000, n)
    ois = np.random.exponential(1e9, n)
    funds = np.random.normal(0, 0.0005, n)

    df = pd.DataFrame({
        "timestamp": timestamps,
        "open": prices * 0.999,
        "high": prices * 1.005,
        "low": prices * 0.995,
        "close": prices,
        "volume": vols,
        "oi": ois,
        "funding_rate": funds,
    })
    return df


@pytest.fixture
def df_missing_column() -> pd.DataFrame:
    return pd.DataFrame({"timestamp": ["2024-01-01"], "open": [100], "close": [101]})


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestValidateAndPrepareDataframe:

    def test_accepts_valid_dataframe(self, minimal_valid_df):
        result = validate_and_prepare_dataframe(minimal_valid_df)
        assert isinstance(result, pd.DataFrame)
        assert len(result) >= 500  # cleaned length may differ slightly

    def test_raises_on_missing_columns(self, df_missing_column):
        with pytest.raises(ValueError, match="Missing required columns"):
            validate_and_prepare_dataframe(df_missing_column)

    def test_timestamps_are_utc(self, minimal_valid_df):
        result = validate_and_prepare_dataframe(minimal_valid_df)
        assert result["timestamp"].dt.tz is not None
        assert str(result["timestamp"].dt.tz) == "UTC"

    def test_duplicates_removed(self):
        base = pd.Timestamp("2024-01-01", tz="UTC")
        timestamps = [base + pd.Timedelta(minutes=5 * i) for i in range(510)]
        df = pd.DataFrame({
            "timestamp": timestamps + [timestamps[5]],  # duplicate
            "open": [100.0] * 511,
            "high": [101.0] * 511,
            "low": [99.0] * 511,
            "close": [100.5] * 511,
            "volume": [1000.0] * 511,
            "oi": [1e9] * 511,
            "funding_rate": [0.0001] * 511,
        })
        result = validate_and_prepare_dataframe(df)
        assert len(result) == len(set(timestamps))

    def test_raises_on_non_positive_prices(self):
        n = 600
        base = pd.Timestamp("2024-01-01", tz="UTC")
        df = pd.DataFrame({
            "timestamp": [base + pd.Timedelta(minutes=5 * i) for i in range(n)],
            "open": [100.0] * n,
            "high": [101.0] * n,
            "low": [99.0] * n,
            "close": [100.5] * n,
            "volume": [1000.0] * n,
            "oi": [1e9] * n,
            "funding_rate": [0.0001] * n,
        })
        df.loc[300, "close"] = -5  # inject bad price
        with pytest.raises(ValueError, match="non-positive OHLC"):
            validate_and_prepare_dataframe(df)

    def test_raises_on_insufficient_rows(self):
        small = pd.DataFrame({
            "timestamp": [pd.Timestamp("2024-01-01", tz="UTC") + pd.Timedelta(minutes=5 * i) for i in range(10)],
            "open": [100.0] * 10,
            "high": [101.0] * 10,
            "low": [99.0] * 10,
            "close": [100.5] * 10,
            "volume": [1000.0] * 10,
            "oi": [1e9] * 10,
            "funding_rate": [0.0001] * 10,
        })
        with pytest.raises(ValueError, match="at least 500"):
            validate_and_prepare_dataframe(small)

    def test_oi_funding_ffilled(self, minimal_valid_df):
        minimal_valid_df.loc[10, "oi"] = np.nan
        minimal_valid_df.loc[15, "funding_rate"] = np.nan
        result = validate_and_prepare_dataframe(minimal_valid_df)
        assert result["oi"].isna().sum() == 0
        assert result["funding_rate"].isna().sum() == 0

    def test_volume_drop_policy(self, minimal_valid_df):
        """Volume=0 is kept (isna()==False preserves it). Only NaN volume drops."""
        minimal_valid_df.loc[10:15, "volume"] = 0.0
        result = validate_and_prepare_dataframe(minimal_valid_df, volume_fill="drop")
        # zeros are NOT NaN, so they should be kept
        assert len(result) == len(minimal_valid_df)


class TestCountMissingCandles:

    def test_full_coverage(self, minimal_valid_df):
        report = count_missing_candles(minimal_valid_df)
        assert report["coverage_pct"] > 99.0

    def test_empty_df(self):
        report = count_missing_candles(pd.DataFrame())
        assert report["coverage_pct"] == 0.0


class TestLoadMarketCsv:

    def test_raises_on_missing_file(self):
        with pytest.raises(FileNotFoundError, match="not found"):
            load_market_csv("/nonexistent/path.csv")
