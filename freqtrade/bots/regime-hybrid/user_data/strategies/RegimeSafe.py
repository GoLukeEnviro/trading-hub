# pragma pylint: disable=missing-docstring, invalid-name, pointless-string-statement
# flake8: noqa: F401
from freqtrade.strategy import IStrategy, DecimalParameter, IntParameter
from pandas import DataFrame
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib
from functools import reduce
import numpy as np


class RegimeSafe(IStrategy):
    """
    Strategy 1: RegimeSafe
    Daily EMA50/200 Crossover + BTC > EMA200 regime filter.
    Only trades when macro trend is bullish.
    """
    INTERFACE_VERSION = 3

    # ROI table: take 7% profit, scale down over time
    minimal_roi = {
        "0": 0.07,
        "1440": 0.03,
        "2880": 0.01,
        "4320": 0.005,
        "0": 0
    }

    # Stoploss: wide for daily timeframe
    stoploss = -0.05

    # Can short? No, regime filter is long-only
    can_short = False

    # Timeframe
    timeframe = '1d'

    # Startup candle count for indicators
    startup_candle_count = 250

    # No trailing stop - proven profit killer on crypto
    trailing_stop = False
    use_custom_stoploss = False

    # Hyperoptable parameters
    ema_short = IntParameter(20, 80, default=50, space="buy")
    ema_long = IntParameter(100, 300, default=200, space="buy")

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Main pair indicators
        dataframe['ema_short'] = ta.EMA(dataframe['close'], timeperiod=self.ema_short.value)
        dataframe['ema_long'] = ta.EMA(dataframe['close'], timeperiod=self.ema_long.value)
        dataframe['ema_short_slope'] = dataframe['ema_short'].diff(3)
        dataframe['ema_long_slope'] = dataframe['ema_long'].diff(5)
        dataframe['adx'] = ta.ADX(dataframe, timeperiod=14)

        # BTC regime filter
        if 'btc_data' not in self.__dict__:
            self.btc_data = {}
        
        try:
            btc_df = self.dp.get_pair_dataframe("BTC/USDT:USDT", "1d")
            btc_df['btc_ema200'] = ta.EMA(btc_df['close'], timeperiod=200)
            dataframe['btc_ema200'] = btc_df['btc_ema200'].reindex(dataframe.index, method='ffill')
            dataframe['btc_close'] = btc_df['close'].reindex(dataframe.index, method='ffill')
        except Exception:
            # Fallback: no BTC data = no regime filter
            dataframe['btc_ema200'] = 0
            dataframe['btc_close'] = 999999
        
        # Regime condition
        dataframe['macro_uptrend'] = dataframe['btc_close'] > dataframe['btc_ema200']
        
        # EMA crossover signal
        dataframe['ema_bullish'] = (
            (dataframe['ema_short'] > dataframe['ema_long']) &
            (dataframe['ema_short_slope'] > 0)
        )
        dataframe['ema_bearish'] = dataframe['ema_short'] < dataframe['ema_long']

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe['ema_bullish']) &
                (dataframe['macro_uptrend']) &
                (dataframe['adx'] > 20) &
                (dataframe['volume'] > 0)
            ),
            ['enter_long', 'enter_tag']
        ] = (1, 'regime_safe_long')

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe['ema_bearish']) |
                (~dataframe['macro_uptrend'])
            ),
            ['exit_long', 'exit_tag']
        ] = (1, 'regime_safe_exit')

        return dataframe
