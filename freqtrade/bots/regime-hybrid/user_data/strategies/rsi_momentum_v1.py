"""
RSIMomentum_v1 — 1h Momentum Breakout Strategy

Key insight from 5 failed strategies:
- Buying oversold (RSI < 30) catches falling knives, not bounces
- The edge is in buying STRENGTH, not weakness
- Enter when RSI crosses above 50 (momentum shift) with ADX confirmation

Design:
- 1h timeframe
- Top 3 pairs: BTC, ETH, SOL
- RSI crosses above 50 from below (bullish momentum shift)
- ADX > 20 (trend strength, not chop)
- SL 3% (room for noise on 1h)
- ROI 8%/4%/2%/0 (aggressive targets)
"""
import talib.abstract as ta
from freqtrade.strategy import IStrategy
from pandas import DataFrame


class RSIMomentum_v1(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "1h"
    can_short = False

    stoploss = -0.03
    use_custom_stoploss = False
    trailing_stop = False

    minimal_roi = {
        "0": 0.08,      # 8% — quick strong move
        "120": 0.04,    # 5d — 4%
        "480": 0.02,    # 20d — 2%
        "960": 0,       # 40d — breakeven
    }

    startup_candle_count = 50  # enough for RSI14 + ADX14
    max_open_trades = 2

    @property
    def protections(self):
        return [
            {"method": "CooldownPeriod", "stop_duration_candles": 24},  # 24h cooldown
            {"method": "StoplossGuard", "lookback_period_candles": 48,
             "trade_limit": 2, "stop_duration_candles": 24,
             "only_per_pair": False, "only_per_side": True},
        ]

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["rsi_ema"] = ta.EMA(dataframe["rsi"], timeperiod=7)
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)
        dataframe["ema50"] = ta.EMA(dataframe["close"], timeperiod=50)
        dataframe["ema200"] = ta.EMA(dataframe["close"], timeperiod=200)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Entry: RSI crosses above 50 (bullish momentum shift)
        # with ADX > 20 (trend, not chop)
        # and price > EMA50 (short-term uptrend)
        entry_cond = (
            (dataframe["rsi"] > 50) &
            (dataframe["rsi"] > dataframe["rsi_ema"]) &  # RSI rising
            (dataframe["adx"] > 20) &
            (dataframe["close"] > dataframe["ema50"])
        )
        dataframe.loc[entry_cond, "enter_long"] = 1
        dataframe.loc[entry_cond, "enter_tag"] = "rsi_momentum"
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        return dataframe
