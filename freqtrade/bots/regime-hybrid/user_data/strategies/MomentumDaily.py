# pragma pylint: disable=missing-docstring, invalid-name, pointless-string-statement
from freqtrade.strategy import IStrategy, DecimalParameter, IntParameter
from pandas import DataFrame
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib
import numpy as np


class MomentumDaily(IStrategy):
    """
    Strategy 3: MomentumDaily
    RSI momentum + EMA200 confirmation + BTC regime filter.
    Enters when RSI crosses above 50 in macro uptrend.
    """
    INTERFACE_VERSION = 3

    minimal_roi = {
        "0": 0.08,
        "1440": 0.04,
        "2880": 0.02,
        "4320": 0.01,
        "0": 0
    }

    stoploss = -0.05
    can_short = False
    timeframe = '1d'
    startup_candle_count = 250
    trailing_stop = False
    use_custom_stoploss = False

    rsi_entry = IntParameter(40, 60, default=50, space="buy")
    rsi_exit = IntParameter(40, 70, default=50, space="sell")

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe['ema200'] = ta.EMA(dataframe['close'], timeperiod=200)
        dataframe['ema200_slope'] = dataframe['ema200'].diff(5)
        
        # RSI
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        
        # MACD for momentum confirmation
        macd = ta.MACD(dataframe)
        dataframe['macd'] = macd['macd']
        dataframe['macd_signal'] = macd['macdsignal']
        dataframe['macd_hist'] = macd['macdhist']
        
        # Volume check
        dataframe['volume_sma20'] = ta.SMA(dataframe['volume'], timeperiod=20)
        dataframe['volume_ok'] = dataframe['volume'] > dataframe['volume_sma20'] * 0.3

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

        # Momentum entry: RSI crossing above 50 with MACD confirmation
        dataframe['momentum_entry'] = (
            (dataframe['rsi'] > self.rsi_entry.value) &
            (dataframe['rsi'].shift(1) <= self.rsi_entry.value) &
            (dataframe['macd'] > dataframe['macd_signal']) &
            (dataframe['close'] > dataframe['ema200']) &
            (dataframe['ema200_slope'] > 0)
        )

        # Exit: RSI dropping below exit threshold, loss of momentum
        dataframe['momentum_exit'] = (
            (dataframe['rsi'] < self.rsi_exit.value) &
            (dataframe['macd'] < dataframe['macd_signal'])
        )

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe['momentum_entry']) &
                (dataframe['macro_uptrend']) &
                (dataframe['volume_ok']) &
                (dataframe['volume'] > 0)
            ),
            ['enter_long', 'enter_tag']
        ] = (1, 'momentum_daily_long')

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe['momentum_exit']) |
                (~dataframe['macro_uptrend'])
            ),
            ['exit_long', 'exit_tag']
        ] = (1, 'momentum_daily_exit')

        return dataframe
