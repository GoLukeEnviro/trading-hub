"""Telegram adapter protocol — dry-run only.

Defines the interface for sending notifications and approval requests to
Telegram. Only a protocol and a dry-run implementation are permitted in
this codebase. The protocol is runtime_checkable so test doubles and
mocks can be verified for protocol conformance.

The dry-run implementation captures messages in memory and NEVER performs
real HTTP calls, never imports os / requests / urllib / httpx, and never
reads tokens, chat IDs, or other credentials. Real Telegram integration
is explicitly out of scope for Phase D.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field


class TelegramMessage(BaseModel):
    """A captured Telegram message (dry-run).

    The dry-run adapter stores these in memory so tests can assert on
    what would have been sent. No real Telegram API is ever called.
    """

    model_config = ConfigDict(strict=False)

    timestamp_utc: str
    bot_id: str
    message_type: str
    content: str
    metadata: dict[str, str | int | float | bool | dict[str, str | int | float] | None] = Field(
        default_factory=dict,
    )


@runtime_checkable
class TelegramAdapter(Protocol):
    """Protocol for sending Telegram messages (dry-run only in Phase D)."""

    def send_message(self, chat_id_hint: str, message: str) -> TelegramMessage:
        """Send a free-form informational message.

        Args:
            chat_id_hint: Opaque chat identifier hint (not used to call any API).
            message: The message content.

        Returns:
            The TelegramMessage that was captured/recorded.
        """
        ...

    def send_approval_request(
        self,
        chat_id_hint: str,
        bot_id: str,
        candidate_sha: str,
        backtest_summary: dict[str, str | int | float],
        walk_forward_summary: dict[str, str | int | float],
        risk_reason: str,
    ) -> TelegramMessage:
        """Send an approval request summarising a candidate.

        Args:
            chat_id_hint: Opaque chat identifier hint.
            bot_id: Bot identifier.
            candidate_sha: SHA256 hash of the mutation candidate.
            backtest_summary: Summary of backtest results.
            walk_forward_summary: Summary of walk-forward results.
            risk_reason: Human-readable risk reason.

        Returns:
            The TelegramMessage that was captured/recorded.
        """
        ...
