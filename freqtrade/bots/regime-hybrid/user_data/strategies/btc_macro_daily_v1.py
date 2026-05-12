"""
BTCMacroDaily_v1 — BTC Regime + RSI Pullback

Entry: BTC > EMA200 (bull market) + RSI < 40 (micro pullback)
Exit: ROI/Stoploss
Pairs: BTC/USDT, ETH/USDT, SOL/USDT
"""
import talib.abstract as ta
from freqtrade.strategy import IStrategy
from pandas import DataFrame


class BTCMacroDaily_v1(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "1d"
    can_short = False

    stoploss = -0.10
    use_custom_stoploss = False
    trailing_stop = False
    process_only_new_candles = True

    minimal_roi = {
        "0": 0.20,
        "30": 0.12,
        "60": 0.06,
        "90": 0,
    }

    startup_candle_count = 200
    max_open_trades = 2

    @property
    def protections(self):
        return [
            {"method": "CooldownPeriod", "stop_duration_candles": 10},
            {"method": "StoplossGuard", "lookback_period_candles": 30,
             "trade_limit": 1, "stop_duration_candles": 30},
        ]

    def informative_pairs(self):
        return [("BTC/USDT", "1d")]

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        if self.dp:
            btc_data = self.dp.get_pair_dataframe("BTC/USDT", "1d")
            btc_ema200 = ta.EMA(btc_data["close"], timeperiod=200)
            dataframe["btc_price"] = btc_data["close"]
            dataframe["btc_ema200"] = btc_ema200
            dataframe["btc_bull"] = dataframe["btc_price"] > dataframe["btc_ema200"]

        dataframe["rsi"] = ta.RSI(dataframe["close"], timeperiod=14)
        dataframe["ema50"] = ta.EMA(dataframe["close"], timeperiod=50)
        dataframe["ema200"] = ta.EMA(dataframe["close"], timeperiod=200)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        macro_ok = dataframe.get("btc_bull", True)

        entry = (
            macro_ok &
            (dataframe["rsi"] < 40) &
            (dataframe["close"] > dataframe["ema200"])
        )
        dataframe.loc[entry, "enter_long"] = 1
        dataframe.loc[entry, "enter_tag"] = "macro_pullback"
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        return dataframe
