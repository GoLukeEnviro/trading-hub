import numpy as np
import talib
import pandas as pd
from freqtrade.strategy import IStrategy
from pandas import DataFrame


class RebelLiquidation(IStrategy):
    """
    FreqAI Strategie mit Liquidations-Proxies als Features.
    Nutzt XGBoostClassifier fuer binaere Klassifikation.
    """

    timeframe = '5m'
    startup_candle_count: int = 40

    minimal_roi = {"0": 0.025}
    stoploss = -0.015
    trailing_stop = True
    trailing_stop_positive = 0.008
    trailing_stop_positive_offset = 0.012

    use_entry_signal = True

    def feature_engineering_expand_all(self, dataframe, period, **kwargs):
        dataframe['%-rsi-period'] = talib.RSI(dataframe['close'], timeperiod=period)
        dataframe['%-mfi-period'] = talib.MFI(dataframe['high'], dataframe['low'],
                                               dataframe['close'], dataframe['volume'],
                                               timeperiod=period)
        dataframe['%-adx-period'] = talib.ADX(dataframe['high'], dataframe['low'],
                                               dataframe['close'], timeperiod=period)
        dataframe['%-ema-period'] = talib.EMA(dataframe['close'], timeperiod=period)
        rolling_vol_mean = dataframe['volume'].rolling(period).mean()
        dataframe['%-vsr-period'] = dataframe['volume'] / (rolling_vol_mean + 1e-8)
        body_top = dataframe[['open', 'close']].max(axis=1)
        body_bot = dataframe[['open', 'close']].min(axis=1)
        candle_range = (dataframe['high'] - dataframe['low']).replace(0, np.nan)
        dataframe['%-upper-wick-ratio'] = (dataframe['high'] - body_top) / candle_range
        dataframe['%-lower-wick-ratio'] = (body_bot - dataframe['low']) / candle_range
        dataframe['%-body-ratio'] = (body_top - body_bot) / candle_range
        atr = talib.ATR(dataframe['high'], dataframe['low'], dataframe['close'], timeperiod=period)
        dataframe['%-vvr-period'] = dataframe['volume'] / (atr + 1e-8)
        dataframe['%-pct-move-period'] = dataframe['close'].pct_change(period)
        return dataframe

    def feature_engineering_expand_basic(self, dataframe, **kwargs):
        dataframe['%-pct-change'] = dataframe['close'].pct_change()
        dataframe['%-raw-volume'] = dataframe['volume']
        dataframe['%-raw-price'] = dataframe['close']
        dataframe['%-hl-spread'] = (dataframe['high'] - dataframe['low']) / dataframe['close']
        return dataframe

    def feature_engineering_standard(self, dataframe, **kwargs):
        dataframe['%-hour-of-day'] = (dataframe['date'].dt.hour + 1) / 25
        dataframe['%-day-of-week'] = (dataframe['date'].dt.dayofweek + 1) / 7
        dataframe['%-close-to-high'] = dataframe['close'] / dataframe['high'].rolling(24).max()
        dataframe['%-close-to-low'] = dataframe['close'] / dataframe['low'].rolling(24).min()
        return dataframe

    def set_freqai_targets(self, dataframe, **kwargs):
        self.freqai.class_names = ['down', 'up']
        dataframe['&s-up_or_down'] = np.where(
            dataframe['close'].shift(-12) > dataframe['close'] * 1.0005,
            'up', 'down'
        )
        return dataframe

    def populate_indicators(self, dataframe, metadata):
        dataframe = self.freqai.start(dataframe, metadata, self)
        return dataframe

    def populate_entry_trend(self, dataframe, metadata):
        dataframe.loc[
            (dataframe['&s-up_or_down'] == 'up') & (dataframe['do_predict'] == 1),
            'enter_long'
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe, metadata):
        dataframe.loc[
            (dataframe['&s-up_or_down'] == 'down') & (dataframe['do_predict'] == 1),
            'exit_long'
        ] = 1
        return dataframe