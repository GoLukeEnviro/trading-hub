# pragma pylint: disable=missing-docstring, invalid-name, pointless-string-statement
# flake8: noqa: F401
# isort: skip_file
# --- Do not remove these libs ---
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy, IntParameter, DecimalParameter
from freqtrade.strategy.parameters import CategoricalParameter

# ── Pair filename mapping (mirrors hermes-bridge convention) ────────
def _pair_to_signal_filename(pair: str) -> str:
    """BTC/USDT:USDT → BTC_USDT_USDT.json"""
    return pair.replace("/", "_").replace(":", "_") + ".json"

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# MinimalViableStrategy_v1 — Hermes-Controlled Primo + Freqtrade Pipeline
# ═══════════════════════════════════════════════════════════════════
#
# Entry:     EMA9/EMA21 crossover with close confirmation
# External:  Requires fresh Hermes-approved Primo signal via shared signal bus
# Stoploss:  Dynamic ATR(14) * 2.5, hard cap -0.03
# ROI:       {"0": 0.02, "120": 0.01, "240": 0}
# Position:  Exactly 1% account risk based on stoploss distance
# Leverage:  Max 10x
# Pairs:     BTC/USDT:USDT, ETH/USDT:USDT, SOL/USDT:USDT
# Timeframe: 1h
# ═══════════════════════════════════════════════════════════════════


class MinimalViableStrategy_v1(IStrategy):
    """
    Hermes-Controlled Minimal Viable Strategy v1.

    This strategy does NOT trade standalone. It requires:
      1. EMA9/EMA21 crossover entry signal
      2. Fresh Hermes-approved Primo signal on the shared signal bus
    Without both conditions met, no entry is opened.
    """

    # ── Strategy Metadata ──────────────────────────────────────────
    INTERFACE_VERSION = 3

    can_short = False  # v1: long-only

    timeframe = "1h"

    # Can include informative timeframes for future use
    # informative_timeframe = ["4h"]

    # ── Pairs ──────────────────────────────────────────────────────
    process_only_new_candles = True
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    # ── Startup candle count ───────────────────────────────────────
    startup_candle_count: int = 50  # Need 21+ for EMA21 + safety margin

    # ── Position sizing ────────────────────────────────────────────
    position_adjustment_enable = False

    # ── Stoploss ───────────────────────────────────────────────────
    use_custom_stoploss = True
    stoploss = -0.03  # Hard max cap (fallback if ATR not available)

    # ── Signal bus config ──────────────────────────────────────────
    signal_bus_dir: str = "/freqtrade/shared/signals"
    signal_max_age_seconds: int = 90

    # ── Entry: EMA Crossover ───────────────────────────────────────
    # These are fixed in v1 but could be tunable later
    ema_fast_period: int = 9
    ema_slow_period: int = 21

    # ── Trailing Stoploss ──────────────────────────────────────────
    trailing_stop = False
    # trailing_stop_positive = 0.01
    # trailing_stop_positive_offset = 0.02
    # trailing_only_offset_is_reached = True

    # ── ROI Table ──────────────────────────────────────────────────
    minimal_roi = {
        "0": 0.02,     # 2% immediate ROI
        "120": 0.01,   # 1% after 2h
        "240": 0,      # Exit after 4h
    }

    # ── Leverage (per-pair, used by leverage() callback below) ─────
    _leverage_map: dict = {
        "BTC/USDT:USDT": 10.0,
        "ETH/USDT:USDT": 10.0,
        "SOL/USDT:USDT": 10.0,
    }

    # ═══════════════════════════════════════════════════════════════
    # Signal Bus Helpers
    # ═══════════════════════════════════════════════════════════════

    def _read_hermes_signal(self, pair: str) -> Optional[Dict[str, Any]]:
        """
        Read the Hermes-approved signal for THIS pair from the shared bus.
        Uses per-pair signal file: /freqtrade/shared/signals/BTC_USDT_USDT.json
        Returns None if missing, stale, invalid, or mismatched pair.
        """
        filename = _pair_to_signal_filename(pair)
        signal_file = Path(self.signal_bus_dir) / filename

        if not signal_file.exists():
            logger.debug(f"Signal file missing for {pair}: {signal_file}")
            return None

        try:
            signal = json.loads(signal_file.read_text())
        except (json.JSONDecodeError, OSError):
            logger.warning(f"Signal file unreadable for {pair}: {signal_file}")
            return None

        if not isinstance(signal, dict):
            return None

        # Check signal pair matches
        signal_pair = signal.get("pair", "")
        if signal_pair != pair:
            logger.debug(f"Signal pair mismatch: {signal_pair} != {pair}")
            return None

        # Check freshness
        ts_str = signal.get("timestamp_utc", "")
        try:
            ts = datetime.fromisoformat(ts_str)
            age = (datetime.now(timezone.utc) - ts).total_seconds()
            if age > self.signal_max_age_seconds:
                logger.debug(f"Signal stale for {pair}: {age:.0f}s old")
                return None
        except (ValueError, TypeError):
            logger.warning(f"Signal timestamp invalid for {pair}: {ts_str!r}")
            return None

        # Check approval
        if signal.get("approved_by") != "hermes":
            logger.debug(f"Signal not approved by Hermes for {pair}")
            return None

        # Check veto
        if signal.get("veto", False):
            logger.debug(f"Signal vetoed for {pair}")
            return None

        # Check direction
        if signal.get("direction") != "long":
            logger.debug(f"Signal direction not long for {pair}: {signal.get('direction')}")
            return None

        return signal

    # ═══════════════════════════════════════════════════════════════
    # Indicator Calculation
    # ═══════════════════════════════════════════════════════════════

    def populate_indicators(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        """
        Add EMA9, EMA21, ATR(14) to the dataframe.
        """

        # ── EMA ────────────────────────────────────────────────────
        dataframe["ema9"] = dataframe["close"].ewm(span=self.ema_fast_period, adjust=False).mean()
        dataframe["ema21"] = dataframe["close"].ewm(span=self.ema_slow_period, adjust=False).mean()

        # ── EMA crossover conditions ───────────────────────────────
        dataframe["ema_cross_up"] = (
            (dataframe["ema9"] > dataframe["ema21"]) &
            (dataframe["ema9"].shift(1) <= dataframe["ema21"].shift(1))
        )
        dataframe["ema9_above_ema21"] = dataframe["ema9"] > dataframe["ema21"]

        # ── ATR(14) ────────────────────────────────────────────────
        high = dataframe["high"]
        low = dataframe["low"]
        close = dataframe["close"]

        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low - close.shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        dataframe["atr"] = tr.rolling(window=14).mean()

        # ── Close confirmation ─────────────────────────────────────
        # Current close > previous close (momentum confirmation)
        dataframe["close_up"] = dataframe["close"] > dataframe["close"].shift(1)

        return dataframe

    # ═══════════════════════════════════════════════════════════════
    # Entry Logic
    # ═══════════════════════════════════════════════════════════════

    def populate_entry_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        """
        Entry conditions:
          1. EMA9 crosses above EMA21
          2. Close confirms (current close > previous close)
          3. Fresh Hermes-approved Primo signal available on signal bus
        """

        pair = metadata.get("pair", "")

        # ── Hermes signal check (only in live/dry-run mode, not backtest) ──
        signal_ok = True  # default: allow in backtest
        if self.dp.runmode.value in ("live", "dry_run"):
            hermes_signal = self._read_hermes_signal(pair)
            signal_ok = hermes_signal is not None
            if signal_ok:
                logger.info(
                    f"[{pair}] Hermes signal ACTIVE: "
                    f"dir={hermes_signal.get('direction')} "
                    f"conf={hermes_signal.get('confidence', 0):.4f}"
                )
            else:
                logger.debug(f"[{pair}] No valid Hermes signal")

        # ── Technical conditions ───────────────────────────────────
        dataframe["enter_long"] = 0
        dataframe.loc[
            (
                dataframe["ema_cross_up"]           # EMA9 crosses EMA21
                & dataframe["close_up"]             # Close confirmation
            ),
            "enter_long"
        ] = 1

        # ── External gate: must have Hermes signal ──────────────────
        if not signal_ok:
            dataframe["enter_long"] = 0

        return dataframe

    def populate_exit_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        """
        Exit handled by stoploss, ROI, and trailing stop.
        No manual exit signal in v1.
        """
        dataframe["exit_long"] = 0
        return dataframe

    # ═══════════════════════════════════════════════════════════════
    # Dynamic Stoploss
    # ═══════════════════════════════════════════════════════════════

    def custom_stoploss(
        self,
        pair: str,
        trade: Trade,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        after_fill: bool,
        **kwargs,
    ) -> Optional[float]:
        """
        Dynamic ATR-based stoploss with profit-gated trailing.

        Behavior:
        - While trade is losing (current_profit <= 0): use hard stoploss -0.03
        - While trade is profitable: calculate ATR(14)*2.5 trailing stop

        This prevents the trailing stop from prematurely exiting losing trades
        when ATR shrinks, which caused 274 false exits with 1.5% win rate.
        """

        if after_fill:
            return None  # Let the trade settle first

        # While losing, use the hard cap stoploss
        if current_profit <= 0:
            return self.stoploss  # -0.03

        # Only trail when in profit
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe.empty:
            return self.stoploss

        last_candle = dataframe.iloc[-1]
        atr = float(last_candle.get("atr", 0))
        close = float(last_candle.get("close", 0))

        if atr <= 0 or close <= 0:
            return self.stoploss

        # ATR(14) * 2.5 as percentage of current price
        atr_stop_pct = (atr * 2.5) / close

        # Cap at the hard stoploss (-0.03)
        effective_stop = min(atr_stop_pct, abs(self.stoploss))

        # Return negative stoploss
        return -effective_stop

    # ═══════════════════════════════════════════════════════════════
    # Custom Stake Amount (1% Account Risk)
    # ═══════════════════════════════════════════════════════════════

    def custom_stake_amount(
        self,
        pair: str,
        current_time: datetime,
        current_rate: float,
        proposed_stake: float,
        min_stake: Optional[float],
        max_stake: float,
        leverage: float,
        entry_tag: Optional[str],
        side: str,
        **kwargs,
    ) -> float:
        """
        Calculate stake size based on exactly 1% account risk.

        stake = (wallet_size * 0.01) / (stoploss_pct * leverage)
        """

        wallet_size = self.wallets.get_total_stake_amount()

        # Determine the stoploss distance for this trade
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if not dataframe.empty:
            last_candle = dataframe.iloc[-1]
            atr = float(last_candle.get("atr", 0))
            close = float(last_candle.get("close", 0))
            if atr > 0 and close > 0:
                stoploss_pct = min((atr * 2.5) / close, abs(self.stoploss))
            else:
                stoploss_pct = abs(self.stoploss)
        else:
            stoploss_pct = abs(self.stoploss)

        # Risk-based sizing
        effective_leverage = leverage if leverage and leverage > 0 else 1.0
        risk_amount = wallet_size * 0.01  # 1% of wallet
        calculated_stake = risk_amount / (stoploss_pct * effective_leverage)

        # Clamp
        result = max(min_stake or 0, min(calculated_stake, max_stake))

        logger.info(
            f"[{pair}] custom_stake_amount: wallet={wallet_size:.1f}, "
            f"risk=1%, stop={stoploss_pct:.4f}, lev={effective_leverage:.1f}x, "
            f"stake={result:.1f}"
        )

        return result

    # ═══════════════════════════════════════════════════════════════
    # Leverage Callback
    # ═══════════════════════════════════════════════════════════════

    def leverage(self, pair: str, current_rate: float, proposed_leverage: float, **kwargs) -> float:
        """Per-pair leverage callback. Freqtrade calls this by method name."""
        return self._leverage_map.get(pair, 10.0)
