"""
SafeEntry_v1 — Ultra-Conservative Strategy

Core insight: Over 24 months (May 2024-May 2026), 
BTC went from ~$60K to ~$80K (+34%), BUT with a -51% crash Oct 2025-Mar 2026.
The ONLY way to survive is regime-filtered entries.

Entry: RSI < 25 on 1h (deep oversold) + price > EMA200 + ADX < 20 (mean reversion)

Exit: ROI 4%/2%/1%/0, SL 3%
"""
import talib.abstract as ta
from freqtrade.strategy import IStrategy
from pandas import DataFrame


class SafeEntry_v1(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "1h"
    can_short = False

    stoploss = -0.03
    use_custom_stoploss = False
    trailing_stop = False

    minimal_roi = {
        "0": 0.04,      # 4%
        "24": 0.02,     # 1d
        "96": 0.01,     # 4d
        "240": 0,       # 10d
    }

    startup_candle_count = 200
    max_open_trades = 2

    @property
    def protections(self):
        return [
            {"method": "CooldownPeriod", "stop_duration_candles": 48},  # 2d cooldown
            {"method": "StoplossGuard", "lookback_period_candles": 168,  # 7d
             "trade_limit": 1, "stop_duration_candles": 168,
             "only_per_pair": False, "only_per_side": True},
        ]

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["ema200"] = ta.EMA(dataframe["close"], timeperiod=200)
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # VERY selective: Deep oversold + major uptrend + no trend (mean reversion setup)
        entry = (
            (dataframe["rsi"] < 25) &           # Deep oversold (stronger than <30)
            (dataframe["close"] > dataframe["ema200"]) &  # In macro uptrend
            (dataframe["adx"] < 25)             # Not in strong downtrend
        )
        dataframe.loc[entry, "enter_long"] = 1
        dataframe.loc[entry, "enter_tag"] = "deep_bounce"
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        return dataframe
