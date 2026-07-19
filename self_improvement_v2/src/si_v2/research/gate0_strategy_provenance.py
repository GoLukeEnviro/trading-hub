"""Gate-0 strategy provenance for FreqForge_Override (C5.1 corrective).

Documents the ACTUAL strategy characteristics, not the simplified description
that was previously ratified. Luke must re-ratify based on real code.

Do NOT import this at module level from the strategy directly — it requires
Freqtrade runtime deps (talib, pandas, freqtrade) not available in CI.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass


@dataclass(frozen=True)
class StrategyProvenance:
    """Pinned provenance for the FreqForge_Override strategy (C5.1).

    All hashes are computed from the committed files on main at the time
    of this corrective. Luke must re-ratify before any holdout evaluation.
    """

    # --- Identity ---
    strategy_class: str = "FreqForge_Override"
    strategy_file: str = "freqforge/user_data/strategies/FreqForge_Override.py"
    strategy_config: str = "freqforge/user_data/config.example.json"
    freqtrade_image: str = (
        "freqtradeorg/freqtrade@sha256:87aa5c6d65359b34e9d99a0bb260a38c0efe0315253811e6f48c2afe8f278a6a"
    )

    # --- Actual strategy characteristics (documented, not assumed) ---
    timeframe: str = "15m"
    informative_timeframe: str = "1h"
    can_short: bool = True
    use_custom_stoploss: bool = True
    trailing_stop: bool = False
    INTERFACE_VERSION: int = 3

    # --- Dependencies detected in the actual strategy code ---
    requires_informative_data: bool = True  # needs 1h candles for EMA/ADX/RSI
    uses_fleet_risk_manager: bool = True  # FleetRiskManager gates entries
    uses_primo_signal: bool = True  # primo_gate_allows() + load_signal_state()
    uses_exit_agent: bool = False  # import exists but not in hot path
    uses_dynamic_risk_gates: bool = True  # FleetRisk reduces long/short gates

    # --- Computed hashes (filled at runtime from git) ---
    strategy_file_sha256: str = ""
    config_file_sha256: str = ""
    shared_module_sha256: str = ""  # Combined hash of freqtrade/shared/*.py

    # --- Notes for Luke's re-ratification ---
    re_ratification_note: str = (
        "The previous ratification described FreqForge_Override as a simple "
        "'ROI + hard stoploss + primo_gate filter' baseline. The ACTUAL code "
        "has: can_short=True, use_custom_stoploss=True, informative_timeframe=1h, "
        "FleetRiskManager dynamic gates, and shared signal state dependencies. "
        "This manifest documents the real strategy. Luke must explicitly re-ratify."
    )

    def compute_hashes(self, repo_root: str | None = None) -> StrategyProvenance:
        """Compute actual file hashes from the repository."""
        from pathlib import Path

        root = Path(repo_root) if repo_root else Path(__file__).resolve().parents[3]

        def file_sha256(rel_path: str) -> str:
            return hashlib.sha256((root / rel_path).read_bytes()).hexdigest()

        shared = root / "freqtrade" / "shared"
        shared_hash = hashlib.sha256()
        for py_file in sorted(shared.glob("*.py")):
            shared_hash.update(py_file.read_bytes())

        return StrategyProvenance(
            strategy_file_sha256=file_sha256(self.strategy_file),
            config_file_sha256=file_sha256(self.strategy_config),
            shared_module_sha256=shared_hash.hexdigest(),
        )


# Pre-computed instance (values frozen at C5.1 corrective time):
# These will be filled by a test that runs compute_hashes() against the
# actual main HEAD at merge time. CI can verify they match.
PRE_COMPUTED = StrategyProvenance()
