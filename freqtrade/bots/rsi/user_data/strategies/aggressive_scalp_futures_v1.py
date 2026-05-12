"""
AggressiveScalpFutures_v1 — Aggressive RSI + BB Scalp, 15m Futures
Breitere Entries, kein Volume-Filter, enger SL, hohe Frequenz.
"""

import talib.abstract as ta
from freqtrade.strategy import IStrategy, IntParameter, DecimalParameter
from pandas import DataFrame


class AggressiveScalpFutures_v1(IStrategy):

    INTERFACE_VERSION = 3
    timeframe = "15m"
    can_short = True

    # Hard stoploss -0.7%
    stoploss = -0.007

    # Aggressive ROI
    minimal_roi = {
        "0": 0.012,
        "20": 0.009,
        "40": 0.006,
        "90": 0.003,
    }

    # No trailing
    trailing_stop = False

    # Hyperopt params
    buy_rsi = IntParameter(30, 50, default=42, space="buy", optimize=True)
    sell_rsi = IntParameter(50, 75, default=65, space="sell", optimize=True)
    short_rsi = IntParameter(50, 70, default=58, space="buy", optimize=True)
    cover_rsi = IntParameter(25, 45, default=35, space="sell", optimize=True)
    bb_tolerance = DecimalParameter(0.995, 1.005, default=1.000, decimals=3, space="buy", optimize=True)

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)

        bb = ta.BBANDS(dataframe, timeperiod=20, nbdevup=2.0, nbdevdn=2.0)
        dataframe["bb_upper"] = bb["upperband"]
        dataframe["bb_lower"] = bb["lowerband"]

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        tol = float(self.bb_tolerance.value)

        # Long: RSI < 42 AND Close <= BB_lower (kein Volume-Filter)
        dataframe.loc[
            (dataframe["rsi"] < self.buy_rsi.value)
            & (dataframe["close"] <= dataframe["bb_lower"] * tol),
            ["enter_long", "enter_tag"],
        ] = (1, "rsi_bb_long")

        # Short: RSI > 58 AND Close >= BB_upper (kein Volume-Filter)
        dataframe.loc[
            (dataframe["rsi"] > self.short_rsi.value)
            & (dataframe["close"] >= dataframe["bb_upper"] * tol),
            ["enter_short", "enter_tag"],
        ] = (1, "rsi_bb_short")

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Long exit: RSI > sell_rsi
        dataframe.loc[
            (dataframe["rsi"] > self.sell_rsi.value),
            ["exit_long", "exit_tag"],
        ] = (1, "rsi_exit_long")

        # Short exit: RSI < cover_rsi
        dataframe.loc[
            (dataframe["rsi"] < self.cover_rsi.value),
            ["exit_short", "exit_tag"],
        ] = (1, "rsi_exit_short")

        return dataframe

    def leverage(self, pair, current_time, current_rate, proposed_leverage,
                 max_leverage, entry_tag, side, **kwargs) -> float:
        return 4.0
