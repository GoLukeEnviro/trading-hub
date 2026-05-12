"""
RegimeSwitchingHybrid_v3_Final
A hybrid strategy that switches between Trend Following (ADX/EMA) 
and Mean Reversion (BB/RSI) based on market regime detection.
Timeframe: 15m
HTF Informative: 1h
Optimized via Phase 16 - Fixed ROI + Recursive Optimization
"""

import logging
from datetime import datetime
from typing import Optional

import talib.abstract as ta
from freqtrade.strategy import IStrategy, IntParameter, DecimalParameter, BooleanParameter, merge_informative_pair
import freqtrade.vendor.qtpylib.indicators as qtpylib
from pandas import DataFrame

logger = logging.getLogger(__name__)

class RegimeSwitchingHybrid_v3_Final(IStrategy):

    INTERFACE_VERSION = 3
    timeframe = "15m"
    informative_timeframe = "1h"
    
    # Strategy settings
    can_short = False
    
    # Base ROI (Fixed for Phase 16 as per instruction)
    minimal_roi = {
        "0": 0.06,
        "60": 0.03,
        "120": 0.01,
        "240": 0
    }

    # Best parameters from Main Hyperopt (400 epochs)
    stoploss = -0.026
    trailing_stop = True
    trailing_stop_positive = 0.248
    trailing_stop_positive_offset = 0.33
    trailing_only_offset_is_reached = True
    
    rsi_overbought = 66

    startup_candle_count = 500

    @property
    def protections(self):
        return [
            {"method": "CooldownPeriod", "stop_duration_candles": 5},
            {"method": "StoplossGuard", "lookback_period_candles": 60, "trade_limit": 3, "stop_duration_candles": 60, "only_per_pair": False},
            {"method": "MaxDrawdown", "lookback_period_candles": 480, "trade_limit": 20, "stop_duration_candles": 96, "max_allowed_drawdown": 0.10},
            {"method": "LowProfitPairs", "lookback_period_candles": 1440, "trade_limit": 2, "stop_duration_candles": 60, "required_profit": 0.00}
        ]

    # Hyperoptable parameters (Buy space)
    # Using defaults from the best Main Hyperopt run
    adx_threshold = IntParameter(20, 35, default=29, space="buy")
    rsi_oversold = IntParameter(20, 40, default=20, space="buy")
    
    def informative_pairs(self):
        pairs = self.dp.current_whitelist()
        return [(pair, self.informative_timeframe) for pair in pairs]

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        if not self.dp: return dataframe
        informative = self.dp.get_pair_dataframe(pair=metadata['pair'], timeframe=self.informative_timeframe)
        informative['ema200'] = ta.EMA(informative, timeperiod=200)
        informative['adx'] = ta.ADX(informative)
        informative['rsi'] = ta.RSI(informative)
        dataframe = merge_informative_pair(dataframe, informative, self.timeframe, self.informative_timeframe, ffill=True)
        
        # Local indicators
        dataframe['adx'] = ta.ADX(dataframe)
        dataframe['rsi'] = ta.RSI(dataframe)
        dataframe['ema50'] = ta.EMA(dataframe, timeperiod=50)
        dataframe['ema200'] = ta.EMA(dataframe, timeperiod=200)
        
        bollinger = qtpylib.bollinger_bands(qtpylib.typical_price(dataframe), window=20, stds=2)
        dataframe['bb_lowerband'] = bollinger['lower']
        dataframe['bb_middleband'] = bollinger['mid']
        dataframe['bb_upperband'] = bollinger['upper']
        dataframe['bb_width'] = (dataframe['bb_upperband'] - dataframe['bb_lowerband']) / dataframe['bb_middleband']
        
        dataframe['volume_mean'] = dataframe['volume'].rolling(window=30).mean()
        
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        adx_htf = dataframe[f'adx_{self.informative_timeframe}']
        ema200_htf = dataframe[f'ema200_{self.informative_timeframe}']
        
        # Trend Regime Pullback
        trend_long = (
            (adx_htf > self.adx_threshold.value) & 
            (dataframe['close'] > ema200_htf) & 
            (dataframe['close'] > dataframe['ema200']) & 
            (dataframe['close'] < dataframe['ema50']) & 
            (dataframe['rsi'] < 50) & 
            (dataframe['volume'] > 0)
        )
        
        # Range Regime Reversion
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
        dataframe.loc[
            (dataframe['rsi'] > self.rsi_overbought) | 
            (dataframe['close'] > dataframe['bb_upperband']), 
            'exit_long'
        ] = 1
        return dataframe
