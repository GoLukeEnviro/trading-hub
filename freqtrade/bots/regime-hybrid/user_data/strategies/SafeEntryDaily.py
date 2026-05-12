# pragma pylint: disable=missing-docstring, invalid-name, pointless-string-statement
from freqtrade.strategy import IStrategy, DecimalParameter, IntParameter
from pandas import DataFrame
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib
import numpy as np


class SafeEntryDaily(IStrategy):
    """
    Strategy 4: SafeEntryDaily
    Pullback entries in confirmed uptrend.
    EMA50 > EMA200 (uptrend confirmed) + RSI pullback (40-55) + BTC regime.
    Waits for dips, never chases. Most conservative.
    """
    INTERFACE_VERSION = 3

    minimal_roi = {
        "0": 0.10,
        "1440": 0.05,
        "2880": 0.03,
        "4320": 0.01,
        "0": 0
    }

    stoploss = -0.05
    can_short = False
    timeframe = '1d'
    startup_candle_count = 250
    trailing_stop = False
    use_custom_stoploss = False

    rsi_floor = IntParameter(30, 45, default=40, space="buy")
    rsi_ceiling = IntParameter(50, 65, default=55, space="buy")
    pullback_pct = DecimalParameter(0.02, 0.08, default=0.04, space="buy")

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe['ema50'] = ta.EMA(dataframe['close'], timeperiod=50)
        dataframe['ema200'] = ta.EMA(dataframe['close'], timeperiod=200)
        dataframe['ema50_slope'] = dataframe['ema50'].diff(5)
        
        # Uptrend confirmation
        dataframe['uptrend_confirmed'] = (
            (dataframe['ema50'] > dataframe['ema200']) &
            (dataframe['ema50_slope'] > 0) &
            (dataframe['close'] > dataframe['ema50'])
        )
        
        # RSI
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        
        # Pullback detection: price dipped from recent high
        dataframe['high_5'] = dataframe['high'].rolling(5).max()
        dataframe['pullback_trigger'] = (
            (dataframe['high_5'] - dataframe['close']) / dataframe['high_5'] > self.pullback_pct.value
        )
        
        # Volume: increased on pullback = accumulation
        dataframe['volume_sma20'] = ta.SMA(dataframe['volume'], timeperiod=20)
        dataframe['volume_spike'] = dataframe['volume'] > dataframe['volume_sma20'] * 0.8

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
        
        # Safe entry: uptrend + pullback + RSI pullback zone + BTC regime
        dataframe['safe_entry'] = (
            (dataframe['uptrend_confirmed']) &
            (dataframe['pullback_trigger']) &
            (dataframe['rsi'] > self.rsi_floor.value) &
            (dataframe['rsi'] < self.rsi_ceiling.value)
        )

        # Exit: trend breaking down
        dataframe['trend_broken'] = (
            (dataframe['close'] < dataframe['ema200']) |
            ((dataframe['ema50'] < dataframe['ema200']) & (dataframe['rsi'] < 50))
        )

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe['safe_entry']) &
                (dataframe['macro_uptrend']) &
                (dataframe['volume_spike']) &
                (dataframe['volume'] > 0)
            ),
            ['enter_long', 'enter_tag']
        ] = (1, 'safe_entry_daily_long')

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe['trend_broken']) |
                (~dataframe['macro_uptrend'])
            ),
            ['exit_long', 'exit_tag']
        ] = (1, 'safe_entry_daily_exit')

        return dataframe
