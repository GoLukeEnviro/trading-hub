"""ResearchRegimeHybridSideAwareV3

Research-only Regime-Hybrid variant for historical signal validation.

Design goals vs v2:
- Use HistoricalSignalLoader JSONL archives, not static fixtures or live-only state.
- Fail closed when no historical signal exists for the candle timestamp.
- Enable shorts (`can_short = True`) but keep only the proven trend-pullback short path.
- Disable/remove range-reversion shorts entirely.
- Use side-aware signal gating with confidence >= 0.70.
- Use ATR-based custom stoploss with a time-based kill after ~90 minutes.

This file is intentionally isolated under user_data/strategies/research_* and must not
be deployed to a live/money bot without separate validation and approval.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import talib.abstract as ta
from freqtrade.strategy import IStrategy, DecimalParameter, merge_informative_pair
import freqtrade.vendor.qtpylib.indicators as qtpylib
from pandas import DataFrame

# Support both container and host execution paths. The first path follows the
# requested research-tool location; the second is the common Freqtrade container
# mount; the third supports host-side compile/import smoke tests.
for _signal_tool_path in (
    "/freqtrade/bots/regime-hybrid/config/research/signal_tools",
    "/freqtrade/config/research/signal_tools",
    "/home/hermes/projects/trading/freqtrade/bots/regime-hybrid/config/research/signal_tools",
):
    if _signal_tool_path not in sys.path:
        sys.path.insert(0, _signal_tool_path)

from signal_loader import HistoricalSignalLoader, normalize_pair, parse_timestamp  # noqa: E402

logger = logging.getLogger(__name__)


class ResearchRegimeHybridSideAwareV3(IStrategy):
    """Historical-signal-gated research strategy.

    v3 deliberately trades only one entry family:
    `research_trend_pullback_short`.

    Long gate support is implemented in `_historical_gate_allows()` for symmetry
    and future experiments, but this v3 does not emit long entries. That keeps the
    first validation focused on the positive short component from v2.
    """

    INTERFACE_VERSION = 3

    timeframe = "15m"
    informative_timeframe = "1h"
    startup_candle_count = 500

    can_short = True
    use_custom_stoploss = True

    minimal_roi = {"0": 0.025, "15": 0.015, "30": 0.008, "60": 0}
    stoploss = -0.05  # fallback hard stop; custom_stoploss is primary

    trailing_stop = False
    process_only_new_candles = True

    # Gate / risk constants. Keep fixed for first v3 validation; do not hyperopt
    # until the historical archive and walk-forward pipeline are proven.
    signal_confidence_threshold = 0.70
    atr_stop_multiplier = 2.2
    max_dynamic_stop = -0.05
    profit_protect_stop = -0.012
    time_kill_minutes = 90
    time_kill_stop = -0.018

    # Conservative trend-pullback knobs inherited from v2 shape.
    adx_rel_threshold = DecimalParameter(0.8, 1.4, default=1.0, space="buy", optimize=False)

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        archive_path = self._resolve_signal_archive_path(config)
        self.signal_archive_path = archive_path
        self.signal_loader = HistoricalSignalLoader(archive_path, strict=False)
        logger.info(
            "ResearchRegimeHybridSideAwareV3 signal archive loaded: %s records from %s",
            len(self.signal_loader),
            archive_path,
        )

    @staticmethod
    def _resolve_signal_archive_path(config: dict) -> str:
        """Return archive path from config with host/container fallbacks."""
        configured = config.get("signal_archive_file") or config.get("research_signal_archive_file")
        if configured:
            return str(configured)

        container_path = Path("/freqtrade/user_data/signals/historical_signals.jsonl")
        if container_path.exists():
            return str(container_path)

        return "/home/hermes/projects/trading/freqtrade/bots/regime-hybrid/user_data/signals/historical_signals.jsonl"

    @staticmethod
    def _coerce_confidence(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _effective_bias(signal: dict[str, Any]) -> str:
        """Extract or infer bullish/bearish bias from bridge-compatible fields.

        The current `trading_pipeline_v1.0` state contains `allow_long_bias` /
        `allow_short_bias` plus action/confidence, but not always an explicit
        `bias` string. For historical compatibility we infer the effective bias
        from those bridge flags while still honoring explicit `bias` when present.
        """
        bias = str(signal.get("bias", "")).lower().strip()
        if bias in {"bullish", "bearish"}:
            return bias
        if signal.get("allow_long_bias") is True:
            return "bullish"
        if signal.get("allow_short_bias") is True:
            return "bearish"
        return "neutral"

    @staticmethod
    def _effective_action(signal: dict[str, Any]) -> str:
        action = str(signal.get("action", signal.get("normalized_action", ""))).lower().strip()
        if action in {"buy", "long"}:
            return "long"
        if action in {"sell", "short"}:
            return "short"
        return "hold"

    def _historical_gate_allows(self, pair: str, candle_time: datetime, side: str) -> bool:
        """Return whether archived historical signal allows this pair/side.

        Rules:
        - Uses the last archived signal state at or before `candle_time`.
        - Fails closed if no archive, no state, stale state, missing pair, neutral
          bias, non-ACCEPTED verdict, or confidence below 0.70.
        - Long requires bullish + long/buy + confidence >= 0.70.
        - Short requires bearish + short/sell + confidence >= 0.70.
        """
        try:
            ts = parse_timestamp(candle_time)
        except Exception:
            return False

        state = self.signal_loader.get_state_at(ts)
        if not isinstance(state, dict) or not state:
            return False
        if state.get("fresh") is not True or state.get("stale") is True:
            return False

        signal = self.signal_loader.get_signal_at(pair, ts)
        if not isinstance(signal, dict) or not signal:
            return False

        verdict = str(signal.get("verdict", "ACCEPTED")).lower().strip()
        if verdict not in {"accepted", "allow"}:
            return False

        confidence = self._coerce_confidence(signal.get("confidence"))
        if confidence < self.signal_confidence_threshold:
            return False

        bias = self._effective_bias(signal)
        action = self._effective_action(signal)
        side = str(side).lower().strip()

        if side == "long":
            return bias == "bullish" and action == "long" and signal.get("allow_long_bias", True) is not False
        if side == "short":
            return bias == "bearish" and action == "short" and signal.get("allow_short_bias", True) is not False
        return False

    def informative_pairs(self):
        """Request 1h informative candles for the active whitelist."""
        if not self.dp:
            return []
        return [(pair, self.informative_timeframe) for pair in self.dp.current_whitelist()]

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Populate 15m + 1h trend/volatility indicators used by v3."""
        if dataframe.empty:
            return dataframe

        pair = metadata.get("pair")
        if self.dp and pair:
            informative = self.dp.get_pair_dataframe(pair=pair, timeframe=self.informative_timeframe)
            informative["ema200"] = ta.EMA(informative, timeperiod=200)
            informative["ema50"] = ta.EMA(informative, timeperiod=50)
            informative["adx"] = ta.ADX(informative)
            dataframe = merge_informative_pair(
                dataframe, informative, self.timeframe, self.informative_timeframe, ffill=True
            )

        dataframe["adx"] = ta.ADX(dataframe)
        dataframe["adx_sma"] = dataframe["adx"].rolling(window=50).mean()
        dataframe["adx_rel"] = dataframe["adx"] / dataframe["adx_sma"]
        dataframe["rsi"] = ta.RSI(dataframe)
        dataframe["ema50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)
        dataframe["atr_pct"] = dataframe["atr"] / dataframe["close"]

        bollinger = qtpylib.bollinger_bands(qtpylib.typical_price(dataframe), window=20, stds=2)
        dataframe["bb_lowerband"] = bollinger["lower"]
        dataframe["bb_middleband"] = bollinger["mid"]
        dataframe["bb_upperband"] = bollinger["upper"]
        dataframe["bb_width"] = (bollinger["upper"] - bollinger["lower"]) / bollinger["mid"]

        dataframe["volume_ma"] = dataframe["volume"].rolling(window=30).mean()
        dataframe["volume_ratio"] = dataframe["volume"] / dataframe["volume_ma"]

        dataframe["trend"] = "neutral"
        dataframe.loc[
            (dataframe["close"] > dataframe["ema200"]) & (dataframe["ema50"] > dataframe["ema200"]),
            "trend",
        ] = "bullish"
        dataframe.loc[
            (dataframe["close"] < dataframe["ema200"]) & (dataframe["ema50"] < dataframe["ema200"]),
            "trend",
        ] = "bearish"

        return dataframe

    def _gate_series(self, dataframe: DataFrame, pair: str, side: str):
        """Vectorized-ish wrapper around `_historical_gate_allows` for research."""
        if "date" in dataframe.columns:
            return dataframe["date"].apply(lambda ts: self._historical_gate_allows(pair, ts, side))
        # Fallback for hand-built dataframes in smoke tests.
        return dataframe.index.to_series().apply(lambda ts: self._historical_gate_allows(pair, ts, side))

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Emit only the v3 trend-pullback short entry.

        `range_reversion_short` is intentionally absent. Long gates are supported
        by `_historical_gate_allows()` but no long entries are emitted in this v3.
        """
        pair = metadata.get("pair", "")

        dataframe["enter_long"] = 0
        dataframe["enter_short"] = 0
        dataframe["enter_tag"] = None

        if dataframe.empty or not pair:
            return dataframe

        ema200_htf_col = f"ema200_{self.informative_timeframe}"
        required = [
            "trend", "adx_rel", "atr_pct", "volume", "volume_ma", "rsi",
            "ema200", ema200_htf_col,
        ]
        missing = [col for col in required if col not in dataframe.columns]
        if missing:
            logger.warning("v3 missing indicator columns for %s: %s", pair, missing)
            return dataframe

        short_gate = self._gate_series(dataframe, pair, "short")
        atr_expanding = dataframe["atr_pct"] > dataframe["atr_pct"].rolling(20).mean()
        volume_ok = dataframe["volume"] > dataframe["volume_ma"]

        trend_pullback_short = (
            (dataframe["trend"] == "bearish")
            & (dataframe["adx_rel"] > self.adx_rel_threshold.value)
            & (dataframe["close"] < dataframe[ema200_htf_col])
            & (dataframe["close"] < dataframe["ema200"])
            & (dataframe["rsi"] > 65)
            & volume_ok
            & atr_expanding
            & short_gate
        )

        dataframe.loc[trend_pullback_short, "enter_short"] = 1
        dataframe.loc[trend_pullback_short, "enter_tag"] = "research_trend_pullback_short"
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """No indicator exit in v3; ROI/custom_stoploss manage exits."""
        return dataframe

    def custom_stoploss(
        self,
        pair: str,
        trade,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        **kwargs,
    ) -> float:
        """ATR-based dynamic stop with a time-kill for stale losers.

        Behavior:
        - If the trade is already >2% in profit, tighten to -1.2% from current.
        - If the trade is older than ~90 minutes and still losing, tighten to -1.8%.
        - Otherwise use `-ATR/current_rate * 2.2`, capped at the fallback -5%.
        """
        if current_profit > 0.02:
            return self.profit_protect_stop

        try:
            trade_duration_min = (current_time - trade.open_date_utc).total_seconds() / 60.0
        except Exception:
            trade_duration_min = 0.0
        if trade_duration_min >= self.time_kill_minutes and current_profit < 0:
            return self.time_kill_stop

        if not self.dp or current_rate <= 0:
            return self.stoploss

        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe is None or dataframe.empty:
            return self.stoploss

        atr = dataframe.iloc[-1].get("atr")
        if atr is None:
            return self.stoploss
        try:
            atr_stop = -(self.atr_stop_multiplier * float(atr) / float(current_rate))
        except (TypeError, ValueError, ZeroDivisionError):
            return self.stoploss

        # Keep stop no wider than max_dynamic_stop/fallback.
        return max(atr_stop, self.max_dynamic_stop)
