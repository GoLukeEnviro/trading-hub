"""Tests for signal engine: compute_signals, add_entry_signals, prepare_strategy_dataframe."""
import numpy as np
import pandas as pd
import pytest

from fomo_phase3.config import StrategyConfig
from fomo_phase3.signals import (
    add_entry_signals,
    compute_signals,
    prepare_strategy_dataframe,
    zscore,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def cfg() -> StrategyConfig:
    return StrategyConfig()


@pytest.fixture
def sample_df() -> pd.DataFrame:
    """Generate enough data for signal computation (600 5m candles)."""
    n = 600
    base = pd.Timestamp("2024-01-01", tz="UTC")
    np.random.seed(42)
    prices = 50000 + np.cumsum(np.random.normal(0, 50, n))
    prices = np.maximum(prices, 100)  # floor

    df = pd.DataFrame({
        "timestamp": [base + pd.Timedelta(minutes=5 * i) for i in range(n)],
        "open": prices * 0.999,
        "high": prices * 1.004,
        "low": prices * 0.996,
        "close": prices,
        "volume": np.abs(np.random.exponential(1000, n)),
        "oi": np.abs(1e9 + np.cumsum(np.random.normal(0, 1e6, n))),
        "funding_rate": np.random.normal(0, 0.0004, n),
    })
    return df


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestZscore:

    def test_zscore_returns_near_zero_for_constant_series(self):
        """Z-score of constant series is all NaN (std=0)."""
        series = pd.Series([100] * 100)
        z = zscore(series, 20)
        assert z.isna().all()  # std=0 -> NaN is correct behaviour

    def test_zscore_nan_during_warmup(self):
        series = pd.Series(np.random.normal(0, 1, 100))
        z = zscore(series, 50)
        assert z.iloc[:49].isna().all()
        assert z.iloc[50:].notna().any()

    def test_zscore_handles_zero_std(self):
        """Z-score of constant series is all NaN (std=0)."""
        series = pd.Series([1.0] * 100)
        z = zscore(series, 20)
        assert z.isna().all()  # std=0 -> NaN is correct behaviour


class TestComputeSignals:

    def test_returns_required_columns(self, sample_df, cfg):
        result = compute_signals(sample_df, cfg)
        required = ["atr", "z_vol", "z_oi", "fomo", "roc3", "trend_slope",
                     "oi_price_alignment", "funding_residual", "prev_close", "movement"]
        for col in required:
            assert col in result.columns, f"Missing column: {col}"

    def test_atr_is_positive(self, sample_df, cfg):
        result = compute_signals(sample_df, cfg)
        assert (result["atr"].iloc[50:] > 0).all()

    def test_fomo_uses_60_40_weight(self, sample_df, cfg):
        result = compute_signals(sample_df, cfg)
        expected = 0.6 * result["z_vol"] + 0.4 * result["z_oi"]
        pd.testing.assert_series_equal(result["fomo"], expected, check_dtype=False, check_names=False)

    def test_nan_during_warmup(self, sample_df, cfg):
        result = compute_signals(sample_df, cfg)
        # atr needs atr_period; z_vol needs z_window; alignment needs oi_alignment_window
        max_warmup = max(cfg.atr_period, cfg.z_window, cfg.oi_alignment_window, cfg.funding_residual_window)
        warmup_nans = result.iloc[:max_warmup][["atr", "fomo", "oi_price_alignment"]].isna().sum()
        assert warmup_nans.sum() > 0  # some should be NaN in warmup

    def test_no_infinite_values(self, sample_df, cfg):
        result = compute_signals(sample_df, cfg)
        numeric_cols = result.select_dtypes(include=[np.number]).columns
        assert not np.isinf(result[numeric_cols]).any().any()


class TestAddEntrySignals:

    def test_returns_entry_signal_column(self, sample_df, cfg):
        signaled = compute_signals(sample_df, cfg)
        result = add_entry_signals(signaled, cfg)
        assert "entry_signal" in result.columns

    def test_entry_signal_values_are_01_or_minus1(self, sample_df, cfg):
        signaled = compute_signals(sample_df, cfg)
        result = add_entry_signals(signaled, cfg)
        valid_values = result["entry_signal"].dropna().unique()
        for v in valid_values:
            assert v in (0, 1, -1), f"Unexpected entry_signal value: {v}"

    def test_no_entry_during_all_nan_warmup(self, sample_df, cfg):
        result = prepare_strategy_dataframe(sample_df, cfg)
        max_warmup = max(cfg.atr_period, cfg.z_window, cfg.oi_alignment_window, cfg.funding_residual_window)
        warmup_signals = result["entry_signal"].iloc[:max_warmup]
        assert (warmup_signals == 0).all(), "No entries should occur during warmup"

    def test_noise_filter_blocks_small_moves(self, sample_df, cfg):
        """If movement is below noise_atr_pct * atr, entry should be blocked."""
        result = prepare_strategy_dataframe(sample_df, cfg)
        # After warmup, find rows where movement < noise_atr_pct * atr
        post_warmup = result.iloc[300:].copy()
        small_move = post_warmup["movement"] < cfg.noise_atr_pct * post_warmup["atr"]
        # No entries on those rows
        assert (post_warmup.loc[small_move, "entry_signal"] == 0).all()


class TestPrepareStrategyDataframe:

    def test_returns_dataframe_with_all_columns(self, sample_df, cfg):
        result = prepare_strategy_dataframe(sample_df, cfg)
        assert isinstance(result, pd.DataFrame)
        assert "entry_signal" in result.columns
        assert "atr" in result.columns
        assert len(result) == len(sample_df)
