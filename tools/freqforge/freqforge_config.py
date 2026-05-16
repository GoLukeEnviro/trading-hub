"""
FreqForge v0.1 Shadow Signal Evaluator — Configuration
Static bot map, DB paths, thresholds, and signal file locations.
"""

from pathlib import Path
from typing import Dict, List, Optional

# ── Project Root ──────────────────────────────────────────────
PROJECT_ROOT = Path("/home/hermes/projects/trading")

# ── Output Paths ─────────────────────────────────────────────
VAR_DIR = PROJECT_ROOT / "var" / "freqforge"
DECISIONS_JSONL = VAR_DIR / "shadow_decisions.jsonl"
STATE_FILE = VAR_DIR / "state.json"
SNAPSHOTS_DIR = VAR_DIR / "snapshots"

# ── Signal Source ────────────────────────────────────────────
SIGNAL_FILE = PROJECT_ROOT / "ai-hedge-fund-crypto" / "output" / "latest" / "hermes_signal.json"
SIGNAL_HISTORY_DIR = PROJECT_ROOT / "ai-hedge-fund-crypto" / "output" / "history"

# ── Report Output ────────────────────────────────────────────
REPORT_DIR = PROJECT_ROOT / "docs" / "context"
REPORT_MD = REPORT_DIR / "freqforge-shadow-evaluator-v0-1-report.md"
REPORT_DECISIONS = REPORT_DIR / "freqforge-shadow-evaluator-v0-1-decisions.jsonl"


# ── Bot Definitions ──────────────────────────────────────────
class BotDef:
    """Single Freqtrade bot definition."""
    def __init__(
        self,
        name: str,
        container: str,
        db_path: str,
        config_path: str,
        strategy: str,
        port: int,
        timeframe: str = "15m",
        active: bool = True,
    ):
        self.name = name
        self.container = container
        self.db_path = db_path          # path INSIDE container
        self.config_path = config_path  # path INSIDE container
        self.strategy = strategy
        self.port = port
        self.timeframe = timeframe
        self.active = active


BOTS: Dict[str, BotDef] = {
    "freqforge": BotDef(
        name="FreqForge",
        container="freqtrade-freqforge",
        db_path="/freqtrade/user_data/tradesv3.freqforge.dryrun.sqlite",
        config_path="/freqtrade/config/config_freqforge_dryrun.json",
        strategy="FreqForge_Override",
        port=8086,
        timeframe="15m",
    ),
    "freqforge-canary": BotDef(
        name="FreqForge-Canary",
        container="freqtrade-freqforge-canary",
        db_path="/freqtrade/user_data/tradesv3.freqforge_canary.dryrun.sqlite",
        config_path="/freqtrade/config/config_canary_dryrun.json",
        strategy="FreqForge_Override",
        port=8081,
        timeframe="15m",
    ),
    "regime-hybrid": BotDef(
        name="Regime-Hybrid",
        container="freqtrade-regime-hybrid",
        db_path="/freqtrade/user_data/tradesv3.regime_hybrid.dryrun.sqlite",
        config_path="/freqtrade/config/config_regime_hybrid_dryrun.json",
        strategy="RegimeSwitchingHybrid_v7_v04_Integration",
        port=8085,
        timeframe="15m",
    ),
    "momentum": BotDef(
        name="Momentum",
        container="freqtrade-momentum",
        db_path="/freqtrade/user_data/tradesv3.momentum.dryrun.sqlite",
        config_path="/freqtrade/config/config.json",
        strategy="MomentumBG15_v1",
        port=8084,
        timeframe="15m",
    ),
    "rsi": BotDef(
        name="RSI",
        container="freqtrade-rsi",
        db_path="/freqtrade/tradesv3.dryrun.sqlite",
        config_path="/freqtrade/config/freqtrade.json",
        strategy="RSIMeanReversionV11",
        port=8081,
        timeframe="15m",
        active=False,
    ),
}


# ── Thresholds ───────────────────────────────────────────────
CONFIDENCE_THRESHOLD = 0.60       # Below = uncertain (NOT automatic veto)
PNL_HARD_STOP = -1.5             # % — absolute hard stop
MAX_FLEET_OPEN = 6               # Fleet-wide open trade limit
MIN_CANDLES_BREATHING = 2        # Min candles before evaluating


# ── Signal Pair Normalization ────────────────────────────────
def normalize_pair(trade_pair: str) -> str:
    """Normalize pair formats for comparison with signal deck.
    
    Handles:
      BTC/USDT:USDT -> BTC/USDT:USDT
      BTC/USDT      -> BTC/USDT:USDT
      NEAR/USDT     -> NEAR/USDT:USDT
    """
    p = trade_pair.strip()
    if ":" not in p:
        p = p + ":USDT"
    return p


# ── Decision Types ───────────────────────────────────────────
DECISION_APPROVE = "approve"
DECISION_VETO = "veto"
DECISION_REDUCE_SIZE = "reduce_size"
DECISION_UNCERTAIN = "uncertain"

# Exit-specific tags
DECISION_FALSE_NEGATIVE = "false_negative_review"
DECISION_VETO_HELPED = "veto_would_have_helped"
DECISION_MISSED_RISK = "missed_risk"

ALL_DECISIONS = [
    DECISION_APPROVE, DECISION_VETO, DECISION_REDUCE_SIZE,
    DECISION_UNCERTAIN, DECISION_FALSE_NEGATIVE,
    DECISION_VETO_HELPED, DECISION_MISSED_RISK,
]


# ── Directories Auto-Create ──────────────────────────────────
def ensure_dirs():
    """Create output directories if missing."""
    for d in [VAR_DIR, SNAPSHOTS_DIR, REPORT_DIR]:
        d.mkdir(parents=True, exist_ok=True)
