"""
SimpleRSIBBFutures — Minimale RSI + BB Strategie, 15m Futures
Nur RSI(14) + BB(20,2). Kein MACD, kein Trailing, kein ATR-Custom-Stop.
"""

import talib.abstract as ta
from freqtrade.strategy import IStrategy, IntParameter, DecimalParameter
from pandas import DataFrame


class SimpleRSIBBFutures(IStrategy):

    INTERFACE_VERSION = 3
    timeframe = "15m"
    can_short = True

    # Hard stoploss
    stoploss = -0.012

    # ROI
    minimal_roi = {
        "0": 0.025,
        "30": 0.015,
        "60": 0.008,
    }

    # No trailing
    trailing_stop = False

    # Hyperopt params
    buy_rsi = IntParameter(20, 40, default=30, space="buy", optimize=True)
    sell_rsi = IntParameter(60, 80, default=65, space="sell", optimize=True)
    short_rsi = IntParameter(60, 80, default=70, space="buy", optimize=True)
    cover_rsi = IntParameter(20, 40, default=35, space="sell", optimize=True)
    bb_tolerance = DecimalParameter(1.000, 1.010, default=1.003, decimals=3, space="buy", optimize=True)

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)

        bb = ta.BBANDS(dataframe, timeperiod=20, nbdevup=2.0, nbdevdn=2.0)
        dataframe["bb_upper"] = bb["upperband"]
        dataframe["bb_lower"] = bb["lowerband"]

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        tol = float(self.bb_tolerance.value)

        # Long: RSI < buy_rsi AND Close <= BB_lower * tolerance
        dataframe.loc[
            (dataframe["rsi"] < self.buy_rsi.value)
            & (dataframe["close"] <= dataframe["bb_lower"] * tol)
            & (dataframe["volume"] > 0),
            ["enter_long", "enter_tag"],
        ] = (1, "rsi_bb_long")

        # Short: RSI > short_rsi AND Close >= BB_upper * tolerance
        dataframe.loc[
            (dataframe["rsi"] > self.short_rsi.value)
            & (dataframe["close"] >= dataframe["bb_upper"] * tol)
            & (dataframe["volume"] > 0),
            ["enter_short", "enter_tag"],
        ] = (1, "rsi_bb_short")

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Long exit: RSI > sell_rsi
        dataframe.loc[
            (dataframe["rsi"] > self.sell_rsi.value)
            & (dataframe["volume"] > 0),
            ["exit_long", "exit_tag"],
        ] = (1, "rsi_exit_long")

        # Short exit: RSI < cover_rsi
        dataframe.loc[
            (dataframe["rsi"] < self.cover_rsi.value)
            & (dataframe["volume"] > 0),
            ["exit_short", "exit_tag"],
        ] = (1, "rsi_exit_short")

        return dataframe

    def leverage(self, pair, current_time, current_rate, proposed_leverage,
                 max_leverage, entry_tag, side, **kwargs) -> float:
        return 3.0
