"""
CLI entry point — backtest / optimize / walk-forward modes.
v2-derived.
"""

from __future__ import annotations

import argparse
import json
import sys

from fomo_phase3.config import StrategyConfig
from fomo_phase3.data import load_market_csv
from fomo_phase3.metrics import result_summary
from fomo_phase3.optimization import optimize_on_dataframe, run_walk_forward
from fomo_phase3.signals import prepare_strategy_dataframe


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="FOMO Bitget Strategy System")
    parser.add_argument("--data", required=True, help="CSV with OHLCV + OI + funding_rate")
    parser.add_argument("--timestamp-col", default="timestamp")
    parser.add_argument(
        "--mode",
        choices=["backtest", "walk-forward", "optimize"],
        default="backtest",
    )
    parser.add_argument("--outdir", default="fomo_results")
    parser.add_argument("--initial-equity", type=float, default=10_000.0)
    parser.add_argument("--trials", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    from fomo_phase3.backtest import backtest
    from fomo_phase3.reporting import write_reports

    args = parse_args(argv)
    df = load_market_csv(args.data, timestamp_col=args.timestamp_col)
    cfg = StrategyConfig()

    if args.mode == "backtest":
        prepared = prepare_strategy_dataframe(df, cfg)
        result = backtest(prepared, cfg, initial_equity=args.initial_equity)
        summary = result_summary(result)
        write_reports(args.outdir, summary, cfg, result=result)
        print(json.dumps(summary, indent=2))
        return 0

    if args.mode == "optimize":
        best_cfg = optimize_on_dataframe(
            df,
            cfg,
            trials=args.trials,
            initial_equity=args.initial_equity,
            seed=args.seed,
        )
        prepared = prepare_strategy_dataframe(df, best_cfg)
        result = backtest(prepared, best_cfg, initial_equity=args.initial_equity)
        summary = result_summary(result)
        write_reports(args.outdir, summary, best_cfg, result=result)
        print(json.dumps({"best_cfg": cfg_to_dict(best_cfg), "summary": summary}, indent=2))
        return 0

    fold_summary, _ = run_walk_forward(
        df,
        cfg,
        trials=args.trials,
        initial_equity=args.initial_equity,
        optimize=True,
    )

    aggregate = {
        "folds": int(len(fold_summary)),
        "avg_test_sharpe": float(fold_summary["sharpe"].mean()) if len(fold_summary) else 0.0,
        "avg_test_return_pct": float(fold_summary["total_return_pct"].mean())
        if len(fold_summary)
        else 0.0,
        "max_test_drawdown_pct": float(fold_summary["max_drawdown_pct"].max())
        if len(fold_summary)
        else 0.0,
        "positive_folds": int((fold_summary["total_return_pct"] > 0).sum())
        if len(fold_summary)
        else 0,
    }

    write_reports(args.outdir, aggregate, cfg, fold_summary=fold_summary)
    print(json.dumps(aggregate, indent=2))
    return 0


def cfg_to_dict(cfg: StrategyConfig) -> dict:
    return {k: v for k, v in cfg.__dict__.items() if not k.startswith("_")}


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
