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
from primo_signal import primo_gate_allows
from fleet_risk_manager import FleetRiskManager

logger = logging.getLogger(__name__)


class FreqForge_Override(IStrategy):

    INTERFACE_VERSION = 3
    timeframe = "15m"
    informative_timeframe = "1h"
    can_short = True  # PAPER-TRADING OVERRIDE (2026-05-17) — siehe SOUL.md

    minimal_roi = {"0": 0.085, "45": 0.045, "90": 0.02, "180": 0}
    stoploss = -0.09
    use_custom_stoploss = False
    trailing_stop = False

    startup_candle_count = 500

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

    def _inject_ai_signal_override(self, dataframe: DataFrame, pair: str) -> None:
        """DISABLED 2026-05-21 (recovery safety repair).

        Previously: overrode v04 columns with raw AI signal if confidence >= 0.80,
        bypassing canonical RiskGuard gate. This is unsafe because it forces
        entries regardless of the pipeline's ACCEPTED/REJECTED verdict.

        Signal overrides must go through trading_pipeline.py -> fleet_risk_manager.py
        using CONFIDENCE_MIN = 0.65, not injected directly into strategy columns.

        Re-enable only after: (1) canonical gate integration, (2) backtest validation.
        """
        # Intentional no-op. AI signals flow through the pipeline correctly
        # without this direct column override.
        pass

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
        long_risk_allowed, long_risk_reason = self.risk_manager.check_entry_allowed(pair, "long")
        short_risk_allowed, short_risk_reason = self.risk_manager.check_entry_allowed(pair, "short")
        if not long_risk_allowed:
            logger.debug(f"[FleetRisk] LONG gate reduced for {pair}: {long_risk_reason}")
        if not short_risk_allowed:
            logger.debug(f"[FleetRisk] SHORT gate reduced for {pair}: {short_risk_reason}")
        long_gate = primo_gate_allows(pair, "long") and long_risk_allowed
        short_gate = primo_gate_allows(pair, "short") and short_risk_allowed

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

        # --- v0.4 SECOND LAYER: Override via v04_action column ---
        long_override_mask = ((dataframe['v04_action'] == 'WATCH') & (trend_long | range_long))

        # Apply combined entries
        long_entries = (trend_long | range_long) & ~long_override_mask

        dataframe.loc[long_entries, 'enter_long'] = 1
        dataframe.loc[long_entries, 'enter_tag'] = 'range_reversion_long'
        dataframe.loc[trend_long & ~long_override_mask, 'enter_tag'] = 'trend_pullback_long'

        # --- SHORT ENTRY LOGIC ---
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
            (dataframe['rsi'] > (100 - self.rsi_oversold.value)) &
            (dataframe['close'] > dataframe['bb_upperband']) &
            (dataframe['volume'] > dataframe['volume_mean']) &
            short_gate
        )

        # v0.4 SIGNAL OVERRIDE: DISABLED 2026-05-21 (recovery safety repair)
        # Previously: confidence >= 0.80 forced short regardless of TA analysis.
        # Signal overrides must go through canonical RiskGuard policy, not bypass TA here.
        # signal_override_short = (
        #     (dataframe['v04_action'] == 'SELL') &
        #     (dataframe['v04_confidence'] >= 0.80) &
        #     short_gate
        # )

        # Native short entries only (no AI signal override)
        short_entries = trend_short | range_short

        dataframe.loc[short_entries, 'enter_short'] = 1
        dataframe.loc[trend_short, 'enter_tag'] = 'trend_pullback_short'
        dataframe.loc[range_short, 'enter_tag'] = 'range_reversion_short'

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Nur ROI + Hard Stoploss — keine Exit-Signale
        return dataframe

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
