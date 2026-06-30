"""Tests for freqtrade_monitor.py bot mapping and None-safe guards.

These tests verify:
- freqai-rebel bot_dir is not None (source-of-truth audit fix).
- get_trade_db_path returns correct host path for all bots.
- get_open_trade_details does not crash when db_path is None.
- get_open_trade_details proceeds to container read even if host DB missing.
- get_container_ip falls back robustly when static network is wrong.
"""

from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest

# Import the module under test
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orchestrator", "scripts"))
import freqtrade_monitor as fm  # noqa: E402


# ---------------------------------------------------------------------------
# Fix 1: freqai-rebel bot_dir must not be None
# ---------------------------------------------------------------------------

class TestRebelBotDir:
    """freqai-rebel must have a real host bind-mount path, not None."""

    def test_rebel_bot_dir_is_not_none(self):
        bot = fm.BOTS["trading-freqai-rebel-1"]
        assert bot["bot_dir"] is not None, "freqai-rebel bot_dir must not be None"

    def test_rebel_bot_dir_is_real_path(self):
        bot = fm.BOTS["trading-freqai-rebel-1"]
        assert "freqai-rebel" in bot["bot_dir"]

    def test_rebel_db_path_resolves(self):
        bot = fm.BOTS["trading-freqai-rebel-1"]
        path = fm.get_trade_db_path("trading-freqai-rebel-1", bot)
        assert path is not None
        assert "tradesv3.freqai_rebel.dryrun.sqlite" in path

    def test_all_bots_have_bot_dir(self):
        """No bot should have bot_dir=None after the fix."""
        for name, bot in fm.BOTS.items():
            assert bot["bot_dir"] is not None, f"{name} has bot_dir=None"


# ---------------------------------------------------------------------------
# Fix 2: get_open_trade_details None-guard
# ---------------------------------------------------------------------------

class TestOpenTradeDetailsNoneGuard:
    """get_open_trade_details must not crash when db_path is None."""

    def test_does_not_crash_with_none_db_path(self, monkeypatch):
        """Simulate a bot with bot_dir=None (legacy config)."""
        bot_info = {"bot_dir": None, "db": "tradesv3.test.dryrun.sqlite"}
        # get_trade_db_path returns None for bot_dir=None
        assert fm.get_trade_db_path("test-bot", bot_info) is None

        # Mock docker_exec to return empty (container not reachable)
        monkeypatch.setattr(fm, "docker_exec", lambda *a, **kw: ("", ""))
        result = fm.get_open_trade_details("test-bot", bot_info)
        assert result == [], "Should return empty list, not crash"

    def test_proceeds_to_container_when_host_db_missing(self, monkeypatch):
        """Even if host DB doesn't exist, container read should proceed."""
        bot_info = {
            "bot_dir": "/nonexistent/path",
            "db": "tradesv3.test.dryrun.sqlite",
        }

        # Mock docker_exec to return a trade
        def fake_docker_exec(container, cmd, timeout=15):
            return ('[{"pair": "BTC/USDT:USDT", "profit_pct": 1.5}]', "")

        monkeypatch.setattr(fm, "docker_exec", fake_docker_exec)
        result = fm.get_open_trade_details("test-bot", bot_info)
        assert len(result) == 1
        assert result[0]["pair"] == "BTC/USDT:USDT"

    def test_returns_empty_when_container_also_fails(self, monkeypatch):
        bot_info = {
            "bot_dir": "/nonexistent/path",
            "db": "tradesv3.test.dryrun.sqlite",
        }
        monkeypatch.setattr(fm, "docker_exec", lambda *a, **kw: ("", ""))
        result = fm.get_open_trade_details("test-bot", bot_info)
        assert result == []


# ---------------------------------------------------------------------------
# Fix 3: get_container_ip robust fallback
# ---------------------------------------------------------------------------

class TestContainerIPFallback:
    """get_container_ip should fall back when static network is wrong."""

    def test_returns_ip_from_configured_network(self, monkeypatch):
        def fake_run_cmd(cmd, timeout=15):
            if "trading_hermes-net" in cmd:
                return ("172.26.0.5", "")
            return ("", "")

        monkeypatch.setattr(fm, "run_cmd", fake_run_cmd)
        monkeypatch.setattr(fm, "CONTAINER_IPS", {})
        ip = fm.get_container_ip("trading-freqai-rebel-1")
        assert ip == "172.26.0.5"

    def test_falls_back_to_first_network(self, monkeypatch):
        """When configured network yields no IP, discover first available."""
        call_count = [0]

        def fake_run_cmd(cmd, timeout=15):
            call_count[0] += 1
            if call_count[0] == 1:
                # First call: configured network → no IP
                return ("", "no value")
            else:
                # Second call: range query → first network
                return ("trading_hermes-net:172.26.0.4", "")

        monkeypatch.setattr(fm, "run_cmd", fake_run_cmd)
        monkeypatch.setattr(fm, "CONTAINER_IPS", {})
        # Mock docker_exec to return empty (won't reach it)
        monkeypatch.setattr(fm, "docker_exec", lambda *a, **kw: ("", ""))
        ip = fm.get_container_ip("trading-freqai-rebel-1")
        assert ip == "172.26.0.4"

    def test_returns_none_when_all_methods_fail(self, monkeypatch):
        monkeypatch.setattr(fm, "run_cmd", lambda *a, **kw: ("", ""))
        monkeypatch.setattr(fm, "CONTAINER_IPS", {})
        monkeypatch.setattr(fm, "docker_exec", lambda *a, **kw: ("", ""))
        ip = fm.get_container_ip("trading-freqai-rebel-1")
        assert ip is None


# ---------------------------------------------------------------------------
# Network mapping sanity
# ---------------------------------------------------------------------------

class TestNetworkMapping:
    """Verify network assignments match docker inspect output from audit."""

    def test_canary_is_on_hermes_net(self):
        assert fm.BOTS["trading-freqtrade-freqforge-canary-1"]["network"] == "hermes-net"

    def test_rebel_is_on_trading_hermes_net(self):
        assert fm.BOTS["trading-freqai-rebel-1"]["network"] == "trading_hermes-net"

    def test_freqforge_is_on_trading_hermes_net(self):
        assert fm.BOTS["trading-freqtrade-freqforge-1"]["network"] == "trading_hermes-net"

    def test_regime_is_on_trading_hermes_net(self):
        assert fm.BOTS["trading-freqtrade-regime-hybrid-1"]["network"] == "trading_hermes-net"

    def test_no_ki_fabrik_references(self):
        """The stale 'ki-fabrik' network must not appear anywhere."""
        assert fm.DOCKER_NETWORK != "ki-fabrik"
        for name, bot in fm.BOTS.items():
            assert bot["network"] != "ki-fabrik", f"{name} still uses ki-fabrik"