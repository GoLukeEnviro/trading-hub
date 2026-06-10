"""Test dry-run behavior: verify no real Docker or Freqtrade calls."""

from __future__ import annotations

import inspect

from si_v2.adapters.dry_run_stub import DryRunStubDocker, DryRunStubFreqtrade
from si_v2.state.schemas import MutationOverlay


class TestDryRunBehavior:
    """Verify all adapter methods return deterministic mock data."""

    def test_docker_exec_no_subprocess(self) -> None:
        """exec_readonly returns mock data without subprocess calls."""
        stub = DryRunStubDocker()
        result = stub.exec_readonly("any-container", ["any", "command"])
        assert result == "mock-stdout: ok"

    def test_docker_exec_deterministic(self) -> None:
        """exec_readonly returns the same value every time."""
        stub = DryRunStubDocker()
        r1 = stub.exec_readonly("c1", ["a"])
        r2 = stub.exec_readonly("c2", ["b"])
        assert r1 == r2

    def test_docker_is_running_deterministic(self) -> None:
        """container_is_running always returns True."""
        stub = DryRunStubDocker()
        assert stub.container_is_running("any") is True
        assert stub.container_is_running("other") is True

    def test_docker_ip_deterministic(self) -> None:
        """get_container_ip always returns 127.0.0.1."""
        stub = DryRunStubDocker()
        assert stub.get_container_ip("any") == "127.0.0.1"

    def test_freqtrade_config_deterministic(self) -> None:
        """read_config returns deterministic data with correct bot_id."""
        stub = DryRunStubFreqtrade()
        c1 = stub.read_config("bot_a")
        c2 = stub.read_config("bot_a")
        assert c1 == c2
        assert c1["bot_id"] == "bot_a"

    def test_freqtrade_trades_deterministic(self) -> None:
        """get_trade_history returns deterministic data."""
        stub = DryRunStubFreqtrade()
        t1 = stub.get_trade_history("bot_a", limit=3)
        t2 = stub.get_trade_history("bot_a", limit=3)
        assert t1 == t2

    def test_freqtrade_backtest_deterministic(self) -> None:
        """run_backtest returns deterministic data."""
        stub = DryRunStubFreqtrade()
        overlay = MutationOverlay(
            max_open_trades=2,
            stake_amount=20.0,
            stoploss=-0.02,
            minimal_roi={"0": 0.035},
        )
        b1 = stub.run_backtest("bot_a", overlay)
        b2 = stub.run_backtest("bot_a", overlay)
        assert b1 == b2

    def test_no_docker_imports(self) -> None:
        """DryRunStubDocker source has no docker/dockerpy imports."""
        source = inspect.getsource(DryRunStubDocker)
        assert "import docker" not in source
        assert "subprocess" not in source

    def test_no_requests_imports(self) -> None:
        """DryRunStubFreqtrade source has no requests/http imports."""
        source = inspect.getsource(DryRunStubFreqtrade)
        assert "import requests" not in source
        assert "urllib" not in source
        assert "httpx" not in source
