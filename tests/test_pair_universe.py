"""test_pair_universe.py — Tests for configurable RiskGuard pair universe.

Tests:
  1. RiskGuard loads active universe from config.
  2. Invalid config fails closed to safe baseline with warning.
  3. Unavailable or blacklisted pairs are rejected.
  4. Stablecoin/stablecoin pairs are rejected.
  5. At least one ACCEPTED pair yields PASS through existing adapter.
  6. All WATCH_ONLY yields FAIL.
  7. Any BLOCK_ENTRY yields FAIL.
  8. Config schema validates pair format BASE/USDT:USDT.
  9. Universe count and verdict counts are reported.
"""

import json
import sys
import tempfile
from pathlib import Path

import pytest

# Add scripts directory to path BEFORE imports
SCRIPTS_DIR = Path(__file__).parent.parent / "orchestrator" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from pair_universe import (
    PairUniverse,
    load_pair_universe,
    validate_pair_format,
    get_verdict_counts,
    SAFE_BASELINE_ACTIVE,
    SAFE_BASELINE_BLACKLIST,
    DEFAULT_PAIR_REGEX,
    STABLECOIN_BASES,
)


# ── Fixtures ───────────────────────────────────────

@pytest.fixture
def valid_config():
    """A valid config with expanded universe."""
    return {
        "schema_version": "1.0",
        "active_universe": [
            "BTC/USDT:USDT",
            "ETH/USDT:USDT",
            "SOL/USDT:USDT",
            "XRP/USDT:USDT",
            "BNB/USDT:USDT",
            "DOGE/USDT:USDT",
            "ADA/USDT:USDT",
            "TRX/USDT:USDT",
            "LINK/USDT:USDT",
            "AVAX/USDT:USDT",
        ],
        "watchlist": [
            "SUI/USDT:USDT",
            "DOT/USDT:USDT",
        ],
        "blacklist": [
            "UST/USDT:USDT",
            "LUNA/USDT:USDT",
            "USDC/USDT:USDT",
        ],
        "max_active_pairs": 10,
        "exchange": "bitget",
        "settle": "USDT",
        "pair_format_regex": "^[A-Z]+/USDT:USDT$",
    }


@pytest.fixture
def config_file(valid_config, tmp_path):
    """Write config to a temp file."""
    p = tmp_path / "riskguard-pair-universe.json"
    p.write_text(json.dumps(valid_config, indent=2))
    return p


@pytest.fixture
def minimal_config():
    """Minimal valid config with only baseline pairs."""
    return {
        "active_universe": ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"],
        "watchlist": [],
        "blacklist": ["UST/USDT:USDT"],
        "max_active_pairs": 10,
    }


@pytest.fixture
def minimal_config_file(minimal_config, tmp_path):
    p = tmp_path / "riskguard-pair-universe.json"
    p.write_text(json.dumps(minimal_config, indent=2))
    return p


# ── Test 1: Load active universe from config ───────

def test_load_active_universe_from_config(config_file):
    """Test 1: RiskGuard loads active universe from config."""
    universe = load_pair_universe(config_file)
    assert universe.source == "config"
    assert len(universe.active_pairs) == 10
    assert "BTC/USDT:USDT" in universe.active_pairs
    assert "XRP/USDT:USDT" in universe.active_pairs
    assert "AVAX/USDT:USDT" in universe.active_pairs
    assert len(universe.watchlist) == 2
    assert "SUI/USDT:USDT" in universe.watchlist


def test_load_minimal_universe(minimal_config_file):
    """Test 1b: Minimal config loads correctly."""
    universe = load_pair_universe(minimal_config_file)
    assert universe.source == "config"
    assert len(universe.active_pairs) == 3
    assert universe.active_pairs == ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"]


# ── Test 2: Invalid config fails closed ─────────────

def test_missing_config_falls_back(tmp_path):
    """Test 2: Missing config file falls back to safe baseline."""
    missing = tmp_path / "nonexistent.json"
    universe = load_pair_universe(missing)
    assert universe.source == "fallback"
    assert universe.active_pairs == SAFE_BASELINE_ACTIVE
    assert any("not found" in w or "falling back" in w for w in universe.warnings)


def test_corrupt_config_falls_back(tmp_path):
    """Test 2b: Corrupt JSON falls back to safe baseline."""
    p = tmp_path / "riskguard-pair-universe.json"
    p.write_text("{invalid json!!!")
    universe = load_pair_universe(p)
    assert universe.source == "fallback"
    assert universe.active_pairs == SAFE_BASELINE_ACTIVE
    assert any("falling back" in w for w in universe.warnings)


def test_empty_active_falls_back(tmp_path):
    """Test 2c: Empty active_universe falls back to safe baseline."""
    p = tmp_path / "riskguard-pair-universe.json"
    p.write_text(json.dumps({"active_universe": [], "blacklist": []}))
    universe = load_pair_universe(p)
    assert universe.source == "fallback"
    assert universe.active_pairs == SAFE_BASELINE_ACTIVE


# ── Test 3: Blacklisted pairs rejected ──────────────

def test_blacklisted_pairs_rejected(tmp_path):
    """Test 3: Pairs in blacklist are rejected from active_universe."""
    p = tmp_path / "riskguard-pair-universe.json"
    p.write_text(json.dumps({
        "active_universe": ["BTC/USDT:USDT", "SOL/USDT:USDT", "ETH/USDT:USDT"],
        "blacklist": ["SOL/USDT:USDT"],
        "max_active_pairs": 10,
    }))
    universe = load_pair_universe(p)
    assert "BTC/USDT:USDT" in universe.active_pairs
    assert "ETH/USDT:USDT" in universe.active_pairs
    assert "SOL/USDT:USDT" not in universe.active_pairs
    assert any("blacklisted" in w for w in universe.warnings)


# ── Test 4: Stablecoin pairs rejected ───────────────

def test_stablecoin_pairs_rejected(tmp_path):
    """Test 4: Stablecoin/stablecoin pairs are rejected."""
    p = tmp_path / "riskguard-pair-universe.json"
    p.write_text(json.dumps({
        "active_universe": [
            "BTC/USDT:USDT",
            "USDC/USDT:USDT",
            "DAI/USDT:USDT",
            "ETH/USDT:USDT",
        ],
        "blacklist": [],
        "max_active_pairs": 10,
    }))
    universe = load_pair_universe(p)
    assert "BTC/USDT:USDT" in universe.active_pairs
    assert "ETH/USDT:USDT" in universe.active_pairs
    assert "USDC/USDT:USDT" not in universe.active_pairs
    assert "DAI/USDT:USDT" not in universe.active_pairs
    assert any("stablecoin" in w for w in universe.warnings)


def test_stablecoin_bases_constant():
    """Test 4b: Known stablecoin bases are in the constant."""
    assert "USDC" in STABLECOIN_BASES
    assert "DAI" in STABLECOIN_BASES
    assert "UST" in STABLECOIN_BASES
    assert "LUNA" in STABLECOIN_BASES


# ── Test 5: ACCEPTED → PASS via adapter ─────────────

def test_accepted_yields_pass():
    """Test 5: At least one ACCEPTED pair yields PASS through existing adapter."""
    # Import the adapter from controlled_apply_actuator
    SI_V2_SRC = Path(__file__).parent.parent / "self_improvement_v2" / "src"
    sys.path.insert(0, str(SI_V2_SRC))
    from si_v2.apply_actuator.controlled_apply_actuator import derive_riskguard_status

    state = {
        "summary": {"status": "ACTIVE"},
        "pairs": {
            "BTC/USDT": {"verdict": "ACCEPTED"},
            "ETH/USDT": {"verdict": "WATCH_ONLY"},
        },
    }
    assert derive_riskguard_status(state) == "PASS"


# ── Test 6: All WATCH_ONLY → FAIL ───────────────────

def test_all_watch_only_yields_fail():
    """Test 6: All WATCH_ONLY yields FAIL."""
    SI_V2_SRC = Path(__file__).parent.parent / "self_improvement_v2" / "src"
    sys.path.insert(0, str(SI_V2_SRC))
    from si_v2.apply_actuator.controlled_apply_actuator import derive_riskguard_status

    state = {
        "summary": {"status": "ACTIVE"},
        "pairs": {
            "BTC/USDT": {"verdict": "WATCH_ONLY"},
            "ETH/USDT": {"verdict": "WATCH_ONLY"},
            "SOL/USDT": {"verdict": "WATCH_ONLY"},
        },
    }
    assert derive_riskguard_status(state) == "FAIL"


# ── Test 7: BLOCK_ENTRY → FAIL ──────────────────────

def test_block_entry_yields_fail():
    """Test 7: Any BLOCK_ENTRY yields FAIL."""
    SI_V2_SRC = Path(__file__).parent.parent / "self_improvement_v2" / "src"
    sys.path.insert(0, str(SI_V2_SRC))
    from si_v2.apply_actuator.controlled_apply_actuator import derive_riskguard_status

    state = {
        "summary": {"status": "ACTIVE"},
        "pairs": {
            "BTC/USDT": {"verdict": "ACCEPTED"},
            "ETH/USDT": {"verdict": "BLOCK_ENTRY"},
        },
    }
    assert derive_riskguard_status(state) == "FAIL"


# ── Test 8: Pair format validation ──────────────────

def test_valid_pair_formats():
    """Test 8: Config schema validates pair format BASE/USDT:USDT."""
    assert validate_pair_format("BTC/USDT:USDT") is True
    assert validate_pair_format("ETH/USDT:USDT") is True
    assert validate_pair_format("DOGE/USDT:USDT") is True
    assert validate_pair_format("SOL/USDT:USDT") is True


def test_invalid_pair_formats():
    """Test 8b: Invalid pair formats are rejected."""
    assert validate_pair_format("BTCUSDT") is False
    assert validate_pair_format("btc/usdt:usdt") is False
    assert validate_pair_format("BTC/USDT") is False  # missing :USDT
    assert validate_pair_format("BTC/USD:USDT") is False  # wrong quote
    assert validate_pair_format("") is False
    assert validate_pair_format(None) is False
    assert validate_pair_format(123) is False


def test_invalid_format_rejected_in_config(tmp_path):
    """Test 8c: Invalid format pairs are rejected during load."""
    p = tmp_path / "riskguard-pair-universe.json"
    p.write_text(json.dumps({
        "active_universe": ["BTC/USDT:USDT", "INVALID", "ETH/USDT:USDT"],
        "blacklist": [],
        "max_active_pairs": 10,
    }))
    universe = load_pair_universe(p)
    assert "BTC/USDT:USDT" in universe.active_pairs
    assert "ETH/USDT:USDT" in universe.active_pairs
    assert "INVALID" not in universe.active_pairs
    assert any("invalid format" in w for w in universe.warnings)


# ── Test 9: Universe count and verdict counts ───────

def test_universe_count_reported(config_file):
    """Test 9: Universe count is reported correctly."""
    universe = load_pair_universe(config_file)
    assert universe.active_count == 10
    assert universe.watchlist_count == 2


def test_verdict_counts_with_accepted(config_file):
    """Test 9b: Verdict counts report ACCEPTED correctly."""
    universe = load_pair_universe(config_file)
    decisions = {
        "BTC/USDT": {"verdict": "ACCEPTED"},
        "ETH/USDT": {"verdict": "WATCH_ONLY"},
        "SOL/USDT": {"verdict": "WATCH_ONLY"},
    }
    counts = get_verdict_counts(decisions, universe)
    assert counts["accepted"] == 1
    assert counts["watch_only"] == 2
    assert counts["block_entry"] == 0
    assert counts["universe_active_count"] == 10


def test_verdict_counts_with_block_entry(config_file):
    """Test 9c: Verdict counts report BLOCK_ENTRY correctly."""
    universe = load_pair_universe(config_file)
    decisions = {
        "BTC/USDT": {"verdict": "BLOCK_ENTRY"},
        "ETH/USDT": {"verdict": "ACCEPTED"},
    }
    counts = get_verdict_counts(decisions, universe)
    assert counts["block_entry"] == 1
    assert counts["accepted"] == 1


def test_max_active_pairs_truncation(tmp_path):
    """Test 9d: max_active_pairs cap is enforced."""
    p = tmp_path / "riskguard-pair-universe.json"
    p.write_text(json.dumps({
        "active_universe": [
            "BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT",
            "XRP/USDT:USDT", "BNB/USDT:USDT", "DOGE/USDT:USDT",
            "ADA/USDT:USDT", "TRX/USDT:USDT", "LINK/USDT:USDT",
            "AVAX/USDT:USDT", "SUI/USDT:USDT", "BCH/USDT:USDT",
        ],
        "blacklist": [],
        "max_active_pairs": 5,
    }))
    universe = load_pair_universe(p)
    assert len(universe.active_pairs) == 5
    assert any("exceeds max" in w for w in universe.warnings)


def test_duplicate_pairs_removed(tmp_path):
    """Test 9e: Duplicate pairs in config are removed."""
    p = tmp_path / "riskguard-pair-universe.json"
    p.write_text(json.dumps({
        "active_universe": ["BTC/USDT:USDT", "BTC/USDT:USDT", "ETH/USDT:USDT"],
        "blacklist": [],
        "max_active_pairs": 10,
    }))
    universe = load_pair_universe(p)
    assert universe.active_pairs.count("BTC/USDT:USDT") == 1
    assert any("duplicate" in w for w in universe.warnings)


def test_watchlist_dedup_vs_active(tmp_path):
    """Test 9f: Pairs in watchlist that are also in active are removed from watchlist."""
    p = tmp_path / "riskguard-pair-universe.json"
    p.write_text(json.dumps({
        "active_universe": ["BTC/USDT:USDT", "ETH/USDT:USDT"],
        "watchlist": ["BTC/USDT:USDT", "SOL/USDT:USDT"],
        "blacklist": [],
        "max_active_pairs": 10,
    }))
    universe = load_pair_universe(p)
    assert "BTC/USDT:USDT" not in universe.watchlist
    assert "SOL/USDT:USDT" in universe.watchlist


def test_is_sanctioned(config_file):
    """Test 9g: is_sanctioned checks active + watchlist."""
    universe = load_pair_universe(config_file)
    assert universe.is_sanctioned("BTC/USDT:USDT") is True
    assert universe.is_sanctioned("SUI/USDT:USDT") is True  # in watchlist
    assert universe.is_sanctioned("TON/USDT:USDT") is False  # not in universe


def test_is_blacklisted(config_file):
    """Test 9h: is_blacklisted checks blacklist."""
    universe = load_pair_universe(config_file)
    assert universe.is_blacklisted("UST/USDT:USDT") is True
    assert universe.is_blacklisted("BTC/USDT:USDT") is False