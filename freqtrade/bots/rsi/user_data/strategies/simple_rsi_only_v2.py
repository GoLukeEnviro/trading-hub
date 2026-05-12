"""
SimpleRSIOnly_v2 — UNLEASHED: Trendfilter ENTFERNT
Reines Mean-Reversion: RSI < 45 = Long, RSI > 55 = Short
Stoploss -3% | Trailing Stop aktiv | Lev 3x
"""

import talib.abstract as ta
from freqtrade.strategy import IStrategy, IntParameter
from pandas import DataFrame


class SimpleRSIOnly_v2(IStrategy):

    INTERFACE_VERSION = 3
    timeframe = "15m"
    can_short = True

    stoploss = -0.03

    minimal_roi = {
        "0": 0.02,
        "60": 0.01,
        "120": 0.005,
    }

    trailing_stop = True
    trailing_stop_positive = 0.01
    trailing_stop_positive_offset = 0.015
    trailing_only_offset_is_reached = True

    buy_rsi = IntParameter(30, 50, default=45, space="buy", optimize=True)
    short_rsi = IntParameter(50, 70, default=55, space="buy", optimize=True)
    sell_rsi = IntParameter(60, 85, default=70, space="sell", optimize=True)
    cover_rsi = IntParameter(15, 40, default=30, space="sell", optimize=True)

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # LONG: RSI < 45 (Mean-Reversion, egal ob Trend)
        dataframe.loc[
            (dataframe["rsi"] < self.buy_rsi.value),
            ["enter_long", "enter_tag"],
        ] = (1, "rsi_long")

        # SHORT: RSI > 55 (Mean-Reversion, egal ob Trend)
        dataframe.loc[
            (dataframe["rsi"] > self.short_rsi.value),
            ["enter_short", "enter_tag"],
        ] = (1, "rsi_short")

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe["rsi"] > self.sell_rsi.value),
            ["exit_long", "exit_tag"],
        ] = (1, "rsi_exit_long")

        dataframe.loc[
            (dataframe["rsi"] < self.cover_rsi.value),
            ["exit_short", "exit_tag"],
        ] = (1, "rsi_exit_short")

        return dataframe

    def leverage(self, pair, current_time, current_rate, proposed_leverage,
                 max_leverage, entry_tag, side, **kwargs) -> float:
        return 3.0
