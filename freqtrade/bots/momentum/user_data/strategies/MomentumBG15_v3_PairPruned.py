"""
MomentumBG15_v3_PairPruned — Pair-Pruned Candidate with Hardcoded Phase 29 Parameters

Based on MomentumBG15_v2_RRRefactor with the following structural changes:
- Phase 29 candidate parameters HARDCODED as defaults (no JSON dependency)
- Pruned pair set: FIL, SOL, AAVE, APT, ARB, AVAX, NEAR, UNI (BTC/ETH/INJ/OP/ATOM removed)
- Explicit NaN-safe guards in populate_entry_trend and populate_exit_trend
- All Hyperopt parameters set optimize=False (frozen for validation)
- stoploss = -0.018 (static, NOT ATR-adaptive)
- trailing_stop = False
- use_custom_stoploss = False
- startup_candle_count = 100
- FleetGuard + PrimoGate preserved
- No shadow JSON required — source is single source of truth

Phase 31: Created for pair-pruned baseline validation.
Phase 30 context: Shift B failed on full 13-pair set (PF 0.77).
Goal: Test whether pair pruning alone improves robustness.
"""

import logging
import sys
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import talib.abstract as ta
from freqtrade.strategy import IStrategy, IntParameter, DecimalParameter
from pandas import DataFrame

sys.path.insert(0, "/freqtrade/shared")
from primo_signal import primo_gate_allows
from fleetguard_v1 import FleetGuard, FleetGuardConfig

logger = logging.getLogger(__name__)


class MomentumBG15_v3_PairPruned(IStrategy):

    INTERFACE_VERSION = 3
    timeframe = "15m"
    can_short = True

    # ---- startup ----
    startup_candle_count = 100

    # ---- CUSTOM STOPLOSS: DISABLED ----
    use_custom_stoploss = False

    # ---- REBALANCED RISK/REWARD (hardcoded from Phase 29 candidate) ----
    stoploss = -0.018  # -1.8%

    minimal_roi = {
        "0": 0.025,    # 2.5% immediate target
        "45": 0.015,   # 1.5% after 45 min
        "120": 0.008,  # 0.8% after 2h
        "240": 0       # exit after 4h at cost
    }

    # ---- TRAILING REMOVED ----
    trailing_stop = False
    trailing_stop_positive = 0.015
    trailing_stop_positive_offset = 0.03
    trailing_only_offset_is_reached = True

    # ---- HYPEROPT PARAMETERS: FROZEN at Phase 29 candidate values ----
    # optimize=False for all — this is a locked candidate, not a search space
    adx_strong_trend = IntParameter(12, 25, default=12, space="buy", optimize=False)
    adx_chaos_threshold = IntParameter(5, 15, default=8, space="buy", optimize=False)

    rsi_oversold = IntParameter(35, 50, default=50, space="buy", optimize=False)
    rsi_overbought = IntParameter(50, 65, default=65, space="buy", optimize=False)

    ema_fast_period = IntParameter(5, 15, default=13, space="buy", optimize=False)
    ema_slow_period = IntParameter(18, 30, default=21, space="buy", optimize=False)
    ema_trend_period = IntParameter(45, 60, default=50, space="buy", optimize=False)

    adx_period = IntParameter(10, 18, default=14, space="buy", optimize=False)

    risk_per_trade_pct = DecimalParameter(0.005, 0.025, default=0.015, decimals=3, space="buy", optimize=False)
    max_portfolio_drawdown_pct = DecimalParameter(0.10, 0.25, default=0.15, decimals=2, space="buy", optimize=False)
    max_daily_loss_pct = DecimalParameter(0.03, 0.08, default=0.05, decimals=2, space="buy", optimize=False)
    max_leverage = IntParameter(2, 5, default=5, space="buy", optimize=False)

    macd_fast = IntParameter(8, 16, default=12, space="buy", optimize=False)
    macd_slow = IntParameter(20, 30, default=26, space="buy", optimize=False)
    macd_signal = IntParameter(7, 12, default=9, space="buy", optimize=False)

    exit_rsi_long = IntParameter(65, 82, default=67, space="sell", optimize=False)
    exit_rsi_short = IntParameter(18, 35, default=26, space="sell", optimize=False)

    # ---- ATR stoploss multiplier (FUTURE — not active) ----
    atr_sl_multiplier = DecimalParameter(1.0, 3.0, default=1.5, decimals=1, space="buy", optimize=False)

    _daily_pnl = {}
    _strategy_starting_balance = None
    _emergency_stopped = False

    # ---- FleetGuard v1 entry safety (unchanged) ----
    _fleetguard = FleetGuard(FleetGuardConfig(
        max_open_trades=4,
        max_open_shorts=2,
        max_open_longs=2,
    ))

    @property
    def protections(self):
        return [
            {"method": "CooldownPeriod", "stop_duration_candles": 2},
            {"method": "StoplossGuard", "lookback_period_candles": 24, "trade_limit": 3, "stop_duration_candles": 8, "only_per_pair": False, "only_per_side": True},
            {"method": "MaxDrawdown", "lookback_period_candles": 48, "trade_limit": 10, "stop_duration_candles": 12, "max_allowed_drawdown": 0.06},
            {"method": "LowProfitPairs", "lookback_period_candles": 24, "trade_limit": 3, "stop_duration_candles": 12, "required_profit": -0.01, "only_per_pair": True, "only_per_side": True},
        ]

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        try:
            dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
            dataframe["ema_fast"] = ta.EMA(dataframe, timeperiod=self.ema_fast_period.value)
            dataframe["ema_slow"] = ta.EMA(dataframe, timeperiod=self.ema_slow_period.value)
            dataframe["ema_trend"] = ta.EMA(dataframe, timeperiod=self.ema_trend_period.value)
            dataframe["adx"] = ta.ADX(dataframe, timeperiod=self.adx_period.value)

            macd_result = ta.MACD(dataframe,
                                  fastperiod=self.macd_fast.value,
                                  slowperiod=self.macd_slow.value,
                                  signalperiod=self.macd_signal.value)
            dataframe["macd"] = macd_result["macd"]
            dataframe["macd_signal"] = macd_result["macdsignal"]
            dataframe["macd_hist"] = macd_result["macdhist"]

            dataframe["regime"] = self._classify_regime(dataframe)
            dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)
        except Exception as e:
            logger.error(f"indicator error: {e}")
            dataframe["regime"] = "sideways"
        return dataframe

    def _classify_regime(self, dataframe: DataFrame) -> DataFrame:
        adx = dataframe["adx"]
        close = dataframe["close"]
        ema_trend = dataframe["ema_trend"]
        ema_fast = dataframe["ema_fast"]
        ema_slow = dataframe["ema_slow"]

        strong = self.adx_strong_trend.value
        chaos = self.adx_chaos_threshold.value

        bull = (adx > strong) & (close > ema_trend) & (ema_fast > ema_slow)
        bear = (adx > strong) & (close < ema_trend) & (ema_fast < ema_slow)
        chaos_cond = adx < chaos

        regime = DataFrame("sideways", index=dataframe.index, columns=["regime"])
        regime.loc[bull, "regime"] = "bull"
        regime.loc[bear, "regime"] = "bear"
        regime.loc[chaos_cond, "regime"] = "chaos"
        return regime["regime"]

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        try:
            pair = metadata.get("pair")
            long_gate = primo_gate_allows(pair, "long")
            short_gate = primo_gate_allows(pair, "short")

            macd_bull = dataframe["macd_hist"] > 0
            macd_bear = dataframe["macd_hist"] < 0

            # NaN-safe guards: mask out any row where critical indicators are NaN
            # This prevents signals on incomplete candles (fixes Phase 30 lookahead warning)
            valid_indicators = (
                dataframe["rsi"].notna() &
                dataframe["macd_hist"].notna() &
                dataframe["adx"].notna() &
                dataframe["ema_fast"].notna() &
                dataframe["ema_slow"].notna() &
                dataframe["ema_trend"].notna()
            )

            # LONG: bull OR sideways + RSI < oversold + MACD-hist > 0 + NaN-safe
            long_cond = (
                valid_indicators &
                (dataframe["regime"].isin(["bull", "sideways"])) &
                (dataframe["rsi"] < self.rsi_oversold.value) &
                macd_bull &
                long_gate
            )
            dataframe.loc[long_cond, ["enter_long", "enter_tag"]] = (1, "v3_momentum_long")

            # SHORT: bear OR sideways + RSI > overbought + MACD-hist < 0 + NaN-safe
            short_cond = (
                valid_indicators &
                (dataframe["regime"].isin(["bear", "sideways"])) &
                (dataframe["rsi"] > self.rsi_overbought.value) &
                macd_bear &
                short_gate
            )
            dataframe.loc[short_cond, ["enter_short", "enter_tag"]] = (1, "v3_momentum_short")

        except Exception as e:
            logger.error(f"entry error: {e}")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        try:
            # NaN-safe guard for exit signals
            rsi_valid = dataframe["rsi"].notna()

            exit_long_cond = rsi_valid & (dataframe["rsi"] > self.exit_rsi_long.value)
            dataframe.loc[exit_long_cond, ["exit_long", "exit_tag"]] = (1, "v3_rsi_exit_long")

            exit_short_cond = rsi_valid & (dataframe["rsi"] < self.exit_rsi_short.value)
            dataframe.loc[exit_short_cond, ["exit_short", "exit_tag"]] = (1, "v3_rsi_exit_short")
        except Exception as e:
            logger.error(f"exit error: {e}")
        return dataframe

    def custom_stoploss(self, pair: str, trade, current_time: datetime,
                        current_rate: float, current_profit: float,
                        after_fill: bool, **kwargs) -> Optional[float]:
        """
        DISABLED — use_custom_stoploss = False.
        Preserved for future ATR-adaptive SL experimentation.
        """
        if current_profit > 0.025:
            return -0.008
        if current_profit > 0.015:
            return -0.012

        try:
            dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            if len(dataframe) > 0:
                last_candle = dataframe.iloc[-1]
                atr_val = last_candle.get("atr", 0)
                if atr_val > 0 and last_candle.get("close", 0) > 0:
                    atr_pct = atr_val / last_candle["close"]
                    sl_distance = atr_pct * self.atr_sl_multiplier.value
                    sl_distance = min(sl_distance, 0.025)
                    return -sl_distance
        except Exception:
            pass

        return None

    def confirm_trade_entry(self, pair: str, order_type: str, amount: float,
                            rate: float, time_in_force: str, current_time: datetime,
                            entry_tag: Optional[str], side: str, **kwargs) -> bool:
        if self._emergency_stopped:
            return False

        open_trades = []
        recent_closed = []
        current_drawdown = 0.0

        try:
            from freqtrade.persistence import Trade

            for t in Trade.get_trades_proxy(is_open=True):
                open_trades.append({"pair": t.pair, "is_short": t.is_short})

            cutoff = current_time - timedelta(hours=24)
            for t in Trade.get_trades_proxy(is_open=False):
                if t.close_date and t.close_date >= cutoff:
                    recent_closed.append({
                        "pair": t.pair,
                        "is_short": t.is_short,
                        "close_profit": t.close_profit or 0.0,
                    })

            total_profit = Trade.get_total_closed_profit()
            starting_balance = self.wallets.get_starting_balance() if hasattr(self, "wallets") and self.wallets else 1000.0
            if starting_balance > 0:
                current_drawdown = abs(min(0, total_profit / starting_balance))
        except Exception as e:
            logger.warning(f"FleetGuard data gathering fallback: {e}")
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

    def leverage(self, pair: str, current_time: datetime, current_rate: float,
                 proposed_leverage: float, max_leverage: float, entry_tag: str,
                 side: str, **kwargs) -> float:
        return min(self.max_leverage.value, max_leverage)
