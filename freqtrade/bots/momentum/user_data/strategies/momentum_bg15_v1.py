"""
MomentumBG15_v2_RRRefactor — Risk/Reward Rebalanced

Based on MomentumBG15_v1 with the following structural changes:
- startup_candle_count = 100 (fixes recursive-analysis error)
- Stoploss tightened from -3% to -1.8% (static, NOT ATR-adaptive)
- Minimal ROI increased: 2.5% -> 1.5% -> 0.8% (larger average wins)
- Trailing stop REMOVED (was forcing tiny wins that couldn't offset SL losses)
- custom_stoploss DISABLED (use_custom_stoploss = False)
  Phase 28 results achieved with static -1.8% SL only.
  ATR-adaptive SL code preserved for future Phase 29+ experimentation.
- Entry/exit logic unchanged from v1 (no lookahead, clean)
- FleetGuard + PrimoGate preserved
- Hyperopt parameters now enabled for future Phase 29

Phase 28 RR Refactor Design:
  v1 RR: avg_win +0.78% vs avg_loss -3.50% = RR 0.22:1 (break-even WR ~82%, actual 65-70%)
  v2 Target: avg_win > 1.2x avg_loss, PF > 1.0 on train before Hyperopt
"""

import logging
import sys
from datetime import datetime, timedelta
from typing import Optional

import talib.abstract as ta
from freqtrade.strategy import IStrategy, IntParameter, DecimalParameter
from pandas import DataFrame

import pathlib
_shared = str(pathlib.Path(__file__).resolve().parents[4] / "shared")
if pathlib.Path(_shared).is_dir():
    sys.path.insert(0, _shared)
else:
    sys.path.insert(0, "/freqtrade/shared")
from primo_signal import primo_gate_allows
from fleetguard_v1 import FleetGuard, FleetGuardConfig

logger = logging.getLogger(__name__)


class MomentumBG15_v1(IStrategy):

    INTERFACE_VERSION = 3
    timeframe = "15m"
    can_short = True

    # ---- FIX: startup_candle_count for recursive analysis ----
    startup_candle_count = 100

    # ---- CUSTOM STOPLOSS: DISABLED ----
    # Phase 28 results achieved with static -1.8% SL.
    # ATR-adaptive code preserved below but NOT active.
    # Set to True in Phase 29+ if ATR-SL experimentation is desired.
    use_custom_stoploss = False

    # ---- REBALANCED RISK/REWARD ----
    # v1 had -3% SL with 1% ROI → avg loss 4.5x avg win → guaranteed loss
    # v2: tighter SL, wider ROI targets
    stoploss = -0.018  # -1.8% (was -3%)

    minimal_roi = {
        "0": 0.025,    # 2.5% immediate target
        "45": 0.015,   # 1.5% after 45 min
        "120": 0.008,  # 0.8% after 2h
        "240": 0       # exit after 4h at cost
    }

    # ---- TRAILING REMOVED ----
    # v1 trailing_stopPositive=1% after 2% offset was locking tiny wins
    # Let ROI table manage exits instead
    trailing_stop = False
    trailing_stop_positive = 0.015
    trailing_stop_positive_offset = 0.03
    trailing_only_offset_is_reached = True

    # ---- HYPEROPT PARAMETERS (enabled for Phase 29) ----
    adx_strong_trend = IntParameter(12, 25, default=15, space="buy", optimize=True)
    adx_chaos_threshold = IntParameter(5, 15, default=8, space="buy", optimize=False)

    rsi_oversold = IntParameter(35, 50, default=42, space="buy", optimize=True)
    rsi_overbought = IntParameter(50, 65, default=58, space="buy", optimize=True)

    ema_fast_period = IntParameter(5, 15, default=8, space="buy", optimize=True)
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

    exit_rsi_long = IntParameter(65, 82, default=72, space="sell", optimize=True)
    exit_rsi_short = IntParameter(18, 35, default=28, space="sell", optimize=True)

    # ---- ATR stoploss multiplier (FUTURE — not active while use_custom_stoploss=False) ----
    # Will be usable when use_custom_stoploss is set to True in a future phase.
    atr_sl_multiplier = DecimalParameter(1.0, 3.0, default=1.5, decimals=1, space="buy", optimize=False)

    _daily_pnl = {}
    _strategy_starting_balance = None
    _emergency_stopped = False

    # ---- FleetGuard v1 entry safety (unchanged from v1) ----
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

            # LONG: bull OR sideways + RSI < oversold + MACD-hist > 0
            long_cond = (
                (dataframe["regime"].isin(["bull", "sideways"])) &
                (dataframe["rsi"] < self.rsi_oversold.value) &
                macd_bull &
                long_gate
            )
            dataframe.loc[long_cond, ["enter_long", "enter_tag"]] = (1, "v2_momentum_long")

            # SHORT: bear OR sideways + RSI > overbought + MACD-hist < 0
            short_cond = (
                (dataframe["regime"].isin(["bear", "sideways"])) &
                (dataframe["rsi"] > self.rsi_overbought.value) &
                macd_bear &
                short_gate
            )
            dataframe.loc[short_cond, ["enter_short", "enter_tag"]] = (1, "v2_momentum_short")

        except Exception as e:
            logger.error(f"entry error: {e}")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        try:
            exit_long_cond = (dataframe["rsi"] > self.exit_rsi_long.value)
            dataframe.loc[exit_long_cond, ["exit_long", "exit_tag"]] = (1, "v2_rsi_exit_long")

            exit_short_cond = (dataframe["rsi"] < self.exit_rsi_short.value)
            dataframe.loc[exit_short_cond, ["exit_short", "exit_tag"]] = (1, "v2_rsi_exit_short")
        except Exception as e:
            logger.error(f"exit error: {e}")
        return dataframe

    def custom_stoploss(self, pair: str, trade, current_time: datetime,
                        current_rate: float, current_profit: float,
                        after_fill: bool, **kwargs) -> Optional[float]:
        """
        DISABLED — use_custom_stoploss = False.
        This method is preserved for future ATR-adaptive SL experimentation.
        When use_custom_stoploss is set to True, this will override the static -1.8% SL.
        Currently Freqtrade does NOT call this method.
        """
        # Progressive tightening when in profit
        if current_profit > 0.025:
            return -0.008  # very tight at 2.5%+
        if current_profit > 0.015:
            return -0.012  # tight at 1.5%+

        # ATR-based stoploss: try to use ATR from entry candles
        try:
            dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            if len(dataframe) > 0:
                last_candle = dataframe.iloc[-1]
                atr_val = last_candle.get("atr", 0)
                if atr_val > 0 and last_candle.get("close", 0) > 0:
                    # ATR as fraction of price, multiplied by config
                    atr_pct = atr_val / last_candle["close"]
                    sl_distance = atr_pct * self.atr_sl_multiplier.value
                    # Cap at max 2.5% to prevent runaway
                    sl_distance = min(sl_distance, 0.025)
                    return -sl_distance
        except Exception:
            pass

        # Static fallback
        return None  # uses the class-level stoploss = -0.018

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
            starting_balance = self.wallets.get_starting_balance() if hasattr(self, 'wallets') and self.wallets else 1000.0
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
