"""Dry-run stub implementations of Docker and Freqtrade adapters.

Returns deterministic mock data. This is the ONLY implementation —
no real adapters exist yet. All methods are safe and have no side effects.
"""

from __future__ import annotations

from si_v2.state.schemas import MutationOverlay


class DryRunStubDocker:
    """Concrete mock implementation of DockerAdapter using deterministic data."""

    def exec_readonly(self, container: str, command: list[str]) -> str:
        """Return a deterministic mock command output.

        Args:
            container: Container name (ignored in dry-run).
            command: Command and arguments (ignored in dry-run).

        Returns:
            Deterministic mock stdout string.
        """
        return "mock-stdout: ok"

    def container_is_running(self, container: str) -> bool:
        """Always return True for dry-run mode.

        Args:
            container: Container name (ignored in dry-run).

        Returns:
            Always True.
        """
        return True

    def get_container_ip(self, container: str) -> str:
        """Return a deterministic mock IP address.

        Args:
            container: Container name (ignored in dry-run).

        Returns:
            Always '127.0.0.1'.
        """
        return "127.0.0.1"


class DryRunStubFreqtrade:
    """Concrete mock implementation of FreqtradeAdapter using deterministic data."""

    def read_config(self, bot_id: str) -> dict[str, str | int | float | bool]:
        """Return a deterministic mock configuration.

        Args:
            bot_id: Bot identifier (incorporated into output).

        Returns:
            Deterministic mock config dictionary.
        """
        return {
            "bot_id": bot_id,
            "dry_run": True,
            "stake_amount": 20.0,
            "max_open_trades": 3,
            "stoploss": -0.02,
        }

    def get_trade_history(self, bot_id: str, limit: int = 100) -> list[dict[str, str | int | float]]:
        """Return a deterministic mock trade history.

        Args:
            bot_id: Bot identifier (incorporated into output).
            limit: Trade limit (used to size the returned list).

        Returns:
            Deterministic list of mock trade records.
        """
        trades: list[dict[str, str | int | float]] = []
        for i in range(min(limit, 5)):
            trades.append(
                {
                    "trade_id": i,
                    "bot_id": bot_id,
                    "pair": "BTC/USDT",
                    "profit_pct": 0.5,
                    "profit_abs": 10.0,
                    "duration_minutes": 120.0,
                }
            )
        return trades

    def run_backtest(self, bot_id: str, overlay: MutationOverlay) -> dict[str, str | int | float]:
        """Return a deterministic mock backtest result.

        Args:
            bot_id: Bot identifier (incorporated into output).
            overlay: Mutation overlay parameters (used in output).

        Returns:
            Deterministic mock backtest result dictionary.
        """
        return {
            "bot_id": bot_id,
            "total_trades": 42,
            "profit_total_pct": 3.5,
            "profit_total_abs": 70.0,
            "max_drawdown_pct": 5.0,
            "win_rate_pct": 60.0,
        }
