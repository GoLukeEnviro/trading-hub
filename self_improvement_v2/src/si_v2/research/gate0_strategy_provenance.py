"""Gate-0 strategy provenance for FreqForge_Gate0_Core_v1 (C5.3 corrective).

Documents the actual strategy characteristics of the stripped Gate-0 variant.
Default provenance is FreqForge_Gate0_Core_v1 (not FreqForge_Override).

Do NOT import this at module level from the strategy directly — it requires
Freqtrade runtime deps (talib, pandas, freqtrade) not available in CI.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass


@dataclass(frozen=True)
class StrategyProvenance:
    """Pinned provenance for the FreqForge_Gate0_Core_v1 strategy (C5.3).

    All hashes are computed from the committed files on main at the time
    of this corrective. Luke must re-ratify before any holdout evaluation.
    """

    # --- Identity ---
    strategy_class: str = "FreqForge_Gate0_Core_v1"
    strategy_file: str = "freqforge/user_data/strategies/FreqForge_Gate0_Core_v1.py"
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
    uses_fleet_risk_manager: bool = False  # removed entirely (C5.3)
    uses_primo_signal: bool = False  # removed entirely (C5.3)
    uses_exit_agent: bool = False
    uses_dynamic_risk_gates: bool = False  # removed entirely (C5.3)

    # --- Computed hashes (filled at runtime from git) ---
    strategy_file_sha256: str = ""
    config_file_sha256: str = ""
    shared_module_sha256: str = ""  # Combined hash of freqtrade/shared/*.py

    # --- Notes for Luke's re-ratification ---
    re_ratification_note: str = (
        "C5.3 corrective: FreqForge_Gate0_Core_v1 is a fully stripped research "
        "variant. Primo signals, FleetRiskManager, AI/Shadow/LLM paths, "
        "sys.path manipulation, file I/O, confirm_trade_entry override, and "
        "bot_loop_start have all been removed entirely. Only deterministic "
        "candle/indicator logic is retained. Luke must explicitly re-ratify "
        "before any holdout evaluation."
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


# Pre-computed instance (values frozen at C5.3 corrective time):
# These will be filled by a test that runs compute_hashes() against the
# actual main HEAD at merge time. CI can verify they match.
PRE_COMPUTED = StrategyProvenance()
