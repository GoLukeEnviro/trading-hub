"""
RegimeSwitchingHybrid_v8_BaselineTest
=====================================
BASELINE-ONLY TEST — no ATR trailing, no protections, no trailing stop.
Purpose: Answer "does the entry logic alone produce a positive edge?"

Changes vs v7:
  REMOVED: custom_stoploss(), protections, ATR-based SL/TP parameters,
           atr_sl_trend, atr_tp_trend, atr_sl_range.
  NEW:     stoploss = -0.03 (hard), minimal_roi = {"0": 0.05} (5% fixed).

KEEP from v7: Entry logic (ADX + EMA50 + RSI + volume + primo_gate),
              FleetGuard entry safety, RSI overbought exit signal.

Timeframe: 15m
Trading Mode: Isolated Futures (dry-run)
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


class RegimeSwitchingHybrid_v8_BaselineTest(IStrategy):

    INTERFACE_VERSION = 3
    timeframe = "15m"
    can_short = False

    # ---- Baseline Exit: ONLY hard stoploss + fixed ROI ----
    # No custom_stoploss, no trailing, no protections
    stoploss = -0.03          # Hard -3% stop
    use_custom_stoploss = False
    trailing_stop = False

    minimal_roi = {
        "0": 0.05,             # Take profit at +5%, done
        "60": 0.03,
        "120": 0.01,
        "240": 0
    }

    # ---- FleetGuard entry safety (unchanged from v7) ----
    _fleetguard = FleetGuard(FleetGuardConfig(
        max_open_trades=3,
        max_open_shorts=2,
        max_open_longs=2,
    ))

    # NO protections in v8 — pure baseline test

    startup_candle_count = 50

    # ---- Hyperoptable Buy Parameters (same as v7) ----
    adx_threshold = DecimalParameter(15.0, 35.0, default=20.0, space="buy")
    ema_pullback_pct = DecimalParameter(0.5, 4.0, default=2.0, space="buy")
    rsi_entry_max = IntParameter(45, 65, default=55, space="buy")
    volume_ma_period = IntParameter(10, 40, default=20, space="buy")

    # Fixed exit parameters
    rsi_overbought = 66

    # ---- Indicators ----
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        if not self.dp:
            return dataframe

        dataframe['adx'] = ta.ADX(dataframe)
        dataframe['ema50'] = ta.EMA(dataframe, timeperiod=50)
        dataframe['rsi'] = ta.RSI(dataframe)
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=14)
        dataframe['atr_pct'] = dataframe['atr'] / dataframe['close']

        dataframe['volume_sma'] = dataframe['volume'].rolling(
            window=self.volume_ma_period.value, min_periods=1
        ).mean()

        bollinger = qtpylib.bollinger_bands(
            qtpylib.typical_price(dataframe), window=20, stds=2
        )
        dataframe['bb_lowerband'] = bollinger['lower']
        dataframe['bb_middleband'] = bollinger['mid']
        dataframe['bb_upperband'] = bollinger['upper']

        return dataframe

    # ---- Entry Logic (UNCHANGED from v7) ----
    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        pair = metadata.get("pair")
        long_gate = primo_gate_allows(pair, "long")

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
        dataframe.loc[trend_continuation, 'enter_tag'] = 'baseline_test_v8'

        return dataframe

    # ---- Exit Logic (SIMPLIFIED: only RSI overbought) ----
    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe['rsi'] > self.rsi_overbought),
            'exit_long'
        ] = 1
        return dataframe

    # ---- FleetGuard Entry Safety (unchanged from v7) ----
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