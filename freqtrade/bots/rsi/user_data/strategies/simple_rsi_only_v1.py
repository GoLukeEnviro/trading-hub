"""
SimpleRSIOnly_v1 — QUARANTINED
Reines Mean-Reversion: RSI < 45 = Long, RSI > 55 = Short
Stoploss -3% | Trailing Stop aktiv | Lev 3x

QUARANTINE ACTIVE — RSI_QUARANTINE_MODE = True
Reason: Negative dry-run performance over 175 trades (-110.68 USDT total, avg -0.71%).
        Short overexposure identified. Worst single trade: -19.05%.
        All new entries blocked until strategy is reworked and quarantine lifted.
        Exit logic remains active to manage existing open positions.
"""

import logging
import sys

import talib.abstract as ta
from freqtrade.strategy import IStrategy, IntParameter
from pandas import DataFrame

sys.path.insert(0, "/freqtrade/shared")
from primo_signal import primo_gate_allows

logger = logging.getLogger(__name__)


class SimpleRSIOnly_v1(IStrategy):

    INTERFACE_VERSION = 3
    timeframe = "15m"
    can_short = True

    # =========================================================================
    # QUARANTINE FLAG — set to False to resume normal trading after rework
    # Reason: -110.68 USDT over 175 trades, short overexposure, worst -19.05%
    # =========================================================================
    RSI_QUARANTINE_MODE = True

    stoploss = -0.03

    minimal_roi = {
        "0": 0.02,
        "60": 0.01,
        "120": 0.005,
    }

    trailing_stop = True
    trailing_stop_positive = 0.01
    trailing_stop_positive_offset = 0.015
    trailing_only_offset_is_reached = True

    buy_rsi = IntParameter(30, 50, default=45, space="buy", optimize=True)
    short_rsi = IntParameter(50, 70, default=55, space="buy", optimize=True)
    sell_rsi = IntParameter(60, 85, default=70, space="sell", optimize=True)
    cover_rsi = IntParameter(15, 40, default=30, space="sell", optimize=True)

    @property
    def protections(self):
        return [
            {"method": "CooldownPeriod", "stop_duration_candles": 2},
            {"method": "StoplossGuard", "lookback_period_candles": 24, "trade_limit": 3, "stop_duration_candles": 8, "only_per_pair": False, "only_per_side": True},
            {"method": "MaxDrawdown", "lookback_period_candles": 48, "trade_limit": 10, "stop_duration_candles": 12, "max_allowed_drawdown": 0.06},
            {"method": "LowProfitPairs", "lookback_period_candles": 24, "trade_limit": 3, "stop_duration_candles": 12, "required_profit": -0.01, "only_per_pair": True, "only_per_side": True},
        ]

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # =====================================================================
        # QUARANTINE GATE — no new entries while RSI_QUARANTINE_MODE is True
        # Returns dataframe with no enter_long / enter_short signals set.
        # primo_signal import kept intact; exit logic completely untouched.
        # =====================================================================
        if self.RSI_QUARANTINE_MODE:
            return dataframe

        # LONG: RSI < 45 (Mean-Reversion, egal ob Trend)
        pair = metadata.get("pair")
        long_gate = primo_gate_allows(pair, "long")
        short_gate = primo_gate_allows(pair, "short")

        dataframe.loc[
            (dataframe["rsi"] < self.buy_rsi.value) & long_gate,
            ["enter_long", "enter_tag"],
        ] = (1, "rsi_long")

        # SHORT: RSI > 55 (Mean-Reversion, egal ob Trend)
        dataframe.loc[
            (dataframe["rsi"] > self.short_rsi.value) & short_gate,
            ["enter_short", "enter_tag"],
        ] = (1, "rsi_short")

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Exit logic ALWAYS active — manages existing open positions even in quarantine
        dataframe.loc[
            (dataframe["rsi"] > self.sell_rsi.value),
            ["exit_long", "exit_tag"],
        ] = (1, "rsi_exit_long")

        dataframe.loc[
            (dataframe["rsi"] < self.cover_rsi.value),
            ["exit_short", "exit_tag"],
        ] = (1, "rsi_exit_short")

        return dataframe

    def confirm_trade_entry(self, pair, order_type, amount, rate, time_in_force,
                            current_time, entry_tag, side, **kwargs):
        """Quarantine hard-block: no new entries at all while quarantined."""
        if self.RSI_QUARANTINE_MODE:
            logger.info(f"RSI QUARANTINE: blocking entry {pair} {side}")
            return False
        return True

    def leverage(self, pair, current_time, current_rate, proposed_leverage,
                 max_leverage, entry_tag, side, **kwargs) -> float:
        return 3.0
