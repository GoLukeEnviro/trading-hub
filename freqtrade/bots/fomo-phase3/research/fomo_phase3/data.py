"""
Data validation and CSV loading for FOMO research.
v2-derived. Fixes applied:
- F3: volume_fill_method controls ffill vs drop policy.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from fomo_phase3.config import StrategyConfig

REQUIRED_COLUMNS = ("timestamp", "open", "high", "low", "close", "volume", "oi", "funding_rate")


def load_market_csv(path: str | Path, timestamp_col: str = "timestamp") -> pd.DataFrame:
    csv_path = Path(path)
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    df = pd.read_csv(csv_path)
    if timestamp_col != "timestamp":
        df = df.rename(columns={timestamp_col: "timestamp"})

    return validate_and_prepare_dataframe(df)


def validate_and_prepare_dataframe(
    df: pd.DataFrame,
    volume_fill: str = "drop",
) -> pd.DataFrame:
    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    out = df.loc[:, list(REQUIRED_COLUMNS)].copy()
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True, errors="coerce")

    numeric_columns = ["open", "high", "low", "close", "volume", "oi", "funding_rate"]
    for col in numeric_columns:
        out[col] = pd.to_numeric(out[col], errors="coerce")

    out = out.dropna(subset=["timestamp", "open", "high", "low", "close"])
    out = out.sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)

    # OI and funding_rate: forward-fill allowed with gap reporting.
    out["oi"] = out["oi"].ffill()
    out["funding_rate"] = out["funding_rate"].ffill()

    # Volume: policy configurable (F3 fix).
    if volume_fill == "ffill":
        out["volume"] = out["volume"].ffill()
    else:
        # drop any rows where volume is NaN/0 after coercion
        mask = (out["volume"] > 0) | (out["volume"].isna() == False)  # noqa: E712
        out = out.loc[mask].copy()

    out = out.dropna(subset=list(REQUIRED_COLUMNS)).reset_index(drop=True)

    if len(out) < 500:
        raise ValueError(
            f"Not enough rows after cleaning. Need at least 500 5m candles. "
            f"Got {len(out)} after dropna."
        )

    bad_prices = (out[["open", "high", "low", "close"]] <= 0).any(axis=1)
    if bad_prices.any():
        raise ValueError(f"Found non-positive OHLC prices in {int(bad_prices.sum())} rows.")

    return out


def count_missing_candles(
    df: pd.DataFrame,
    timeframe_minutes: int = 5,
) -> dict:
    """Report missing candle gaps and coverage percentage."""
    if df.empty:
        return {"total_rows": 0, "missing_gaps": 0, "coverage_pct": 0.0}

    timestamps = pd.to_datetime(df["timestamp"], utc=True)
    expected_range = pd.date_range(
        start=timestamps.min(),
        end=timestamps.max(),
        freq=f"{timeframe_minutes}min",
        tz="UTC",
    )
    present = timestamps.isin(expected_range).sum()
    total = len(expected_range)
    return {
        "total_rows": len(df),
        "expected_candles": total,
        "present_candles": int(present),
        "missing_candles": total - int(present),
        "coverage_pct": round(float(present / total * 100) if total > 0 else 0, 2),
    }
