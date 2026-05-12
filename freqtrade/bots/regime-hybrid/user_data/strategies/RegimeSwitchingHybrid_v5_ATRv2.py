"""
RegimeSwitchingHybrid_v5_ATRv2
A hybrid strategy that switches between Trend Following (ADX/EMA) 
and Mean Reversion (BB/RSI) based on market regime detection.
Timeframe: 15m
HTF Informative: 1h
Phase 18 - Relative ADX + ATR v2
"""

import logging
from datetime import datetime
from typing import Optional

import talib.abstract as ta
from freqtrade.strategy import IStrategy, IntParameter, DecimalParameter, BooleanParameter, merge_informative_pair
import freqtrade.vendor.qtpylib.indicators as qtpylib
from pandas import DataFrame

logger = logging.getLogger(__name__)

class RegimeSwitchingHybrid_v5_ATRv2(IStrategy):

    INTERFACE_VERSION = 3
    timeframe = "15m"
    informative_timeframe = "1h"
    
    # Strategy settings
    can_short = False
    
    # Base ROI (Locked)
    minimal_roi = {
        "0": 0.06,
        "60": 0.03,
        "120": 0.01,
        "240": 0
    }

    # Failsafe stoploss - real stoploss handled via custom_stoploss()
    stoploss = -0.99
    use_custom_stoploss = True
    trailing_stop = False # Handled by custom_stoploss

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
    # CHANGE 2: ADX Relative Threshold
    adx_rel_threshold = DecimalParameter(0.8, 1.4, default=1.0, space="buy")
    rsi_oversold = IntParameter(20, 40, default=20, space="buy")
    
    # ATR Multipliers (Sell space)
    # CHANGE 4: Extended ranges
    atr_sl_trend = DecimalParameter(2.0, 6.0, default=3.6, space="sell", optimize=True)
    atr_sl_range = DecimalParameter(1.5, 4.0, default=2.4, space="sell", optimize=True)
    # CHANGE 3: Lower minimum for TP trigger
    atr_tp_trend = DecimalParameter(0.3, 2.0, default=0.8, space="sell", optimize=True)
    
    # Fixed parameters
    rsi_overbought = 66

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
        # CHANGE 1: Relative ADX
        dataframe['adx_sma'] = dataframe['adx'].rolling(window=50).mean()
        dataframe['adx_rel'] = dataframe['adx'] / dataframe['adx_sma']
        
        dataframe['rsi'] = ta.RSI(dataframe)
        dataframe['ema50'] = ta.EMA(dataframe, timeperiod=50)
        dataframe['ema200'] = ta.EMA(dataframe, timeperiod=200)
        
        # ATR calculation for dynamic stops
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=14)
        dataframe['atr_pct'] = dataframe['atr'] / dataframe['close']
        
        bollinger = qtpylib.bollinger_bands(qtpylib.typical_price(dataframe), window=20, stds=2)
        dataframe['bb_lowerband'] = bollinger['lower']
        dataframe['bb_middleband'] = bollinger['mid']
        dataframe['bb_upperband'] = bollinger['upper']
        dataframe['bb_width'] = (dataframe['bb_upperband'] - dataframe['bb_lowerband']) / dataframe['bb_middleband']
        
        dataframe['volume_mean'] = dataframe['volume'].rolling(window=30).mean()
        
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        ema200_htf = dataframe[f'ema200_{self.informative_timeframe}']
        
        # Trend Regime Pullback
        # CHANGE 2: Using relative ADX condition
        trend_long = (
            (dataframe['adx_rel'] > self.adx_rel_threshold.value) & 
            (dataframe['close'] > ema200_htf) & 
            (dataframe['close'] > dataframe['ema200']) & 
            (dataframe['close'] < dataframe['ema50']) & 
            (dataframe['rsi'] < 50) & 
            (dataframe['volume'] > 0)
        )
        
        # Range Regime Reversion
        range_long = (
            (dataframe['adx_rel'] <= self.adx_rel_threshold.value) & 
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
        # Keep intact (logic from v3/v4)
        dataframe.loc[
            (dataframe['rsi'] > self.rsi_overbought) | 
            (dataframe['close'] > dataframe['bb_upperband']), 
            'exit_long'
        ] = 1
        return dataframe

    def custom_stoploss(self, pair: str, trade, current_time, current_rate,
                        current_profit: float, **kwargs) -> float:
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe.empty:
            return self.stoploss
            
        last = dataframe.iloc[-1]
        atr_pct = last['atr_pct']
        
        # CHANGE 1: Relative ADX Regime Detection
        adx_rel = last.get('adx_rel', 1.0)
        is_trend = adx_rel > self.adx_rel_threshold.value
        
        if is_trend:
            sl_distance = atr_pct * self.atr_sl_trend.value
            # Trailing trigger logic
            if current_profit > (atr_pct * self.atr_tp_trend.value):
                # Trail: lock in partial profit
                return max(-sl_distance, current_profit - sl_distance)
        else:
            sl_distance = atr_pct * self.atr_sl_range.value
            
        return -sl_distance
