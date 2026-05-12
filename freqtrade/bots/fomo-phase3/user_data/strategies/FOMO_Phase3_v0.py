"""
FOMO Phase 3 — v0 PLACEHOLDER STRATEGY

This is a SKELETON file. The actual FOMO / OI / Funding strategy logic
has NOT been implemented yet.

=== NEXT STEPS ===
1. Replace this file with your actual strategy class.
2. The class name must match what is set in config: "FOMO_Phase3_v0"
3. Ensure the following methods are implemented:
   - populate_indicators()
   - populate_entry_trend()
   - populate_exit_trend()
4. Place any helper modules in user_data/strategies/ or add them
   to the Freqtrade container's PYTHONPATH.

=== SHARED INFRASTRUCTURE AVAILABLE ===
- /freqtrade/shared/fleetguard_v1.py  (fleet-level entry safety)
- /freqtrade/shared/exit_agent_v9.py  (sentient exit agent)
- /freqtrade/shared/primo_gate.py    (legacy gate — optional)
- /freqtrade/shared/signals/          (signal relay directory)

=== EXISTING BOT COMPARISON ===
- FreqForge_Override (gold standard): trailing_stop=False, use_custom_stoploss=False,
  stoploss=-0.09, ROI={0:0.085, 45:0.045, 90:0.02, 180:0}
- RegimeSwitchingHybrid: futures, isolated margin, trailing_stop=FIXED Phase 43

=== INTEGRATION POINTS ===
- ai-hedge-fund-crypto signal: read from shared/signals/latest_signal.json
- FleetGuard: import and call from populate_entry_trend()
- ExitAgent V9: import and call from populate_exit_trend()

=== DISABLED BOT ===
This config has "initial_state": "stopped". The bot will NOT trade
until you either start it manually or change initial_state to "running".
"""

from freqtrade.strategy import IStrategy, IntParameter, DecimalParameter
import pandas as pd


class FOMO_Phase3_v0(IStrategy):
    """
    TODO: Replace this docstring with your strategy description.
    """

    # ============== PARAMETERS (TUNE THESE) ==============

    # Stoploss and ROI are defined in the config JSON.
    # Set them here only if you need strategy-level overrides.
    stoploss = -0.15
    trailing_stop = False
    use_custom_stoploss = False

    minimal_roi = {
        "0": 0.10,
        "60": 0.05,
        "120": 0.02,
        "240": 0,
    }

    # Optimal timeframe
    timeframe = "15m"

    # Run "populate_*()" only on new candles
    process_only_new_candles = True

    # Number of candles the strategy requires before producing signals
    startup_candle_count: int = 100

    # Enable futures trading
    can_short = True

    # ============== INDICATORS ==============

    def populate_indicators(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        """
        TODO: Add your FOMO / OI / Funding indicators here.

        Suggested indicators to implement:
        - Open Interest change rate
        - Funding Rate (positive/negative regimes)
        - Fear & Greed Index (if available as external data)
        - Volume profile / CVD
        - Long/Short ratio
        - RSI, MACD, Bollinger (traditional baseline)

        Example:
            dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)

        Return the dataframe with all new columns added.
        """
        return dataframe

    # ============== ENTRY SIGNALS ==============

    def populate_entry_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        """
        TODO: Implement entry logic.

        Key constraints:
        - All entries must verify dataframe['enter_long'] or ['enter_short'] == 1
        - Respect FleetGuard limits if integrated
        - Consider ai-hedge-fund-crypto signal as a filter (not trigger)

        Return the dataframe with enter_long / enter_short signals.
        """
        # Placeholder: no entries
        dataframe.loc[:, "enter_long"] = 0
        dataframe.loc[:, "enter_short"] = 0

        return dataframe

    # ============== EXIT SIGNALS ==============

    def populate_exit_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        """
        TODO: Implement exit logic.

        Consider:
        - ExitAgent V9 integration (shared/exit_agent_v9.py)
        - Fixed ROI table + trailing stop
        - Funding-rate-based exits (positive funding → take profit)

        Return the dataframe with exit_long / exit_short signals.
        """
        # Placeholder: no exits
        dataframe.loc[:, "exit_long"] = 0
        dataframe.loc[:, "exit_short"] = 0

        return dataframe
