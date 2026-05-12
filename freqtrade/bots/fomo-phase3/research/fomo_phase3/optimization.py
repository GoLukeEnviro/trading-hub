"""
Optimization — Optuna integration for parameter search.
v2-derived. Fixes applied:
- F1/F2: Scoring uses position-aggregated metrics.
- F6: min_trades constraint in scoring.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, replace

import pandas as pd

from fomo_phase3.backtest import backtest
from fomo_phase3.config import StrategyConfig
from fomo_phase3.metrics import position_profit_factor, result_summary
from fomo_phase3.signals import prepare_strategy_dataframe

try:
    import optuna
except ImportError:
    optuna = None


def sample_config(trial: "optuna.Trial", base: StrategyConfig) -> StrategyConfig:
    return replace(
        base,
        fomo_entry=trial.suggest_float("fomo_entry", 1.4, 2.4),
        fomo_exit=trial.suggest_float("fomo_exit", 0.05, 0.6),
        roc_long=trial.suggest_float("roc_long", 0.0006, 0.0020),
        roc_short=trial.suggest_float("roc_short", -0.0020, -0.0006),
        trend_min=trial.suggest_float("trend_min", 0.03, 0.30),
        noise_atr_pct=trial.suggest_float("noise_atr_pct", 0.15, 0.50),
        oi_price_alignment_thresh=trial.suggest_float(
            "oi_price_alignment_thresh", 0.03, 0.30
        ),
        funding_residual_thresh_long=trial.suggest_float(
            "funding_residual_thresh_long", 0.0001, 0.0008
        ),
        funding_residual_thresh_short=trial.suggest_float(
            "funding_residual_thresh_short", -0.0008, -0.0001
        ),
        sl_atr_mult=trial.suggest_float("sl_atr_mult", 1.0, 2.5),
        tp1_atr_mult=trial.suggest_float("tp1_atr_mult", 1.2, 3.0),
        tp2_atr_mult=trial.suggest_float("tp2_atr_mult", 2.5, 6.0),
        trail_atr_mult=trial.suggest_float("trail_atr_mult", 0.4, 1.4),
        max_bars=trial.suggest_int("max_bars", 12, 48),
    )


def score_result_for_optimization(result, cfg: StrategyConfig) -> float:
    position_count = result.trades

    if position_count < cfg.min_trades_per_test:
        return -999.0

    if result.max_drawdown_pct > cfg.max_drawdown_constraint * 100.0:
        return -999.0 - result.max_drawdown_pct

    # Use position-aggregated PF if available
    pf = position_profit_factor(result.trades_df)
    if not math.isfinite(pf):
        pf_component = 3.0
    else:
        pf_component = min(pf, 3.0)

    return (
        result.sharpe
        + 0.25 * pf_component
        + 0.02 * result.total_return_pct
        - 0.05 * result.max_drawdown_pct
    )


def optimize_on_dataframe(
    df: pd.DataFrame,
    base_cfg: StrategyConfig,
    trials: int,
    initial_equity: float,
    seed: int = 42,
) -> StrategyConfig:
    if optuna is None:
        raise RuntimeError("Optuna is not installed. Install with: pip install optuna")

    def objective(trial: "optuna.Trial") -> float:
        cfg = sample_config(trial, base_cfg)
        prepared = prepare_strategy_dataframe(df, cfg)
        result = backtest(prepared, cfg, initial_equity=initial_equity)
        score = score_result_for_optimization(result, cfg)
        return score

    sampler = optuna.samplers.TPESampler(seed=seed)
    study = optuna.create_study(direction="maximize", sampler=sampler)
    study.optimize(objective, n_trials=trials, show_progress_bar=False)

    best = base_cfg
    for key, value in study.best_params.items():
        best = replace(best, **{key: value})
    return best


def run_walk_forward(
    df: pd.DataFrame,
    base_cfg: StrategyConfig,
    trials: int = 100,
    initial_equity: float = 10_000.0,
    optimize: bool = True,
) -> tuple[pd.DataFrame, list]:
    from fomo_phase3.walk_forward import make_walk_forward_windows, slice_by_time

    folds = make_walk_forward_windows(df)
    if not folds:
        raise ValueError("No walk-forward folds could be created from this dataset.")

    rows: list[dict[str, float | int | str]] = []
    results: list = []

    for fold in folds:
        train_df = slice_by_time(df, fold.train_start, fold.train_end)
        test_df = slice_by_time(df, fold.test_start, fold.test_end)

        if len(train_df) < 500 or len(test_df) < 200:
            continue

        cfg = (
            optimize_on_dataframe(train_df, base_cfg, trials, initial_equity)
            if optimize
            else base_cfg
        )

        prepared_test = prepare_strategy_dataframe(test_df, cfg)
        test_result = backtest(prepared_test, cfg, initial_equity=initial_equity)
        results.append(test_result)

        row: dict = {
            "fold": fold.fold,
            "train_start": fold.train_start.date().isoformat(),
            "train_end": fold.train_end.date().isoformat(),
            "test_start": fold.test_start.date().isoformat(),
            "test_end": fold.test_end.date().isoformat(),
        }
        row.update(result_summary(test_result))
        row["cfg"] = json.dumps(asdict(cfg), sort_keys=True)
        rows.append(row)

    return pd.DataFrame(rows), results
