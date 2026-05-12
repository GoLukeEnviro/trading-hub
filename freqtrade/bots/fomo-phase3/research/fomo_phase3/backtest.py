"""
Backtest engine — stateful row-by-row execution simulation.
v2-derived.
"""

from __future__ import annotations

from typing import Callable

import numpy as np
import pandas as pd

from fomo_phase3.config import Direction, ExitReason, StrategyConfig
from fomo_phase3.execution import (
    OpenPosition,
    apply_exit_slippage,
    apply_entry_slippage,
    direction_sign,
    process_funding,
    update_trailing_stop,
)
from fomo_phase3.metrics import BacktestResult, Trade
from fomo_phase3.signals import prepare_strategy_dataframe


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

    # Include funding accumulated for this position (F1 fix)
    funding_leg_share = pos.funding_pnl_accumulated * (qty_to_close / pos.qty) if pos.qty > 0 else 0.0

    net_pnl = gross_pnl - fees + funding_leg_share
    equity_after = equity + net_pnl

    fraction = qty_to_close / pos.qty if pos.qty > 0 else 0.0

    trade = Trade(
        position_id=pos.position_id,
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
        funding_pnl=funding_leg_share,
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


def backtest(
    df: pd.DataFrame,
    cfg: StrategyConfig,
    initial_equity: float = 10_000.0,
    regime_mult_fn: Callable[[pd.Timestamp], float] | None = None,
) -> BacktestResult:
    from fomo_phase3.execution import reset_position_counter

    reset_position_counter()

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

    import dataclasses

    trades_df = pd.DataFrame([dataclasses.asdict(t) for t in trades])
    equity_curve = pd.DataFrame(equity_points)
    if not equity_curve.empty:
        equity_curve["timestamp"] = pd.to_datetime(equity_curve["timestamp"], utc=True)
        equity_curve["equity"] = pd.to_numeric(equity_curve["equity"], errors="coerce")
    else:
        equity_curve = pd.DataFrame(
            [{"timestamp": data.iloc[0]["timestamp"], "equity": initial_equity}]
        )

    from fomo_phase3.metrics import (
        BacktestResult,
        calc_drawdown,
        calc_sharpe,
        result_summary,
    )

    final_equity = float(equity)
    total_return_pct = (final_equity / initial_equity - 1.0) * 100.0
    max_drawdown_pct = calc_drawdown(equity_curve["equity"]) * 100.0
    sharpe = calc_sharpe(equity_curve["equity"], cfg.periods_per_year)

    if trades_df.empty:
        profit_factor = 0.0
        win_rate = 0.0
        position_count = 0
    else:
        wins = trades_df.loc[trades_df["net_pnl"] > 0, "net_pnl"].sum()
        losses = trades_df.loc[trades_df["net_pnl"] < 0, "net_pnl"].sum()
        profit_factor = float(wins / abs(losses)) if losses < 0 else float("inf")
        win_rate = float((trades_df["net_pnl"] > 0).mean() * 100.0)
        position_count = int(trades_df["position_id"].nunique())

    return BacktestResult(
        initial_equity=initial_equity,
        final_equity=final_equity,
        total_return_pct=total_return_pct,
        max_drawdown_pct=max_drawdown_pct,
        sharpe=sharpe,
        profit_factor=profit_factor,
        win_rate=win_rate,
        trades=position_count,
        closed_legs=len(trades_df),
        funding_pnl=funding_pnl_total,
        trades_df=trades_df,
        equity_curve=equity_curve,
    )
