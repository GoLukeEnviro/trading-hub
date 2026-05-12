"""
SimpleTrendEMA_v1 — 1h Trend Following Strategy

Design:
- 1h timeframe (reduces noise vs 15m)
- Only BTC/ETH/SOL (top 3 pairs, most liquid)
- EMA200 uptrend filter (only long when price > EMA200)
- RSI < 30 oversold entry within uptrend
- SL 2%, ROI 4%/2%/1%/0
- Proven design: trend filter protects against bear regimes
"""
import talib.abstract as ta
from freqtrade.strategy import IStrategy
from pandas import DataFrame


class SimpleTrendEMA_v1(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "1h"
    can_short = False

    stoploss = -0.02
    use_custom_stoploss = False
    trailing_stop = False

    minimal_roi = {
        "0": 0.04,      # 4% — immediate take profit
        "240": 0.02,    # 10d — 2%
        "720": 0.01,    # 30d — 1%
        "1440": 0,      # 60d — breakeven
    }

    startup_candle_count = 500  # Enough for EMA200

    # Limit trades — prevent overtrading
    max_open_trades = 2

    @property
    def protections(self):
        return [
            {"method": "CooldownPeriod", "stop_duration_candles": 12},  # 12h cooldown per pair
            {"method": "StoplossGuard", "lookback_period_candles": 24,
             "trade_limit": 2, "stop_duration_candles": 12,
             "only_per_pair": False, "only_per_side": True},
            {"method": "MaxDrawdown", "lookback_period_candles": 168,
             "trade_limit": 3, "stop_duration_candles": 24,
             "max_allowed_drawdown": 0.05},
        ]

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # EMA200 for trend filter
        dataframe["ema200"] = ta.EMA(dataframe["close"], timeperiod=200)
        # EMA50 for trend strength confirmation
        dataframe["ema50"] = ta.EMA(dataframe["close"], timeperiod=50)
        # RSI for entry timing
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Entry conditions:
        # 1. Price > EMA200 (major uptrend)
        # 2. RSI < 30 (oversold — potential bounce entry)
        # 3. EMA50 > EMA200 (healthy trend structure)
        entry_cond = (
            (dataframe["close"] > dataframe["ema200"]) &
            (dataframe["rsi"] < 30) &
            (dataframe["ema50"] > dataframe["ema200"])
        )
        dataframe.loc[entry_cond, "enter_long"] = 1
        dataframe.loc[entry_cond, "enter_tag"] = "trend_bounce"
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # No exit signals — let ROI + stoploss handle exits
        return dataframe
