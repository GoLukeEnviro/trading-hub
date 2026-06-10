"""Tests for the audit hook contract (adapters/audit.py).

Covers: event shape, sink record/retrieve, mode enum, count_by_adapter.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from si_v2.adapters.audit import (
    AdapterAuditEvent,
    AdapterAuditSink,
    AdapterMode,
    InMemoryAdapterAuditSink,
)


class TestAdapterMode:
    """Tests for the :class:`AdapterMode` enum."""

    def test_values(self) -> None:
        assert AdapterMode.dry_run.value == "dry_run"
        assert AdapterMode.real.value == "real"
        assert AdapterMode.simulated.value == "simulated"

    def test_all_three_distinct(self) -> None:
        modes = {AdapterMode.dry_run, AdapterMode.real, AdapterMode.simulated}
        assert len(modes) == 3


class TestAdapterAuditEvent:
    """Tests for the :class:`AdapterAuditEvent` model."""

    def test_minimal_event(self) -> None:
        """Create an event with only required fields."""
        now = datetime.now(UTC)
        event = AdapterAuditEvent(
            timestamp_utc=now,
            adapter_name="MyAdapter",
            method_name="do_stuff",
            mode=AdapterMode.real,
            call_id="abc-123",
            allowed=True,
        )
        assert event.adapter_name == "MyAdapter"
        assert event.method_name == "do_stuff"
        assert event.mode == AdapterMode.real
        assert event.call_id == "abc-123"
        assert event.allowed is True
        assert event.reason == ""
        assert event.duration_ms is None
        assert event.error is None

    def test_full_event(self) -> None:
        """Create an event with all fields."""
        now = datetime.now(UTC)
        event = AdapterAuditEvent(
            timestamp_utc=now,
            adapter_name="RealDockerAdapter",
            method_name="exec_readonly",
            mode=AdapterMode.dry_run,
            call_id="def-456",
            allowed=False,
            reason="Gate disabled",
            duration_ms=12.5,
            error="Connection timeout",
        )
        assert event.reason == "Gate disabled"
        assert event.duration_ms == 12.5
        assert event.error == "Connection timeout"

    def test_missing_required_field_raises(self) -> None:
        """Missing required fields raise ValidationError."""
        with pytest.raises(ValidationError):
            AdapterAuditEvent()  # type: ignore[call-arg]

    def test_timestamp_utc_timezone(self) -> None:
        """timestamp_utc should contain timezone info (UTC)."""
        event = AdapterAuditEvent(
            timestamp_utc=datetime.now(UTC),
            adapter_name="A",
            method_name="m",
            mode=AdapterMode.real,
            call_id="id",
            allowed=True,
        )
        assert event.timestamp_utc.tzinfo is not None


class TestInMemoryAdapterAuditSink:
    """Tests for :class:`InMemoryAdapterAuditSink`."""

    def test_record_and_get_events(self) -> None:
        sink = InMemoryAdapterAuditSink()
        assert len(sink.get_events()) == 0

        event = _make_event(adapter_name="Test", allowed=True)
        sink.record(event)
        events = sink.get_events()
        assert len(events) == 1
        assert events[0].adapter_name == "Test"

    def test_record_retrieves_copy(self) -> None:
        """get_events returns a copy, not the internal list."""
        sink = InMemoryAdapterAuditSink()
        event = _make_event()
        sink.record(event)
        events = sink.get_events()
        assert len(events) == 1
        # Clearing the sink should not affect the returned copy
        sink.clear()
        assert len(sink.get_events()) == 0
        # The previously returned copy should still have the event
        assert len(events) == 1

    def test_clear(self) -> None:
        sink = InMemoryAdapterAuditSink()
        sink.record(_make_event())
        sink.record(_make_event())
        assert len(sink.get_events()) == 2
        sink.clear()
        assert len(sink.get_events()) == 0

    def test_count_by_adapter(self) -> None:
        sink = InMemoryAdapterAuditSink()
        sink.record(_make_event(adapter_name="Docker"))
        sink.record(_make_event(adapter_name="Docker"))
        sink.record(_make_event(adapter_name="Freqtrade"))
        counts = sink.count_by_adapter()
        assert counts == {"Docker": 2, "Freqtrade": 1}

    def test_count_by_adapter_empty(self) -> None:
        sink = InMemoryAdapterAuditSink()
        assert sink.count_by_adapter() == {}

    def test_protocol_runtime_checkable(self) -> None:
        """InMemoryAdapterAuditSink satisfies AdapterAuditSink protocol."""
        sink: AdapterAuditSink = InMemoryAdapterAuditSink()
        assert isinstance(sink, AdapterAuditSink)

    def test_multiple_records_preserve_order(self) -> None:
        sink = InMemoryAdapterAuditSink()
        e1 = _make_event(adapter_name="first")
        e2 = _make_event(adapter_name="second")
        e3 = _make_event(adapter_name="third")
        sink.record(e1)
        sink.record(e2)
        sink.record(e3)
        names = [e.adapter_name for e in sink.get_events()]
        assert names == ["first", "second", "third"]


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _make_event(
    adapter_name: str = "TestAdapter",
    allowed: bool = True,
) -> AdapterAuditEvent:
    """Create a minimal audit event for testing."""
    return AdapterAuditEvent(
        timestamp_utc=datetime.now(UTC),
        adapter_name=adapter_name,
        method_name="test_method",
        mode=AdapterMode.dry_run,
        call_id="test-call-id",
        allowed=allowed,
    )
