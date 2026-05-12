"""
Walk-forward window generation — fold creation and time slicing.
v2-derived. DateOffset-based, no fragile exact timestamp matching.
"""

from __future__ import annotations

import pandas as pd

from fomo_phase3.config import WalkForwardFold


def make_walk_forward_windows(
    df: pd.DataFrame,
    train_months: int = 8,
    test_months: int = 3,
    step_months: int = 4,
) -> list[WalkForwardFold]:
    timestamps = pd.to_datetime(df["timestamp"], utc=True)
    data_start = timestamps.min().normalize()
    data_end = timestamps.max().normalize()

    folds: list[WalkForwardFold] = []
    fold_start = data_start
    fold_num = 1

    while True:
        train_start = fold_start
        train_end = train_start + pd.DateOffset(months=train_months) - pd.Timedelta(seconds=1)
        test_start = train_end + pd.Timedelta(seconds=1)
        test_end = test_start + pd.DateOffset(months=test_months) - pd.Timedelta(seconds=1)

        if test_end > data_end:
            break

        folds.append(
            WalkForwardFold(
                fold=fold_num,
                train_start=pd.Timestamp(train_start),
                train_end=pd.Timestamp(train_end),
                test_start=pd.Timestamp(test_start),
                test_end=pd.Timestamp(test_end),
            )
        )
        fold_num += 1
        fold_start = fold_start + pd.DateOffset(months=step_months)

    return folds


def slice_by_time(df: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    ts = pd.to_datetime(df["timestamp"], utc=True)
    mask = (ts >= start) & (ts <= end)
    return df.loc[mask].reset_index(drop=True)
