"""
FreqForge_Override — Experiment #001 Shadow Layer
Basiert auf RegimeSwitchingHybrid_v7_v04_Integration
+ DeepSeek V4 Flash Shadow confirm_trade_entry()

PASSIVER SHADOW: confirm_trade_entry() gibt immer True zurueck.
Das LLM wird beobachtend angefragt, schreibt Ergebnisse in freqforge_shadow.log.
KEIN EINGRIFF in Trades.
"""
import logging
import sys
import json
import os
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

import talib.abstract as ta
from freqtrade.strategy import IStrategy, IntParameter, DecimalParameter, merge_informative_pair
import freqtrade.vendor.qtpylib.indicators as qtpylib
from pandas import DataFrame

sys.path.insert(0, "/freqtrade/shared")
from primo_signal import primo_gate_allows
from fleetguard_v1 import FleetGuard, FleetGuardConfig

logger = logging.getLogger(__name__)

DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"

# ============================================================
# CONSTANTS (module-level, read-only)
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

class FreqForge_Override(IStrategy):

    INTERFACE_VERSION = 3
    timeframe = "15m"
    informative_timeframe = "1h"
    can_short = False

    minimal_roi = {"0": 0.085, "45": 0.045, "90": 0.02, "180": 0}
    stoploss = -0.09
    use_custom_stoploss = False
    trailing_stop = False
    # trailing_stop_positive = 0.01
    # trailing_stop_positive_offset = 0.02
    # trailing_only_offset_is_reached = True

    startup_candle_count = 500

    # NOTE: Im Shadow-Modus gibt confirm_trade_entry immer True.
    # FleetGuard bleibt als Instanz fuer Vergleiche erhalten.
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

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        # Per-pair regime history — no cross-pair contamination
        self._regime_histories: Dict[str, list] = {}

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

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        ema200_htf = dataframe[f'ema200_{self.informative_timeframe}']
        pair = metadata.get("pair")
        long_gate = primo_gate_allows(pair, "long")
        short_gate = primo_gate_allows(pair, "short")

        # --- Strategy-native LONG conditions ---
        trend_long = (
            (dataframe['adx_rel'] > self.adx_rel_threshold.value) &
            (dataframe['close'] > ema200_htf) &
            (dataframe['close'] > dataframe['ema200']) &
            (dataframe['close'] < dataframe['ema50']) &
            (dataframe['rsi'] < 50) &
            (dataframe['volume'] > dataframe['volume_mean']) &
            long_gate
        )

        range_long = (
            (dataframe['adx_rel'] <= self.adx_rel_threshold.value) &
            (dataframe['rsi'] < self.rsi_oversold.value) &
            (dataframe['close'] < dataframe['bb_lowerband']) &
            (dataframe['volume'] > dataframe['volume_mean']) &
            long_gate
        )

        # --- Strategy-native SHORT conditions ---
        trend_short = (
            (dataframe['adx_rel'] > self.adx_rel_threshold.value) &
            (dataframe['close'] < ema200_htf) &
            (dataframe['close'] < dataframe['ema200']) &
            (dataframe['close'] > dataframe['ema50']) &
            (dataframe['rsi'] > 50) &
            (dataframe['volume'] > dataframe['volume_mean']) &
            short_gate
        )

        range_short = (
            (dataframe['adx_rel'] <= self.adx_rel_threshold.value) &
            (dataframe['rsi'] > 75) &
            (dataframe['close'] > dataframe['bb_upperband']) &
            (dataframe['volume'] > dataframe['volume_mean']) &
            short_gate
        )

        # --- v0.4 SECOND LAYER: Override via v04_action column ---
        long_override_mask = ((dataframe['v04_action'] == 'WATCH') & (trend_long | range_long))
        short_override_mask = ((dataframe['v04_action'] == 'WATCH') & (trend_short | range_short))

        # Apply combined entries (v0.4 can override to WATCH)
        long_entries = (trend_long | range_long) & ~long_override_mask
        short_entries = (trend_short | range_short) & ~short_override_mask

        dataframe.loc[long_entries, 'enter_long'] = 1
        dataframe.loc[long_entries, 'enter_tag'] = 'range_reversion_long'
        dataframe.loc[trend_long & ~long_override_mask, 'enter_tag'] = 'trend_pullback_long'
        dataframe.loc[short_entries, 'enter_short'] = 1
        dataframe.loc[short_entries, 'enter_tag'] = 'range_reversion_short'
        dataframe.loc[trend_short & ~short_override_mask, 'enter_tag'] = 'trend_pullback_short'

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Exit-Signale deaktiviert — nur ROI + Hard Stoploss
        return dataframe

    def confirm_trade_entry(self, pair: str, order_type: str, amount: float,
                            rate: float, time_in_force: str, current_time: datetime,
                            entry_tag: Optional[str], side: str, **kwargs) -> bool:
        """
        FREQFORGE SHADOW LAYER — Experiment #001
        Sammelt Markt-Kontext, fragt DeepSeek V4 Flash,
        loggt die LLM-Entscheidung in freqforge_shadow.log.
        Gibt IMMER True zurueck — reiner Shadow-Modus.

        Um echte LLM-Calls zu aktivieren: DEEPSEEK_API_KEY als Env-Variable setzen.
        Ohne Key wird nur "SKIP_NO_KEY" geloggt.
        """
        # --- MARKT-KONTEXT SAMMELN ---
        log_entry = {
            "timestamp": current_time.isoformat(),
            "pair": pair,
            "rate": float(rate),
            "side": side,
            "entry_tag": entry_tag,
            "amount": float(amount),
            "strategy": "FreqForge_Override",
            "experiment": "001-shadow-deepseek",
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

        # --- DEEPSEEK V4 FLASH SHADOW CALL ---
        api_key = os.environ.get("DEEPSEEK_API_KEY", "")
        if api_key:
            prompt_parts = [
                "Du bist ein Signal-Reviewer. Bewerte diesen Trade.",
                f"Pair: {pair}",
                f"Side: {side}",
                f"Rate: {rate}",
                f"Entry Tag: {entry_tag}",
                f"RSI: {log_entry.get('rsi', '?')}",
                f"ADX: {log_entry.get('adx', '?')}",
                f"ADX_rel: {log_entry.get('adx_rel', '?')}",
                f"ATR%: {log_entry.get('atr_pct', '?')}",
                f"v0.4 Action: {log_entry.get('v04_action', '?')}",
                f"v0.4 Regime: {log_entry.get('v04_regime', '?')}",
                "",
                "Antworte NUR mit YES, NO oder REDUCE_50. Keine Erklarung.",
            ]
            prompt = "\n".join(prompt_parts)

            try:
                payload = json.dumps({
                    "model": "deepseek-chat",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 10,
                    "temperature": 0.0,
                }).encode("utf-8")

                req = urllib.request.Request(
                    DEEPSEEK_API_URL,
                    data=payload,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {api_key}",
                    },
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    result = json.loads(resp.read().decode("utf-8"))
                    llm_raw = result["choices"][0]["message"]["content"].strip().upper()
                    # Clean up — nur YES/NO/REDUCE_50 extrahieren
                    for token in ["YES", "NO", "REDUCE_50"]:
                        if token in llm_raw:
                            log_entry["llm_decision"] = token
                            break
                    else:
                        log_entry["llm_decision"] = f"UNEXPECTED:{llm_raw}"
                    logger.info(
                        f"FreqForge Shadow [{pair} {side}]: "
                        f"LLM sagt {log_entry['llm_decision']} "
                        f"(RSI={log_entry.get('rsi','?')}, "
                        f"v04={log_entry.get('v04_action','?')})"
                    )

            except urllib.error.HTTPError as e:
                log_entry["llm_error"] = f"HTTP {e.code}: {e.reason}"
                logger.warning(f"FreqForge Shadow HTTP Error: {e.code} - {e.reason}")
            except urllib.error.URLError as e:
                log_entry["llm_error"] = f"URL Error: {e.reason}"
                logger.warning(f"FreqForge Shadow URL Error: {e.reason}")
            except Exception as e:
                log_entry["llm_error"] = str(e)
                logger.warning(f"FreqForge Shadow Call failed: {e}")
        else:
            log_entry["llm_decision"] = "SKIP_NO_KEY"
            logger.info(
                f"FreqForge Shadow [{pair} {side}]: "
                f"DEEPSEEK_API_KEY nicht gesetzt — uebersprungen"
            )

        # --- SHADOW LOG SCHREIBEN (JSONL) ---
        try:
            log_path = "/freqtrade/logs/freqforge_shadow.log"
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            with open(log_path, "a") as f:
                f.write(json.dumps(log_entry) + "\n")
        except Exception as e:
            logger.error(f"FreqForge Shadow log write failed: {e}")

        # ENTRY-VETO MODE — LLM-Entscheidung respektieren
        # YES: Trade durchlassen | NO: Trade ablehnen | REDUCE_50: durchlassen (später custom_stake)
        decision = log_entry.get("llm_decision", "YES")
        if decision == "NO":
            logger.info(
                f"FreqForge VETO [{pair} {side}]: "
                f"Trade abgelehnt (LLM sagt NO)"
            )
            return False
        # YES / REDUCE_50 / SKIP_NO_KEY / UNEXPECTED -> Trade durchlassen
        return True

    def custom_stoploss(self, pair: str, trade, current_time, current_rate,
                        current_profit: float, **kwargs) -> float:
        """ATR-based dynamic stoploss with regime-aware trailing."""
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe.empty:
            return self.stoploss

        last = dataframe.iloc[-1]
        atr_pct = last['atr_pct']
        adx_rel = last.get('adx_rel', 1.0)
        is_trend = adx_rel > self.adx_rel_threshold.value

        if is_trend:
            sl_distance = atr_pct * self.atr_sl_trend
            tp_trigger = atr_pct * self.atr_tp_trend.value
            if current_profit > tp_trigger:
                return max(-sl_distance, current_profit - sl_distance)
            return -sl_distance
        else:
            sl_distance = atr_pct * self.atr_sl_range.value
            return -sl_distance
