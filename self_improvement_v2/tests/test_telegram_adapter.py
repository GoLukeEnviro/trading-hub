"""Unit tests for the dry-run Telegram adapter."""

from __future__ import annotations

from datetime import UTC, datetime

from si_v2.adapters.dry_run_stub import DryRunTelegramAdapter
from si_v2.adapters.telegram_adapter import TelegramAdapter, TelegramMessage


class TestDryRunTelegramAdapterInfo:
    """send_message captures an info message in memory."""

    def test_send_message_appends_info_message(self) -> None:
        adapter = DryRunTelegramAdapter()
        msg = adapter.send_message(chat_id_hint="chat-1", message="hello")
        assert isinstance(msg, TelegramMessage)
        assert msg.message_type == "info"
        assert msg.content == "hello"
        assert msg.metadata["chat_id_hint"] == "chat-1"

    def test_send_message_increments_store(self) -> None:
        adapter = DryRunTelegramAdapter()
        adapter.send_message("c1", "a")
        adapter.send_message("c1", "b")
        adapter.send_message("c2", "c")
        msgs = adapter.get_messages()
        assert len(msgs) == 3
        assert [m.content for m in msgs] == ["a", "b", "c"]


class TestDryRunTelegramAdapterApproval:
    """send_approval_request captures an approval request message."""

    def test_send_approval_request_appends_message(self) -> None:
        adapter = DryRunTelegramAdapter()
        msg = adapter.send_approval_request(
            chat_id_hint="chat-1",
            bot_id="bot_a",
            candidate_sha="abc123",
            backtest_summary={"profit_total_pct": 3.5},
            walk_forward_summary={"stability_score": 0.8},
            risk_reason="all good",
        )
        assert msg.message_type == "approval_request"
        assert msg.bot_id == "bot_a"
        assert msg.metadata["candidate_sha"] == "abc123"
        assert msg.metadata["status"] == "pending_human_approval"
        assert msg.metadata["risk_reason"] == "all good"
        assert msg.metadata["backtest_summary"] == {"profit_total_pct": 3.5}
        assert msg.metadata["walk_forward_summary"] == {"stability_score": 0.8}

    def test_timestamp_is_iso8601(self) -> None:
        adapter = DryRunTelegramAdapter()
        msg = adapter.send_message("c", "hi")
        # Must parse back as ISO 8601
        datetime.fromisoformat(msg.timestamp_utc)
        # And should be in UTC (the "+00:00" form)
        assert msg.timestamp_utc.endswith("+00:00")


class TestDryRunTelegramAdapterSafety:
    """The adapter must not import networking libraries."""

    def test_no_network_imports(self) -> None:
        import re

        import si_v2.adapters.dry_run_stub as mod

        with open(mod.__file__, encoding="utf-8") as f:
            src = f.read()
        # Look for import statements at the start of a line (preceded by
        # optional whitespace). This avoids false positives where the
        # substrings "import os" etc. appear inside a docstring.
        import_pattern = re.compile(r"^\s*import\s+(os|requests|urllib|httpx)\b", re.MULTILINE)
        from_pattern = re.compile(r"^\s*from\s+(os|requests|urllib|httpx)\b", re.MULTILINE)
        assert not import_pattern.search(src), "found forbidden 'import' statement"
        assert not from_pattern.search(src), "found forbidden 'from' statement"

    def test_telegram_adapter_protocol_no_network_imports(self) -> None:
        import re

        import si_v2.adapters.telegram_adapter as mod

        with open(mod.__file__, encoding="utf-8") as f:
            src = f.read()
        import_pattern = re.compile(r"^\s*import\s+(os|requests|urllib|httpx)\b", re.MULTILINE)
        from_pattern = re.compile(r"^\s*from\s+(os|requests|urllib|httpx)\b", re.MULTILINE)
        assert not import_pattern.search(src), "found forbidden 'import' statement"
        assert not from_pattern.search(src), "found forbidden 'from' statement"


class TestTelegramAdapterProtocol:
    """The TelegramAdapter protocol must be runtime checkable."""

    def test_dry_run_adapter_satisfies_protocol(self) -> None:
        adapter = DryRunTelegramAdapter()
        assert isinstance(adapter, TelegramAdapter)

    def test_telegram_message_is_pydantic_model(self) -> None:
        msg = TelegramMessage(
            timestamp_utc=datetime.now(UTC).isoformat(),
            bot_id="b",
            message_type="info",
            content="x",
        )
        assert msg.bot_id == "b"
        assert msg.message_type == "info"


class TestDryRunTelegramAdapterInMemoryOnly:
    """The adapter must not perform any I/O."""

    def test_get_messages_returns_copy(self) -> None:
        adapter = DryRunTelegramAdapter()
        adapter.send_message("c", "x")
        first = adapter.get_messages()
        # Mutate the returned list — the internal store must be unaffected
        first.clear()
        second = adapter.get_messages()
        assert len(second) == 1
