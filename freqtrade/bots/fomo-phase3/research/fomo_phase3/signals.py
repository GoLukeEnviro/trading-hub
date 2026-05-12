"""
Signal engine — vectorized indicator computation for FOMO strategy.
v2-derived. Pure pandas vectorized operations.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from fomo_phase3.config import StrategyConfig


def zscore(series: pd.Series, window: int) -> pd.Series:
    mean = series.rolling(window).mean()
    std = series.rolling(window).std()
    return (series - mean) / std.replace(0, np.nan)


def compute_signals(df: pd.DataFrame, cfg: StrategyConfig) -> pd.DataFrame:
    out = df.copy()

    prev_close = out["close"].shift(1)
    tr = pd.concat(
        [
            out["high"] - out["low"],
            (out["high"] - prev_close).abs(),
            (out["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    out["atr"] = tr.ewm(alpha=1 / cfg.atr_period, adjust=False).mean()
    out["z_vol"] = zscore(out["volume"], cfg.z_window)
    out["oi_delta"] = out["oi"].pct_change()
    out["z_oi"] = zscore(out["oi_delta"], cfg.z_window)
    out["fomo"] = (out["z_vol"] * 0.6) + (out["z_oi"] * 0.4)
    out["roc3"] = out["close"].pct_change(3)

    ema_fast = out["close"].ewm(span=cfg.ema_fast, adjust=False).mean()
    ema_slow = out["close"].ewm(span=cfg.ema_slow, adjust=False).mean()
    out["trend_slope"] = (ema_fast - ema_slow) / out["atr"].replace(0, np.nan)

    out["price_delta"] = out["close"].pct_change()
    out["oi_price_alignment"] = out["oi_delta"].rolling(cfg.oi_alignment_window).corr(
        out["price_delta"]
    )

    funding_mean = out["funding_rate"].rolling(cfg.funding_residual_window).mean()
    out["funding_residual"] = out["funding_rate"] - funding_mean
    out["prev_close"] = prev_close
    out["movement"] = out["close"].diff().abs()

    return out


def add_entry_signals(df: pd.DataFrame, cfg: StrategyConfig) -> pd.DataFrame:
    out = df.copy()

    required_signal_cols = [
        "atr",
        "fomo",
        "roc3",
        "trend_slope",
        "oi_price_alignment",
        "funding_residual",
        "movement",
    ]

    valid = out[required_signal_cols].notna().all(axis=1)
    valid &= out["atr"] > 0
    valid &= out["movement"] >= cfg.noise_atr_pct * out["atr"]

    long_mask = (
        valid
        & (out["fomo"] > cfg.fomo_entry)
        & (out["roc3"] > cfg.roc_long)
        & (out["trend_slope"] >= cfg.trend_min)
        & (out["oi_price_alignment"] >= cfg.oi_price_alignment_thresh)
        & (out["funding_residual"] <= cfg.funding_residual_thresh_long)
    )

    short_mask = (
        valid
        & (out["fomo"] > cfg.fomo_entry)
        & (out["roc3"] < cfg.roc_short)
        & (out["trend_slope"] <= -cfg.trend_min)
        & (out["oi_price_alignment"] <= -cfg.oi_price_alignment_thresh)
        & (out["funding_residual"] >= cfg.funding_residual_thresh_short)
    )

    out["entry_signal"] = 0
    out.loc[long_mask, "entry_signal"] = 1
    out.loc[short_mask, "entry_signal"] = -1

    return out


def prepare_strategy_dataframe(df: pd.DataFrame, cfg: StrategyConfig) -> pd.DataFrame:
    signaled = compute_signals(df, cfg)
    return add_entry_signals(signaled, cfg)
