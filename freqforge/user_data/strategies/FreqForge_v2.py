"""
FreqForge_v2 — Schlanke Baseline (korrigiert)
Basiert auf FreqForge_Override (v1). Ballast entfernt.
"""
import logging
from datetime import datetime
from typing import Optional
import talib.abstract as ta
from freqtrade.strategy import IStrategy, IntParameter, merge_informative_pair
import freqtrade.vendor.qtpylib.indicators as qtpylib
from pandas import DataFrame
import sys
sys.path.insert(0, "/freqtrade/shared")
from primo_signal import primo_gate_allows

logger = logging.getLogger(__name__)

class FreqForge_v2(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "15m"
    informative_timeframe = "1h"
    can_short = False
    minimal_roi = {"0": 0.085, "45": 0.045, "90": 0.02, "180": 0}
    stoploss = -0.09
    use_custom_stoploss = False
    trailing_stop = False
    startup_candle_count = 500

    @property
    def protections(self):
        return [
            {"method": "CooldownPeriod", "stop_duration_candles": 5},
            {"method": "StoplossGuard", "lookback_period_candles": 60, "trade_limit": 3, "stop_duration_candles": 60, "only_per_pair": False, "only_per_side": True},
            {"method": "MaxDrawdown", "lookback_period_candles": 480, "trade_limit": 20, "stop_duration_candles": 96, "max_allowed_drawdown": 0.06},
            {"method": "LowProfitPairs", "lookback_period_candles": 1440, "trade_limit": 2, "stop_duration_candles": 60, "required_profit": -0.01},
        ]

    adx_threshold = IntParameter(20, 28, default=22, space="buy")
    rsi_oversold = IntParameter(20, 30, default=25, space="buy")
    rsi_pullback_max = IntParameter(40, 55, default=50, space="buy")

    def informative_pairs(self):
        pairs = self.dp.current_whitelist()
        return [(pair, self.informative_timeframe) for pair in pairs]

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        if not self.dp:
            return dataframe
        pair = metadata.get("pair", "UNKNOWN")
        informative = self.dp.get_pair_dataframe(pair=pair, timeframe=self.informative_timeframe)
        informative['ema200'] = ta.EMA(informative, timeperiod=200)
        informative['ema50'] = ta.EMA(informative, timeperiod=50)
        informative['adx'] = ta.ADX(informative)
        dataframe = merge_informative_pair(dataframe, informative, self.timeframe, self.informative_timeframe, ffill=True)
        dataframe['adx'] = ta.ADX(dataframe)
        dataframe['adx_sma'] = dataframe['adx'].rolling(window=50).mean()
        dataframe['rsi'] = ta.RSI(dataframe)
        dataframe['ema50'] = ta.EMA(dataframe, timeperiod=50)
        dataframe['ema200'] = ta.EMA(dataframe, timeperiod=200)
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=14)
        dataframe['atr_pct'] = dataframe['atr'] / dataframe['close']
        bollinger = qtpylib.bollinger_bands(qtpylib.typical_price(dataframe), window=20, stds=2)
        dataframe['bb_lowerband'] = bollinger['lower']
        dataframe['volume_mean'] = dataframe['volume'].rolling(window=30).mean()
        dataframe['volume_ratio'] = dataframe['volume'] / dataframe['volume_mean']
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        ema200_htf = dataframe[f'ema200_{self.informative_timeframe}']
        ema50_htf = dataframe[f'ema50_{self.informative_timeframe}']
        pair = metadata.get("pair")
        long_gate = primo_gate_allows(pair, "long")
        trend_long = (
            (dataframe['adx'] > self.adx_threshold.value) &
            (dataframe['close'] > ema200_htf) &
            (dataframe['close'] > dataframe['ema200']) &
            (dataframe['close'] < dataframe['ema50']) &
            (dataframe['close'] > ema50_htf * 0.98) &
            (dataframe['rsi'] < self.rsi_pullback_max.value) &
            (dataframe['volume'] > 0.8 * dataframe['volume_mean']) &
            long_gate
        )
        range_long = (
            (dataframe['adx'] <= self.adx_threshold.value) &
            (dataframe['rsi'] < self.rsi_oversold.value) &
            (dataframe['close'] < dataframe['bb_lowerband']) &
            (dataframe['volume'] > 0.8 * dataframe['volume_mean']) &
            long_gate
        )
        dataframe.loc[trend_long, 'enter_long'] = 1
        dataframe.loc[trend_long, 'enter_tag'] = 'trend_pullback_v2'
        dataframe.loc[~trend_long & range_long, 'enter_long'] = 1
        dataframe.loc[~trend_long & range_long, 'enter_tag'] = 'range_reversion_v2'
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        return dataframe

    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float,
                            time_in_force: str, current_time: datetime, entry_tag: Optional[str],
                            side: str, **kwargs) -> bool:
        return True
