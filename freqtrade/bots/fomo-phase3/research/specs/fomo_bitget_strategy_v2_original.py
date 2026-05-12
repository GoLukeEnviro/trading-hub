#!/usr/bin/env python3
"""
FOMO Bitget Futures Strategy System

Complete research system for a FOMO/OI/Funding strategy:
- Data validation
- Vectorized signal engine
- Vectorized entry filter generation
- Stateful execution backtester with TP1/TP2, trailing, fees, slippage and latency
- Walk-forward window generation
- Optional Optuna optimization per fold
- CLI reports to CSV/JSON

Expected CSV columns:
timestamp, open, high, low, close, volume, oi, funding_rate

This is research/backtesting software. Start with dry-run only.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import math
import sys
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Callable, Literal

import numpy as np
import pandas as pd

try:
    import optuna
except ImportError:  # pragma: no cover
    optuna = None


Direction = Literal["LONG", "SHORT"]
ExitReason = Literal[
    "SL_HIT",
    "TP1_HIT",
    "TP2_HIT",
    "FOMO_DECAY",
    "TIME_EXIT",
    "END_OF_DATA",
]


@dataclass(frozen=True)
class StrategyConfig:
    # Signal thresholds
    fomo_entry: float = 1.8
    fomo_exit: float = 0.3
    roc_long: float = 0.0012
    roc_short: float = -0.0012
    trend_min: float = 0.1
    noise_atr_pct: float = 0.30
    oi_price_alignment_thresh: float = 0.15
    funding_residual_thresh_long: float = 0.0004
    funding_residual_thresh_short: float = -0.0004

    # Signal windows
    z_window: int = 20
    atr_period: int = 14
    ema_fast: int = 21
    ema_slow: int = 55
    oi_alignment_window: int = 288
    funding_residual_window: int = 288

    # Risk and execution
    risk_per_trade: float = 0.01
    max_notional_pct: float = 1.0
    sl_atr_mult: float = 1.5
    tp1_atr_mult: float = 2.0
    tp2_atr_mult: float = 4.0
    tp1_fraction: float = 0.60
    trail_atr_mult: float = 0.8
    max_bars: int = 24
    taker_fee: float = 0.0006
    slippage_bps: float = 0.001
    latency_candles: int = 1

    # Funding simulation
    simulate_funding: bool = True
    funding_hours_utc: tuple[int, ...] = (0, 8, 16)

    # Backtest safety
    conservative_intrabar: bool = True
    min_trades_per_test: int = 10
    max_drawdown_constraint: float = 0.12

    # Annualization for 5m bars: 365 * 24 * 12
    periods_per_year: int = 105_120


@dataclass
class OpenPosition:
    direction: Direction
    entry_idx: int
    entry_time: pd.Timestamp
    entry_price: float
    qty: float
    remaining_qty: float
    sl: float
    tp1: float
    tp2: float
    atr: float
    bars: int = 0
    tp1_done: bool = False


@dataclass
class Trade:
    entry_time: str
    exit_time: str
    direction: Direction
    exit_reason: ExitReason
    entry_price: float
    exit_price: float
    qty: float
    fraction_of_initial: float
    gross_pnl: float
    fees: float
    net_pnl: float
    equity_after: float
    bars_held: int


@dataclass
class BacktestResult:
    initial_equity: float
    final_equity: float
    total_return_pct: float
    max_drawdown_pct: float
    sharpe: float
    profit_factor: float
    win_rate: float
    trades: int
    closed_legs: int
    funding_pnl: float
    trades_df: pd.DataFrame
    equity_curve: pd.DataFrame


@dataclass
class WalkForwardFold:
    fold: int
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp


REQUIRED_COLUMNS = ("timestamp", "open", "high", "low", "close", "volume", "oi", "funding_rate")


def load_market_csv(path: str | Path, timestamp_col: str = "timestamp") -> pd.DataFrame:
    csv_path = Path(path)
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    df = pd.read_csv(csv_path)
    if timestamp_col != "timestamp":
        df = df.rename(columns={timestamp_col: "timestamp"})

    return validate_and_prepare_dataframe(df)


def validate_and_prepare_dataframe(df: pd.DataFrame) -> pd.DataFrame:
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

    for col in ["volume", "oi", "funding_rate"]:
        out[col] = out[col].ffill()

    out = out.dropna(subset=list(REQUIRED_COLUMNS)).reset_index(drop=True)

    if len(out) < 500:
        raise ValueError("Not enough rows after cleaning. Need at least 500 5m candles.")

    bad_prices = (out[["open", "high", "low", "close"]] <= 0).any(axis=1)
    if bad_prices.any():
        raise ValueError(f"Found non-positive OHLC prices in {int(bad_prices.sum())} rows.")

    return out


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


def is_funding_timestamp(ts: pd.Timestamp, cfg: StrategyConfig) -> bool:
    if not cfg.simulate_funding:
        return False
    utc_ts = ts.tz_convert("UTC") if ts.tzinfo is not None else ts.tz_localize("UTC")
    return utc_ts.hour in cfg.funding_hours_utc and utc_ts.minute == 0


def direction_sign(direction: Direction) -> int:
    return 1 if direction == "LONG" else -1


def apply_entry_slippage(price: float, direction: Direction, cfg: StrategyConfig) -> float:
    sign = direction_sign(direction)
    return price * (1 + sign * cfg.slippage_bps)


def apply_exit_slippage(price: float, direction: Direction, cfg: StrategyConfig) -> float:
    sign = direction_sign(direction)
    return price * (1 - sign * cfg.slippage_bps)


def calc_drawdown(equity: pd.Series) -> float:
    peak = equity.cummax()
    drawdown = (equity / peak) - 1.0
    return abs(float(drawdown.min())) if len(drawdown) else 0.0


def calc_sharpe(equity: pd.Series, periods_per_year: int) -> float:
    returns = equity.pct_change().replace([np.inf, -np.inf], np.nan).dropna()
    if len(returns) < 2:
        return 0.0
    std = float(returns.std())
    if std == 0 or math.isnan(std):
        return 0.0
    return float((returns.mean() / std) * math.sqrt(periods_per_year))


def close_position_leg(
    *,
    pos: OpenPosition,
    exit_time: pd.Timestamp,
    exit_price_raw: float,
    reason: ExitReason,
    qty_to_close: float,
    equity: float,
    cfg: StrategyConfig,
) -> tuple[float, Trade]:
    exit_price = apply_exit_slippage(exit_price_raw, pos.direction, cfg)
    sign = direction_sign(pos.direction)

    gross_pnl = sign * (exit_price - pos.entry_price) * qty_to_close
    entry_notional = abs(pos.entry_price * qty_to_close)
    exit_notional = abs(exit_price * qty_to_close)
    fees = (entry_notional + exit_notional) * cfg.taker_fee
    net_pnl = gross_pnl - fees
    equity_after = equity + net_pnl

    fraction = qty_to_close / pos.qty if pos.qty > 0 else 0.0

    trade = Trade(
        entry_time=pos.entry_time.isoformat(),
        exit_time=exit_time.isoformat(),
        direction=pos.direction,
        exit_reason=reason,
        entry_price=pos.entry_price,
        exit_price=exit_price,
        qty=qty_to_close,
        fraction_of_initial=fraction,
        gross_pnl=gross_pnl,
        fees=fees,
        net_pnl=net_pnl,
        equity_after=equity_after,
        bars_held=pos.bars,
    )
    return equity_after, trade


def open_position_from_signal(
    df: pd.DataFrame,
    signal_idx: int,
    exec_idx: int,
    equity: float,
    cfg: StrategyConfig,
    regime_mult: float,
) -> OpenPosition | None:
    signal = int(df.at[signal_idx, "entry_signal"])
    if signal == 0:
        return None

    direction: Direction = "LONG" if signal == 1 else "SHORT"
    atr = float(df.at[signal_idx, "atr"])
    if not np.isfinite(atr) or atr <= 0:
        return None

    raw_entry_price = float(df.at[exec_idx, "open"])
    entry_price = apply_entry_slippage(raw_entry_price, direction, cfg)

    sl_dist = cfg.sl_atr_mult * atr
    risk_cash = equity * cfg.risk_per_trade * regime_mult
    if risk_cash <= 0 or sl_dist <= 0:
        return None

    qty_by_risk = risk_cash / sl_dist
    max_notional = equity * cfg.max_notional_pct
    qty_by_notional = max_notional / entry_price
    qty = min(qty_by_risk, qty_by_notional)

    if qty <= 0 or not np.isfinite(qty):
        return None

    sign = direction_sign(direction)
    sl = entry_price - sign * sl_dist
    tp1 = entry_price + sign * cfg.tp1_atr_mult * atr
    tp2 = entry_price + sign * cfg.tp2_atr_mult * atr

    return OpenPosition(
        direction=direction,
        entry_idx=exec_idx,
        entry_time=pd.Timestamp(df.at[exec_idx, "timestamp"]),
        entry_price=entry_price,
        qty=qty,
        remaining_qty=qty,
        sl=sl,
        tp1=tp1,
        tp2=tp2,
        atr=atr,
    )


def process_funding(
    pos: OpenPosition,
    row: pd.Series,
    equity: float,
    cfg: StrategyConfig,
) -> tuple[float, float]:
    ts = pd.Timestamp(row["timestamp"])
    if not is_funding_timestamp(ts, cfg):
        return equity, 0.0

    funding_rate = float(row["funding_rate"])
    notional = abs(float(row["close"]) * pos.remaining_qty)
    sign = direction_sign(pos.direction)

    # Positive funding: longs pay shorts. Negative funding: shorts pay longs.
    funding_pnl = -sign * funding_rate * notional
    return equity + funding_pnl, funding_pnl


def update_trailing_stop(pos: OpenPosition, row: pd.Series, cfg: StrategyConfig) -> None:
    if not pos.tp1_done:
        return

    sign = direction_sign(pos.direction)
    close_price = float(row["close"])
    trail_price = close_price - sign * cfg.trail_atr_mult * pos.atr

    if sign * (trail_price - pos.sl) > 0:
        pos.sl = trail_price


def backtest(
    df: pd.DataFrame,
    cfg: StrategyConfig,
    initial_equity: float = 10_000.0,
    regime_mult_fn: Callable[[pd.Timestamp], float] | None = None,
) -> BacktestResult:
    if "entry_signal" not in df.columns:
        data = prepare_strategy_dataframe(df, cfg)
    else:
        data = df.copy()

    equity = float(initial_equity)
    funding_pnl_total = 0.0
    trades: list[Trade] = []
    equity_points: list[dict[str, float | str]] = []
    pos: OpenPosition | None = None

    i = 0
    n = len(data)

    while i < n:
        row = data.iloc[i]
        ts = pd.Timestamp(row["timestamp"])

        if pos is None:
            signal = int(row.get("entry_signal", 0))
            exec_idx = i + cfg.latency_candles

            if signal != 0 and exec_idx < n:
                exec_ts = pd.Timestamp(data.at[exec_idx, "timestamp"])
                regime_mult = regime_mult_fn(exec_ts) if regime_mult_fn else 1.0
                pos = open_position_from_signal(data, i, exec_idx, equity, cfg, regime_mult)

                if pos is not None:
                    i = exec_idx
                    row = data.iloc[i]
                    ts = pd.Timestamp(row["timestamp"])
                else:
                    equity_points.append({"timestamp": ts.isoformat(), "equity": equity})
                    i += 1
                    continue
            else:
                equity_points.append({"timestamp": ts.isoformat(), "equity": equity})
                i += 1
                continue

        assert pos is not None

        equity, funding_pnl = process_funding(pos, row, equity, cfg)
        funding_pnl_total += funding_pnl

        high = float(row["high"])
        low = float(row["low"])
        close = float(row["close"])
        sign = direction_sign(pos.direction)

        stop_hit = low <= pos.sl if pos.direction == "LONG" else high >= pos.sl
        tp1_hit = high >= pos.tp1 if pos.direction == "LONG" else low <= pos.tp1
        tp2_hit = high >= pos.tp2 if pos.direction == "LONG" else low <= pos.tp2

        # Conservative ambiguity handling: if stop and target happen in same candle, stop wins.
        if cfg.conservative_intrabar and stop_hit:
            qty_to_close = pos.remaining_qty
            equity, trade = close_position_leg(
                pos=pos,
                exit_time=ts,
                exit_price_raw=pos.sl,
                reason="SL_HIT",
                qty_to_close=qty_to_close,
                equity=equity,
                cfg=cfg,
            )
            trades.append(trade)
            pos = None
            equity_points.append({"timestamp": ts.isoformat(), "equity": equity})
            i += 1
            continue

        if tp1_hit and not pos.tp1_done:
            qty_to_close = min(pos.remaining_qty, pos.qty * cfg.tp1_fraction)
            equity, trade = close_position_leg(
                pos=pos,
                exit_time=ts,
                exit_price_raw=pos.tp1,
                reason="TP1_HIT",
                qty_to_close=qty_to_close,
                equity=equity,
                cfg=cfg,
            )
            trades.append(trade)
            pos.remaining_qty -= qty_to_close
            pos.tp1_done = True

            # After TP1, bring stop at least to breakeven after slippage/fees cushion.
            breakeven_buffer = pos.entry_price * (cfg.taker_fee + cfg.slippage_bps)
            breakeven_sl = pos.entry_price + sign * breakeven_buffer
            if sign * (breakeven_sl - pos.sl) > 0:
                pos.sl = breakeven_sl

        if pos is not None and pos.remaining_qty > 0 and tp2_hit:
            qty_to_close = pos.remaining_qty
            equity, trade = close_position_leg(
                pos=pos,
                exit_time=ts,
                exit_price_raw=pos.tp2,
                reason="TP2_HIT",
                qty_to_close=qty_to_close,
                equity=equity,
                cfg=cfg,
            )
            trades.append(trade)
            pos = None
            equity_points.append({"timestamp": ts.isoformat(), "equity": equity})
            i += 1
            continue

        if pos is not None and not cfg.conservative_intrabar and stop_hit:
            qty_to_close = pos.remaining_qty
            equity, trade = close_position_leg(
                pos=pos,
                exit_time=ts,
                exit_price_raw=pos.sl,
                reason="SL_HIT",
                qty_to_close=qty_to_close,
                equity=equity,
                cfg=cfg,
            )
            trades.append(trade)
            pos = None
            equity_points.append({"timestamp": ts.isoformat(), "equity": equity})
            i += 1
            continue

        if pos is not None and pos.remaining_qty > 0:
            fomo = float(row["fomo"]) if np.isfinite(row["fomo"]) else 0.0
            if fomo < cfg.fomo_exit:
                qty_to_close = pos.remaining_qty
                equity, trade = close_position_leg(
                    pos=pos,
                    exit_time=ts,
                    exit_price_raw=close,
                    reason="FOMO_DECAY",
                    qty_to_close=qty_to_close,
                    equity=equity,
                    cfg=cfg,
                )
                trades.append(trade)
                pos = None
                equity_points.append({"timestamp": ts.isoformat(), "equity": equity})
                i += 1
                continue

        if pos is not None and pos.remaining_qty > 0 and pos.bars >= cfg.max_bars:
            qty_to_close = pos.remaining_qty
            equity, trade = close_position_leg(
                pos=pos,
                exit_time=ts,
                exit_price_raw=close,
                reason="TIME_EXIT",
                qty_to_close=qty_to_close,
                equity=equity,
                cfg=cfg,
            )
            trades.append(trade)
            pos = None
            equity_points.append({"timestamp": ts.isoformat(), "equity": equity})
            i += 1
            continue

        if pos is not None:
            update_trailing_stop(pos, row, cfg)
            pos.bars += 1

        equity_points.append({"timestamp": ts.isoformat(), "equity": equity})
        i += 1

    if pos is not None and pos.remaining_qty > 0:
        last = data.iloc[-1]
        last_ts = pd.Timestamp(last["timestamp"])
        equity, trade = close_position_leg(
            pos=pos,
            exit_time=last_ts,
            exit_price_raw=float(last["close"]),
            reason="END_OF_DATA",
            qty_to_close=pos.remaining_qty,
            equity=equity,
            cfg=cfg,
        )
        trades.append(trade)
        equity_points.append({"timestamp": last_ts.isoformat(), "equity": equity})

    trades_df = pd.DataFrame([dataclasses.asdict(t) for t in trades])
    equity_curve = pd.DataFrame(equity_points)
    if not equity_curve.empty:
        equity_curve["timestamp"] = pd.to_datetime(equity_curve["timestamp"], utc=True)
        equity_curve["equity"] = pd.to_numeric(equity_curve["equity"], errors="coerce")
    else:
        equity_curve = pd.DataFrame(
            [{"timestamp": data.iloc[0]["timestamp"], "equity": initial_equity}]
        )

    final_equity = float(equity)
    total_return_pct = (final_equity / initial_equity - 1.0) * 100.0
    max_drawdown_pct = calc_drawdown(equity_curve["equity"]) * 100.0
    sharpe = calc_sharpe(equity_curve["equity"], cfg.periods_per_year)

    if trades_df.empty:
        profit_factor = 0.0
        win_rate = 0.0
        trade_count = 0
    else:
        wins = trades_df.loc[trades_df["net_pnl"] > 0, "net_pnl"].sum()
        losses = trades_df.loc[trades_df["net_pnl"] < 0, "net_pnl"].sum()
        profit_factor = float(wins / abs(losses)) if losses < 0 else float("inf")
        win_rate = float((trades_df["net_pnl"] > 0).mean() * 100.0)
        trade_count = int((trades_df["entry_time"] + trades_df["direction"]).nunique())

    return BacktestResult(
        initial_equity=initial_equity,
        final_equity=final_equity,
        total_return_pct=total_return_pct,
        max_drawdown_pct=max_drawdown_pct,
        sharpe=sharpe,
        profit_factor=profit_factor,
        win_rate=win_rate,
        trades=trade_count,
        closed_legs=len(trades_df),
        funding_pnl=funding_pnl_total,
        trades_df=trades_df,
        equity_curve=equity_curve,
    )


def result_summary(result: BacktestResult) -> dict[str, float | int]:
    return {
        "initial_equity": round(result.initial_equity, 8),
        "final_equity": round(result.final_equity, 8),
        "total_return_pct": round(result.total_return_pct, 4),
        "max_drawdown_pct": round(result.max_drawdown_pct, 4),
        "sharpe": round(result.sharpe, 4),
        "profit_factor": round(result.profit_factor, 4)
        if math.isfinite(result.profit_factor)
        else 9999.0,
        "win_rate": round(result.win_rate, 4),
        "trades": result.trades,
        "closed_legs": result.closed_legs,
        "funding_pnl": round(result.funding_pnl, 8),
    }


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


def score_result_for_optimization(result: BacktestResult, cfg: StrategyConfig) -> float:
    summary = result_summary(result)

    if result.trades < cfg.min_trades_per_test:
        return -999.0

    if result.max_drawdown_pct > cfg.max_drawdown_constraint * 100.0:
        return -999.0 - result.max_drawdown_pct

    if not math.isfinite(result.profit_factor):
        pf_component = 3.0
    else:
        pf_component = min(result.profit_factor, 3.0)

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
) -> tuple[pd.DataFrame, list[BacktestResult]]:
    folds = make_walk_forward_windows(df)
    if not folds:
        raise ValueError("No walk-forward folds could be created from this dataset.")

    rows: list[dict[str, float | int | str]] = []
    results: list[BacktestResult] = []

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

        row = {
            "fold": fold.fold,
            "train_start": fold.train_start.date().isoformat(),
            "train_end": fold.train_end.date().isoformat(),
            "test_start": fold.test_start.date().isoformat(),
            "test_end": fold.test_end.date().isoformat(),
            **result_summary(test_result),
            "cfg": json.dumps(asdict(cfg), sort_keys=True),
        }
        rows.append(row)

    return pd.DataFrame(rows), results


def write_reports(
    outdir: str | Path,
    summary: dict[str, float | int],
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
    (path / "config.json").write_text(
        json.dumps(asdict(cfg), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    if result is not None:
        result.trades_df.to_csv(path / "trades.csv", index=False)
        result.equity_curve.to_csv(path / "equity_curve.csv", index=False)

    if fold_summary is not None:
        fold_summary.to_csv(path / "walk_forward_summary.csv", index=False)


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
        print(json.dumps({"best_cfg": asdict(best_cfg), "summary": summary}, indent=2))
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


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
