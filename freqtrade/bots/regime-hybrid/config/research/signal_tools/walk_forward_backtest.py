#!/usr/bin/env python3
"""
Rolling walk-forward backtest framework for Freqtrade research strategies.

Runs Freqtrade backtesting over rolling OOS test windows and extracts metrics from
Freqtrade JSON reports inside the generated result ZIP files. No regex parsing.

Default windows:
  train 30d / test 7d / step 7d

Example:
  python3 walk_forward_backtest.py \
    --strategy ResearchRegimeHybridSideAwareV2 \
    --config /freqtrade/config/research/config_regime_hybrid_sideaware_v2.json \
    --timerange 20260301-20260517 \
    --strategy-path /freqtrade/user_data/strategies
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

DATE_RE = re.compile(r"(20\d{2})[-/]?(\d{2})[-/]?(\d{2})")


def parse_yyyymmdd(value: str) -> datetime:
    return datetime.strptime(value, "%Y%m%d").replace(tzinfo=timezone.utc)


def fmt_yyyymmdd(value: datetime) -> str:
    return value.strftime("%Y%m%d")


def parse_timerange(timerange: str) -> tuple[datetime, datetime]:
    if "-" not in timerange:
        raise ValueError(f"timerange must look like YYYYMMDD-YYYYMMDD, got: {timerange}")
    start_s, end_s = timerange.split("-", 1)
    if not start_s or not end_s:
        raise ValueError("open-ended timeranges are not supported for walk-forward; pass explicit start and end")
    return parse_yyyymmdd(start_s), parse_yyyymmdd(end_s)


def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_")


@dataclass
class Window:
    index: int
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime

    @property
    def train_timerange(self) -> str:
        return f"{fmt_yyyymmdd(self.train_start)}-{fmt_yyyymmdd(self.train_end)}"

    @property
    def test_timerange(self) -> str:
        return f"{fmt_yyyymmdd(self.test_start)}-{fmt_yyyymmdd(self.test_end)}"


@dataclass
class WindowResult:
    window: int
    train_period: str
    test_period: str
    status: str
    trades: int = 0
    long_trades: int = 0
    short_trades: int = 0
    winrate: float = 0.0
    profit_factor: float = 0.0
    total_profit_abs: float = 0.0
    total_profit_pct: float = 0.0
    max_drawdown_abs: float = 0.0
    max_drawdown_pct: float = 0.0
    expectancy: float = 0.0
    skipped: bool = False
    reason: str = ""
    result_zip: str = ""


def build_windows(start: datetime, end: datetime, train_days: int, test_days: int, step_days: int) -> list[Window]:
    windows: list[Window] = []
    cursor = start
    idx = 0
    while cursor + timedelta(days=train_days + test_days) <= end:
        train_start = cursor
        train_end = cursor + timedelta(days=train_days)
        test_start = train_end
        test_end = test_start + timedelta(days=test_days)
        windows.append(Window(idx, train_start, train_end, test_start, test_end))
        idx += 1
        cursor += timedelta(days=step_days)
    return windows


def run_command(cmd: list[str], cwd: Optional[Path] = None, timeout: Optional[int] = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=str(cwd) if cwd else None, text=True, capture_output=True, timeout=timeout)


def maybe_run_hyperopt(args: argparse.Namespace, window: Window, output_dir: Path) -> None:
    """Placeholder-capable hyperopt runner for train windows.

    Disabled by default. When enabled, runs a conservative command and writes logs,
    but does not parse/apply parameters automatically. This prevents hidden shadow JSON
    contamination from being silently treated as a valid optimization result.
    """
    if not args.hyperopt:
        return
    log_file = output_dir / f"window_{window.index:03d}_hyperopt.log"
    cmd = [
        args.freqtrade_bin,
        "hyperopt",
        "--config",
        args.config,
        "--strategy",
        args.strategy,
        "--timerange",
        window.train_timerange,
        "--epochs",
        str(args.hyperopt_epochs),
        "--min-trades",
        str(args.hyperopt_min_trades),
    ]
    if args.strategy_path:
        cmd.extend(["--strategy-path", args.strategy_path])
    if args.timeframe:
        cmd.extend(["--timeframe", args.timeframe])
    if args.hyperopt_spaces:
        cmd.extend(["--spaces", *args.hyperopt_spaces.split(",")])

    proc = run_command(cmd, timeout=args.command_timeout)
    log_file.write_text(proc.stdout + "\n--- STDERR ---\n" + proc.stderr, encoding="utf-8")
    if proc.returncode != 0:
        raise RuntimeError(f"hyperopt failed for train window {window.train_timerange}; see {log_file}")


def run_backtest(args: argparse.Namespace, window: Window, output_dir: Path) -> Path:
    bt_dir = output_dir / f"window_{window.index:03d}_{window.test_timerange}"
    if bt_dir.exists():
        shutil.rmtree(bt_dir)
    bt_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        args.freqtrade_bin,
        "backtesting",
        "--config",
        args.config,
        "--strategy",
        args.strategy,
        "--timerange",
        window.test_timerange,
        "--export",
        "trades",
        "--breakdown",
        "day",
        "--backtest-directory",
        str(bt_dir),
    ]
    if args.strategy_path:
        cmd.extend(["--strategy-path", args.strategy_path])
    if args.timeframe:
        cmd.extend(["--timeframe", args.timeframe])
    if args.enable_protections:
        cmd.append("--enable-protections")

    proc = run_command(cmd, timeout=args.command_timeout)
    (bt_dir / "backtest.stdout.log").write_text(proc.stdout, encoding="utf-8")
    (bt_dir / "backtest.stderr.log").write_text(proc.stderr, encoding="utf-8")
    if proc.returncode != 0:
        raise RuntimeError(f"backtest failed for {window.test_timerange}; see {bt_dir}/backtest.stderr.log")

    zips = sorted(bt_dir.glob("*.zip"), key=lambda p: p.stat().st_mtime)
    if not zips:
        raise FileNotFoundError(f"no Freqtrade result ZIP found in {bt_dir}")
    return zips[-1]


def find_strategy_summary(data: dict[str, Any], strategy: str) -> dict[str, Any]:
    strategies = data.get("strategy")
    if not isinstance(strategies, dict) or not strategies:
        return {}
    if strategy in strategies and isinstance(strategies[strategy], dict):
        return strategies[strategy]
    # Fallback for class/file naming differences: use the only strategy if exactly one.
    if len(strategies) == 1:
        only = next(iter(strategies.values()))
        return only if isinstance(only, dict) else {}
    return {}


def load_backtest_summary(result_zip: Path, strategy: str) -> dict[str, Any]:
    with zipfile.ZipFile(result_zip) as zh:
        candidates = [name for name in zh.namelist() if name.endswith(".json") and "meta" not in name and "config" not in name]
        if not candidates:
            raise FileNotFoundError(f"no JSON result inside {result_zip}")
        data = json.loads(zh.read(candidates[0]))
    return find_strategy_summary(data, strategy)


def extract_metrics(summary: dict[str, Any], result_zip: Path, window: Window, min_trades: int) -> WindowResult:
    trades = int(summary.get("total_trades") or len(summary.get("trades", []) or []))
    long_trades = int(summary.get("total_long_trades") or summary.get("long_trades") or 0)
    short_trades = int(summary.get("total_short_trades") or summary.get("short_trades") or 0)
    if (long_trades + short_trades) == 0 and isinstance(summary.get("trades"), list):
        for trade in summary["trades"]:
            if trade.get("is_short"):
                short_trades += 1
            else:
                long_trades += 1

    total_profit_abs = float(summary.get("profit_total_abs") or summary.get("total_profit_abs") or summary.get("profit_abs") or 0.0)
    total_profit_pct = float(summary.get("profit_total") or summary.get("total_profit") or 0.0) * 100.0
    profit_factor = float(summary.get("profit_factor") or 0.0)
    expectancy = float(summary.get("expectancy") or 0.0)
    max_dd_abs = float(summary.get("max_drawdown_abs") or summary.get("max_drawdown_account") or 0.0)
    max_dd_pct_raw = float(summary.get("max_drawdown") or summary.get("max_relative_drawdown") or 0.0)
    max_dd_pct = max_dd_pct_raw * 100.0 if abs(max_dd_pct_raw) <= 1.0 else max_dd_pct_raw

    winrate = float(summary.get("winrate") or 0.0)
    if winrate <= 1.0 and trades > 0:
        winrate *= 100.0

    skipped = trades < min_trades
    reason = f"too_few_trades({trades}<{min_trades})" if skipped else ""
    return WindowResult(
        window=window.index,
        train_period=window.train_timerange,
        test_period=window.test_timerange,
        status="SKIP" if skipped else "OK",
        trades=trades,
        long_trades=long_trades,
        short_trades=short_trades,
        winrate=winrate,
        profit_factor=profit_factor,
        total_profit_abs=total_profit_abs,
        total_profit_pct=total_profit_pct,
        max_drawdown_abs=max_dd_abs,
        max_drawdown_pct=max_dd_pct,
        expectancy=expectancy,
        skipped=skipped,
        reason=reason,
        result_zip=str(result_zip),
    )


def detect_available_timerange(args: argparse.Namespace) -> Optional[str]:
    """Best-effort data timerange detection via `freqtrade list-data --show-timerange`.

    This is intentionally conservative. If parsing fails, the caller should require
    an explicit --timerange.
    """
    cmd = [args.freqtrade_bin, "list-data", "--config", args.config, "--show-timerange"]
    proc = run_command(cmd, timeout=120)
    text = proc.stdout + "\n" + proc.stderr
    dates: list[datetime] = []
    for y, m, d in DATE_RE.findall(text):
        try:
            dates.append(datetime(int(y), int(m), int(d), tzinfo=timezone.utc))
        except ValueError:
            continue
    if len(dates) < 2:
        return None
    return f"{fmt_yyyymmdd(min(dates))}-{fmt_yyyymmdd(max(dates))}"


def write_csv(results: list[WindowResult], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(asdict(results[0]).keys()) if results else list(WindowResult(0, '', '', '').__dict__.keys()))
        writer.writeheader()
        for result in results:
            writer.writerow(asdict(result))


def print_table(results: list[WindowResult]) -> None:
    headers = ["Win", "Test", "Status", "Trades", "L/S", "WR%", "PF", "PnL%", "DD%", "Exp", "Reason"]
    rows = []
    for r in results:
        rows.append([
            str(r.window),
            r.test_period,
            r.status,
            str(r.trades),
            f"{r.long_trades}/{r.short_trades}",
            f"{r.winrate:.1f}",
            f"{r.profit_factor:.2f}",
            f"{r.total_profit_pct:.2f}",
            f"{r.max_drawdown_pct:.2f}",
            f"{r.expectancy:.3f}",
            r.reason,
        ])
    widths = [len(h) for h in headers]
    for row in rows:
        widths = [max(w, len(cell)) for w, cell in zip(widths, row)]
    fmt = "  ".join("{:<" + str(w) + "}" for w in widths)
    print(fmt.format(*headers))
    print(fmt.format(*["-" * w for w in widths]))
    for row in rows:
        print(fmt.format(*row))


def summarize(results: list[WindowResult]) -> str:
    valid = [r for r in results if not r.skipped and r.status == "OK"]
    if not valid:
        return "No valid OOS windows after skip filters."
    pfs = [r.profit_factor for r in valid]
    profits = [r.total_profit_pct for r in valid]
    worst = min(valid, key=lambda r: r.total_profit_pct)
    avg_pf = sum(pfs) / len(pfs)
    avg_profit = sum(profits) / len(profits)
    positive = sum(1 for r in valid if r.total_profit_pct > 0)
    stability = positive / len(valid) * 100.0
    return (
        f"Valid windows: {len(valid)}/{len(results)} | "
        f"Avg OOS PF: {avg_pf:.2f} | Avg OOS Profit: {avg_profit:.2f}% | "
        f"Positive-window stability: {stability:.1f}% | "
        f"Worst window: #{worst.window} {worst.test_period} profit={worst.total_profit_pct:.2f}% PF={worst.profit_factor:.2f}"
    )


def maybe_write_equity_csv(results: list[WindowResult], path: Optional[Path]) -> None:
    if not path:
        return
    equity = 1.0
    rows = []
    for r in results:
        if r.skipped or r.status != "OK":
            continue
        equity *= 1.0 + (r.total_profit_pct / 100.0)
        rows.append({"window": r.window, "test_period": r.test_period, "equity_index": equity})
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["window", "test_period", "equity_index"])
        writer.writeheader()
        writer.writerows(rows)


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rolling walk-forward Freqtrade backtest runner")
    parser.add_argument("--strategy", required=True, help="Freqtrade strategy class name")
    parser.add_argument("--config", required=True, help="Freqtrade config path")
    parser.add_argument("--timerange", help="Full walk-forward range, YYYYMMDD-YYYYMMDD. If omitted, best-effort auto-detect is attempted.")
    parser.add_argument("--strategy-path", help="Optional Freqtrade --strategy-path")
    parser.add_argument("--timeframe", help="Optional Freqtrade --timeframe")
    parser.add_argument("--train-days", type=int, default=30)
    parser.add_argument("--test-days", type=int, default=7)
    parser.add_argument("--step-days", type=int, default=7)
    parser.add_argument("--min-trades", type=int, default=1, help="Skip OOS windows below this trade count")
    parser.add_argument("--output-dir", type=Path, default=Path("/freqtrade/user_data/backtest_results/walk_forward"))
    parser.add_argument("--csv", type=Path, help="CSV output path. Default: output-dir/walk_forward_results_YYYYMMDD.csv")
    parser.add_argument("--equity-csv", type=Path, help="Optional equity-index CSV over valid test windows")
    parser.add_argument("--freqtrade-bin", default="freqtrade")
    parser.add_argument("--command-timeout", type=int, default=1800)
    parser.add_argument("--enable-protections", action="store_true")
    parser.add_argument("--hyperopt", action="store_true", help="Experimental: run hyperopt on each train window before OOS backtest; parameters are not auto-applied")
    parser.add_argument("--hyperopt-epochs", type=int, default=50)
    parser.add_argument("--hyperopt-min-trades", type=int, default=20)
    parser.add_argument("--hyperopt-spaces", default="buy,sell", help="Comma-separated spaces for hyperopt")
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    timerange = args.timerange or detect_available_timerange(args)
    if not timerange:
        print("ERROR: Could not auto-detect data range. Pass --timerange YYYYMMDD-YYYYMMDD.", file=sys.stderr)
        return 2

    start, end = parse_timerange(timerange)
    windows = build_windows(start, end, args.train_days, args.test_days, args.step_days)
    if not windows:
        print("ERROR: No windows generated. Check timerange/train-days/test-days/step-days.", file=sys.stderr)
        return 2

    run_stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = args.csv or (args.output_dir / f"walk_forward_results_{datetime.now(timezone.utc).strftime('%Y%m%d')}.csv")

    print(f"Walk-forward: strategy={args.strategy} config={args.config}")
    print(f"Range={timerange} windows={len(windows)} train={args.train_days}d test={args.test_days}d step={args.step_days}d")
    print(f"Output={args.output_dir} CSV={csv_path}")

    results: list[WindowResult] = []
    for window in windows:
        print(f"\n=== Window {window.index} | train={window.train_timerange} | test={window.test_timerange} ===")
        try:
            maybe_run_hyperopt(args, window, args.output_dir)
            result_zip = run_backtest(args, window, args.output_dir)
            summary = load_backtest_summary(result_zip, args.strategy)
            if not summary:
                raise ValueError("strategy summary missing in Freqtrade JSON report")
            result = extract_metrics(summary, result_zip, window, args.min_trades)
        except Exception as exc:
            result = WindowResult(
                window=window.index,
                train_period=window.train_timerange,
                test_period=window.test_timerange,
                status="ERROR",
                skipped=True,
                reason=str(exc),
            )
        results.append(result)
        print(f"status={result.status} trades={result.trades} pf={result.profit_factor:.2f} profit={result.total_profit_pct:.2f}% reason={result.reason}")

    print("\n=== Walk-forward Results ===")
    print_table(results)
    write_csv(results, csv_path)
    maybe_write_equity_csv(results, args.equity_csv)
    print(f"\nCSV written: {csv_path}")
    if args.equity_csv:
        print(f"Equity CSV written: {args.equity_csv}")
    print(summarize(results))
    return 1 if any(r.status == "ERROR" for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
