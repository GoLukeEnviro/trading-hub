"""Audit hook contract for real adapter invocations.

All real adapters call ``_record_audit(...)`` on every method invocation,
regardless of whether the call was allowed or denied. The audit sink
captures these events for monitoring, debugging, and compliance.

Two concrete sinks are provided:
- :class:`InMemoryAdapterAuditSink` — stores events in a Python list
  (suitable for tests and transient sessions).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from enum import StrEnum
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field


class AdapterMode(StrEnum):
    """Operational mode of a real adapter invocation.

    Values:
        dry_run:    A no-op / mock execution (no real side effects).
        real:       Actual execution against the live target.
        simulated:  A synthetic execution for testing or rehearsal.
    """

    dry_run = "dry_run"
    real = "real"
    simulated = "simulated"


class AdapterAuditEvent(BaseModel):
    """A single audited invocation on a real adapter.

    All fields are required except ``reason``, ``duration_ms``, and
    ``error``, which default to empty / ``None``.
    """

    timestamp_utc: datetime = Field(
        description="UTC timestamp of the invocation.",
    )
    adapter_name: str = Field(
        description="Class name of the adapter (e.g. ``RealDockerAdapter``).",
    )
    method_name: str = Field(
        description="Method called (e.g. ``exec_readonly``).",
    )
    mode: AdapterMode = Field(
        description="Operational mode at invocation time.",
    )
    call_id: str = Field(
        description="Unique call identifier (UUID).",
    )
    allowed: bool = Field(
        description="Whether the invocation was allowed by the gate / budget.",
    )
    reason: str = Field(
        default="",
        description="Human-readable reason for the allow/deny decision.",
    )
    duration_ms: float | None = Field(
        default=None,
        description="Execution duration in milliseconds, if measured.",
    )
    error: str | None = Field(
        default=None,
        description="Error message if the invocation raised, else ``None``.",
    )


@runtime_checkable
class AdapterAuditSink(Protocol):
    """Protocol for durable audit event storage.

    Implementations must be :func:`~abc.runtime_checkable` so callers
    can verify conformance with ``isinstance(sink, AdapterAuditSink)``.
    """

    def record(self, event: AdapterAuditEvent) -> None:
        """Persist a single audit event."""
        ...


class InMemoryAdapterAuditSink:
    """In-memory audit sink that stores events in a Python list.

    Useful for tests and transient sessions. Not thread-safe.
    """

    def __init__(self) -> None:
        """Initialise with an empty event store."""
        self._events: list[AdapterAuditEvent] = []

    def record(self, event: AdapterAuditEvent) -> None:
        """Append *event* to the in-memory store.

        Args:
            event: The audit event to store.
        """
        self._events.append(event)

    def get_events(self) -> Sequence[AdapterAuditEvent]:
        """Return a read-only view of all recorded events.

        Returns:
            A copy of the internal event list.
        """
        return list(self._events)

    def clear(self) -> None:
        """Remove all recorded events."""
        self._events.clear()

    def count_by_adapter(self) -> dict[str, int]:
        """Count events grouped by ``adapter_name``.

        Returns:
            Dictionary mapping adapter name -> event count.
        """
        counts: dict[str, int] = {}
        for event in self._events:
            counts[event.adapter_name] = counts.get(event.adapter_name, 0) + 1
        return counts
