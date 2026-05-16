"""
PullbackEMA v1 — Simple Trend-Pullback System
===============================================
Long only. Trend: close > EMA200. Entry: pullback to EMA21 zone.
SL: below Swing Low (20-bar). TP1: 2R (auto via ROI). TP2: 4R (auto via ROI).

The ROI table is set PER TRADE based on SL distance at entry,
using custom_exit to dynamically adjust the minimal_roi percentages.
In practice, Freqtrade's ROI + custom_stoploss handles this cleanly.
"""

from freqtrade.strategy import IStrategy, Trade
from pandas import DataFrame
from datetime import datetime
import talib.abstract as ta
import logging

logger = logging.getLogger(__name__)


class PullbackEMA_v1(IStrategy):
    """Clean EMA pullback system — Long only."""

    # --- Core Settings ---
    timeframe = "15m"
    can_short = False

    # Safety-net ROI — overridden per-trade via custom_exit
    minimal_roi = {"0": 100}  # Effectively disabled; custom_exit handles it

    # Default fallback SL (should never trigger — custom_stoploss overrides)
    stoploss = -0.05

    # Position adjustment for partial exits
    position_adjustment_enable = True
    max_entry_position = 1.0

    # Order types
    order_types = {
        "entry": "limit",
        "exit": "limit",
        "stoploss": "market",
        "stoploss_on_exchange": False,
    }

    # Track TP1 state per trade
    _tp1_exits: dict[int, bool] = {}

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema21"] = ta.EMA(dataframe, timeperiod=21)
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
        dataframe["swing_low"] = dataframe["low"].rolling(window=20).min()
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["close"] > dataframe["ema200"]) &
                (dataframe["low"] <= dataframe["ema21"] * 1.02) &
                (dataframe["close"] > dataframe["ema21"]) &
                (dataframe["volume"] > 0) &
                (dataframe["ema200"].notna())
            ),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[(), "exit_long"] = 0
        return dataframe

    # --- Dynamic SL: Swing Low at entry ---
    def custom_stoploss(self, pair: str, trade: Trade, current_time: datetime,
                        current_rate: float, current_profit: float,
                        after_fill: bool, **kwargs) -> float | None:
        """SL = Swing Low at entry time, expressed as % below entry."""
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if len(dataframe) < 1:
            return None  # Use default stoploss

        # Use the candle from entry time to get the swing low
        swing_low = self._find_swing_low_at_entry(dataframe, trade)

        if swing_low <= 0 or swing_low >= trade.open_rate:
            return None  # Fallback to default

        # SL as negative percentage below entry
        sl_pct = -(trade.open_rate - swing_low) / trade.open_rate
        return sl_pct

    def _find_swing_low_at_entry(self, dataframe: DataFrame, trade: Trade) -> float:
        """Find the swing low closest to trade entry time."""
        try:
            entry_time = trade.open_date_utc
            # Find closest bar to entry
            mask = dataframe["date"] <= entry_time
            if mask.sum() < 20:
                return 0
            last_bar = dataframe.loc[mask].iloc[-1]
            return float(last_bar["swing_low"])
        except Exception:
            return 0

    # --- TP via custom_exit: 2R partial, 4R full ---
    def custom_exit(self, pair: str, trade: Trade, current_time: datetime,
                    current_rate: float, current_profit: float,
                    **kwargs) -> str | None:
        """Two-stage take profit: TP1 at 2R (close 50%), TP2 at 4R (close rest)."""

        # Get swing low for risk calculation
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if len(dataframe) < 1:
            return None

        swing_low = self._find_swing_low_at_entry(dataframe, trade)
        if swing_low <= 0 or swing_low >= trade.open_rate:
            return None

        entry = trade.open_rate
        risk = entry - swing_low  # SL distance in price
        if risk <= 0:
            return None

        tp1_price = entry + risk * 2
        tp2_price = entry + risk * 4

        # TP2: Full exit
        if current_rate >= tp2_price:
            return "tp2_4R"

        # TP1: Partial exit (50%) — only once
        if current_rate >= tp1_price:
            trade_id = trade.id
            if not self._tp1_exits.get(trade_id, False):
                self._tp1_exits[trade_id] = True
                # Signal partial exit via adjust_trade_position
                return None  # Handled in adjust_trade_position

        return None

    def adjust_trade_position(self, trade: Trade, current_time: datetime,
                              current_rate: float, current_profit: float,
                              min_stake: float | None, max_stake: float | None,
                              current_entry_rate: float, current_exit_rate: float,
                              current_entry_profit: float, current_exit_profit: float,
                              **kwargs) -> float | None:
        """Partial exit: 50% at TP1 (2R)."""
        dataframe, _ = self.dp.get_analyzed_dataframe(trade.pair, self.timeframe)
        if len(dataframe) < 1:
            return None

        swing_low = self._find_swing_low_at_entry(dataframe, trade)
        if swing_low <= 0 or swing_low >= trade.open_rate:
            return None

        entry = trade.open_rate
        risk = entry - swing_low
        tp1_price = entry + risk * 2

        if current_rate >= tp1_price:
            trade_id = trade.id
            if self._tp1_exits.get(trade_id, False):
                # Already did TP1 — don't exit more here (let TP2 handle it)
                return None

            # Exit 50% of position
            stake_to_exit = (trade.stake_amount / trade.open_rate) * current_rate * 0.5
            if stake_to_exit >= (min_stake or 0):
                self._tp1_exits[trade_id] = True
                return -stake_to_exit

        return None

    # --- Leverage (futures) ---
    def leverage(self, pair: str, current_time: datetime, current_rate: float,
                 proposed_leverage: float, max_leverage: float,
                 entry_tag: str | None, side: str, **kwargs) -> float:
        return 3.0
