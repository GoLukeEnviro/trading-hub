"""
MomentumBG15_v3_SL_Fix — Wider Stoploss, keep RSI-based exit
Based on v2_RRRefactor.

FIX v3:
- Stoploss widened from -1.8% to -3.5% (was killing 65% of trades prematurely)
- Exit signals preserved (RSI > 72 for longs, RSI < 28 for shorts)
- All other logic unchanged
"""
import logging
import sys
import json
import os
from datetime import timedelta, datetime
from typing import Optional

import talib.abstract as ta
from freqtrade.strategy import IStrategy, IntParameter, DecimalParameter, merge_informative_pair
import freqtrade.vendor.qtpylib.indicators as qtpylib
from pandas import DataFrame

sys.path.insert(0, "/freqtrade/shared")
from primo_signal import primo_gate_allows

logger = logging.getLogger(__name__)


class MomentumBG15_v3(IStrategy):

    INTERFACE_VERSION = 3
    timeframe = "15m"
    informative_timeframe = "1h"
    can_short = False

    # FIX: Widened from -1.8% to -3.5% — was killing 65% of trades prematurely
    minimal_roi = {'0': 0.06, '45': 0.03, '120': 0.015, '240': 0}
    stoploss = -0.02
    use_custom_stoploss = False
    trailing_stop = False

    startup_candle_count = 100

    @property
    def protections(self):
        return [
            {"method": "CooldownPeriod", "stop_duration_candles": 5},
            {"method": "StoplossGuard", "lookback_period_candles": 60,
             "trade_limit": 3, "stop_duration_candles": 60,
             "only_per_pair": False, "only_per_side": True},
        ]

    rsi_oversold = IntParameter(35, 50, default=42, space="buy", optimize=True)
    rsi_overbought = IntParameter(50, 65, default=58, space="buy", optimize=True)

    # Exit thresholds
    exit_rsi_long = IntParameter(65, 82, default=72, space="sell", optimize=True)
    exit_rsi_short = IntParameter(18, 35, default=28, space="sell", optimize=True)

    # Trading strategy pacing
    max_open_trades_cache: int = 5

    def informative_pairs(self):
        pairs = self.dp.current_whitelist()
        return [(pair, self.informative_timeframe) for pair in pairs]

    def _get_regime(self, dataframe: DataFrame) -> DataFrame:
        adx = ta.ADX(dataframe)
        close = dataframe["close"]
        ema_trend = ta.EMA(close, timeperiod=200)
        ema_fast = ta.EMA(close, timeperiod=50)
        ema_slow = ta.EMA(close, timeperiod=200)
        strong = 25
        chaos = 20
        bull = (adx > strong) & (close > ema_trend) & (ema_fast > ema_slow)
        bear = (adx > strong) & (close < ema_trend) & (ema_fast < ema_slow)
        chaos_cond = adx < chaos

        regime = DataFrame("sideways", index=dataframe.index, columns=["regime"])
        regime.loc[bull, "regime"] = "bull"
        regime.loc[bear, "regime"] = "bear"
        regime.loc[chaos_cond, "regime"] = "chaos"
        return regime["regime"]

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["regime"] = self._get_regime(dataframe)
        macd = ta.MACD(dataframe)
        dataframe["macd"], dataframe["macd_signal"], dataframe["macd_hist"] = (
            macd["macd"], macd["macdsignal"], macd["macdhist"]
        )
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        try:
            pair = metadata.get("pair")
            long_gate = primo_gate_allows(pair, "long")
            short_gate = primo_gate_allows(pair, "short")

            macd_bull = dataframe["macd_hist"] > 0
            macd_bear = dataframe["macd_hist"] < 0

            # LONG: bull OR sideways + RSI < oversold + MACD-hist > 0
            long_cond = (
                (dataframe["regime"].isin(["bull", "sideways"])) &
                (dataframe["rsi"] < self.rsi_oversold.value) &
                macd_bull &
                long_gate
            )
            dataframe.loc[long_cond, ["enter_long", "enter_tag"]] = (1, "v2_momentum_long")

            # SHORT: bear OR sideways + RSI > overbought + MACD-hist < 0
            short_cond = (
                (dataframe["regime"].isin(["bear", "sideways"])) &
                (dataframe["rsi"] > self.rsi_overbought.value) &
                macd_bear &
                short_gate
            )
            dataframe.loc[short_cond, ["enter_short", "enter_tag"]] = (1, "v2_momentum_short")

        except Exception as e:
            logger.error(f"entry error: {e}")
        return dataframe

    def populate_exit_trend(self, dataframe, metadata):
        return dataframe

    def confirm_trade_entry(self, pair: str, order_type: str, amount: float,
                            rate: float, time_in_force: str, current_time: datetime,
                            entry_tag: Optional[str], side: str, **kwargs) -> bool:
        open_trades = []
        recent_closed = []
        current_drawdown = 0.0

        try:
            from freqtrade.persistence import Trade
            for t in Trade.get_trades_proxy(is_open=True):
                open_trades.append({"pair": t.pair, "is_short": t.is_short})
            cutoff = current_time - timedelta(hours=24)
            for t in Trade.get_trades_proxy(is_open=False):
                if t.close_date and t.close_date >= cutoff:
                    recent_closed.append({
                        "pair": t.pair, "is_short": t.is_short,
                        "close_profit": t.close_profit or 0.0,
                    })

            # FleetGuard v1: max open trades per side
            max_open_shorts = 2
            open_shorts = sum(1 for t in open_trades if t.get("is_short", False))
            if side == "short" and open_shorts >= max_open_shorts:
                logger.info(f"FleetGuard REJECT: {pair} {side} — max_open_shorts({open_shorts}>={max_open_shorts})")
                return False

            # FleetGuard v1: max 2 losses in 24h on same pair
            pair_losses_24h = [t for t in recent_closed if t.get("pair") == pair and t.get("close_profit", 0) < 0]
            if len(pair_losses_24h) >= 2:
                logger.info(f"FleetGuard REJECT: {pair} {side} — losses_24h({len(pair_losses_24h)}>=2)")
                return False

            # FleetGuard v1: max 4 losses total in 24h
            total_losses_24h = sum(1 for t in recent_closed if t.get("close_profit", 0) < 0)
            if total_losses_24h >= 4:
                logger.info(f"FleetGuard REJECT: {pair} {side} — total_losses_24h({total_losses_24h}>=4)")
                return False

            trade_manager = kwargs.get("trade_manager", None)
            if trade_manager:
                _config = self.config if hasattr(self, "config") else {}
                starting_balance = 1000
                try:
                    if hasattr(self, 'wallets') and self.wallets:
                        starting_balance = self.wallets.get_starting_balance()
                except Exception:
                    starting_balance = 1000

                total_closed_profit = Trade.get_total_closed_profit()
                total_closed_profit_pct = total_closed_profit / starting_balance if starting_balance > 0 else 0
                if total_closed_profit_pct < -0.05:
                    current_drawdown = abs(total_closed_profit_pct)
                    if current_drawdown >= 0.05:
                        logger.info(f"FleetGuard REJECT: {pair} {side} — drawdown_hard({total_closed_profit_pct:.3f}>=-0.05)")
                        return False

        except Exception as e:
            logger.error(f"FleetGuard error: {e}")

        return True
