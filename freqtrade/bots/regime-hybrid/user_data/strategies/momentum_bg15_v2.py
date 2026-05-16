"""
MomentumBG15_v2 — Entry-Logic Fix

Based on MomentumBG15_v1 (RR-Refactor branch) with 3 targeted changes:

CHANGE 1: RSI thresholds widened
  - LONG:  RSI < 42 → RSI < 50
  - SHORT: RSI > 58 → RSI > 50
  Reason: v1 produced 0 trades because RSI < 42 + MACD > 0 + regime filter
  never triggered simultaneously on 15m candles.

CHANGE 2: Regime filter REMOVED from entry logic
  - v1 required regime in (bull, sideways) for LONG and (bear, sideways) for SHORT
  - This filtered out 38% of all bars (bear regime = no longs allowed)
  - v2: no regime check in populate_entry_trend at all
  - Regime classification still computed for future use / logging

CHANGE 3: MACD condition changed from "positive" to "rising"
  - v1: macd_hist > 0 (absolute level — too restrictive in sideways)
  - v2: macd_hist > macd_hist.shift(1) (momentum direction, not absolute)
  - Catches momentum rotations better, works in all market phases

All other logic UNTOUCHED:
  - Stoploss: -1.8% (static)
  - ROI: 2.5% → 1.5% → 0.8% → 0 after 4h
  - Trailing: OFF
  - FleetGuard: active (max 4 open, 2 long, 2 short)
  - Protections: Cooldown, StoplossGuard, MaxDrawdown, LowProfitPairs
  - PrimoGate: active (fallback to allow when stale)
  - Hyperopt params: same ranges, same defaults
  - custom_stoploss: disabled (code preserved)
"""

import logging
import sys
from datetime import datetime, timedelta
from typing import Optional

import talib.abstract as ta
from freqtrade.strategy import IStrategy, IntParameter, DecimalParameter
from pandas import DataFrame

sys.path.insert(0, "/freqtrade/shared")
from primo_signal import primo_gate_allows
from fleetguard_v1 import FleetGuard, FleetGuardConfig

logger = logging.getLogger(__name__)


class MomentumBG15_v2(IStrategy):

    INTERFACE_VERSION = 3
    timeframe = "15m"
    can_short = True

    startup_candle_count = 100

    use_custom_stoploss = False

    stoploss = -0.018  # -1.8%

    minimal_roi = {
        "0": 0.025,    # 2.5% immediate
        "45": 0.015,   # 1.5% after 45 min
        "120": 0.008,  # 0.8% after 2h
        "240": 0       # exit after 4h at cost
    }

    trailing_stop = False
    trailing_stop_positive = 0.015
    trailing_stop_positive_offset = 0.03
    trailing_only_offset_is_reached = True

    # ---- Hyperopt parameters ----
    adx_strong_trend = IntParameter(12, 25, default=15, space="buy", optimize=True)
    adx_chaos_threshold = IntParameter(5, 15, default=8, space="buy", optimize=False)

    # CHANGE 1: RSI thresholds widened from 42/58 to 50/50
    rsi_oversold = IntParameter(35, 55, default=50, space="buy", optimize=True)
    rsi_overbought = IntParameter(45, 65, default=50, space="buy", optimize=True)

    ema_fast_period = IntParameter(5, 15, default=8, space="buy", optimize=True)
    ema_slow_period = IntParameter(18, 30, default=21, space="buy", optimize=False)
    ema_trend_period = IntParameter(45, 60, default=50, space="buy", optimize=False)

    adx_period = IntParameter(10, 18, default=14, space="buy", optimize=False)

    risk_per_trade_pct = DecimalParameter(0.005, 0.025, default=0.015, decimals=3, space="buy", optimize=False)
    max_portfolio_drawdown_pct = DecimalParameter(0.10, 0.25, default=0.15, decimals=2, space="buy", optimize=False)
    max_daily_loss_pct = DecimalParameter(0.03, 0.08, default=0.05, decimals=2, space="buy", optimize=False)
    max_leverage = IntParameter(2, 5, default=5, space="buy", optimize=False)

    macd_fast = IntParameter(8, 16, default=12, space="buy", optimize=False)
    macd_slow = IntParameter(20, 30, default=26, space="buy", optimize=False)
    macd_signal = IntParameter(7, 12, default=9, space="buy", optimize=False)

    exit_rsi_long = IntParameter(65, 82, default=72, space="sell", optimize=True)
    exit_rsi_short = IntParameter(18, 35, default=28, space="sell", optimize=True)

    atr_sl_multiplier = DecimalParameter(1.0, 3.0, default=1.5, decimals=1, space="buy", optimize=False)

    _daily_pnl = {}
    _strategy_starting_balance = None
    _emergency_stopped = False

    _fleetguard = FleetGuard(FleetGuardConfig(
        max_open_trades=4,
        max_open_shorts=2,
        max_open_longs=2,
    ))

    @property
    def protections(self):
        return [
            {"method": "CooldownPeriod", "stop_duration_candles": 2},
            {"method": "StoplossGuard", "lookback_period_candles": 24, "trade_limit": 3, "stop_duration_candles": 8, "only_per_pair": False, "only_per_side": True},
            {"method": "MaxDrawdown", "lookback_period_candles": 48, "trade_limit": 10, "stop_duration_candles": 12, "max_allowed_drawdown": 0.06},
            {"method": "LowProfitPairs", "lookback_period_candles": 24, "trade_limit": 3, "stop_duration_candles": 12, "required_profit": -0.01, "only_per_pair": True, "only_per_side": True},
        ]

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        try:
            dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
            dataframe["ema_fast"] = ta.EMA(dataframe, timeperiod=self.ema_fast_period.value)
            dataframe["ema_slow"] = ta.EMA(dataframe, timeperiod=self.ema_slow_period.value)
            dataframe["ema_trend"] = ta.EMA(dataframe, timeperiod=self.ema_trend_period.value)
            dataframe["adx"] = ta.ADX(dataframe, timeperiod=self.adx_period.value)

            macd_result = ta.MACD(dataframe,
                                  fastperiod=self.macd_fast.value,
                                  slowperiod=self.macd_slow.value,
                                  signalperiod=self.macd_signal.value)
            dataframe["macd"] = macd_result["macd"]
            dataframe["macd_signal"] = macd_result["macdsignal"]
            dataframe["macd_hist"] = macd_result["macdhist"]

            # CHANGE 3: precompute MACD-hist rising for entry logic
            dataframe["macd_hist_rising"] = dataframe["macd_hist"] > dataframe["macd_hist"].shift(1)

            # Regime still computed (for logging/future use) but NOT used in entry
            dataframe["regime"] = self._classify_regime(dataframe)
            dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)
        except Exception as e:
            logger.error(f"indicator error: {e}")
            dataframe["regime"] = "sideways"
        return dataframe

    def _classify_regime(self, dataframe: DataFrame) -> DataFrame:
        adx = dataframe["adx"]
        close = dataframe["close"]
        ema_trend = dataframe["ema_trend"]
        ema_fast = dataframe["ema_fast"]
        ema_slow = dataframe["ema_slow"]

        strong = self.adx_strong_trend.value
        chaos = self.adx_chaos_threshold.value

        bull = (adx > strong) & (close > ema_trend) & (ema_fast > ema_slow)
        bear = (adx > strong) & (close < ema_trend) & (ema_fast < ema_slow)
        chaos_cond = adx < chaos

        regime = DataFrame("sideways", index=dataframe.index, columns=["regime"])
        regime.loc[bull, "regime"] = "bull"
        regime.loc[bear, "regime"] = "bear"
        regime.loc[chaos_cond, "regime"] = "chaos"
        return regime["regime"]

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        try:
            pair = metadata.get("pair")
            long_gate = primo_gate_allows(pair, "long")
            short_gate = primo_gate_allows(pair, "short")

            # CHANGE 2: NO regime filter — all regimes allowed
            # CHANGE 1: RSI < 50 (was < 42) for LONG, RSI > 50 (was > 58) for SHORT
            # CHANGE 3: MACD-hist rising (was MACD-hist > 0)

            long_cond = (
                (dataframe["rsi"] < self.rsi_oversold.value) &
                dataframe["macd_hist_rising"] &
                long_gate
            )
            dataframe.loc[long_cond, ["enter_long", "enter_tag"]] = (1, "v2_momentum_long")

            short_cond = (
                (dataframe["rsi"] > self.rsi_overbought.value) &
                ~dataframe["macd_hist_rising"] &  # MACD falling
                short_gate
            )
            dataframe.loc[short_cond, ["enter_short", "enter_tag"]] = (1, "v2_momentum_short")

        except Exception as e:
            logger.error(f"entry error: {e}")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        try:
            exit_long_cond = (dataframe["rsi"] > self.exit_rsi_long.value)
            dataframe.loc[exit_long_cond, ["exit_long", "exit_tag"]] = (1, "v2_rsi_exit_long")

            exit_short_cond = (dataframe["rsi"] < self.exit_rsi_short.value)
            dataframe.loc[exit_short_cond, ["exit_short", "exit_tag"]] = (1, "v2_rsi_exit_short")
        except Exception as e:
            logger.error(f"exit error: {e}")
        return dataframe

    def custom_stoploss(self, pair: str, trade, current_time: datetime,
                        current_rate: float, current_profit: float,
                        after_fill: bool, **kwargs) -> Optional[float]:
        # DISABLED — use_custom_stoploss = False
        if current_profit > 0.025:
            return -0.008
        if current_profit > 0.015:
            return -0.012

        try:
            dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            if len(dataframe) > 0:
                last_candle = dataframe.iloc[-1]
                atr_val = last_candle.get("atr", 0)
                if atr_val > 0 and last_candle.get("close", 0) > 0:
                    atr_pct = atr_val / last_candle["close"]
                    sl_distance = atr_pct * self.atr_sl_multiplier.value
                    sl_distance = min(sl_distance, 0.025)
                    return -sl_distance
        except Exception:
            pass

        return None

    def confirm_trade_entry(self, pair: str, order_type: str, amount: float,
                            rate: float, time_in_force: str, current_time: datetime,
                            entry_tag: Optional[str], side: str, **kwargs) -> bool:
        if self._emergency_stopped:
            return False

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
                        "pair": t.pair,
                        "is_short": t.is_short,
                        "close_profit": t.close_profit or 0.0,
                    })

            total_profit = Trade.get_total_closed_profit()
            starting_balance = self.wallets.get_starting_balance() if hasattr(self, 'wallets') and self.wallets else 1000.0
            if starting_balance > 0:
                current_drawdown = abs(min(0, total_profit / starting_balance))
        except Exception as e:
            logger.warning(f"FleetGuard data gathering fallback: {e}")
            try:
                for t in Trade.get_trades_proxy(is_open=True):
                    open_trades.append({"pair": t.pair, "is_short": t.is_short})
            except Exception:
                pass

        allowed, reason = self._fleetguard.check_entry(
            pair=pair, side=side, open_trades=open_trades,
            recent_closed_trades=recent_closed, current_drawdown_pct=current_drawdown
        )
        if not allowed:
            logger.info(f"FleetGuard REJECT: {pair} {side} — {reason}")
            return False
        return True

    def leverage(self, pair: str, current_time: datetime, current_rate: float,
                 proposed_leverage: float, max_leverage: float, entry_tag: str,
                 side: str, **kwargs) -> float:
        return min(self.max_leverage.value, max_leverage)
