# pragma pylint: disable=missing-docstring, invalid-name, pointless-string-statement
from freqtrade.strategy import IStrategy, DecimalParameter, IntParameter
from pandas import DataFrame
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib
import numpy as np


class TrendDaily(IStrategy):
    """
    Strategy 2: TrendDaily
    ADX-based trend strength filter + EMA50 confirmation + BTC regime.
    Enters when ADX > threshold in confirmed macro uptrend.
    """
    INTERFACE_VERSION = 3

    minimal_roi = {
        "0": 0.08,
        "1440": 0.04,
        "2880": 0.02,
        "4320": 0.01
    }

    stoploss = -0.05
    can_short = False
    timeframe = '1d'
    startup_candle_count = 250
    trailing_stop = False
    use_custom_stoploss = False

    # Hyperoptable params
    adx_threshold = IntParameter(18, 35, default=25, space="buy")
    ema_trend = IntParameter(30, 100, default=50, space="buy")

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe['ema_trend'] = ta.EMA(dataframe['close'], timeperiod=self.ema_trend.value)
        dataframe['ema_trend_slope'] = dataframe['ema_trend'].diff(3)
        dataframe['adx'] = ta.ADX(dataframe, timeperiod=14)
        dataframe['plus_di'] = ta.PLUS_DI(dataframe, timeperiod=14)
        dataframe['minus_di'] = ta.MINUS_DI(dataframe, timeperiod=14)
        
        # Volume spike detection
        dataframe['volume_sma20'] = ta.SMA(dataframe['volume'], timeperiod=20)
        dataframe['volume_ok'] = dataframe['volume'] > dataframe['volume_sma20'] * 0.5

        # BTC regime filter
        try:
            btc_df = self.dp.get_pair_dataframe("BTC/USDT:USDT", "1d")
            btc_df['btc_ema200'] = ta.EMA(btc_df['close'], timeperiod=200)
            dataframe['btc_ema200'] = btc_df['btc_ema200'].reindex(dataframe.index, method='ffill')
            dataframe['btc_close'] = btc_df['close'].reindex(dataframe.index, method='ffill')
        except Exception:
            dataframe['btc_ema200'] = 0
            dataframe['btc_close'] = 999999
        
        dataframe['macro_uptrend'] = dataframe['btc_close'] > dataframe['btc_ema200']

        # Entry conditions
        dataframe['trend_strong'] = (
            (dataframe['adx'] > self.adx_threshold.value) &
            (dataframe['plus_di'] > dataframe['minus_di']) &
            (dataframe['close'] > dataframe['ema_trend']) &
            (dataframe['ema_trend_slope'] > 0)
        )

        # Exit: trend weakening
        dataframe['trend_weak'] = (
            (dataframe['adx'] < 18) |
            ((dataframe['plus_di'] < dataframe['minus_di']) & (dataframe['adx'] > 20))
        )

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe['trend_strong']) &
                (dataframe['macro_uptrend']) &
                (dataframe['volume_ok']) &
                (dataframe['volume'] > 0)
            ),
            ['enter_long', 'enter_tag']
        ] = (1, 'trend_daily_long')

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe['trend_weak']) |
                (~dataframe['macro_uptrend'])
            ),
            ['exit_long', 'exit_tag']
        ] = (1, 'trend_daily_exit')

        return dataframe
