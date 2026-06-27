"""test_signal_pair_universe.py — Tests for config-driven signal pair universe.

Tests that the signal generator (sentiment_collector, portfolio_management_node)
correctly uses config-driven pairs instead of hardcoded BTC/ETH/SOL.
"""

import json
import sys
import os
from pathlib import Path

import pytest

# Add scripts directory to path
SCRIPTS_DIR = Path(__file__).parent.parent / "orchestrator" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from pair_universe import (
    load_pair_universe,
    pair_to_base,
    pair_to_bitget_ticker,
    pair_to_coingecko_id,
    get_active_tickers,
    get_active_coingecko_ids,
    build_coingecko_url,
    COINGECKO_ID_MAP,
)


# ── Test: Load 10 active pairs ─────────────────────

def test_loads_10_active_pairs():
    """Test 1: Loads 10 active pairs from riskguard-pair-universe.json."""
    universe = load_pair_universe()
    assert universe.active_count == 10
    assert "BTC/USDT:USDT" in universe.active_pairs
    assert "XRP/USDT:USDT" in universe.active_pairs
    assert "AVAX/USDT:USDT" in universe.active_pairs


# ── Test: Convert BASE/USDT:USDT to BASE ticker ────

def test_pair_to_base_conversion():
    """Test 2: Converts BASE/USDT:USDT to BASE ticker symbols."""
    assert pair_to_base("BTC/USDT:USDT") == "BTC"
    assert pair_to_base("ETH/USDT:USDT") == "ETH"
    assert pair_to_base("DOGE/USDT:USDT") == "DOGE"
    assert pair_to_base("XRP/USDT:USDT") == "XRP"


def test_pair_to_base_edge_cases():
    """Test 2b: Edge cases for pair_to_base."""
    assert pair_to_base("") == ""
    assert pair_to_base(None) == ""
    # String without "/" returns itself uppercased
    assert pair_to_base("INVALID") == "INVALID"


def test_pair_to_bitget_ticker():
    """Test 2c: Converts pair to Bitget ticker."""
    assert pair_to_bitget_ticker("BTC/USDT:USDT") == "BTCUSDT"
    assert pair_to_bitget_ticker("ETH/USDT:USDT") == "ETHUSDT"
    assert pair_to_bitget_ticker("DOGE/USDT:USDT") == "DOGEUSDT"


def test_pair_to_coingecko_id():
    """Test 2d: Converts pair to CoinGecko coin ID."""
    assert pair_to_coingecko_id("BTC/USDT:USDT") == "bitcoin"
    assert pair_to_coingecko_id("ETH/USDT:USDT") == "ethereum"
    assert pair_to_coingecko_id("SOL/USDT:USDT") == "solana"
    assert pair_to_coingecko_id("DOGE/USDT:USDT") == "dogecoin"
    assert pair_to_coingecko_id("UNKNOWN/USDT:USDT") == ""


# ── Test: Sentiment collector covers all active tickers

def test_coingecko_id_map_covers_all_active():
    """Test 3: Sentiment collector covers all active tickers via CoinGecko ID map."""
    universe = load_pair_universe()
    for pair in universe.active_pairs:
        base = pair_to_base(pair)
        assert base in COINGECKO_ID_MAP, f"Active pair {pair} base {base} not in COINGECKO_ID_MAP"


def test_get_active_coingecko_ids():
    """Test 3b: get_active_coingecko_ids returns all active pairs."""
    universe = load_pair_universe()
    ids = get_active_coingecko_ids(universe)
    assert len(ids) == 10
    assert ids["BTC/USDT:USDT"] == "bitcoin"
    assert ids["DOGE/USDT:USDT"] == "dogecoin"
    assert ids["XRP/USDT:USDT"] == "ripple"


# ── Test: Portfolio management loop is config-driven

def test_portfolio_management_not_hardcoded():
    """Test 4: Portfolio management loop iterates config-driven tickers, not BTC/ETH/SOL hardcode."""
    # Read the source file and verify the hardcoded list is removed
    pm_path = Path(__file__).parent.parent / "ai-hedge-fund-crypto" / "src" / "graph" / "portfolio_management_node.py"
    content = pm_path.read_text()
    # The old hardcoded line should not be present
    assert 'for pair in ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"]:' not in content
    # The new config-driven code should be present
    assert "sentiment_pairs" in content
    assert "composites.keys()" in content


# ── Test: Fallback to BTC/ETH/SOL ──────────────────

def test_fallback_when_config_missing(tmp_path):
    """Test 5: Fallback to BTC/ETH/SOL works when config is missing/invalid."""
    missing = tmp_path / "nonexistent.json"
    universe = load_pair_universe(missing)
    assert universe.source == "fallback"
    assert universe.active_pairs == ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"]


def test_sentiment_collector_fallback_pairs():
    """Test 5b: sentiment_collector has fallback pairs defined."""
    sc_path = Path(__file__).parent.parent / "ai-hedge-fund-crypto" / "src" / "sentiment_collector.py"
    content = sc_path.read_text()
    assert "_FALLBACK_PAIRS" in content
    assert "BTC/USDT:USDT" in content
    assert "ETH/USDT:USDT" in content
    assert "SOL/USDT:USDT" in content


# ── Test: No stablecoin/blacklisted pair emitted ───

def test_no_stablecoin_in_active():
    """Test 6: No stablecoin/blacklisted pair is emitted in active universe."""
    universe = load_pair_universe()
    for pair in universe.active_pairs:
        assert not universe.is_stablecoin_pair(pair), f"Stablecoin {pair} in active_universe!"
        assert not universe.is_blacklisted(pair), f"Blacklisted {pair} in active_universe!"


def test_no_blacklisted_in_coingecko_ids():
    """Test 6b: No blacklisted pair in CoinGecko IDs."""
    universe = load_pair_universe()
    ids = get_active_coingecko_ids(universe)
    for pair in ids:
        assert not universe.is_blacklisted(pair)


# ── Test: AI signal output can contain all active pairs

def test_config_yaml_has_10_tickers():
    """Test 7: AI signal config.yaml tickers matches active universe."""
    import yaml
    cfg_path = Path(__file__).parent.parent / "ai-hedge-fund-crypto" / "config.yaml"
    with open(cfg_path) as f:
        cfg = yaml.safe_load(f)
    tickers = cfg["signals"]["tickers"]
    assert len(tickers) == 10
    assert "BTC/USDT:USDT" in tickers
    assert "XRP/USDT:USDT" in tickers
    assert "DOGE/USDT:USDT" in tickers
    assert "AVAX/USDT:USDT" in tickers
    # No old pairs
    assert "NEAR/USDT:USDT" not in tickers
    assert "ARB/USDT:USDT" not in tickers
    assert "OP/USDT:USDT" not in tickers


def test_sentiment_collector_uses_config():
    """Test 7b: sentiment_collector loads from config, not hardcoded."""
    sc_path = Path(__file__).parent.parent / "ai-hedge-fund-crypto" / "src" / "sentiment_collector.py"
    content = sc_path.read_text()
    assert "_load_active_pairs_from_config" in content
    assert "riskguard-pair-universe.json" in content
    # Old hardcoded SYMBOL_MAP should not have literal pair entries
    assert '"BTC/USDT:USDT": "BTCUSDT",' not in content
    assert '"NEAR/USDT:USDT": "NEARUSDT",' not in content


# ── Test: RiskGuard service still reports universe ─

def test_riskguard_reports_universe():
    """Test 8: RiskGuard service still reports universe counts."""
    rg_path = Path(__file__).parent.parent / "orchestrator" / "scripts" / "riskguard_service.py"
    content = rg_path.read_text()
    assert "pair_universe" in content
    assert "PAIR_UNIVERSE" in content
    assert "active_count" in content
    assert "watchlist_count" in content


# ── Test: CoinGecko URL builder ────────────────────

def test_build_coingecko_url():
    """Test 9: build_coingecko_url generates valid URL with all active pairs."""
    url = build_coingecko_url()
    assert "api.coingecko.com" in url
    assert "bitcoin" in url
    assert "ethereum" in url
    assert "solana" in url
    assert "ripple" in url
    assert "dogecoin" in url
    assert "include_24hr_change=true" in url


def test_get_active_tickers():
    """Test 9b: get_active_tickers returns base tickers for all active pairs."""
    tickers = get_active_tickers()
    assert len(tickers) == 10
    assert "BTC" in tickers
    assert "ETH" in tickers
    assert "DOGE" in tickers
    assert "XRP" in tickers