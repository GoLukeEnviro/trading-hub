"""
RegimeSwitchingHybrid_v6_Stable
A hybrid strategy that switches between Trend Following (ADX/EMA) 
and Mean Reversion (BB/RSI) based on market regime detection.
Timeframe: 15m
HTF Informative: 1h
Phase 19 - Fixed SL Trend + Narrowed Search

Phase 5: Tightened protections (MaxDrawdown 0.10→0.06, StoplossGuard +only_per_side,
         LowProfitPairs required_profit 0.00→-0.01). Added FleetGuard entry safety.
         stoploss=-0.08 is a failsafe; actual SL handled by custom_stoploss().
"""

import logging
import sys
from datetime import datetime, timedelta
from typing import Optional

import talib.abstract as ta
from freqtrade.strategy import IStrategy, IntParameter, DecimalParameter, BooleanParameter, merge_informative_pair
import freqtrade.vendor.qtpylib.indicators as qtpylib
from pandas import DataFrame

sys.path.insert(0, "/freqtrade/shared")
from primo_signal import primo_gate_allows
from fleetguard_v1 import FleetGuard, FleetGuardConfig

logger = logging.getLogger(__name__)

class RegimeSwitchingHybrid_v6_Stable(IStrategy):

    INTERFACE_VERSION = 3
    timeframe = "15m"
    informative_timeframe = "1h"
    
    # Strategy settings
    can_short = True
    
    # Base ROI (Phase 27 — realistic targets; old 6% was hit too rarely)
    minimal_roi = {
        "0": 0.015,
        "60": 0.008,
        "120": 0.004,
        "240": 0
    }

    # Failsafe stoploss — only triggers if custom_stoploss() fails.
    # Normal SL is ATR-based via custom_stoploss(). 8% emergency cap.
    stoploss = -0.08
    use_custom_stoploss = True
    trailing_stop = False # Handled by custom_stoploss

    startup_candle_count = 500

    # ---- FleetGuard v1 entry safety (conservative limits) ----
    _fleetguard = FleetGuard(FleetGuardConfig(
        max_open_trades=3,
        max_open_shorts=2,
        max_open_longs=2,
    ))

    @property
    def protections(self):
        return [
            {"method": "CooldownPeriod", "stop_duration_candles": 5},
            {"method": "StoplossGuard", "lookback_period_candles": 60, "trade_limit": 3, "stop_duration_candles": 60, "only_per_pair": False, "only_per_side": True},
            {"method": "MaxDrawdown", "lookback_period_candles": 480, "trade_limit": 20, "stop_duration_candles": 96, "max_allowed_drawdown": 0.06},
            {"method": "LowProfitPairs", "lookback_period_candles": 1440, "trade_limit": 2, "stop_duration_candles": 60, "required_profit": -0.01}
        ]

    # Hyperoptable parameters (Buy space)
    adx_rel_threshold = DecimalParameter(0.8, 1.4, default=1.0, space="buy")
    rsi_oversold = IntParameter(20, 40, default=20, space="buy")
    
    # ATR Multipliers (Sell space)
    # CHANGE 1 (Phase 27): Tightened atr_sl_trend — losses were 6.7x larger than wins
    atr_sl_trend = 2.5
    
    # CHANGE 2 (Phase 27): Tightened atr_sl_range — narrower stops for range trades
    atr_sl_range = DecimalParameter(1.5, 2.5, default=2.0, space="sell", optimize=True)
    
    # CHANGE 3 (Phase 19): Narrowed atr_tp_trend
    atr_tp_trend = DecimalParameter(0.5, 2.0, default=1.7, space="sell", optimize=True)
    
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
        pair = metadata.get("pair")
        long_gate = primo_gate_allows(pair, "long")
        
        # Trend Regime Pullback
        trend_long = (
            (dataframe['adx_rel'] > self.adx_rel_threshold.value) & 
            (dataframe['close'] > ema200_htf) & 
            (dataframe['close'] > dataframe['ema200']) & 
            (dataframe['close'] < dataframe['ema50']) & 
            (dataframe['rsi'] < 50) & 
            (dataframe['volume'] > 0) &
            long_gate
        )
        
        # Range Regime Reversion
        range_long = (
            (dataframe['adx_rel'] <= self.adx_rel_threshold.value) & 
            (dataframe['rsi'] < self.rsi_oversold.value) & 
            (dataframe['close'] < dataframe['bb_lowerband']) & 
            (dataframe['volume'] > 0) &
            long_gate
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

    def confirm_trade_entry(self, pair: str, order_type: str, amount: float,
                            rate: float, time_in_force: str, current_time: datetime,
                            entry_tag: Optional[str], side: str, **kwargs) -> bool:
        """FleetGuard entry safety check with real trade data."""
        # Gather real trade data from Trade persistence
        open_trades = []
        recent_closed = []
        current_drawdown = 0.0

        try:
            from freqtrade.persistence import Trade

            # Open trades with pair and side info
            for t in Trade.get_trades_proxy(is_open=True):
                open_trades.append({"pair": t.pair, "is_short": t.is_short})

            # Recent closed trades (last 24h) for pair/side loss locks
            cutoff = current_time - timedelta(hours=24)
            for t in Trade.get_trades_proxy(is_open=False):
                if t.close_date and t.close_date >= cutoff:
                    recent_closed.append({
                        "pair": t.pair,
                        "is_short": t.is_short,
                        "close_profit": t.close_profit or 0.0,
                    })

            # Calculate current drawdown from starting balance
            total_profit = Trade.get_total_closed_profit()
            starting_balance = self.wallets.get_starting_balance() if hasattr(self, 'wallets') and self.wallets else 1000.0
            if starting_balance > 0:
                current_drawdown = abs(min(0, total_profit / starting_balance))
        except Exception as e:
            logger.warning(f"FleetGuard data gathering fallback: {e}")
            # Safe fallback: no pair/side lock data, but still check max_open from dp
            try:
                for t in Trade.get_trades_proxy(is_open=True):
                    open_trades.append({"pair": t.pair, "is_short": t.is_short})
            except Exception:
                pass

        allowed, reason = self._fleetguard.check_entry(
            pair=pair, side=side, open_trades=open_trades,
            recent_closed_trades=recent_closed, current_drawdown_pct=current_drawdown
        )
        if not allowed:
            logger.info(f"FleetGuard REJECT: {pair} {side} — {reason}")
            return False
        return True

    def custom_stoploss(self, pair: str, trade, current_time, current_rate,
                        current_profit: float, **kwargs) -> float:
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe.empty:
            return self.stoploss
            
        last = dataframe.iloc[-1]
        atr_pct = last['atr_pct']
        
        adx_rel = last.get('adx_rel', 1.0)
        is_trend = adx_rel > self.adx_rel_threshold.value
        
        if is_trend:
            sl_distance = atr_pct * self.atr_sl_trend
            if current_profit > max(0.015, atr_pct * self.atr_tp_trend.value):
                return max(-sl_distance, current_profit - sl_distance)
        else:
            sl_distance = atr_pct * self.atr_sl_range.value
            
        return -sl_distance
