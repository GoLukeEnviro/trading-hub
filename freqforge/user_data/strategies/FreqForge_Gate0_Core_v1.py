"""
FreqForge_Gate0_Core_v1 — deterministic research variant (C5.3 corrective).

Derived from FreqForge_Override Baseline v1 at commit cef26c8.
Modified for deterministic Gate-0 evaluation:
- Primo signals: removed entirely
- FleetRiskManager: removed entirely
- AI/Shadow/LLM paths: removed entirely
- sys.path manipulation: removed entirely
- File I/O (shadow logging): removed entirely
- confirm_trade_entry: removed entirely (inherits IStrategy default)
- bot_loop_start: removed entirely (inherits IStrategy default)
- confirm_trade_entry is deterministic and performs no I/O

Only deterministic candle/indicator logic is retained.
Canonical evaluation reference only — NOT for live deployment.
"""

import logging
from datetime import datetime
from typing import ClassVar

import freqtrade.vendor.qtpylib.indicators as qtpylib
import talib.abstract as ta
from freqtrade.strategy import (
    DecimalParameter,
    IntParameter,
    IStrategy,
    merge_informative_pair,
)
from pandas import DataFrame

logger = logging.getLogger(__name__)


class FreqForge_Gate0_Core_v1(IStrategy):

    INTERFACE_VERSION = 3
    timeframe = "15m"
    informative_timeframe = "1h"
    can_short = True  # PAPER-TRADING OVERRIDE (2026-05-17) — siehe SOUL.md

    minimal_roi: ClassVar[dict[str, float]] = {
        "0": 0.060,
        "180": 0.040,
        "480": 0.025,
        "960": 0.015,
    }
    stoploss = -0.050
    use_custom_stoploss = True
    trailing_stop = False

    startup_candle_count = 500

    @property
    def protections(self):
        return [
            {"method": "CooldownPeriod", "stop_duration_candles": 5},
            {
                "method": "StoplossGuard",
                "lookback_period_candles": 60,
                "trade_limit": 3,
                "stop_duration_candles": 60,
                "only_per_pair": False,
                "only_per_side": True,
            },
            {
                "method": "MaxDrawdown",
                "lookback_period_candles": 480,
                "trade_limit": 20,
                "stop_duration_candles": 96,
                "max_allowed_drawdown": 0.06,
            },
            {
                "method": "LowProfitPairs",
                "lookback_period_candles": 1440,
                "trade_limit": 2,
                "stop_duration_candles": 60,
                "required_profit": -0.01,
            },
        ]

    adx_rel_threshold = DecimalParameter(0.75, 1.20, default=0.90, space="buy")
    rsi_oversold = IntParameter(24, 42, default=32, space="buy")

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        self._regime_histories: dict = {}

    def _get_stable_regime(self, pair: str, current_regime: str) -> str:
        """2-cycle hysteresis per pair.

        Uses entry-time-only data: only the current and previous candle
        are considered, preventing lookahead from post-entry candles.
        """
        if pair not in self._regime_histories:
            self._regime_histories[pair] = []
        history = self._regime_histories[pair]
        history.append(current_regime)
        if len(history) > 2:
            history.pop(0)
        if len(history) == 2 and history[0] == history[1]:
            return history[1]
        return history[0] if history else "unknown"

    def informative_pairs(self):
        pairs = self.dp.current_whitelist()
        return [(pair, self.informative_timeframe) for pair in pairs]

    def _build_v04_signal_layer(self, dataframe: DataFrame, pair: str) -> None:
        """Pre-compute v0.4 signals as vectorized columns.

        Uses per-pair regime tracking with entry-time-only data.
        No AI override, no shadow state, no external signal injection.
        """
        dataframe["prev_close"] = dataframe["close"].shift(1)

        # Path 1: Mean Reversion
        rsi_buy = dataframe["rsi"] <= 30
        rsi_sell = dataframe["rsi"] >= 70
        mean_rev_active = rsi_buy | rsi_sell

        # Path 2: Trend Following
        trend_active = (
            (dataframe["adx"] > 22)
            & dataframe["ema50"].notna()
            & dataframe["ema200"].notna()
        )
        trend_buy = trend_active & (dataframe["ema50"] > dataframe["ema200"])
        trend_sell = trend_active & (dataframe["ema50"] <= dataframe["ema200"])

        # Path 3: Breakout
        breakout_active = (dataframe["bb_width"] < 0.5) & (
            dataframe["volume_ratio"] > 1.05
        )
        breakout_buy = breakout_active & dataframe["close"].gt(dataframe["prev_close"])
        breakout_sell = breakout_active & dataframe["close"].le(dataframe["prev_close"])

        # Initialize all as WATCH
        dataframe["v04_action"] = "WATCH"
        dataframe["v04_confidence"] = 0.0
        dataframe["v04_strategy"] = None
        dataframe["v04_regime"] = "unknown"

        # Per-pair stable regime (last candle only — entry-time data)
        if len(dataframe) > 0:
            last_row = dataframe.iloc[-1]
            adx_val = last_row.get("adx", 0)
            raw_regime = "trending" if adx_val > 22 else "ranging"
            stable_regime = self._get_stable_regime(pair, raw_regime)
            dataframe["v04_regime"] = stable_regime

        # Priority: MEAN_REVERSION > TREND > BREAKOUT > WATCH
        mr_buy_mask = mean_rev_active & rsi_buy
        mr_sell_mask = mean_rev_active & rsi_sell
        trend_buy_mask = trend_buy & ~mean_rev_active
        trend_sell_mask = trend_sell & ~mean_rev_active
        breakout_buy_mask = breakout_buy & ~mean_rev_active & ~trend_buy
        breakout_sell_mask = breakout_sell & ~mean_rev_active & ~trend_sell

        # MEAN REVERSION
        dataframe.loc[mr_buy_mask, "v04_action"] = "BUY"
        dataframe.loc[mr_buy_mask, "v04_strategy"] = "MEAN_REVERSION"
        ext = (dataframe.loc[mr_buy_mask, "rsi"] - 30).abs() / 10
        dataframe.loc[mr_buy_mask, "v04_confidence"] = ext.clip(0, 1).round(4)

        dataframe.loc[mr_sell_mask, "v04_action"] = "SELL"
        dataframe.loc[mr_sell_mask, "v04_strategy"] = "MEAN_REVERSION"
        ext = (dataframe.loc[mr_sell_mask, "rsi"] - 70).abs() / 10
        dataframe.loc[mr_sell_mask, "v04_confidence"] = ext.clip(0, 1).round(4)

        # TREND FOLLOWING
        dataframe.loc[trend_buy_mask, "v04_action"] = "BUY"
        dataframe.loc[trend_buy_mask, "v04_strategy"] = "TREND_FOLLOWING"
        adx_raw = ((dataframe.loc[trend_buy_mask, "adx"] - 22) / 18).clip(0, 1)
        rsi_factor = (
            (dataframe.loc[trend_buy_mask, "rsi"] >= 35)
            & (dataframe.loc[trend_buy_mask, "rsi"] <= 65)
        ).astype(float) * 0.3 + 0.7
        vol_factor = (
            1.1 * (dataframe.loc[trend_buy_mask, "volume_ratio"] > 1.1).astype(float)
            + 0.9 * (dataframe.loc[trend_buy_mask, "volume_ratio"] <= 1.1).astype(float)
        )
        dataframe.loc[trend_buy_mask, "v04_confidence"] = (
            (adx_raw * rsi_factor * vol_factor).clip(0, 1).round(4)
        )

        dataframe.loc[trend_sell_mask, "v04_action"] = "SELL"
        dataframe.loc[trend_sell_mask, "v04_strategy"] = "TREND_FOLLOWING"
        adx_raw = ((dataframe.loc[trend_sell_mask, "adx"] - 22) / 18).clip(0, 1)
        rsi_factor = (
            (dataframe.loc[trend_sell_mask, "rsi"] >= 35)
            & (dataframe.loc[trend_sell_mask, "rsi"] <= 65)
        ).astype(float) * 0.3 + 0.7
        vol_factor = (
            1.1 * (dataframe.loc[trend_sell_mask, "volume_ratio"] > 1.1).astype(float)
            + 0.9
            * (dataframe.loc[trend_sell_mask, "volume_ratio"] <= 1.1).astype(float)
        )
        dataframe.loc[trend_sell_mask, "v04_confidence"] = (
            (adx_raw * rsi_factor * vol_factor).clip(0, 1).round(4)
        )

        # BREAKOUT
        dataframe.loc[breakout_buy_mask, "v04_action"] = "BUY"
        dataframe.loc[breakout_buy_mask, "v04_strategy"] = "BREAKOUT"
        squeeze = ((0.5 - dataframe.loc[breakout_buy_mask, "bb_width"]) / 0.4).clip(
            0, 1
        )
        vol = (dataframe.loc[breakout_buy_mask, "volume_ratio"] / 1.5).clip(0, 1)
        dataframe.loc[breakout_buy_mask, "v04_confidence"] = (
            (0.5 * squeeze + 0.5 * vol).clip(0, 1).round(4)
        )

        dataframe.loc[breakout_sell_mask, "v04_action"] = "SELL"
        dataframe.loc[breakout_sell_mask, "v04_strategy"] = "BREAKOUT"
        squeeze = ((0.5 - dataframe.loc[breakout_sell_mask, "bb_width"]) / 0.4).clip(
            0, 1
        )
        vol = (dataframe.loc[breakout_sell_mask, "volume_ratio"] / 1.5).clip(0, 1)
        dataframe.loc[breakout_sell_mask, "v04_confidence"] = (
            (0.5 * squeeze + 0.5 * vol).clip(0, 1).round(4)
        )

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        if not self.dp:
            return dataframe

        pair = metadata.get("pair", "UNKNOWN")

        informative = self.dp.get_pair_dataframe(
            pair=pair, timeframe=self.informative_timeframe
        )
        informative["ema200"] = ta.EMA(informative, timeperiod=200)
        informative["adx"] = ta.ADX(informative)
        informative["rsi"] = ta.RSI(informative)
        dataframe = merge_informative_pair(
            dataframe,
            informative,
            self.timeframe,
            self.informative_timeframe,
            ffill=True,
        )

        dataframe["adx"] = ta.ADX(dataframe)
        dataframe["adx_sma"] = dataframe["adx"].rolling(window=50).mean()
        dataframe["adx_rel"] = dataframe["adx"] / dataframe["adx_sma"]

        dataframe["rsi"] = ta.RSI(dataframe)
        dataframe["ema50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)

        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)
        dataframe["atr_pct"] = dataframe["atr"] / dataframe["close"]

        bollinger = qtpylib.bollinger_bands(
            qtpylib.typical_price(dataframe), window=20, stds=2
        )
        dataframe["bb_lowerband"] = bollinger["lower"]
        dataframe["bb_middleband"] = bollinger["mid"]
        dataframe["bb_upperband"] = bollinger["upper"]
        dataframe["bb_width"] = (bollinger["upper"] - bollinger["lower"]) / bollinger[
            "mid"
        ]

        dataframe["volume_mean"] = dataframe["volume"].rolling(window=30).mean()
        dataframe["volume_ratio"] = dataframe["volume"] / dataframe["volume_mean"]

        # v0.4 signal pre-computation (vectorized, per-pair regime tracking)
        self._build_v04_signal_layer(dataframe, pair)

        return dataframe

    def custom_stoploss(
        self,
        pair: str,
        trade,
        current_time,
        current_rate,
        current_profit: float,
        after_fill: bool,
        **kwargs,
    ) -> float:
        """Wider profit protection without the old trailing-stop choke.

        - Default hard floor stays at -5.0%
        - Only tighten once profit is meaningful (> 4%)
        - Losers are only accelerated after hours of dead money
        """
        trade_duration = (current_time - trade.open_date_utc).total_seconds() / 60

        if current_profit >= 0.07:
            return -0.010
        if current_profit >= 0.04:
            return -0.015
        if trade_duration > 360 and current_profit < -0.015:
            return -0.030
        if trade_duration > 1080 and current_profit < 0:
            return -0.020

        return -0.050

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        ema200_htf = dataframe[f"ema200_{self.informative_timeframe}"]

        # --- Strategy-native LONG conditions ---
        trend_long = (
            (dataframe["adx_rel"] > self.adx_rel_threshold.value)
            & (dataframe["close"] > (ema200_htf * 0.995))
            & (dataframe["close"] > (dataframe["ema200"] * 0.995))
            & (dataframe["close"] < (dataframe["ema50"] * 1.015))
            & (dataframe["rsi"] < 56)
            & (dataframe["rsi"] > 28)
            & (dataframe["volume_ratio"] > 0.85)
        )

        range_long = (
            (dataframe["adx_rel"] <= (self.adx_rel_threshold.value * 1.05))
            & (dataframe["rsi"] < self.rsi_oversold.value)
            & (dataframe["close"] <= (dataframe["bb_lowerband"] * 1.01))
            & (dataframe["volume_ratio"] > 0.75)
        )

        long_entries = trend_long | range_long
        dataframe.loc[long_entries, "enter_long"] = 1
        dataframe.loc[range_long, "enter_tag"] = "range_reversion_long"
        dataframe.loc[trend_long, "enter_tag"] = "trend_pullback_long"

        # --- SHORT ENTRY LOGIC ---
        trend_short = (
            (dataframe["adx_rel"] > self.adx_rel_threshold.value)
            & (dataframe["close"] < (ema200_htf * 1.005))
            & (dataframe["close"] < (dataframe["ema200"] * 1.005))
            & (dataframe["close"] > (dataframe["ema50"] * 0.985))
            & (dataframe["rsi"] > 44)
            & (dataframe["rsi"] < 72)
            & (dataframe["volume_ratio"] > 0.85)
        )

        range_short = (
            (dataframe["adx_rel"] <= (self.adx_rel_threshold.value * 1.05))
            & (dataframe["rsi"] > (100 - self.rsi_oversold.value))
            & (dataframe["close"] >= (dataframe["bb_upperband"] * 0.99))
            & (dataframe["volume_ratio"] > 0.75)
        )

        short_entries = trend_short | range_short
        dataframe.loc[short_entries, "enter_short"] = 1
        dataframe.loc[trend_short, "enter_tag"] = "trend_pullback_short"
        dataframe.loc[range_short, "enter_tag"] = "range_reversion_short"

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Nur ROI + custom_exit + Hard Stoploss — keine Exit-Signale im Candle-Frame
        return dataframe

    def custom_exit(
        self,
        pair: str,
        trade,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        **kwargs,
    ):
        trade_duration = (current_time - trade.open_date_utc).total_seconds() / 60
        try:
            dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            if dataframe is None or dataframe.empty:
                return None
            last = dataframe.iloc[-1]
            rsi = float(last.get("rsi", 50.0))
            adx_rel = float(last.get("adx_rel", 1.0))
            v04_strategy = str(last.get("v04_strategy", ""))
        except Exception:
            return None

        if current_profit >= 0.055:
            if trade.is_short and rsi <= 32:
                return "tp_exhaustion_short"
            if not trade.is_short and rsi >= 68:
                return "tp_exhaustion_long"

        if current_profit >= 0.03 and trade_duration > 240 and adx_rel < 0.90:
            return "tp_trend_fade"

        if (
            current_profit >= 0.015
            and trade_duration > 960
            and v04_strategy != "AI_OVERRIDE"
        ):
            return "tp_time_decay"

        return None
