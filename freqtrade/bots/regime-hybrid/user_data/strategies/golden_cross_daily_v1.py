"""
GoldenCrossDaily_v1 — Daily Trend Following

Entry: EMA50 crosses above EMA200 (golden cross)
Regime: BTC > EMA200 (bear market protection)
Exit: ROI/Stoploss only

Pairs: BTC/USDT, ETH/USDT, SOL/USDT
"""
import talib.abstract as ta
from freqtrade.strategy import IStrategy
from pandas import DataFrame


class GoldenCrossDaily_v1(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "1d"
    can_short = False

    stoploss = -0.12
    use_custom_stoploss = False
    trailing_stop = False
    process_only_new_candles = True

    minimal_roi = {
        "0": 0.25,      # 25% — quick strong move
        "30": 0.15,     # 30 days — 15%
        "60": 0.08,     # 60 days — 8%
        "90": 0,        # 90 days — breakeven
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
        # Get BTC data for macro regime filter
        if self.dp:
            btc_data = self.dp.get_pair_dataframe("BTC/USDT", "1d")
            btc_ema200 = ta.EMA(btc_data["close"], timeperiod=200)
            dataframe["btc_price"] = btc_data["close"]
            dataframe["btc_ema200"] = btc_ema200
            dataframe["btc_bull"] = dataframe["btc_price"] > dataframe["btc_ema200"]

        # Pair indicators
        dataframe["ema50"] = ta.EMA(dataframe["close"], timeperiod=50)
        dataframe["ema200"] = ta.EMA(dataframe["close"], timeperiod=200)
        dataframe["ema50_above_ema200"] = dataframe["ema50"] > dataframe["ema200"]
        dataframe["golden_cross"] = (
            (dataframe["ema50"] > dataframe["ema200"]) &
            (dataframe["ema50"].shift(1) <= dataframe["ema200"].shift(1))
        )

        # ADX for trend quality
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        macro_ok = dataframe.get("btc_bull", True)

        entry = (
            macro_ok &
            dataframe["golden_cross"] &
            (dataframe["adx"] > 20)
        )
        dataframe.loc[entry, "enter_long"] = 1
        dataframe.loc[entry, "enter_tag"] = "golden_cross"
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        return dataframe
