"""
TrendStrengthDaily_v1 — ADX + MACD Momentum

Entry: ADX > 25 (strong trend) + MACD hist > 0 (bullish momentum)
Regime: BTC > EMA200
"""
import talib.abstract as ta
from freqtrade.strategy import IStrategy
from pandas import DataFrame


class TrendStrengthDaily_v1(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "1d"
    can_short = False

    stoploss = -0.12
    use_custom_stoploss = False
    trailing_stop = False
    process_only_new_candles = True

    minimal_roi = {
        "0": 0.20,
        "30": 0.12,
        "60": 0.06,
        "90": 0,
    }

    startup_candle_count = 100
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

        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)
        macd = ta.MACD(dataframe)
        dataframe["macd"], dataframe["macd_signal"], dataframe["macd_hist"] = macd["macd"], macd["macdsignal"], macd["macdhist"]
        dataframe["ema50"] = ta.EMA(dataframe["close"], timeperiod=50)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        macro_ok = dataframe.get("btc_bull", True)

        entry = (
            macro_ok &
            (dataframe["adx"] > 25) &
            (dataframe["macd_hist"] > 0) &
            (dataframe["close"] > dataframe["ema50"])
        )
        dataframe.loc[entry, "enter_long"] = 1
        dataframe.loc[entry, "enter_tag"] = "trend_strength"
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        return dataframe
