"""pair_universe.py — Configurable RiskGuard pair universe loader and validator.

Loads the sanctioned pair universe from a tracked JSON config file.
If config is missing or invalid, fails closed to the safe BTC/ETH/SOL baseline
with an explicit warning.

Usage:
    from pair_universe import load_pair_universe, validate_pair_format
    universe = load_pair_universe()
    print(universe.active_pairs)   # ["BTC/USDT:USDT", ...]
    print(universe.watchlist)      # ["SUI/USDT:USDT", ...]
    print(universe.blacklist)      # ["UST/USDT:USDT", ...]

Design:
  - Config is loaded read-only.
  - If config file missing or invalid → fallback to SAFE_BASELINE with warning.
  - Pair format validated against regex: ^[A-Z]+/USDT:USDT$
  - Blacklisted pairs are rejected from active_universe.
  - Stablecoin/stablecoin pairs are rejected.
  - max_active_pairs cap enforced.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger("riskguard.pair_universe")

# ── Paths ──────────────────────────────────────────

PROJECT_DIR = Path("/home/hermes/projects/trading")
CONFIG_DIR = PROJECT_DIR / "orchestrator/config"
CONFIG_FILE = CONFIG_DIR / "riskguard-pair-universe.json"
EXAMPLE_CONFIG_FILE = CONFIG_DIR / "riskguard-pair-universe.example.json"

# ── Safe fallback ──────────────────────────────────

SAFE_BASELINE_ACTIVE = [
    "BTC/USDT:USDT",
    "ETH/USDT:USDT",
    "SOL/USDT:USDT",
]
SAFE_BASELINE_WATCHLIST: List[str] = []
SAFE_BASELINE_BLACKLIST = [
    "UST/USDT:USDT",
    "LUNA/USDT:USDT",
    "LUNC/USDT:USDT",
    "TUSD/USDT:USDT",
    "USDC/USDT:USDT",
    "DAI/USDT:USDT",
]

# ── Validation ─────────────────────────────────────

DEFAULT_PAIR_REGEX = r"^[A-Z]+/USDT:USDT$"
STABLECOIN_BASES = {"UST", "LUNA", "LUNC", "TUSD", "USDC", "DAI", "FRAX", "BUSD"}


@dataclass
class PairUniverse:
    """Validated pair universe loaded from config."""
    active_pairs: List[str]
    watchlist: List[str]
    blacklist: List[str]
    max_active_pairs: int = 10
    exchange: str = "bitget"
    settle: str = "USDT"
    source: str = "config"  # "config" or "fallback"
    warnings: List[str] = field(default_factory=list)

    @property
    def all_pairs(self) -> List[str]:
        """All sanctioned pairs (active + watchlist)."""
        return list(self.active_pairs) + list(self.watchlist)

    @property
    def active_count(self) -> int:
        return len(self.active_pairs)

    @property
    def watchlist_count(self) -> int:
        return len(self.watchlist)

    def is_sanctioned(self, pair: str) -> bool:
        """Check if a pair is in the active universe or watchlist."""
        return pair in self.all_pairs

    def is_blacklisted(self, pair: str) -> bool:
        """Check if a pair is explicitly blacklisted."""
        return pair in self.blacklist

    def is_stablecoin_pair(self, pair: str) -> bool:
        """Check if a pair involves a stablecoin base (e.g., USDC/USDT)."""
        try:
            base = pair.split("/")[0]
            return base.upper() in STABLECOIN_BASES
        except (IndexError, AttributeError):
            return False


def validate_pair_format(pair: str, pattern: str = DEFAULT_PAIR_REGEX) -> bool:
    """Validate that a pair matches the expected format BASE/USDT:USDT."""
    if not isinstance(pair, str):
        return False
    return re.match(pattern, pair) is not None


def _is_stablecoin_pair(pair: str) -> bool:
    """Check if a pair involves a stablecoin base."""
    try:
        base = pair.split("/")[0]
        return base.upper() in STABLECOIN_BASES
    except (IndexError, AttributeError):
        return False


def _validate_and_filter(
    pairs: List[str],
    blacklist: List[str],
    label: str,
    pattern: str,
    warnings: List[str],
) -> List[str]:
    """Validate a list of pairs: format, stablecoin, blacklist checks.

    For blacklist entries: format is validated, but stablecoin check is skipped
    (blacklist is supposed to contain stablecoins and problematic assets).
    """
    result = []
    seen = set()
    for pair in pairs:
        # Skip duplicates
        if pair in seen:
            warnings.append(f"{label}: duplicate pair {pair!r} removed")
            continue
        seen.add(pair)

        # Format check
        if not validate_pair_format(pair, pattern):
            warnings.append(f"{label}: invalid format {pair!r} rejected")
            continue

        # Stablecoin check — skip for blacklist itself
        if label != "blacklist" and _is_stablecoin_pair(pair):
            warnings.append(f"{label}: stablecoin pair {pair!r} rejected")
            continue

        # Blacklist check (only for active/watchlist, not for blacklist itself)
        if label != "blacklist" and pair in blacklist:
            warnings.append(f"{label}: blacklisted pair {pair!r} rejected")
            continue

        result.append(pair)
    return result


def load_pair_universe(config_path: Optional[Path] = None) -> PairUniverse:
    """Load and validate the pair universe from config.

    If config is missing, invalid, or fails validation:
      → fall back to SAFE_BASELINE with explicit warning.
    """
    path = config_path or CONFIG_FILE
    warnings: List[str] = []

    # Try to load config file
    raw: Optional[dict] = None
    try:
        if path.exists():
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                warnings.append(f"Config root is not a dict, falling back")
                raw = None
        else:
            warnings.append(f"Config file not found at {path}, falling back to safe baseline")
    except (json.JSONDecodeError, OSError) as e:
        warnings.append(f"Config load error: {e}, falling back to safe baseline")
        raw = None

    # If config missing or invalid, fall back
    if raw is None:
        logger.warning("Pair universe config unavailable — using SAFE_BASELINE: %s", warnings)
        return PairUniverse(
            active_pairs=list(SAFE_BASELINE_ACTIVE),
            watchlist=list(SAFE_BASELINE_WATCHLIST),
            blacklist=list(SAFE_BASELINE_BLACKLIST),
            source="fallback",
            warnings=warnings,
        )

    # Parse config
    pattern = raw.get("pair_format_regex", DEFAULT_PAIR_REGEX)
    max_active = int(raw.get("max_active_pairs", 10))

    raw_blacklist = raw.get("blacklist", [])
    if not isinstance(raw_blacklist, list):
        warnings.append("blacklist is not a list, using safe default")
        raw_blacklist = list(SAFE_BASELINE_BLACKLIST)

    # Validate blacklist (format only — no self-blacklist check)
    blacklist = _validate_and_filter(
        raw_blacklist, [], "blacklist", pattern, warnings
    )

    raw_active = raw.get("active_universe", [])
    if not isinstance(raw_active, list):
        warnings.append("active_universe is not a list, falling back to safe baseline")
        raw_active = list(SAFE_BASELINE_ACTIVE)

    # Validate active
    active = _validate_and_filter(
        raw_active, blacklist, "active", pattern, warnings
    )

    # Enforce max_active_pairs
    if len(active) > max_active:
        warnings.append(
            f"active_universe has {len(active)} pairs, exceeds max_active_pairs={max_active}, truncating"
        )
        active = active[:max_active]

    # If active is empty after validation, fall back
    if not active:
        warnings.append("active_universe empty after validation, falling back to safe baseline")
        active = list(SAFE_BASELINE_ACTIVE)
        return PairUniverse(
            active_pairs=active,
            watchlist=[],
            blacklist=blacklist,
            max_active_pairs=max_active,
            exchange=raw.get("exchange", "bitget"),
            settle=raw.get("settle", "USDT"),
            source="fallback",
            warnings=warnings,
        )

    raw_watchlist = raw.get("watchlist", [])
    if not isinstance(raw_watchlist, list):
        warnings.append("watchlist is not a list, ignoring")
        raw_watchlist = []

    # Validate watchlist
    watchlist = _validate_and_filter(
        raw_watchlist, blacklist, "watchlist", pattern, warnings
    )

    # Remove pairs from watchlist that are already in active
    watchlist = [p for p in watchlist if p not in active]

    for w in warnings:
        logger.warning("Pair universe: %s", w)

    return PairUniverse(
        active_pairs=active,
        watchlist=watchlist,
        blacklist=blacklist,
        max_active_pairs=max_active,
        exchange=raw.get("exchange", "bitget"),
        settle=raw.get("settle", "USDT"),
        source="config",
        warnings=warnings,
    )


def get_verdict_counts(
    decisions: dict,
    universe: Optional[PairUniverse] = None,
) -> dict:
    """Count ACCEPTED / WATCH_ONLY / BLOCK_ENTRY verdicts.

    Also reports universe count and whether any pair is outside the sanctioned universe.
    """
    if universe is None:
        universe = load_pair_universe()

    accepted = 0
    watch_only = 0
    block_entry = 0
    outside_universe = 0

    for pair_key, pair_data in decisions.items():
        if not isinstance(pair_data, dict):
            continue
        verdict = pair_data.get("verdict", "")
        norm = pair_key.split(":")[0] + ":USDT" if ":" in pair_key else pair_key
        # Check if pair is in sanctioned universe
        if not universe.is_sanctioned(norm) and not universe.is_sanctioned(pair_key):
            outside_universe += 1

        if verdict == "ACCEPTED":
            accepted += 1
        elif verdict == "WATCH_ONLY":
            watch_only += 1
        elif verdict == "BLOCK_ENTRY":
            block_entry += 1

    return {
        "universe_active_count": universe.active_count,
        "universe_watchlist_count": universe.watchlist_count,
        "accepted": accepted,
        "watch_only": watch_only,
        "block_entry": block_entry,
        "outside_universe": outside_universe,
        "universe_source": universe.source,
    }


# ── Ticker / CoinGecko ID conversion ───────────────

# CoinGecko coin IDs for supported bases
# This map covers all reviewed active universe + watchlist pairs.
COINGECKO_ID_MAP = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
    "XRP": "ripple",
    "BNB": "binancecoin",
    "DOGE": "dogecoin",
    "ADA": "cardano",
    "TRX": "tron",
    "LINK": "chainlink",
    "AVAX": "avalanche-2",
    "SUI": "sui",
    "BCH": "bitcoin-cash",
    "XLM": "stellar",
    "DOT": "polkadot",
    "ATOM": "cosmos",
    "UNI": "uniswap",
    "AAVE": "aave",
    # Legacy pairs for backward compatibility
    "NEAR": "near",
    "ARB": "arbitrum",
    "OP": "optimism",
}


def pair_to_base(pair: str) -> str:
    """Convert a pair string like 'BTC/USDT:USDT' to its base ticker 'BTC'."""
    try:
        return pair.split("/")[0].upper()
    except (IndexError, AttributeError):
        return ""


def pair_to_bitget_ticker(pair: str) -> str:
    """Convert a pair string like 'BTC/USDT:USDT' to Bitget ticker 'BTCUSDT'."""
    base = pair_to_base(pair)
    return f"{base}USDT" if base else ""


def pair_to_coingecko_id(pair: str) -> str:
    """Convert a pair string like 'BTC/USDT:USDT' to CoinGecko coin ID 'bitcoin'.

    Returns empty string if the base is not in the COINGECKO_ID_MAP.
    """
    base = pair_to_base(pair)
    return COINGECKO_ID_MAP.get(base, "")


def get_active_tickers(universe: Optional[PairUniverse] = None) -> list[str]:
    """Return active universe pairs as base ticker strings (e.g., ['BTC', 'ETH', ...])."""
    if universe is None:
        universe = load_pair_universe()
    return [pair_to_base(p) for p in universe.active_pairs if pair_to_base(p)]


def get_active_coingecko_ids(universe: Optional[PairUniverse] = None) -> dict[str, str]:
    """Return active universe pairs as {pair: coingecko_id} mapping.

    Only includes pairs that have a known CoinGecko ID.
    """
    if universe is None:
        universe = load_pair_universe()
    result = {}
    for pair in universe.active_pairs:
        cg_id = pair_to_coingecko_id(pair)
        if cg_id:
            result[pair] = cg_id
    return result


def build_coingecko_url(universe: Optional[PairUniverse] = None) -> str:
    """Build a CoinGecko simple/price URL for all active universe pairs.

    Falls back to BTC/ETH/SOL if config is unavailable.
    """
    if universe is None:
        universe = load_pair_universe()
    ids = get_active_coingecko_ids(universe)
    if not ids:
        # Fallback to BTC/ETH/SOL
        ids = {"BTC/USDT:USDT": "bitcoin", "ETH/USDT:USDT": "ethereum", "SOL/USDT:USDT": "solana"}
    coin_ids = ",".join(sorted(set(ids.values())))
    return (
        f"https://api.coingecko.com/api/v3/simple/price"
        f"?ids={coin_ids}"
        f"&vs_currencies=usd"
        f"&include_24hr_change=true"
        f"&include_7d_change=true"
        f"&include_24hr_vol=true"
    )