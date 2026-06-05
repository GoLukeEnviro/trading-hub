import numpy as np
import talib
from freqtrade.strategy import IStrategy


class RebelLiquidationWFTop15(IStrategy):
    """
    Temp walk-forward validation variant.
    Feature space is pruned toward the most important feature families from the
    latest importance analysis (EMA / ADX / RSI / MFI / pct-move / raw-price).
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
        dataframe['%-mfi-period'] = talib.MFI(
            dataframe['high'], dataframe['low'], dataframe['close'], dataframe['volume'], timeperiod=period
        )
        dataframe['%-adx-period'] = talib.ADX(dataframe['high'], dataframe['low'], dataframe['close'], timeperiod=period)
        dataframe['%-ema-period'] = talib.EMA(dataframe['close'], timeperiod=period)
        dataframe['%-pct-move-period'] = dataframe['close'].pct_change(period)
        return dataframe

    def feature_engineering_expand_basic(self, dataframe, **kwargs):
        dataframe['%-raw-price'] = dataframe['close']
        return dataframe

    def feature_engineering_standard(self, dataframe, **kwargs):
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
