"""
RegimeSwitchingHybrid_v2
A hybrid strategy that switches between Trend Following (ADX/EMA) 
and Mean Reversion (BB/RSI) based on market regime detection.
Timeframe: 15m
HTF Informative: 1h
"""

import logging
from datetime import datetime
from typing import Optional

import talib.abstract as ta
from freqtrade.strategy import IStrategy, IntParameter, DecimalParameter, merge_informative_pair
import freqtrade.vendor.qtpylib.indicators as qtpylib
from pandas import DataFrame

logger = logging.getLogger(__name__)

class RegimeSwitchingHybrid_v2(IStrategy):

    INTERFACE_VERSION = 3
    timeframe = "15m"
    informative_timeframe = "1h"
    
    # Strategy settings
    can_short = False  # Fixed to spot as per requirements
    stoploss = -0.10   # Protective hard stop
    
    minimal_roi = {
        "0": 0.05,
        "60": 0.02,
        "120": 0.01,
        "240": 0
    }

    startup_candle_count = 400

    @property
    def protections(self):
        return [
            {
                "method": "CooldownPeriod",
                "stop_duration_candles": 5
            },
            {
                "method": "StoplossGuard",
                "lookback_period_candles": 60,
                "trade_limit": 3,
                "stop_duration_candles": 60,
                "only_per_pair": False
            },
            {
                "method": "MaxDrawdown",
                "lookback_period_candles": 480,
                "trade_limit": 20,
                "stop_duration_candles": 96,
                "max_allowed_drawdown": 0.10
            },
            {
                "method": "LowProfitPairs",
                "lookback_period_candles": 1440,
                "trade_limit": 2,
                "stop_duration_candles": 60,
                "required_profit": 0.00
            }
        ]

    # Hyperoptable parameters
    adx_threshold = IntParameter(20, 30, default=25, space="buy")
    rsi_oversold = IntParameter(25, 40, default=30, space="buy")
    rsi_overbought = IntParameter(60, 75, default=70, space="sell")

    def informative_pairs(self):
        pairs = self.dp.current_whitelist()
        return [(pair, self.informative_timeframe) for pair in pairs]

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Get HTF indicators
        if not self.dp:
            return dataframe
        
        informative = self.dp.get_pair_dataframe(pair=metadata['pair'], timeframe=self.informative_timeframe)
        
        # HTF: EMA 200 and ADX for overall market regime
        informative['ema200'] = ta.EMA(informative, timeperiod=200)
        informative['adx'] = ta.ADX(informative)
        informative['rsi'] = ta.RSI(informative)
        
        # Merge HTF into 15m dataframe
        dataframe = merge_informative_pair(dataframe, informative, self.timeframe, self.informative_timeframe, ffill=True)
        
        # Base indicators (15m)
        dataframe['adx'] = ta.ADX(dataframe)
        dataframe['rsi'] = ta.RSI(dataframe)
        dataframe['ema50'] = ta.EMA(dataframe, timeperiod=50)
        dataframe['ema200'] = ta.EMA(dataframe, timeperiod=200)
        
        # Bollinger Bands
        bollinger = qtpylib.bollinger_bands(qtpylib.typical_price(dataframe), window=20, stds=2)
        dataframe['bb_lowerband'] = bollinger['lower']
        dataframe['bb_middleband'] = bollinger['mid']
        dataframe['bb_upperband'] = bollinger['upper']
        dataframe['bb_width'] = (dataframe['bb_upperband'] - dataframe['bb_lowerband']) / dataframe['bb_middleband']
        
        # Volume
        dataframe['volume_mean'] = dataframe['volume'].rolling(window=30).mean()
        
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Regime detection logic
        # Trend Regime: HTF ADX > threshold AND Price > HTF EMA200
        # Range Regime: HTF ADX <= threshold
        
        adx_htf = dataframe[f'adx_{self.informative_timeframe}']
        ema200_htf = dataframe[f'ema200_{self.informative_timeframe}']
        
        # Condition 1: Trend Pullback (Buy in uptrend when price dips to EMA50 on 15m)
        trend_long = (
            (adx_htf > self.adx_threshold.value) &
            (dataframe['close'] > ema200_htf) &
            (dataframe['close'] > dataframe['ema200']) &
            (dataframe['close'] < dataframe['ema50']) &
            (dataframe['rsi'] < 50) &
            (dataframe['volume'] > 0)
        )
        
        # Condition 2: Range Reversion (Buy when price hits BB lowerband in sideways market)
        range_long = (
            (adx_htf <= self.adx_threshold.value) &
            (dataframe['rsi'] < self.rsi_oversold.value) &
            (dataframe['close'] < dataframe['bb_lowerband']) &
            (dataframe['volume'] > 0)
        )
        
        dataframe.loc[trend_long, 'enter_long'] = 1
        dataframe.loc[trend_long, 'enter_tag'] = 'trend_pullback'
        
        dataframe.loc[range_long, 'enter_long'] = 1
        dataframe.loc[range_long, 'enter_tag'] = 'range_reversion'
        
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Exit when RSI is overbought or price hits upper BB
        dataframe.loc[
            (dataframe['rsi'] > self.rsi_overbought.value) |
            (dataframe['close'] > dataframe['bb_upperband']),
            'exit_long'
        ] = 1
        
        return dataframe
