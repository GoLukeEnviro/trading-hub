#!/usr/bin/env python3
"""
run_optuna.py — Optuna optimization on REAL 5m BTC/USDT:USDT data.
Uses build_5m_dataset.py output with merged OI proxy + funding rate.

Strict original thresholds (fomo_entry=1.8, noise_atr_pct=0.30, etc.).
Min trades gate: 30. Max drawdown constraint: 12%.
"""

import json
import math
import os
import time
import warnings

import numpy as np
import optuna
import pandas as pd

warnings.filterwarnings("ignore", category=FutureWarning)

from fomo_phase3.backtest import backtest
from fomo_phase3.config import StrategyConfig
from fomo_phase3.metrics import BacktestResult

# ── Config ──────────────────────────────────────────────────────────────────
DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "btc_5m.feather")
OUT_DIR = os.path.join(os.path.dirname(__file__), "optuna_results")
os.makedirs(OUT_DIR, exist_ok=True)

# Train on first 50K bars (~173 days at 5m) for speed
# OOS: last 25,000 bars (~87 days at 5m)
TRAIN_BARS = 50_000
OOS_BARS = 25_000
MIN_TRADES = 30
N_TRIALS = 20


# ── Data ────────────────────────────────────────────────────────────────────
def load_data() -> pd.DataFrame:
    """Load the 5m dataset with real OI proxy + funding rate."""
    print(f"[DATA] Loading {DATA_PATH} ...")
    df = pd.read_feather(DATA_PATH)
    n = len(df)
    print(f"[DATA] {n:,} rows, {df['timestamp'].iloc[0]} to {df['timestamp'].iloc[-1]}")

    required = ["timestamp", "open", "high", "low", "close", "volume",
                 "oi", "funding_rate"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing columns: {missing}")
    print(f"[DATA] Columns: {list(df.columns)}")
    print(f"[DATA] OI range: {df['oi'].min():.0f} to {df['oi'].max():.0f}")
    print(f"[DATA] funding range: {df['funding_rate'].min():.8f} to {df['funding_rate'].max():.8f}")
    return df


# ── Scoring ─────────────────────────────────────────────────────────────────
def score_result(r: BacktestResult) -> float:
    """Combined score: Sharpe × log10(1+trades) + PF excess / DD penalty."""
    if r.trades < MIN_TRADES:
        return -9999.0
    dd_penalty = 1.0 + max(0.0, r.max_drawdown_pct / 20.0)
    profit_term = max(0.0, r.profit_factor - 1.0)
    score = r.sharpe * math.log10(1 + r.trades) + profit_term * 5.0
    score = score / dd_penalty
    if math.isnan(score) or math.isinf(score):
        return -9999.0
    return score


# ── Objective ───────────────────────────────────────────────────────────────
def objective(trial: optuna.Trial, df: pd.DataFrame) -> float:
    cfg = StrategyConfig(
        # Signal thresholds — strict ranges around original defaults
        fomo_entry=trial.suggest_float("fomo_entry", 0.8, 3.0),
        roc_long=trial.suggest_float("roc_long", 0.0003, 0.005),
        roc_short=trial.suggest_float("roc_short", -0.005, -0.0003),
        trend_min=trial.suggest_float("trend_min", 0.02, 0.5),
        noise_atr_pct=trial.suggest_float("noise_atr_pct", 0.10, 0.60),
        oi_price_alignment_thresh=trial.suggest_float(
            "oi_price_alignment_thresh", -0.3, 0.5
        ),
        funding_residual_thresh_long=trial.suggest_float(
            "funding_residual_thresh_long", 0.0001, 0.002
        ),
        funding_residual_thresh_short=trial.suggest_float(
            "funding_residual_thresh_short", -0.002, -0.0001
        ),
        # Windows — widened for 5m resolution
        z_window=trial.suggest_int("z_window", 10, 120),
        atr_period=trial.suggest_int("atr_period", 7, 40),
        # Risk
        sl_atr_mult=trial.suggest_float("sl_atr_mult", 1.0, 5.0),
        tp1_atr_mult=trial.suggest_float("tp1_atr_mult", 1.0, 6.0),
        tp2_atr_mult=trial.suggest_float("tp2_atr_mult", 2.0, 8.0),
        tp1_fraction=trial.suggest_float("tp1_fraction", 0.3, 0.8),
        max_bars=trial.suggest_int("max_bars", 12, 48),
        # FOMO exit
        fomo_exit=trial.suggest_float("fomo_exit", 0.0, 1.0),
    )

    try:
        train_end = TRAIN_BARS
        train_df = df.iloc[:train_end].reset_index(drop=True)
        r = backtest(train_df, cfg, initial_equity=10_000.0)
        return score_result(r)
    except Exception:
        return -9999.0


# ── Main ────────────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("FOMO Phase 3 — Optuna Optimization (REAL BTC 5m)")
    print(f"OOS: last {OOS_BARS:,} bars (~{OOS_BARS//288:.0f} days)")
    print(f"Min trades: {MIN_TRADES}")
    print("=" * 60)

    df = load_data()

    # For backtesting: use TRAIN_BARS for training, last OOS_BARS for eval
    n_train = TRAIN_BARS
    print(f"\n[TRAIN] {n_train:,} rows ({df['timestamp'].iloc[0]} to "
          f"{df['timestamp'].iloc[n_train-1]})")
    print(f"[OOS]   {OOS_BARS:,} rows ({df['timestamp'].iloc[-OOS_BARS]} to "
          f"{df['timestamp'].iloc[-1]})")

    optuna.logging.set_verbosity(optuna.logging.WARNING)

    study = optuna.create_study(
        direction="maximize",
        sampler=optuna.samplers.TPESampler(seed=42, n_startup_trials=20),
        study_name="fomo_phase3_v1_5m",
    )

    n_trials = N_TRIALS
    print(f"\n[OPTUNA] Starting {n_trials} trials on {TRAIN_BARS:,} training bars (5m)...")

    progress_path = os.path.join(OUT_DIR, "optuna_progress.log")
    t_start = time.time()
    for i in range(n_trials):
        trial = study.ask()
        val = objective(trial, df)
        study.tell(trial, val)
        if (i + 1) % 5 == 0 or i == 0:
            elapsed = time.time() - t_start
            best = study.best_trial
            rate = (i + 1) / elapsed
            eta = (n_trials - i - 1) / rate if rate > 0 else 0
            msg = f"  Trial {i+1}/{n_trials} — best: {best.value:.2f} (#{best.number}) — {elapsed:.0f}s elapsed, ~{eta:.0f}s remain"
            print(msg, flush=True)
            with open(progress_path, "a") as pf:
                pf.write(msg + "\n")

    best = study.best_trial
    print("\n" + "=" * 60)
    print("BEST TRIAL")
    print(f"  Score: {best.value:.2f}")
    print(f"  Trial #{best.number}")
    print("\n  Best Parameters:")
    for k, v in best.params.items():
        print(f"    {k}: {v}")

    # ── Evaluate best config ──
    best_cfg = StrategyConfig(**best.params)

    print("\n[EVAL] Training set backtest...")
    train_df = df.iloc[:TRAIN_BARS].reset_index(drop=True)
    result_train = backtest(train_df, best_cfg, initial_equity=10_000.0)

    print("[EVAL] OOS backtest...")
    oos_df = df.iloc[-OOS_BARS:].reset_index(drop=True)
    result_oos = backtest(oos_df, best_cfg, initial_equity=10_000.0)

    print("\n" + "-" * 60)
    print("BACKTEST RESULTS (REAL 5m DATA)")
    print(f"  {'Metric':<18} {'Train':<14} {'OOS':<14}")
    print(f"  {'─'*44}")
    print(f"  {'Trades':<18} {result_train.trades:<14} {result_oos.trades:<14}")
    print(f"  {'Return %':<18} {result_train.total_return_pct:<14.2f} {result_oos.total_return_pct:<14.2f}")
    print(f"  {'Max DD %':<18} {result_train.max_drawdown_pct:<14.2f} {result_oos.max_drawdown_pct:<14.2f}")
    print(f"  {'Sharpe':<18} {result_train.sharpe:<14.4f} {result_oos.sharpe:<14.4f}")
    print(f"  {'Profit Factor':<18} {result_train.profit_factor:<14.4f} {result_oos.profit_factor:<14.4f}")
    print(f"  {'Win Rate %':<18} {result_train.win_rate:<14.2f} {result_oos.win_rate:<14.2f}")

    # ── Save results ──
    output = {
        "best_params": best.params,
        "best_score": best.value,
        "train": {
            "trades": result_train.trades,
            "total_return_pct": result_train.total_return_pct,
            "max_drawdown_pct": result_train.max_drawdown_pct,
            "sharpe": result_train.sharpe,
            "profit_factor": result_train.profit_factor,
            "win_rate": result_train.win_rate,
        },
        "oos": {
            "trades": result_oos.trades,
            "total_return_pct": result_oos.total_return_pct,
            "max_drawdown_pct": result_oos.max_drawdown_pct,
            "sharpe": result_oos.sharpe,
            "profit_factor": result_oos.profit_factor,
            "win_rate": result_oos.win_rate,
        },
    }
    result_path = os.path.join(OUT_DIR, "best_cfg.json")
    with open(result_path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\n[SAVED] {result_path}")

    # ── Save equity curves ──
    ec_paths = {}
    for name, result in [("train", result_train), ("oos", result_oos)]:
        if result.equity_curve is not None and not result.equity_curve.empty:
            path = os.path.join(OUT_DIR, f"{name}_equity_curve.csv")
            result.equity_curve.to_csv(path, index=False)
            ec_paths[name] = path
            print(f"[SAVED] {path}")

    print("\n[DONE]")


if __name__ == "__main__":
    main()
