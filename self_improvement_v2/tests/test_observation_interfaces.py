"""Tests for #148: Offline observation interface contract stubs.

Verifies that:
- ``DisabledObserverPlaceholder`` cannot be instantiated.
- ``FakeLocalObserver`` returns fake data.
- ``ObserverProtocol`` is structural (works with ``FakeLocalObserver``).
- Future integration placeholders all raise ``RuntimeError``.
"""

from __future__ import annotations

import pytest

from rehearsal.observation_interfaces import (
    BitgetObserverPlaceholder,
    DisabledObserverPlaceholder,
    DockerObserverPlaceholder,
    FakeLocalObserver,
    ObservationResult,
    ObserverProtocol,
    SubprocessObserverPlaceholder,
)

# ---------------------------------------------------------------------------
# DisabledObserverPlaceholder
# ---------------------------------------------------------------------------


class TestDisabledObserverPlaceholder:
    """"Default activation impossible" — cannot instantiate."""

    def test_instantiation_raises_runtime_error(self) -> None:
        """Constructing DisabledObserverPlaceholder should raise RuntimeError."""
        with pytest.raises(RuntimeError):
            DisabledObserverPlaceholder()

    def test_cannot_be_used_as_observer(self) -> None:
        """Since it can't be instantiated, it can't be used."""
        with pytest.raises(RuntimeError):
            DisabledObserverPlaceholder()


# ---------------------------------------------------------------------------
# FakeLocalObserver
# ---------------------------------------------------------------------------


class TestFakeLocalObserver:
    """Fake observer should return deterministic fake data."""

    def test_returns_observation_result(self) -> None:
        observer = FakeLocalObserver()
        result = observer.observe()
        assert isinstance(result, ObservationResult)

    def test_is_fake_flag(self) -> None:
        observer = FakeLocalObserver()
        result = observer.observe()
        assert result.is_fake is True

    def test_default_source(self) -> None:
        observer = FakeLocalObserver()
        result = observer.observe()
        assert result.source == "fake-local"

    def test_custom_source(self) -> None:
        observer = FakeLocalObserver()
        result = observer.observe("custom-source")
        assert result.source == "custom-source"

    def test_has_timestamp(self) -> None:
        observer = FakeLocalObserver()
        result = observer.observe()
        assert len(result.timestamp) > 0
        assert "T" in result.timestamp  # ISO-8601 format
        assert result.timestamp.endswith("Z")

    def test_has_content(self) -> None:
        observer = FakeLocalObserver()
        result = observer.observe()
        assert len(result.content) > 0
        assert "Fake observation" in result.content

    def test_has_metadata_with_observer_type(self) -> None:
        observer = FakeLocalObserver()
        result = observer.observe()
        assert result.metadata.get("observer_type") == "FakeLocalObserver"
        assert result.metadata.get("offline") is True

    def test_deterministic_with_same_source(self) -> None:
        observer = FakeLocalObserver()
        result1 = observer.observe("same-source")
        result2 = observer.observe("same-source")
        assert result1.source == result2.source
        assert result1.is_fake == result2.is_fake
        # Timestamps may differ if time passes between calls, but source and
        # content structure should be the same
        assert result1.content.startswith("Fake observation data for 'same-source'")
        assert result2.content.startswith("Fake observation data for 'same-source'")


# ---------------------------------------------------------------------------
# ObserverProtocol structural typing
# ---------------------------------------------------------------------------


class TestObserverProtocol:
    """Protocol should be structural — any class with 'observe' method matches."""

    def test_fake_local_observer_satisfies_protocol(self) -> None:
        """FakeLocalObserver should be structurally compatible with ObserverProtocol."""
        observer: ObserverProtocol = FakeLocalObserver()
        result = observer.observe("test")
        assert isinstance(result, ObservationResult)

    def test_protocol_is_runtime_checkable(self) -> None:
        """ObserverProtocol should be runtime-checkable."""
        assert isinstance(FakeLocalObserver(), ObserverProtocol)

    def test_plain_object_not_protocol(self) -> None:
        """A plain object without 'observe' should not match the protocol."""

        class NotAnObserver:
            pass

        assert not isinstance(NotAnObserver(), ObserverProtocol)

    def test_protocol_signature(self) -> None:
        """The protocol observe method should accept a source string."""
        # Verify the method signature exists
        assert hasattr(ObserverProtocol, "observe")


# ---------------------------------------------------------------------------
# Future integration placeholders
# ---------------------------------------------------------------------------


class TestIntegrationPlaceholders:
    """All future integration placeholders must raise RuntimeError."""

    def test_bitget_placeholder_raises(self) -> None:
        with pytest.raises(RuntimeError) as exc_info:
            BitgetObserverPlaceholder()
        assert "not yet implemented" in str(exc_info.value)

    def test_docker_placeholder_raises(self) -> None:
        with pytest.raises(RuntimeError) as exc_info:
            DockerObserverPlaceholder()
        assert "Docker" in str(exc_info.value)

    def test_subprocess_placeholder_raises(self) -> None:
        with pytest.raises(RuntimeError) as exc_info:
            SubprocessObserverPlaceholder()
        assert "subprocess" in str(exc_info.value)
