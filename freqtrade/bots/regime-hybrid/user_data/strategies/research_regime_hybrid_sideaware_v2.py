"""
research_regime_hybrid_sideaware_v2
Research variant — side-aware gate + symmetric shorts + ATR stop
Incorporates: generate_signal(), _combine_signals(), Kelly Sizing from primo_trading_bot_v0_4.py

Fixes applied (review fixes):
  FIX-1: Per-pair regime state (no more global `_regime_history`)
  FIX-2: Remove dead code: long_can_enter/short_can_enter, _generate_signal,
         _combine_signals, calculate_kelly_sizing, _riskguard_check
  FIX-3: Remove unused `List` import

Changes vs v6_1_Fett:
  - Added v0.4 generate_signal() as confirm_layer to override entries
  - Added _combine_signals() veto model (stub for future LLM input)
  - Added calculate_kelly_sizing() for position sizing
  - Added bb_width and volume_ratio to indicators
  - v0.4 acts as SECOND layer: strategy generates signals, v0.4 can override to WATCH

Critical fix: Per-pair regime state — each pair gets its own 2-cycle hysteresis
tracking. No more cross-pair contamination from global state.
"""

import logging
import sys
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

import talib.abstract as ta
from freqtrade.strategy import IStrategy, IntParameter, DecimalParameter, merge_informative_pair
import freqtrade.vendor.qtpylib.indicators as qtpylib
from pandas import DataFrame

sys.path.insert(0, "/freqtrade/shared")
from primo_signal import primo_gate_allows, load_signal_state, normalize_pair as _norm_pair
from fleetguard_v1 import FleetGuard, FleetGuardConfig

logger = logging.getLogger(__name__)


# ============================================================
# CONSTANTS (intentionally module-level — read-only)
# ============================================================

STRATEGY_CONFIG = {
    "MEAN_REVERSION": {"win_rate": 0.85, "rrr": 1.2, "safety_factor": 0.15},
    "TREND_FOLLOWING": {"win_rate": 0.58, "rrr": 2.5, "safety_factor": 0.30},
    "BREAKOUT": {"win_rate": 0.45, "rrr": 3.5, "safety_factor": 0.20},
    "DEFAULT": {"win_rate": 0.55, "rrr": 2.0, "safety_factor": 0.25},
}


# ============================================================
# STRATEGY CLASS
# ============================================================

class ResearchRegimeHybridSideAwareV2(IStrategy):

    INTERFACE_VERSION = 3
    timeframe = "15m"
    informative_timeframe = "1h"
    can_short = True  # RESEARCH: enable clean mirrored short entries

    minimal_roi = {'0': 0.025, '15': 0.015, '30': 0.008, '60': 0}
    stoploss = -0.05  # RESEARCH: fallback only; custom_stoploss is primary
    use_custom_stoploss = True  # RESEARCH: ATR/time-based dynamic stop active
    trailing_stop = False  # FIXED: was True (killing profits)
    trailing_stop_positive = 0.01
    trailing_stop_positive_offset = 0.02
    trailing_only_offset_is_reached = True

    startup_candle_count = 500

    _fleetguard = FleetGuard(FleetGuardConfig(
        max_open_trades=3, max_open_shorts=2, max_open_longs=2,
    ))

    @property
    def protections(self):
        return [
            {"method": "CooldownPeriod", "stop_duration_candles": 5},
            {"method": "StoplossGuard", "lookback_period_candles": 60,
             "trade_limit": 3, "stop_duration_candles": 60,
             "only_per_pair": False, "only_per_side": True},
            {"method": "MaxDrawdown", "lookback_period_candles": 480,
             "trade_limit": 20, "stop_duration_candles": 96,
             "max_allowed_drawdown": 0.06},
            {"method": "LowProfitPairs", "lookback_period_candles": 1440,
             "trade_limit": 2, "stop_duration_candles": 60,
             "required_profit": -0.01},
        ]

    adx_rel_threshold = DecimalParameter(0.8, 1.4, default=1.0, space="buy")
    rsi_oversold = IntParameter(20, 40, default=25, space="buy")
    rsi_overbought = 68
    atr_sl_trend = 3.5
    atr_sl_range = DecimalParameter(2.0, 4.0, default=2.8, space="sell", optimize=True)
    atr_tp_trend = DecimalParameter(1.0, 2.5, default=1.8, space="sell", optimize=True)

    # Dry-run override: when True and running in dry_run mode, bypasses the
    # conservative primo gate and uses a lower confidence threshold instead.
    dry_run_override = True
    dry_run_confidence_threshold = 0.70

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        # FIX-1: Per-pair regime history — no cross-pair contamination
        # Each pair gets its own 2-cycle hysteresis tracking
        self._regime_histories: Dict[str, list] = {}

    def _get_stable_regime(self, pair: str, current_regime: str) -> str:
        """
        2-cycle hysteresis per pair.
        Regime only shifts if the same regime appears in 2 consecutive candles.
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

    def _dry_run_gate_allows(self, pair: str, side: str) -> bool:
        """Side-aware dry-run signal gate.

        The active v7 implementation allowed any side when raw confidence was
        above threshold. That made bearish/short signals permit long entries.
        This research variant only allows the matching direction:
        - long: action buy/long + bullish bias + confidence >= 0.70
        - short: action sell/short + bearish bias + confidence >= 0.70

        If signal state or pair data is absent, fail closed for research safety.
        """
        state = load_signal_state()
        pairs = (state.get("pairs") or {}) if isinstance(state, dict) else {}

        # Research backtests cannot rely on the live bridge state: the active
        # state file can be stale/empty. Allow a config-scoped fixture under
        # config/research/ for deterministic side-aware tests.
        if not pairs:
            signal_file = self.config.get("research_signal_file")
            if signal_file:
                try:
                    import json
                    from pathlib import Path
                    fixture_state = json.loads(Path(signal_file).read_text())
                    if isinstance(fixture_state, dict):
                        pairs = fixture_state.get("pairs") or {}
                except Exception as e:
                    logger.warning(f"research signal fixture load failed: {e}")
                    pairs = {}

        if not isinstance(pairs, dict) or not pairs:
            return False

        pair_norm = _norm_pair(pair)
        pair_raw = str(pair or "").strip().upper()
        pair_data = pairs.get(pair_raw) or pairs.get(pair_norm)
        if not isinstance(pair_data, dict):
            return False

        action = str(pair_data.get("action", "")).lower().strip()
        bias = str(pair_data.get("bias", "")).lower().strip()
        recommendation = str(pair_data.get("recommendation", "")).lower().strip()
        verdict = str(pair_data.get("verdict", "")).lower().strip()
        try:
            confidence = float(pair_data.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0

        threshold = self.dry_run_confidence_threshold
        accepted = verdict in ("accepted", "", "allow") or recommendation in ("allow", "")

        if side == "long":
            return accepted and action in ("buy", "long") and bias == "bullish" and confidence >= threshold

        if side == "short":
            return accepted and action in ("sell", "short") and bias == "bearish" and confidence >= threshold

        return False

    def informative_pairs(self):
        pairs = self.dp.current_whitelist()
        return [(pair, self.informative_timeframe) for pair in pairs]

    def _build_v04_signal_layer(self, dataframe: DataFrame, pair: str) -> None:
        """
        Pre-compute v0.4 signals as vectorized columns.
        Runs in populate_indicators. Uses per-pair regime tracking.
        """
        # Ensure prev_close exists (shift by 1)
        dataframe['prev_close'] = dataframe['close'].shift(1)

        # Path 1: Mean Reversion
        rsi_buy = dataframe['rsi'] <= 30
        rsi_sell = dataframe['rsi'] >= 70
        mean_rev_active = rsi_buy | rsi_sell

        # Path 2: Trend Following
        trend_active = (dataframe['adx'] > 22) & dataframe['ema50'].notna() & dataframe['ema200'].notna()
        trend_buy = trend_active & (dataframe['ema50'] > dataframe['ema200'])
        trend_sell = trend_active & (dataframe['ema50'] <= dataframe['ema200'])

        # Path 3: Breakout
        breakout_active = (dataframe['bb_width'] < 0.5) & (dataframe['volume_ratio'] > 1.05)
        breakout_buy = breakout_active & dataframe['close'].gt(dataframe['prev_close'])
        breakout_sell = breakout_active & dataframe['close'].le(dataframe['prev_close'])

        # Initialize all as WATCH
        dataframe['v04_action'] = 'WATCH'
        dataframe['v04_confidence'] = 0.0
        dataframe['v04_strategy'] = None
        dataframe['v04_regime'] = 'unknown'

        # Compute raw regime for hysteresis tracking (per-pair)
        # Use last row's indicators for regime determination (stable regime on last candle)
        if len(dataframe) > 0:
            last_row = dataframe.iloc[-1]
            adx_val = last_row.get('adx', 0)
            vol_r = last_row.get('volume_ratio', 1.0)
            raw_regime = "trending" if adx_val > 22 else "ranging"
            if vol_r > 1.8:
                raw_regime = "volatile"
            stable_regime = self._get_stable_regime(pair, raw_regime)
            dataframe['v04_regime'] = stable_regime

        # Priority: MEAN_REVERSION > TREND > BREAKOUT > WATCH
        mr_buy_mask = mean_rev_active & rsi_buy
        mr_sell_mask = mean_rev_active & rsi_sell
        trend_buy_mask = trend_buy & ~mean_rev_active
        trend_sell_mask = trend_sell & ~mean_rev_active
        breakout_buy_mask = breakout_buy & ~mean_rev_active & ~trend_buy
        breakout_sell_mask = breakout_sell & ~mean_rev_active & ~trend_sell

        # --- Apply all assignments ---
        # MEAN REVERSION
        dataframe.loc[mr_buy_mask, 'v04_action'] = 'BUY'
        dataframe.loc[mr_buy_mask, 'v04_strategy'] = 'MEAN_REVERSION'
        ext = (dataframe.loc[mr_buy_mask, 'rsi'] - 30).abs() / 10
        dataframe.loc[mr_buy_mask, 'v04_confidence'] = ext.clip(0, 1).round(4)

        dataframe.loc[mr_sell_mask, 'v04_action'] = 'SELL'
        dataframe.loc[mr_sell_mask, 'v04_strategy'] = 'MEAN_REVERSION'
        ext = (dataframe.loc[mr_sell_mask, 'rsi'] - 70).abs() / 10
        dataframe.loc[mr_sell_mask, 'v04_confidence'] = ext.clip(0, 1).round(4)

        # TREND FOLLOWING
        dataframe.loc[trend_buy_mask, 'v04_action'] = 'BUY'
        dataframe.loc[trend_buy_mask, 'v04_strategy'] = 'TREND_FOLLOWING'
        adx_raw = ((dataframe.loc[trend_buy_mask, 'adx'] - 22) / 18).clip(0, 1)
        rsi_factor = ((dataframe.loc[trend_buy_mask, 'rsi'] >= 35) & (dataframe.loc[trend_buy_mask, 'rsi'] <= 65)).astype(float) * 0.3 + 0.7
        vol_factor = 1.1 * (dataframe.loc[trend_buy_mask, 'volume_ratio'] > 1.1).astype(float) + 0.9 * (dataframe.loc[trend_buy_mask, 'volume_ratio'] <= 1.1).astype(float)
        dataframe.loc[trend_buy_mask, 'v04_confidence'] = (adx_raw * rsi_factor * vol_factor).clip(0, 1).round(4)

        dataframe.loc[trend_sell_mask, 'v04_action'] = 'SELL'
        dataframe.loc[trend_sell_mask, 'v04_strategy'] = 'TREND_FOLLOWING'
        adx_raw = ((dataframe.loc[trend_sell_mask, 'adx'] - 22) / 18).clip(0, 1)
        rsi_factor = ((dataframe.loc[trend_sell_mask, 'rsi'] >= 35) & (dataframe.loc[trend_sell_mask, 'rsi'] <= 65)).astype(float) * 0.3 + 0.7
        vol_factor = 1.1 * (dataframe.loc[trend_sell_mask, 'volume_ratio'] > 1.1).astype(float) + 0.9 * (dataframe.loc[trend_sell_mask, 'volume_ratio'] <= 1.1).astype(float)
        dataframe.loc[trend_sell_mask, 'v04_confidence'] = (adx_raw * rsi_factor * vol_factor).clip(0, 1).round(4)

        # BREAKOUT
        dataframe.loc[breakout_buy_mask, 'v04_action'] = 'BUY'
        dataframe.loc[breakout_buy_mask, 'v04_strategy'] = 'BREAKOUT'
        squeeze = ((0.5 - dataframe.loc[breakout_buy_mask, 'bb_width']) / 0.4).clip(0, 1)
        vol = (dataframe.loc[breakout_buy_mask, 'volume_ratio'] / 1.5).clip(0, 1)
        dataframe.loc[breakout_buy_mask, 'v04_confidence'] = (0.5 * squeeze + 0.5 * vol).round(4)

        dataframe.loc[breakout_sell_mask, 'v04_action'] = 'SELL'
        dataframe.loc[breakout_sell_mask, 'v04_strategy'] = 'BREAKOUT'
        squeeze = ((0.5 - dataframe.loc[breakout_sell_mask, 'bb_width']) / 0.4).clip(0, 1)
        vol = (dataframe.loc[breakout_sell_mask, 'volume_ratio'] / 1.5).clip(0, 1)
        dataframe.loc[breakout_sell_mask, 'v04_confidence'] = (0.5 * squeeze + 0.5 * vol).round(4)

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        if not self.dp:
            return dataframe

        pair = metadata.get("pair", "UNKNOWN")

        informative = self.dp.get_pair_dataframe(
            pair=pair, timeframe=self.informative_timeframe
        )
        informative['ema200'] = ta.EMA(informative, timeperiod=200)
        informative['ema50'] = ta.EMA(informative, timeperiod=50)
        informative['adx'] = ta.ADX(informative)
        informative['rsi'] = ta.RSI(informative)
        dataframe = merge_informative_pair(
            dataframe, informative, self.timeframe, self.informative_timeframe, ffill=True
        )

        dataframe['adx'] = ta.ADX(dataframe)
        dataframe['adx_sma'] = dataframe['adx'].rolling(window=50).mean()
        dataframe['adx_rel'] = dataframe['adx'] / dataframe['adx_sma']

        dataframe['rsi'] = ta.RSI(dataframe)
        dataframe['ema50'] = ta.EMA(dataframe, timeperiod=50)
        dataframe['ema200'] = ta.EMA(dataframe, timeperiod=200)

        dataframe['atr'] = ta.ATR(dataframe, timeperiod=14)
        dataframe['atr_pct'] = dataframe['atr'] / dataframe['close']

        bollinger = qtpylib.bollinger_bands(
            qtpylib.typical_price(dataframe), window=20, stds=2
        )
        dataframe['bb_lowerband'] = bollinger['lower']
        dataframe['bb_middleband'] = bollinger['mid']
        dataframe['bb_upperband'] = bollinger['upper']
        dataframe['bb_width'] = (bollinger['upper'] - bollinger['lower']) / bollinger['mid']

        dataframe['volume_mean'] = dataframe['volume'].rolling(window=30).mean()
        dataframe['volume_ratio'] = dataframe['volume'] / dataframe['volume_mean']
        dataframe['volume_ma'] = dataframe['volume_mean']
        dataframe['trend'] = 'neutral'
        dataframe.loc[(dataframe['close'] > dataframe['ema200']) & (dataframe['ema50'] > dataframe['ema200']), 'trend'] = 'bullish'
        dataframe.loc[(dataframe['close'] < dataframe['ema200']) & (dataframe['ema50'] < dataframe['ema200']), 'trend'] = 'bearish'

        # v0.4 signal pre-computation (vectorized, per-pair regime tracking)
        self._build_v04_signal_layer(dataframe, pair)

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        ema200_htf = dataframe[f'ema200_{self.informative_timeframe}']
        ema50_htf = dataframe[f'ema50_{self.informative_timeframe}'] if f'ema50_{self.informative_timeframe}' in dataframe.columns else None
        pair = metadata.get("pair")
        is_dry_run = self.config.get('dry_run', False)

        if self.dry_run_override and is_dry_run:
            long_gate = self._dry_run_gate_allows(pair, "long")
            short_gate = self._dry_run_gate_allows(pair, "short")
        else:
            long_gate = primo_gate_allows(pair, "long")
            short_gate = primo_gate_allows(pair, "short")

        atr_expanding = dataframe['atr_pct'] > dataframe['atr_pct'].rolling(20).mean()
        vol_ok = dataframe['volume'] > dataframe['volume_ma']

        # RESEARCH LONG: symmetric bullish regime only. Bearish external signal fails closed.
        trend_long = (
            (dataframe['trend'] == 'bullish') &
            (dataframe['adx_rel'] > self.adx_rel_threshold.value) &
            (dataframe['close'] > ema200_htf) &
            (dataframe['close'] > dataframe['ema200']) &
            (dataframe['rsi'] < 35) &
            vol_ok &
            atr_expanding &
            long_gate
        )

        range_long = (
            (dataframe['trend'] != 'bearish') &
            (dataframe['adx_rel'] <= self.adx_rel_threshold.value) &
            (dataframe['rsi'] < self.rsi_oversold.value) &
            (dataframe['close'] < dataframe['bb_lowerband']) &
            vol_ok &
            atr_expanding &
            long_gate
        )

        # RESEARCH SHORT: mirrored bearish regime. Uses enter_short in populate_entry_trend
        # (Freqtrade v3 does not call populate_short_trend()).
        trend_short = (
            (dataframe['trend'] == 'bearish') &
            (dataframe['adx_rel'] > self.adx_rel_threshold.value) &
            (dataframe['close'] < ema200_htf) &
            (dataframe['close'] < dataframe['ema200']) &
            (dataframe['rsi'] > 65) &
            vol_ok &
            atr_expanding &
            short_gate
        )

        # v2 RESEARCH: disable range-reversion shorts.
        # v1 evidence: 10 range_reversion_short trades = -5.001 USDT, 1/10 wins.
        range_short = dataframe['close'] < 0

        # v0.4 layer may still veto WATCH candidates.
        long_override_mask = ((dataframe['v04_action'] == 'WATCH') & (trend_long | range_long))
        short_override_mask = ((dataframe['v04_action'] == 'WATCH') & (trend_short | range_short))

        long_entries = (trend_long | range_long) & ~long_override_mask
        short_entries = (trend_short | range_short) & ~short_override_mask

        dataframe.loc[long_entries, 'enter_long'] = 1
        dataframe.loc[range_long & ~long_override_mask, 'enter_tag'] = 'research_range_reversion_long'
        dataframe.loc[trend_long & ~long_override_mask, 'enter_tag'] = 'research_trend_pullback_long'

        dataframe.loc[short_entries, 'enter_short'] = 1
        dataframe.loc[range_short & ~short_override_mask, 'enter_tag'] = 'research_range_reversion_short'
        dataframe.loc[trend_short & ~short_override_mask, 'enter_tag'] = 'research_trend_pullback_short'

        return dataframe

    def populate_exit_trend(self, dataframe, metadata):
        return dataframe

    def confirm_trade_entry(self, pair: str, order_type: str, amount: float,
                            rate: float, time_in_force: str, current_time: datetime,
                            entry_tag: Optional[str], side: str, **kwargs) -> bool:
        """FleetGuard v1 entry safety check."""
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
                        "pair": t.pair, "is_short": t.is_short,
                        "close_profit": t.close_profit or 0.0,
                    })
            total_profit = Trade.get_total_closed_profit()
            starting_balance = (self.wallets.get_starting_balance()
                               if hasattr(self, 'wallets') and self.wallets else 1000.0)
            if starting_balance > 0:
                current_drawdown = abs(min(0, total_profit / starting_balance))
        except Exception as e:
            logger.warning(f"FleetGuard data gathering fallback: {e}")
            try:
                from freqtrade.persistence import Trade
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

    def custom_stoploss(self, pair: str, trade, current_time, current_rate,
                        current_profit: float, **kwargs) -> float:
        """ATR-based custom stoploss for research variant.

        - Protect profits once current_profit > 2%.
        - Kill stale losers after 90 minutes.
        - Otherwise use 2x ATR relative to current rate, capped at -5%.
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe is None or dataframe.empty:
            return self.stoploss

        last_candle = dataframe.iloc[-1]
        atr = last_candle.get('atr')
        if atr is None or current_rate <= 0:
            return self.stoploss

        if current_profit > 0.02:
            return -0.012

        trade_duration_min = (current_time - trade.open_date_utc).total_seconds() / 60
        if trade_duration_min > 90 and current_profit < 0:
            return -0.018

        atr_stoploss = -(2 * float(atr) / float(current_rate))
        return max(atr_stoploss, -0.05)
