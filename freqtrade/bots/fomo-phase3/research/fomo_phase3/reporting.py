"""
Reporting — write summary, config, trades, equity curve, walk-forward to disk.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from fomo_phase3.config import StrategyConfig
from fomo_phase3.metrics import BacktestResult


def write_reports(
    outdir: str | Path,
    summary: dict,
    cfg: StrategyConfig,
    result: BacktestResult | None = None,
    fold_summary: pd.DataFrame | None = None,
) -> None:
    path = Path(outdir)
    path.mkdir(parents=True, exist_ok=True)

    (path / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    cfg_dict = {k: v for k, v in cfg.__dict__.items() if not k.startswith("_")}
    (path / "config.json").write_text(
        json.dumps(cfg_dict, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    if result is not None and result.trades_df is not None:
        result.trades_df.to_csv(path / "trades.csv", index=False)

    if result is not None and result.equity_curve is not None:
        result.equity_curve.to_csv(path / "equity_curve.csv", index=False)

    if fold_summary is not None:
        fold_summary.to_csv(path / "walk_forward_summary.csv", index=False)
