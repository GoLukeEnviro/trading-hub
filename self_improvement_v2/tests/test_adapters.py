"""Test adapters: DryRunStubDocker and DryRunStubFreqtrade."""

from __future__ import annotations

from si_v2.adapters.docker_adapter import DockerAdapter
from si_v2.adapters.dry_run_stub import DryRunStubDocker, DryRunStubFreqtrade
from si_v2.adapters.freqtrade_adapter import FreqtradeAdapter
from si_v2.state.schemas import MutationOverlay


class TestDryRunStubDocker:
    """Tests for the DryRunStubDocker adapter."""

    def test_implements_protocol(self) -> None:
        """DryRunStubDocker satisfies the DockerAdapter protocol."""
        stub = DryRunStubDocker()
        assert isinstance(stub, DockerAdapter)

    def test_exec_readonly_returns_string(self) -> None:
        """exec_readonly returns a string."""
        stub = DryRunStubDocker()
        result = stub.exec_readonly("test-container", ["echo", "hello"])
        assert isinstance(result, str)
        assert result == "mock-stdout: ok"

    def test_container_is_running_returns_bool(self) -> None:
        """container_is_running returns True."""
        stub = DryRunStubDocker()
        result = stub.container_is_running("test-container")
        assert isinstance(result, bool)
        assert result is True

    def test_get_container_ip_returns_string(self) -> None:
        """get_container_ip returns a valid IP string."""
        stub = DryRunStubDocker()
        result = stub.get_container_ip("test-container")
        assert isinstance(result, str)
        assert result == "127.0.0.1"


class TestDryRunStubFreqtrade:
    """Tests for the DryRunStubFreqtrade adapter."""

    def test_implements_protocol(self) -> None:
        """DryRunStubFreqtrade satisfies the FreqtradeAdapter protocol."""
        stub = DryRunStubFreqtrade()
        assert isinstance(stub, FreqtradeAdapter)

    def test_read_config_returns_dict(self) -> None:
        """read_config returns a configuration dictionary."""
        stub = DryRunStubFreqtrade()
        result = stub.read_config("bot_a")
        assert isinstance(result, dict)
        assert result["bot_id"] == "bot_a"
        assert "dry_run" in result

    def test_get_trade_history_returns_list(self) -> None:
        """get_trade_history returns a list of trade dicts."""
        stub = DryRunStubFreqtrade()
        result = stub.get_trade_history("bot_a", limit=10)
        assert isinstance(result, list)
        assert len(result) > 0
        assert result[0]["bot_id"] == "bot_a"

    def test_get_trade_history_respects_limit(self) -> None:
        """get_trade_history respects the limit parameter."""
        stub = DryRunStubFreqtrade()
        result = stub.get_trade_history("bot_a", limit=2)
        assert len(result) == 2

    def test_run_backtest_returns_dict(self) -> None:
        """run_backtest returns a results dictionary."""
        stub = DryRunStubFreqtrade()
        overlay = MutationOverlay(
            max_open_trades=2,
            stake_amount=20.0,
            stoploss=-0.02,
            minimal_roi={"0": 0.035},
        )
        result = stub.run_backtest("bot_a", overlay)
        assert isinstance(result, dict)
        assert result["bot_id"] == "bot_a"
        assert result["total_trades"] == 42
