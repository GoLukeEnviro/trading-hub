"""
MomentumBG15_v3_1 — Fix Over-Tight Stoploss (Iteration 5)

Iteration 4 result: 40t | 5.0% WR | -$49.79 | SL avg -1.69%
R:R = 2.07 (great!) but WR catastrophically low.
ROI: 2t avg +3.50% = $6.90 | SL: 16t avg -1.69% = -$26.82 | TrailingSL: 4t avg -1.04%
18 other exits (signal/protection/force) all losses.

DIAGNOSIS: ATR × 1.5 stoploss is ~1 ATR wide — a single 15m candle can stop
you out. The SL tightening at +1.5% profit makes it worse: trades briefly
touch +1.5%, the SL snaps to -1.2% from current rate, then normal noise
triggers it. Result: R:R is perfect on paper but WR is impossibly low because
trades never get to develop. The 3.5% ROI cap compounds the problem — trades
need to survive long enough to reach it but the tight SL kills them first.

CHANGE 24: Widen ATR-based stoploss
  - ATR multiplier: 1.5 → 2.5 (give trades 2.5 ATR of noise room)
  - Cap: 2.5% → 3.5% (allow wider SL for volatile pairs)
  - Static fallback: -3.5% (was -2.5%)
  - Expected avg SL loss: ~-2.0 to -2.5% (was -1.69%)

CHANGE 25: Relax profit-based SL tightening
  - Remove the +1.5% profit tier entirely (was killing trades at +1.5%)
  - +2.5% profit tier: -1.2% from current (was -0.8%, too aggressive)
  - +4.0% profit tier: -0.8% from current (lock in large gains)
  - Only tighten SL when trade is well into profit territory

CHANGE 26: Tighter ROI table
  - 0: 2.5% → 30m: 1.5% → 90m: 0.6% → 240m: 0
  - Was: 0: 3.5% → 60m: 2.0% → 180m: 0.8% → 360m: 0
  - 3.5% cap was unreachable with tight SL — trades died first
  - 2.5% cap with faster time decay should capture more ROI exits
  - Breakeven WR at 2.5% ROI / 2.0% SL ≈ 44%

CHANGE 27: Adjust trailing stop
  - Offset: 2.5% → 1.8% (activate trailing sooner)
  - Trail: 1.2% → 0.8% (tighter trail to lock gains)
  - Protects trades reaching +1.8% with floor at +1.0%

Preserved from iteration 4:
  - CHANGE 20: Custom stoploss enabled (ATR-based)
  - CHANGE 21: Candle body confirmation
  - CHANGE 23: RSI exit bands 80/20
  - CHANGE 15-18: RSI momentum, ADX≥20, Vol>1.2x, EMA spread≥0.05%
  - CHANGE 10: BB expansion filter
  - EMA200 trend, MACD hist rising/falling, EMA alignment
  - FleetGuard: active | Protections: same
"""

import logging
import sys
from datetime import datetime, timedelta
from typing import Optional

import talib.abstract as ta
from freqtrade.strategy import IStrategy, IntParameter, DecimalParameter
from pandas import DataFrame

sys.path.insert(0, "/freqtrade/shared")
from primo_signal import primo_gate_allows
from fleetguard_v1 import FleetGuard, FleetGuardConfig

logger = logging.getLogger(__name__)


class MomentumBG15_v3_1(IStrategy):

    INTERFACE_VERSION = 3
    timeframe = "15m"
    can_short = True

    startup_candle_count = 200  # increased for EMA200 warmup

    # CHANGE 20: Enable ATR-based custom stoploss (was disabled!)
    use_custom_stoploss = True

    stoploss = -0.035  # -3.5% fallback (CHANGE 24: was -2.5%)

    # CHANGE 26: Tighter ROI — 3.5% was unreachable with ATR SL
    minimal_roi = {
        "0": 0.025,    # 2.5% immediate cap
        "30": 0.015,   # 1.5% after 30m
        "90": 0.006,   # 0.6% after 1.5h
        "240": 0       # exit after 4h at cost
    }

    # CHANGE 27: Adjusted trailing — activate sooner, tighter lock-in
    trailing_stop = True
    trailing_stop_positive = 0.008      # 0.8% trail distance (was 1.2%)
    trailing_stop_positive_offset = 0.018  # activate at 1.8% profit (was 2.5%)
    trailing_only_offset_is_reached = True

    # ---- Hyperopt parameters ----
    adx_strong_trend = IntParameter(12, 25, default=15, space="buy", optimize=True)
    adx_chaos_threshold = IntParameter(5, 15, default=8, space="buy", optimize=False)

    rsi_oversold = IntParameter(35, 55, default=50, space="buy", optimize=True)
    rsi_overbought = IntParameter(45, 65, default=50, space="buy", optimize=True)

    ema_fast_period = IntParameter(5, 15, default=8, space="buy", optimize=True)
    ema_slow_period = IntParameter(18, 30, default=21, space="buy", optimize=False)
    ema_trend_period = IntParameter(45, 60, default=50, space="buy", optimize=False)

    # CHANGE 4: EMA200 period as parameter
    ema_trend_conf_period = IntParameter(180, 220, default=200, space="buy", optimize=False)

    adx_period = IntParameter(10, 18, default=14, space="buy", optimize=False)

    risk_per_trade_pct = DecimalParameter(0.005, 0.025, default=0.015, decimals=3, space="buy", optimize=False)
    max_portfolio_drawdown_pct = DecimalParameter(0.10, 0.25, default=0.15, decimals=2, space="buy", optimize=False)
    max_daily_loss_pct = DecimalParameter(0.03, 0.08, default=0.05, decimals=2, space="buy", optimize=False)
    max_leverage = IntParameter(2, 5, default=5, space="buy", optimize=False)

    macd_fast = IntParameter(8, 16, default=12, space="buy", optimize=False)
    macd_slow = IntParameter(20, 30, default=26, space="buy", optimize=False)
    macd_signal = IntParameter(7, 12, default=9, space="buy", optimize=False)

    exit_rsi_long = IntParameter(65, 90, default=80, space="sell", optimize=True)   # CHANGE 23: 72→80
    exit_rsi_short = IntParameter(10, 35, default=20, space="sell", optimize=True)   # CHANGE 23: 28→20

    atr_sl_multiplier = DecimalParameter(1.0, 3.0, default=2.5, decimals=1, space="buy", optimize=False)  # CHANGE 24: was 1.5

    _daily_pnl = {}
    _strategy_starting_balance = None
    _emergency_stopped = False

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

            # CHANGE 4: EMA200 for trend confirmation
            dataframe["ema200"] = ta.EMA(dataframe, timeperiod=self.ema_trend_conf_period.value)

            dataframe["adx"] = ta.ADX(dataframe, timeperiod=self.adx_period.value)

            macd_result = ta.MACD(dataframe,
                                  fastperiod=self.macd_fast.value,
                                  slowperiod=self.macd_slow.value,
                                  signalperiod=self.macd_signal.value)
            dataframe["macd"] = macd_result["macd"]
            dataframe["macd_signal"] = macd_result["macdsignal"]
            dataframe["macd_hist"] = macd_result["macdhist"]

            dataframe["macd_hist_rising"] = dataframe["macd_hist"] > dataframe["macd_hist"].shift(1)

            dataframe["regime"] = self._classify_regime(dataframe)
            dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)

            # CHANGE 7: Volume SMA for entry filter
            dataframe["volume_sma"] = ta.SMA(dataframe["volume"], timeperiod=20)

            # CHANGE 10: Bollinger Band width for expansion filter
            bb = ta.BBANDS(dataframe, timeperiod=20, nbdevup=2.0, nbdevdn=2.0)
            dataframe["bb_width"] = (bb["upperband"] - bb["lowerband"]) / bb["middleband"]
            dataframe["bb_expanding"] = dataframe["bb_width"] > dataframe["bb_width"].shift(1)
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

            # CHANGE 4: EMA200 trend confirmation
            # CHANGE 6: ADX ≥ 20 to reject weak-trend entries
            # CHANGE 7: Volume > 1.2x 20-SMA for liquidity confirmation
            # CHANGE 9: EMA alignment (fast > slow for longs, fast < slow for shorts)
            # CHANGE 10: BB expansion — only enter on volatility breakout
            # CHANGE 15: RSI momentum confirm (RSI > 50 for longs, RSI < 50 for shorts)
            # CHANGE 16: ADX ≥ 20 (relaxed from 25)
            # CHANGE 17: Volume > 1.2x SMA (relaxed from 1.5x)
            # CHANGE 18: EMA spread ≥ 0.05% (relaxed from 0.15%)
            # CHANGE 21: Candle body confirmation (close > open for longs)

            ema_spread = (dataframe["ema_fast"] - dataframe["ema_slow"]) / dataframe["close"]

            long_cond = (
                (dataframe["close"] > dataframe["ema200"]) &
                (dataframe["adx"] >= 20) &
                (dataframe["volume"] > dataframe["volume_sma"] * 1.2) &
                (dataframe["bb_expanding"]) &
                (ema_spread > 0.0005) &
                (dataframe["ema_fast"] > dataframe["ema_slow"]) &
                (dataframe["rsi"] > 50) &
                (dataframe["rsi"] < 75) &
                dataframe["macd_hist_rising"] &
                (dataframe["close"] > dataframe["open"]) &  # CHANGE 21: bullish candle
                long_gate
            )
            dataframe.loc[long_cond, ["enter_long", "enter_tag"]] = (1, "v3_trend_long")

            short_cond = (
                (dataframe["close"] < dataframe["ema200"]) &
                (dataframe["adx"] >= 20) &
                (dataframe["volume"] > dataframe["volume_sma"] * 1.2) &
                (dataframe["bb_expanding"]) &
                (ema_spread < -0.0005) &
                (dataframe["ema_fast"] < dataframe["ema_slow"]) &
                (dataframe["rsi"] < 50) &
                (dataframe["rsi"] > 25) &
                ~dataframe["macd_hist_rising"] &
                (dataframe["close"] < dataframe["open"]) &  # CHANGE 21: bearish candle
                short_gate
            )
            dataframe.loc[short_cond, ["enter_short", "enter_tag"]] = (1, "v3_trend_short")

        except Exception as e:
            logger.error(f"entry error: {e}")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        try:
            exit_long_cond = (dataframe["rsi"] > self.exit_rsi_long.value)
            dataframe.loc[exit_long_cond, ["exit_long", "exit_tag"]] = (1, "v3_rsi_exit_long")

            exit_short_cond = (dataframe["rsi"] < self.exit_rsi_short.value)
            dataframe.loc[exit_short_cond, ["exit_short", "exit_tag"]] = (1, "v3_rsi_exit_short")
        except Exception as e:
            logger.error(f"exit error: {e}")
        return dataframe

    def custom_stoploss(self, pair: str, trade, current_time: datetime,
                        current_rate: float, current_profit: float,
                        after_fill: bool, **kwargs) -> Optional[float]:
        # CHANGE 25: Relax profit-based tightening tiers
        if current_profit > 0.040:
            return -0.008   # lock in large gains: SL at +3.2% from entry
        if current_profit > 0.025:
            return -0.012   # tighten moderately: SL at +1.3% from entry

        try:
            dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            if len(dataframe) > 0:
                last_candle = dataframe.iloc[-1]
                atr_val = last_candle.get("atr", 0)
                if atr_val > 0 and last_candle.get("close", 0) > 0:
                    atr_pct = atr_val / last_candle["close"]
                    sl_distance = atr_pct * self.atr_sl_multiplier.value
                    sl_distance = min(sl_distance, 0.035)  # CHANGE 24: cap 3.5% (was 2.5%)
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
