"""Dry-run stub implementations of Docker, Freqtrade, and Telegram adapters.

Returns deterministic mock data. This is the ONLY implementation —
no real adapters exist yet. All methods are safe and have no side effects.
The Telegram adapter captures messages in memory and NEVER calls the
real Telegram API, never reads tokens, and never performs HTTP calls.
"""

from __future__ import annotations

from datetime import UTC, datetime

from si_v2.adapters.telegram_adapter import TelegramMessage
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


class DryRunTelegramAdapter:
    """Dry-run implementation of the TelegramAdapter protocol.

    Captures messages in self._messages and never performs any network
    I/O. Does NOT import os, requests, urllib, or httpx. NEVER reads
    TELEGRAM_BOT_TOKEN or any other secrets. NEVER calls the real
    Telegram API. Safe for use in tests and sandboxed simulations.
    """

    def __init__(self) -> None:
        """Initialise with an empty in-memory message store."""
        self._messages: list[TelegramMessage] = []

    def send_message(self, chat_id_hint: str, message: str) -> TelegramMessage:
        """Capture a free-form informational message in memory.

        Args:
            chat_id_hint: Opaque chat identifier hint (never used to call any API).
            message: Message content to capture.

        Returns:
            The TelegramMessage that was stored.
        """
        captured = TelegramMessage(
            timestamp_utc=datetime.now(UTC).isoformat(),
            bot_id="",
            message_type="info",
            content=message,
            metadata={"chat_id_hint": chat_id_hint},
        )
        self._messages.append(captured)
        return captured

    def send_approval_request(
        self,
        chat_id_hint: str,
        bot_id: str,
        candidate_sha: str,
        backtest_summary: dict[str, str | int | float],
        walk_forward_summary: dict[str, str | int | float],
        risk_reason: str,
    ) -> TelegramMessage:
        """Capture an approval request message in memory.

        Args:
            chat_id_hint: Opaque chat identifier hint.
            bot_id: Bot identifier.
            candidate_sha: SHA256 hash of the mutation candidate.
            backtest_summary: Backtest summary dictionary.
            walk_forward_summary: Walk-forward summary dictionary.
            risk_reason: Human-readable risk reason.

        Returns:
            The TelegramMessage that was stored, with
            status="pending_human_approval" in its metadata.
        """
        content = f"Approval requested for {bot_id} candidate {candidate_sha}: {risk_reason}"
        captured = TelegramMessage(
            timestamp_utc=datetime.now(UTC).isoformat(),
            bot_id=bot_id,
            message_type="approval_request",
            content=content,
            metadata={
                "chat_id_hint": chat_id_hint,
                "candidate_sha": candidate_sha,
                "backtest_summary": dict(backtest_summary),
                "walk_forward_summary": dict(walk_forward_summary),
                "risk_reason": risk_reason,
                "status": "pending_human_approval",
            },
        )
        self._messages.append(captured)
        return captured

    def get_messages(self) -> list[TelegramMessage]:
        """Return the in-memory list of captured messages.

        Returns:
            A copy of the captured messages list, preserving the
            original ordering.
        """
        return list(self._messages)
