"""
RegimeSwitchingHybrid_v9_1_Sentient
=====================================
v8.1 Entry Engine + v9.0 LLM Sentient Exit Layer.

Changes vs v8.1:
  REMOVED: populate_exit_trend (RSI overbought exit)
  NEW:     custom_exit() — calls ExitAgent with full trade context
  NEW:     import exit_agent_v9 from shared
  KEEP:    Entry logic (ADX + EMA50 + RSI + volume + primo_gate)
  KEEP:    FleetGuard entry safety (confirm_trade_entry)
  KEEP:    stoploss = -0.01, minimal_roi = {"0": 0.02}

Guardrail-Hierarchie (im ExitAgent implementiert):
  G1: Trade < 2 candles → HOLD
  G2: PnL > +1.5% → HOLD (ROI-Exit priorisiert)
  G3: PnL <= -1.5% → CUT (Hard Stop, nie verhandelbar)
  G4: Offene Trades > 3 → HOLD (FleetGuard)
  G5: BTC Flash Crash → CUT
  LLM: Momentum-Evaluation → HOLD/CUT/MOVE_SL
"""

import logging
import sys
from datetime import datetime, timedelta
from typing import Optional

import talib.abstract as ta
from freqtrade.strategy import IStrategy, IntParameter, DecimalParameter
import freqtrade.vendor.qtpylib.indicators as qtpylib
from pandas import DataFrame

sys.path.insert(0, "/freqtrade/shared")
from primo_signal import primo_gate_allows
from fleetguard_v1 import FleetGuard, FleetGuardConfig
from exit_agent_v9 import ExitAgent

logger = logging.getLogger(__name__)


class RegimeSwitchingHybrid_v9_1_Sentient(IStrategy):

    INTERFACE_VERSION = 3
    timeframe = "15m"
    can_short = False

    # ---- Exit: ROI + Hard Stop (Sicherheitsnetz) ----
    stoploss = -0.015         # Hard Stop -1.5% (G3-Sicherheitsnetz)
    use_custom_stoploss = False
    trailing_stop = False

    minimal_roi = {
        "0": 0.02,             # ROI-Exit bei +2%
    }

    # ---- FleetGuard entry safety ----
    _fleetguard = FleetGuard(FleetGuardConfig(
        max_open_trades=3,
        max_open_shorts=2,
        max_open_longs=2,
    ))

    # ---- ExitAgent (Sentient Layer) ----
    exit_agent = ExitAgent()

    startup_candle_count = 50

    # ---- Hyperoptable Buy Parameters ----
    adx_threshold = DecimalParameter(15.0, 35.0, default=25.0, space="buy")
    ema_pullback_pct = DecimalParameter(0.5, 4.0, default=2.0, space="buy")
    rsi_entry_max = IntParameter(45, 65, default=48, space="buy")
    volume_ma_period = IntParameter(10, 40, default=20, space="buy")

    # ---- Indicators ----
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        if not self.dp:
            return dataframe

        dataframe['adx'] = ta.ADX(dataframe)
        dataframe['ema50'] = ta.EMA(dataframe, timeperiod=50)
        dataframe['rsi'] = ta.RSI(dataframe)
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=14)
        dataframe['atr_pct'] = dataframe['atr'] / dataframe['close']
        dataframe['volume_sma'] = dataframe['volume'].rolling(
            window=self.volume_ma_period.value, min_periods=1
        ).mean()

        bollinger = qtpylib.bollinger_bands(
            qtpylib.typical_price(dataframe), window=20, stds=2
        )
        dataframe['bb_lowerband'] = bollinger['lower']
        dataframe['bb_middleband'] = bollinger['mid']
        dataframe['bb_upperband'] = bollinger['upper']

        return dataframe

    # ---- Entry Logic (v8.3 optimiert) ----
    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        pair = metadata.get("pair")
        long_gate = primo_gate_allows(pair, "long")

        pullback_pct = self.ema_pullback_pct.value / 100.0
        pullback_ceiling = dataframe['ema50'] * (1.0 - pullback_pct)

        trend_continuation = (
            (dataframe['adx'] > self.adx_threshold.value) &
            (dataframe['close'] >= pullback_ceiling) &
            (dataframe['close'] < dataframe['ema50']) &
            (dataframe['rsi'] < self.rsi_entry_max.value) &
            (dataframe['volume'] > dataframe['volume_sma']) &
            long_gate
        )

        dataframe.loc[trend_continuation, 'enter_long'] = 1
        dataframe.loc[trend_continuation, 'enter_tag'] = 'v9_1_sentient_entry'

        return dataframe

    # ---- NO populate_exit_trend — LLM Layer übernimmt ----
    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        return dataframe

    # ---- Sentient Exit: LLM-Agent Callback ----
    def custom_exit(self, pair: str, trade: 'Trade',
                    current_time: datetime, current_rate: float,
                    current_profit: float, **kwargs) -> Optional[str]:
        """Called on every open candle. Delegates exit decision to ExitAgent."""

        # Guardrail G4: Portfolio-Status erfassen
        open_trades_count = 0
        try:
            from freqtrade.persistence import Trade as TradeModel
            open_trades_count = len(TradeModel.get_trades_proxy(is_open=True, pair=pair))
        except Exception:
            pass

        # Candle-Dauer berechnen: 15m = open_duration
        trade_age_minutes = (current_time - trade.open_date_utc).total_seconds() / 60.0
        open_duration_candles = int(trade_age_minutes / 15)

        # Kontext für den ExitAgent bauen
        context = {
            "trade": {
                "pair": pair,
                "unrealized_pnl_pct": current_profit * 100,  # in Prozent
                "open_duration_candles": open_duration_candles,
                "entry_price": trade.open_rate,
                "current_price": current_rate,
            },
            "portfolio": {
                "open_trades_count": open_trades_count,
            },
            "market_context": {
                "btc_change_15m": 0.0,           # v9.2: echten BTC-Change laden
            },
        }

        decision = self.exit_agent.evaluate_safe(context)

        logger.info(
            f"ExitAgent[{pair}] | PnL={current_profit*100:+.2f}% | "
            f"Candles={open_duration_candles} | "
            f"Decision={decision['decision']} | Conf={decision['confidence']:.2f} | "
            f"Reason={decision['reasoning']}"
        )

        if decision['decision'] == "CUT":
            return "llm_exit_cut"

        return None

    # ---- FleetGuard Entry Safety (v8.3 same) ----
    def confirm_trade_entry(self, pair: str, order_type: str, amount: float,
                            rate: float, time_in_force: str, current_time: datetime,
                            entry_tag: Optional[str], side: str, **kwargs) -> bool:
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
            starting_balance = (
                self.wallets.get_starting_balance()
                if hasattr(self, 'wallets') and self.wallets else 1000.0
            )
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
