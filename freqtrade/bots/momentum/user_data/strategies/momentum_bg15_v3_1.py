"""
MomentumBG15_v3_1 — Fix Short Bias & Entry Quality (Iteration 6)

Iteration 5 result: 33t | 12.1% WR | -$50.13 | SL avg -2.46%
ROI: 4t avg +2.52% = $9.96 | SL: 11t avg -2.46% = -$26.93
TrailingSL: 7t avg -1.20% = -$8.34 | Other: 11t = -$24.82
Long/Short: 13/20

DIAGNOSIS: Three compounding problems:
1. SHORT BIAS: 20/33 trades are shorts, almost all losing. ARB (7t, 0% WR,
   -$10.77) and ETH (4t, 0% WR, -$9.73) are the worst. Crypto's upward bias
   makes shorting unreliable with these momentum signals.
2. LATE ENTRY: BB expanding + MACD rising + volume surge = entering at the
   peak of a move. By the time all conditions align, the move is exhausted.
3. TRAILING CONFUSION: trailing_stop_loss exits avg -1.20% despite offset at
   +1.8%. custom_stoploss ATR-based SL overrides the trailing floor, making
   the trailing mechanism unreliable.

CHANGE 28: Add ROC(3) momentum confirmation
  - Compute 3-candle rate of change (45min momentum)
  - Longs require ROC > 0 (price actively rising)
  - Shorts require ROC < 0 (price actively falling)
  - Filters entries where indicators align but price has stalled

CHANGE 29: Strengthen short entry requirements
  - Shorts require ADX ≥ 25 (longs stay at 20)
  - Shorts require volume > 1.5x SMA (longs stay at 1.2x)
  - 20/33 shorts with ~0% WR: crypto upward bias demands stronger proof

CHANGE 30: Tighter ROI table
  - 0: 1.8% → 20m: 0.8% → 60m: 0.3% → 150m: 0
  - Only 4/33 trades reached the 2.5% cap. Lower cap = more ROI exits

CHANGE 31: Tighter ATR stoploss
  - Multiplier: 2.5 → 2.0 (2 ATR noise room)
  - Cap: 3.5% → 3.0% | Static fallback: -3.5% → -3.0%
  - Avg SL -2.46% ≈ avg ROI +2.52%. Tighter SL improves R:R

CHANGE 32: Replace freqtrade trailing with custom_stoploss profit protection
  - Disable trailing_stop (was causing -1.20% avg exits from SL override)
  - +0.6% profit → SL at breakeven (return -0.006)
  - +1.2% profit → SL at ~+0.9% from entry (return -0.003)
  - +2.0% profit → SL at ~+1.5% from entry (return -0.005)
  - Explicit profit tiers replace unreliable freqtrade trailing

Preserved:
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

    stoploss = -0.030  # -3.0% fallback (CHANGE 31: was -3.5%)

    # CHANGE 30: Tighter ROI — 2.5% cap rarely reached (only 4/33 trades)
    minimal_roi = {
        "0": 0.018,    # 1.8% immediate cap
        "20": 0.008,   # 0.8% after 20m
        "60": 0.003,   # 0.3% after 1h
        "150": 0       # exit after 2.5h at cost
    }

    # CHANGE 32: Disable freqtrade trailing — use custom_stoploss profit tiers instead
    trailing_stop = False

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

    atr_sl_multiplier = DecimalParameter(1.0, 3.0, default=2.0, decimals=1, space="buy", optimize=False)  # CHANGE 31: was 2.5

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

            # CHANGE 28: Rate of Change for momentum confirmation
            dataframe["roc"] = ta.ROC(dataframe, timeperiod=3)
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
            # CHANGE 28: ROC(3) > 0 for longs, < 0 for shorts (momentum not stalled)
            # CHANGE 29: Shorts need ADX ≥ 25 and volume > 1.5x SMA

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
                (dataframe["roc"] > 0) &  # CHANGE 28: price rising over 3 candles
                long_gate
            )
            dataframe.loc[long_cond, ["enter_long", "enter_tag"]] = (1, "v3_trend_long")

            short_cond = (
                (dataframe["close"] < dataframe["ema200"]) &
                (dataframe["adx"] >= 25) &  # CHANGE 29: stronger trend for shorts
                (dataframe["volume"] > dataframe["volume_sma"] * 1.5) &  # CHANGE 29: higher volume for shorts
                (dataframe["bb_expanding"]) &
                (ema_spread < -0.0005) &
                (dataframe["ema_fast"] < dataframe["ema_slow"]) &
                (dataframe["rsi"] < 50) &
                (dataframe["rsi"] > 25) &
                ~dataframe["macd_hist_rising"] &
                (dataframe["close"] < dataframe["open"]) &  # CHANGE 21: bearish candle
                (dataframe["roc"] < 0) &  # CHANGE 28: price falling over 3 candles
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
        # CHANGE 32: Profit protection tiers (replaces unreliable freqtrade trailing)
        if current_profit > 0.020:
            return -0.005   # SL ~+1.5% above entry — lock in large gains
        if current_profit > 0.012:
            return -0.003   # SL ~+0.9% above entry — protect moderate gains
        if current_profit > 0.006:
            return -0.006   # SL at breakeven — protect small gains

        try:
            dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            if len(dataframe) > 0:
                last_candle = dataframe.iloc[-1]
                atr_val = last_candle.get("atr", 0)
                if atr_val > 0 and last_candle.get("close", 0) > 0:
                    atr_pct = atr_val / last_candle["close"]
                    sl_distance = atr_pct * self.atr_sl_multiplier.value
                    sl_distance = min(sl_distance, 0.030)  # CHANGE 31: cap 3.0% (was 3.5%)
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
