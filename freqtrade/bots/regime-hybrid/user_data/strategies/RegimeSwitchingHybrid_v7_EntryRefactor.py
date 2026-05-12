"""
RegimeSwitchingHybrid_v7_EntryRefactor
Trend Continuation Pullback — No HTF Merge, No Lookahead Bias
Phase 26B: Replaces v6 entry logic with candle-close-safe architecture.

Key Changes vs v6:
  REMOVED: merge_informative_pair, HTF ema200, range_reversion,
           adx_rel, 50-bar rolling regime, ffill-based HTF propagation.
  KEEP:    ATR-based custom_stoploss, FleetGuard, protections,
           dry-run compatible behavior, basic strategy shell.
  NEW:     Trend Continuation Pullback (ADX absolute + EMA50 + volume).

Entry Logic:
  1. ADX_absolute > adx_threshold (trend confirmed)
  2. close > ema50 (uptrend confirmed)
  3. close < ema50 * (1 - pullback_pct) (pullback zone)
  4. rsi < rsi_entry_max (upside room)
  5. volume > volume_sma (confirmation)

Timeframe: 15m
Trading Mode: Isolated Futures (dry-run)
Side: Long only (can_short=False)
"""

import logging
import sys
from datetime import datetime, timedelta
from typing import Optional

import talib.abstract as ta
from freqtrade.strategy import IStrategy, IntParameter, DecimalParameter, BooleanParameter
import freqtrade.vendor.qtpylib.indicators as qtpylib
from pandas import DataFrame

sys.path.insert(0, "/freqtrade/shared")
from primo_signal import primo_gate_allows
from fleetguard_v1 import FleetGuard, FleetGuardConfig

logger = logging.getLogger(__name__)


class RegimeSwitchingHybrid_v7_EntryRefactor(IStrategy):

    INTERFACE_VERSION = 3
    timeframe = "15m"

    # Long only — no shorts in v7 initial version
    can_short = False

    # ---- Base ROI (locked, not hyperopted in v7) ----
    minimal_roi = {
        "0": 0.06,
        "60": 0.03,
        "120": 0.01,
        "240": 0
    }

    # Failsafe stoploss — only triggers if custom_stoploss() fails.
    # Actual SL is ATR-based via custom_stoploss(). 8% emergency cap.
    stoploss = -0.08
    use_custom_stoploss = True
    trailing_stop = False  # Handled by custom_stoploss

    startup_candle_count = 50

    # ---- FleetGuard v1 entry safety (conservative limits) ----
    _fleetguard = FleetGuard(FleetGuardConfig(
        max_open_trades=3,
        max_open_shorts=2,
        max_open_longs=2,
    ))

    @property
    def protections(self):
        return [
            {"method": "CooldownPeriod", "stop_duration_candles": 5},
            {"method": "StoplossGuard", "lookback_period_candles": 60, "trade_limit": 3,
             "stop_duration_candles": 60, "only_per_pair": False, "only_per_side": True},
            {"method": "MaxDrawdown", "lookback_period_candles": 480, "trade_limit": 20,
             "stop_duration_candles": 96, "max_allowed_drawdown": 0.06},
            {"method": "LowProfitPairs", "lookback_period_candles": 1440, "trade_limit": 2,
             "stop_duration_candles": 60, "required_profit": -0.01}
        ]

    # ---- Hyperoptable Buy Parameters ----
    # Trend strength threshold (absolute ADX, no ratio)
    adx_threshold = DecimalParameter(15.0, 35.0, default=20.0, space="buy")
    # Maximum pullback from EMA50 in percent
    ema_pullback_pct = DecimalParameter(0.5, 4.0, default=2.0, space="buy")
    # RSI entry ceiling (must be below this to enter)
    rsi_entry_max = IntParameter(45, 65, default=55, space="buy")
    # Volume SMA period
    volume_ma_period = IntParameter(10, 40, default=20, space="buy")

    # ---- ATR Sell Parameters (from v6 proven values, conservative start) ----
    # ATR multiplier for stoploss distance in trend mode
    atr_sl_trend = 4.5
    # ATR multiplier for stoploss distance in range/sideways
    atr_sl_range = DecimalParameter(2.5, 4.5, default=3.5, space="sell", optimize=True)
    # ATR multiplier for trailing profit take in trend mode
    atr_tp_trend = DecimalParameter(0.5, 2.0, default=1.7, space="sell", optimize=True)

    # Fixed parameters
    rsi_overbought = 66

    # ---- Indicators ----
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        if not self.dp:
            return dataframe

        # ADX — absolute trend strength (no rolling ratio)
        dataframe['adx'] = ta.ADX(dataframe)

        # EMA50 — primary trend line
        dataframe['ema50'] = ta.EMA(dataframe, timeperiod=50)

        # RSI — momentum filter
        dataframe['rsi'] = ta.RSI(dataframe)

        # ATR — for dynamic stoploss
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=14)
        dataframe['atr_pct'] = dataframe['atr'] / dataframe['close']

        # Volume SMA — for volume confirmation (safe rolling, small window)
        dataframe['volume_sma'] = dataframe['volume'].rolling(
            window=self.volume_ma_period.value, min_periods=1
        ).mean()

        # Bollinger Bands — for exit signal only
        bollinger = qtpylib.bollinger_bands(
            qtpylib.typical_price(dataframe), window=20, stds=2
        )
        dataframe['bb_lowerband'] = bollinger['lower']
        dataframe['bb_middleband'] = bollinger['mid']
        dataframe['bb_upperband'] = bollinger['upper']

        return dataframe

    # ---- Entry Logic (Trend Continuation Pullback) ----
    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        pair = metadata.get("pair")
        long_gate = primo_gate_allows(pair, "long")

# Trend continuation pullback conditions:
        # 1. ADX > threshold (trend strength confirmed)
        # 2. close is above EMA50 * (1 - pullback_pct) (price in pullback zone near EMA50)
        # 3. rsi < rsi_entry_max (still has upside room)
        # 4. volume > volume_sma (institutional participation confirmed)
        # 5. long_gate (primo signal permission)
        #
        # Entry: price pulled back from ema50 into the pullback zone.
        # We require close >= ema50 * (1 - pullback_pct) AND close < ema50
        # to ensure price is "close to EMA50 from below" but not too far away.

        pullback_pct = self.ema_pullback_pct.value / 100.0
        pullback_ceiling = dataframe['ema50'] * (1.0 - pullback_pct)

        trend_continuation = (
            (dataframe['adx'] > self.adx_threshold.value) &
            (dataframe['close'] >= pullback_ceiling) &
            (dataframe['close'] < dataframe['ema50']) &
            (dataframe['rsi'] < self.rsi_entry_max.value) &
            (dataframe['volume'] > dataframe['volume_sma']) &
            long_gate
        )

        dataframe.loc[trend_continuation, 'enter_long'] = 1
        dataframe.loc[trend_continuation, 'enter_tag'] = 'trend_continuation_v7'

        return dataframe

    # ---- Exit Logic (conservative) ----
    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Exit when RSI overbought OR close breaks above BB upper
        dataframe.loc[
            (
                (dataframe['rsi'] > self.rsi_overbought) |
                (dataframe['close'] > dataframe['bb_upperband'])
            ),
            'exit_long'
        ] = 1
        return dataframe

    # ---- FleetGuard Entry Safety ----
    def confirm_trade_entry(self, pair: str, order_type: str, amount: float,
                            rate: float, time_in_force: str, current_time: datetime,
                            entry_tag: Optional[str], side: str, **kwargs) -> bool:
        """FleetGuard entry safety check with real trade data."""
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
            starting_balance = (
                self.wallets.get_starting_balance()
                if hasattr(self, 'wallets') and self.wallets else 1000.0
            )
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

    # ---- ATR Custom Stoploss ----
    def custom_stoploss(self, pair: str, trade, current_time, current_rate,
                        current_profit: float, **kwargs) -> float:
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe.empty:
            return self.stoploss

        last = dataframe.iloc[-1]
        atr_pct = last['atr_pct']
        adx = last.get('adx', 25.0)

        # Use ADX absolute for regime detection (no ratio needed)
        is_trend = adx > self.adx_threshold.value

        if is_trend:
            sl_distance = atr_pct * self.atr_sl_trend
            if current_profit > (atr_pct * self.atr_tp_trend.value):
                return max(-sl_distance, current_profit - sl_distance)
        else:
            sl_distance = atr_pct * self.atr_sl_range.value

        return -sl_distance