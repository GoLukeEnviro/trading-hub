"""Offline observation interface contract stubs (#148).

Defines the ``ObserverProtocol``, concrete fake observer, and disabled
placeholder for future integrations.

**MUST be offline-only.** No network, no subprocess, no Docker.
All future integration placeholders raise ``RuntimeError`` by default.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol, runtime_checkable

# ─────────────────────────────────────────────────────────────────────────────
# ObservationResult
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ObservationResult:
    """A single observation result from an observer.

    Attributes
    ----------
    source : str
        Human-readable name of the observation source (e.g. "fake-local").
    timestamp : str
        ISO-8601 UTC timestamp of when the observation was taken.
    content : str
        The observed content (always fake/deterministic for offline stubs).
    is_fake : bool
        Always ``True`` for offline stubs — marks this as non-production data.
    metadata : dict
        Optional extra metadata attached to the observation.
    """

    source: str = "unknown"
    timestamp: str = ""
    content: str = ""
    is_fake: bool = True
    metadata: dict = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# ObserverProtocol
# ─────────────────────────────────────────────────────────────────────────────


@runtime_checkable
class ObserverProtocol(Protocol):
    """Structural protocol for any observation source.

    Implementations **must** be offline-only.  Future integration adapters
    (e.g. ``BitgetObserver``, ``DockerObserver``) are placeholders that raise
    ``RuntimeError`` until explicitly wired.
    """

    def observe(self, source: str = "") -> ObservationResult:
        """Take a single observation from *source*.

        Parameters
        ----------
        source : str
            Optional identifier for the observation source.  If empty the
            observer's default source is used.

        Returns
        -------
        ObservationResult
            The observation result — always fake for offline stubs.
        """
        ...


# ─────────────────────────────────────────────────────────────────────────────
# FakeLocalObserver
# ─────────────────────────────────────────────────────────────────────────────


class FakeLocalObserver:
    """A fake observer that returns deterministic fake data.

    No network, no subprocess, no Docker — purely offline.

    Examples
    --------
    >>> obs = FakeLocalObserver()
    >>> result = obs.observe("local-regime-stats")
    >>> result.is_fake
    True
    >>> result.source
    'local-regime-stats'
    """

    def __init__(self) -> None:
        self._default_source = "fake-local"

    def observe(self, source: str = "") -> ObservationResult:
        """Return a deterministic fake observation."""
        src = source or self._default_source
        return ObservationResult(
            source=src,
            timestamp=_now_utc(),
            content=f"Fake observation data for '{src}' — offline stub only",
            is_fake=True,
            metadata={"observer_type": "FakeLocalObserver", "offline": True},
        )


# ─────────────────────────────────────────────────────────────────────────────
# DisabledObserverPlaceholder
# ─────────────────────────────────────────────────────────────────────────────


class DisabledObserverPlaceholder:
    """Placeholder for an observer that is not yet implemented.

    Raises ``RuntimeError`` on instantiation so callers cannot accidentally
    activate an integration that would require network / subprocess / Docker
    access.

    Examples
    --------
    >>> try:
    ...     obs = DisabledObserverPlaceholder()
    ... except RuntimeError as e:
    ...     print("Blocked:", e)
    Blocked: DisabledObserverPlaceholder: ...
    """

    def __init__(self) -> None:
        raise RuntimeError(
            "DisabledObserverPlaceholder: this observer is not yet implemented "
            "and cannot be instantiated.  Use FakeLocalObserver for offline tests."
        )

    def observe(self, source: str = "") -> ObservationResult:
        """Should never be called — the constructor raises."""
        raise RuntimeError(
            "DisabledObserverPlaceholder.observe() was called, but this "
            "observer cannot be instantiated."
        )


# ─────────────────────────────────────────────────────────────────────────────
# Future integration placeholders (all raise RuntimeError)
# ─────────────────────────────────────────────────────────────────────────────


class BitgetObserverPlaceholder:
    """Placeholder for future Bitget REST observer.

    Raises ``RuntimeError`` on instantiation.  Will require network access
    when implemented.
    """

    def __init__(self) -> None:
        raise RuntimeError(
            "BitgetObserverPlaceholder is not yet implemented and requires "
            "network access.  Use FakeLocalObserver for offline tests."
        )

    def observe(self, source: str = "") -> ObservationResult:
        raise RuntimeError("BitgetObserverPlaceholder cannot observe.")


class DockerObserverPlaceholder:
    """Placeholder for future Docker-container observer.

    Raises ``RuntimeError`` on instantiation.  Will require Docker access
    when implemented.
    """

    def __init__(self) -> None:
        raise RuntimeError(
            "DockerObserverPlaceholder is not yet implemented and requires "
            "Docker access.  Use FakeLocalObserver for offline tests."
        )

    def observe(self, source: str = "") -> ObservationResult:
        raise RuntimeError("DockerObserverPlaceholder cannot observe.")


class SubprocessObserverPlaceholder:
    """Placeholder for future subprocess-based observer.

    Raises ``RuntimeError`` on instantiation.  Will require ``subprocess``
    when implemented.
    """

    def __init__(self) -> None:
        raise RuntimeError(
            "SubprocessObserverPlaceholder is not yet implemented and requires "
            "subprocess access.  Use FakeLocalObserver for offline tests."
        )

    def observe(self, source: str = "") -> ObservationResult:
        raise RuntimeError("SubprocessObserverPlaceholder cannot observe.")


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _now_utc() -> str:
    """Return current UTC time as ISO-8601 string."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
