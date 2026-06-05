"""
FreqForge_Override — Baseline v1
Basiert auf RegimeSwitchingHybrid_v7_v04_Integration

Nur ROI + Hard Stoploss (-9%).
Kein Trailing, keine Exit-Signale, kein LLM-Layer.
Shadow-JSONL-Logging in freqforge_shadow.log (passiv).
"""
import logging
import sys
import json
import os
from datetime import datetime
from typing import Optional
from pathlib import Path

import talib.abstract as ta
from freqtrade.strategy import IStrategy, IntParameter, DecimalParameter, merge_informative_pair
import freqtrade.vendor.qtpylib.indicators as qtpylib
from pandas import DataFrame

sys.path.insert(0, "/freqtrade/shared")
from primo_signal import primo_gate_allows, load_signal_state, normalize_pair
from fleet_risk_manager import FleetRiskManager

logger = logging.getLogger(__name__)


class FreqForge_Override(IStrategy):

    INTERFACE_VERSION = 3
    timeframe = "15m"
    informative_timeframe = "1h"
    can_short = True  # PAPER-TRADING OVERRIDE (2026-05-17) — siehe SOUL.md

    minimal_roi = {"0": 0.060, "180": 0.040, "480": 0.025, "960": 0.015}
    stoploss = -0.050
    use_custom_stoploss = True
    trailing_stop = False

    startup_candle_count = 500
    AI_OVERRIDE_ALLOWED_PAIRS = {"BTC/USDT", "ETH/USDT", "SOL/USDT"}
    AI_OVERRIDE_CONFIDENCE_MIN = 0.75

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

    adx_rel_threshold = DecimalParameter(0.75, 1.20, default=0.90, space="buy")
    rsi_oversold = IntParameter(24, 42, default=32, space="buy")

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        self._regime_histories: dict = {}
        self.risk_manager = FleetRiskManager()
        self._fleet_source = str(config.get("bot_name") or self.__class__.__name__)

    def _get_stable_regime(self, pair: str, current_regime: str) -> str:
        """2-cycle hysteresis per pair. Regime shifts only after 2 consecutive same candles."""
        if pair not in self._regime_histories:
            self._regime_histories[pair] = []
        history = self._regime_histories[pair]
        history.append(current_regime)
        if len(history) > 2:
            history.pop(0)
        if len(history) == 2 and history[0] == history[1]:
            return history[1]
        return history[0] if history else "unknown"

    def bot_loop_start(self, current_time: datetime, **kwargs) -> None:
        try:
            from freqtrade.persistence import Trade
            source = self._fleet_source
            open_trades = list(Trade.get_trades_proxy(is_open=True))
            closed_trades = list(Trade.get_trades_proxy(is_open=False))
            self.risk_manager.sync_trade_state(source=source, open_trades=open_trades, closed_trades=closed_trades)
            if hasattr(self, "wallets") and self.wallets:
                try:
                    self.risk_manager.update_source_equity(source, float(self.wallets.get_total_stake_amount()))
                except Exception as wallet_err:
                    logger.debug(f"FleetRisk source equity skipped for {source}: {wallet_err}")
        except Exception as exc:
            logger.debug(f"FleetRisk sync skipped for {self._fleet_source}: {exc}")

    def informative_pairs(self):
        pairs = self.dp.current_whitelist()
        return [(pair, self.informative_timeframe) for pair in pairs]

    def _build_v04_signal_layer(self, dataframe: DataFrame, pair: str) -> None:
        """Pre-compute v0.4 signals as vectorized columns. Uses per-pair regime tracking."""
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

        # Per-pair stable regime (last candle)
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
        rsi_factor = ((dataframe.loc[trend_buy_mask, 'rsi'] >= 35) &
                      (dataframe.loc[trend_buy_mask, 'rsi'] <= 65)).astype(float) * 0.3 + 0.7
        vol_factor = 1.1 * (dataframe.loc[trend_buy_mask, 'volume_ratio'] > 1.1).astype(float) + \
                     0.9 * (dataframe.loc[trend_buy_mask, 'volume_ratio'] <= 1.1).astype(float)
        dataframe.loc[trend_buy_mask, 'v04_confidence'] = (adx_raw * rsi_factor * vol_factor).clip(0, 1).round(4)

        dataframe.loc[trend_sell_mask, 'v04_action'] = 'SELL'
        dataframe.loc[trend_sell_mask, 'v04_strategy'] = 'TREND_FOLLOWING'
        adx_raw = ((dataframe.loc[trend_sell_mask, 'adx'] - 22) / 18).clip(0, 1)
        rsi_factor = ((dataframe.loc[trend_sell_mask, 'rsi'] >= 35) &
                      (dataframe.loc[trend_sell_mask, 'rsi'] <= 65)).astype(float) * 0.3 + 0.7
        vol_factor = 1.1 * (dataframe.loc[trend_sell_mask, 'volume_ratio'] > 1.1).astype(float) + \
                     0.9 * (dataframe.loc[trend_sell_mask, 'volume_ratio'] <= 1.1).astype(float)
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

        # AI SIGNAL OVERRIDE: Inject primo bridge confidence into v04 columns
        # Enables execution override in populate_entry_trend for high-conviction AI signals
        self._inject_ai_signal_override(dataframe, pair)

    def _get_ai_override_signal(self, pair: str) -> Optional[dict]:
        normalized_pair = normalize_pair(pair)
        if normalized_pair not in self.AI_OVERRIDE_ALLOWED_PAIRS:
            return None

        state = load_signal_state()
        if not isinstance(state, dict) or not state.get("fresh", False):
            return None

        pair_state = (state.get("pairs") or {}).get(normalized_pair)
        if not isinstance(pair_state, dict):
            return None

        verdict = str(pair_state.get("verdict", "UNKNOWN")).upper().strip()
        action = str(pair_state.get("action", "HOLD")).upper().strip()
        confidence = float(pair_state.get("confidence", 0.0) or 0.0)
        riskguard_reason = str(pair_state.get("riskguard_reason", "") or "")
        riskguard_accepted = verdict == "ACCEPTED" or riskguard_reason.upper().startswith("PASS")

        if verdict != "ACCEPTED":
            return None
        if action not in {"BUY", "LONG", "SELL", "SHORT"}:
            return None
        if not (confidence >= self.AI_OVERRIDE_CONFIDENCE_MIN or riskguard_accepted):
            return None

        bias_allowed = bool(pair_state.get("allow_long_bias", False)) if action in {"BUY", "LONG"} else bool(pair_state.get("allow_short_bias", False))
        if not bias_allowed:
            return None

        return {
            "pair": normalized_pair,
            "action": action,
            "confidence": confidence,
            "verdict": verdict,
            "riskguard_reason": riskguard_reason,
        }

    def _inject_ai_signal_override(self, dataframe: DataFrame, pair: str) -> None:
        """Inject ACCEPTED ai-hedge-fund-crypto signals for BTC/ETH/SOL only.

        Safety gates:
        - canonical primo_signal_state must mark the pair ACCEPTED
        - confidence must be >= 0.75 OR RiskGuard must have passed the signal
        - allow_long_bias / allow_short_bias must still agree with the side
        - only the latest candle is overridden (dry-run forward mode, no backfill)
        """
        if dataframe.empty:
            return

        signal = self._get_ai_override_signal(pair)
        if not signal:
            return

        idx = dataframe.index[-1]
        action = "BUY" if signal["action"] in {"BUY", "LONG"} else "SELL"
        dataframe.at[idx, 'v04_action'] = action
        dataframe.at[idx, 'v04_confidence'] = max(float(dataframe.at[idx, 'v04_confidence']), signal["confidence"])
        dataframe.at[idx, 'v04_strategy'] = 'AI_OVERRIDE'
        dataframe.at[idx, 'v04_regime'] = f"ai_{action.lower()}"
        logger.info(
            "[AIOverride] %s -> %s conf=%.2f verdict=%s",
            signal["pair"],
            action,
            signal["confidence"],
            signal["verdict"],
        )

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        if not self.dp:
            return dataframe

        pair = metadata.get("pair", "UNKNOWN")

        informative = self.dp.get_pair_dataframe(
            pair=pair, timeframe=self.informative_timeframe
        )
        informative['ema200'] = ta.EMA(informative, timeperiod=200)
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

        # v0.4 signal pre-computation (vectorized, per-pair regime tracking)
        self._build_v04_signal_layer(dataframe, pair)

        return dataframe

    def custom_stoploss(self, pair: str, trade, current_time, current_rate,
                         current_profit: float, after_fill: bool, **kwargs) -> float:
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
        ema200_htf = dataframe[f'ema200_{self.informative_timeframe}']
        pair = metadata.get("pair")
        long_risk_allowed, long_risk_reason = self.risk_manager.check_entry_allowed(pair, "long")
        short_risk_allowed, short_risk_reason = self.risk_manager.check_entry_allowed(pair, "short")
        if not long_risk_allowed:
            logger.debug(f"[FleetRisk] LONG gate reduced for {pair}: {long_risk_reason}")
        if not short_risk_allowed:
            logger.debug(f"[FleetRisk] SHORT gate reduced for {pair}: {short_risk_reason}")
        long_gate = primo_gate_allows(pair, "long") and long_risk_allowed
        short_gate = primo_gate_allows(pair, "short") and short_risk_allowed

        # --- Strategy-native LONG conditions (slightly loosened to recover flow) ---
        trend_long = (
            (dataframe['adx_rel'] > self.adx_rel_threshold.value) &
            (dataframe['close'] > (ema200_htf * 0.995)) &
            (dataframe['close'] > (dataframe['ema200'] * 0.995)) &
            (dataframe['close'] < (dataframe['ema50'] * 1.015)) &
            (dataframe['rsi'] < 56) &
            (dataframe['rsi'] > 28) &
            (dataframe['volume_ratio'] > 0.85) &
            long_gate
        )

        range_long = (
            (dataframe['adx_rel'] <= (self.adx_rel_threshold.value * 1.05)) &
            (dataframe['rsi'] < self.rsi_oversold.value) &
            (dataframe['close'] <= (dataframe['bb_lowerband'] * 1.01)) &
            (dataframe['volume_ratio'] > 0.75) &
            long_gate
        )

        signal_override_long = (
            dataframe['v04_strategy'].eq('AI_OVERRIDE') &
            dataframe['v04_action'].isin(['BUY', 'LONG']) &
            (dataframe['v04_confidence'] >= self.AI_OVERRIDE_CONFIDENCE_MIN) &
            long_gate
        )

        long_entries = trend_long | range_long | signal_override_long
        dataframe.loc[long_entries, 'enter_long'] = 1
        dataframe.loc[range_long, 'enter_tag'] = 'range_reversion_long'
        dataframe.loc[trend_long, 'enter_tag'] = 'trend_pullback_long'
        dataframe.loc[signal_override_long, 'enter_tag'] = 'ai_override_long'

        # --- SHORT ENTRY LOGIC ---
        trend_short = (
            (dataframe['adx_rel'] > self.adx_rel_threshold.value) &
            (dataframe['close'] < (ema200_htf * 1.005)) &
            (dataframe['close'] < (dataframe['ema200'] * 1.005)) &
            (dataframe['close'] > (dataframe['ema50'] * 0.985)) &
            (dataframe['rsi'] > 44) &
            (dataframe['rsi'] < 72) &
            (dataframe['volume_ratio'] > 0.85) &
            short_gate
        )

        range_short = (
            (dataframe['adx_rel'] <= (self.adx_rel_threshold.value * 1.05)) &
            (dataframe['rsi'] > (100 - self.rsi_oversold.value)) &
            (dataframe['close'] >= (dataframe['bb_upperband'] * 0.99)) &
            (dataframe['volume_ratio'] > 0.75) &
            short_gate
        )

        signal_override_short = (
            dataframe['v04_strategy'].eq('AI_OVERRIDE') &
            dataframe['v04_action'].isin(['SELL', 'SHORT']) &
            (dataframe['v04_confidence'] >= self.AI_OVERRIDE_CONFIDENCE_MIN) &
            short_gate
        )

        short_entries = trend_short | range_short | signal_override_short
        dataframe.loc[short_entries, 'enter_short'] = 1
        dataframe.loc[trend_short, 'enter_tag'] = 'trend_pullback_short'
        dataframe.loc[range_short, 'enter_tag'] = 'range_reversion_short'
        dataframe.loc[signal_override_short, 'enter_tag'] = 'ai_override_short'

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Nur ROI + custom_exit + Hard Stoploss — keine Exit-Signale im Candle-Frame
        return dataframe

    def custom_exit(self, pair: str, trade, current_time: datetime, current_rate: float,
                    current_profit: float, **kwargs):
        trade_duration = (current_time - trade.open_date_utc).total_seconds() / 60
        try:
            dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            if dataframe is None or dataframe.empty:
                return None
            last = dataframe.iloc[-1]
            rsi = float(last.get("rsi", 50.0))
            adx_rel = float(last.get("adx_rel", 1.0))
            v04_action = str(last.get("v04_action", "WATCH")).upper()
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

        if current_profit >= 0.02 and v04_strategy == "AI_OVERRIDE":
            if trade.is_short and v04_action not in {"SELL", "SHORT"}:
                return "ai_bias_lost"
            if not trade.is_short and v04_action not in {"BUY", "LONG"}:
                return "ai_bias_lost"

        if current_profit >= 0.015 and trade_duration > 960 and v04_strategy != "AI_OVERRIDE":
            return "tp_time_decay"

        return None

    def confirm_trade_entry(self, pair: str, order_type: str, amount: float,
                            rate: float, time_in_force: str, current_time: datetime,
                            entry_tag: Optional[str], side: str, **kwargs) -> bool:
        """
        PASSIVES SHADOW-LOGGING — zeichnet jeden Trade mit Marktkontext auf.
        Gibt immer True zurueck (kein Eingriff in Trades).
        """
        risk_allowed, risk_reason = self.risk_manager.check_entry_allowed(pair, side)
        if not risk_allowed:
            logger.info(f"[FleetRisk] Entry blockiert: {pair} {side} -> {risk_reason}")
            return False
        if not primo_gate_allows(pair, side):
            logger.info(f"[PrimoGate] Entry blockiert: {pair} {side}")
            return False

        log_entry = {
            "timestamp": current_time.isoformat(),
            "pair": pair,
            "rate": float(rate),
            "side": side,
            "entry_tag": entry_tag,
            "amount": float(amount),
            "strategy": "FreqForge_Override",
            "config": "baseline-v1",
        }

        # DataFrame-Kontext aus der letzten Kerze holen
        try:
            dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            if dataframe is not None and not dataframe.empty:
                last = dataframe.iloc[-1]
                log_entry["close"] = float(last.get("close", 0))
                log_entry["rsi"] = float(last.get("rsi", 0))
                log_entry["adx"] = float(last.get("adx", 0))
                log_entry["adx_rel"] = float(last.get("adx_rel", 1.0))
                log_entry["atr_pct"] = float(last.get("atr_pct", 0))
                log_entry["bb_width"] = float(last.get("bb_width", 0))
                log_entry["v04_action"] = str(last.get("v04_action", "N/A"))
                log_entry["v04_confidence"] = float(last.get("v04_confidence", 0))
                log_entry["v04_strategy"] = str(last.get("v04_strategy", "N/A"))
                log_entry["v04_regime"] = str(last.get("v04_regime", "N/A"))
                log_entry["volume_ratio"] = float(
                    last.get("volume", 0) / last.get("volume_mean", 1)
                    if last.get("volume_mean", 0) > 0 else 0
                )
        except Exception as e:
            log_entry["context_error"] = str(e)

        log_entry["fleet_risk_level"] = self.risk_manager.get_drawdown_level()
        log_entry["fleet_risk_reason"] = risk_reason
        try:
            cluster = self.risk_manager._get_cluster(pair)
            stats = self.risk_manager.get_cluster_stats(cluster)
            log_entry["fleet_risk_cluster"] = cluster
            log_entry["fleet_cluster_winrate"] = round(float(stats.get("winrate", 0.5)), 4)
            log_entry["fleet_cluster_pnl"] = round(float(stats.get("pnl", 0.0)), 4)
        except Exception as exc:
            log_entry["fleet_risk_context_error"] = str(exc)

        # JSONL-Log schreiben
        try:
            log_path = "/freqtrade/logs/freqforge_shadow.log"
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            with open(log_path, "a") as f:
                f.write(json.dumps(log_entry) + "\\n")
        except Exception as e:
            logger.error(f"FreqForge Shadow log write failed: {e}")

        return True
