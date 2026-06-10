"""Tests for real adapter base classes (adapters/real_base.py).

Each base MUST refuse instantiation without SI_V2_ENABLE_REAL_ADAPTERS=1.
Each base MUST record a denied audit event when the gate blocks creation.

The tests use monkeypatch to control the environment and inject an
in-memory audit sink.
"""

from __future__ import annotations

import pytest

from si_v2.adapters.audit import (
    AdapterAuditSink,
    InMemoryAdapterAuditSink,
)
from si_v2.adapters.call_budget import CallBudgetChecker, CallBudgetConfig
from si_v2.adapters.real_base import (
    RealAdapterBase,
    RealAi4tradeAdapterBase,
    RealDockerAdapterBase,
    RealFreqtradeAdapterBase,
    RealTelegramAdapterBase,
)
from si_v2.config.gate import SI_V2_ENABLE_REAL_ADAPTERS

# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture
def audit_sink() -> AdapterAuditSink:
    """Provide a fresh :class:`InMemoryAdapterAuditSink`."""
    return InMemoryAdapterAuditSink()


@pytest.fixture
def call_budget() -> CallBudgetChecker:
    """Provide a permissive budget checker (not really used in these tests)."""
    return CallBudgetChecker(CallBudgetConfig(max_calls=100, window_seconds=60.0))


# ------------------------------------------------------------------
# RealAdapterBase
# ------------------------------------------------------------------


class TestRealAdapterBase:
    """Tests for the abstract :class:`RealAdapterBase`."""

    def test_raises_without_env_var(
        self,
        monkeypatch: pytest.MonkeyPatch,
        audit_sink: AdapterAuditSink,
    ) -> None:
        """Refuses instantiation without SI_V2_ENABLE_REAL_ADAPTERS=1."""
        monkeypatch.delenv(SI_V2_ENABLE_REAL_ADAPTERS, raising=False)

        with pytest.raises(RuntimeError, match=SI_V2_ENABLE_REAL_ADAPTERS):
            _ConcreteRealAdapter(audit_sink=audit_sink)

    def test_raises_with_env_var_0(
        self,
        monkeypatch: pytest.MonkeyPatch,
        audit_sink: AdapterAuditSink,
    ) -> None:
        """Refuses instantiation when env var is ``\"0\"``."""
        monkeypatch.setenv(SI_V2_ENABLE_REAL_ADAPTERS, "0")

        with pytest.raises(RuntimeError, match=SI_V2_ENABLE_REAL_ADAPTERS):
            _ConcreteRealAdapter(audit_sink=audit_sink)

    def test_instantiates_with_env_var_1(
        self,
        monkeypatch: pytest.MonkeyPatch,
        audit_sink: AdapterAuditSink,
    ) -> None:
        """Instantiates when env var is ``\"1\"``."""
        monkeypatch.setenv(SI_V2_ENABLE_REAL_ADAPTERS, "1")

        adapter = _ConcreteRealAdapter(audit_sink=audit_sink)
        assert adapter is not None
        assert isinstance(adapter, RealAdapterBase)

    def test_instantiates_with_call_budget(
        self,
        monkeypatch: pytest.MonkeyPatch,
        audit_sink: AdapterAuditSink,
        call_budget: CallBudgetChecker,
    ) -> None:
        """Instantiates with both audit_sink and call_budget."""
        monkeypatch.setenv(SI_V2_ENABLE_REAL_ADAPTERS, "1")

        adapter = _ConcreteRealAdapter(audit_sink=audit_sink, call_budget=call_budget)
        assert adapter is not None

    def test_raises_with_custom_gate_flag(
        self,
        monkeypatch: pytest.MonkeyPatch,
        audit_sink: AdapterAuditSink,
    ) -> None:
        """Uses the custom gate_flag if provided."""
        monkeypatch.delenv(SI_V2_ENABLE_REAL_ADAPTERS, raising=False)
        monkeypatch.delenv("MY_CUSTOM_GATE", raising=False)

        with pytest.raises(RuntimeError, match="MY_CUSTOM_GATE"):
            _ConcreteRealAdapter(audit_sink=audit_sink, gate_flag="MY_CUSTOM_GATE")

    def test_instantiates_with_custom_gate_flag(
        self,
        monkeypatch: pytest.MonkeyPatch,
        audit_sink: AdapterAuditSink,
    ) -> None:
        """Instantiates when custom gate flag is ``\"1\"``."""
        monkeypatch.setenv("MY_CUSTOM_GATE", "1")

        adapter = _ConcreteRealAdapter(audit_sink=audit_sink, gate_flag="MY_CUSTOM_GATE")
        assert adapter is not None

    def test_record_audit_records_event(
        self,
        monkeypatch: pytest.MonkeyPatch,
        audit_sink: AdapterAuditSink,
    ) -> None:
        """_record_audit adds an event to the sink."""
        monkeypatch.setenv(SI_V2_ENABLE_REAL_ADAPTERS, "1")

        adapter = _ConcreteRealAdapter(audit_sink=audit_sink)
        adapter._record_audit("test_method", allowed=True, reason="all good")

        events = audit_sink.get_events()  # type: ignore[union-attr]
        assert len(events) == 1
        assert events[0].method_name == "test_method"
        assert events[0].allowed is True
        assert events[0].reason == "all good"

    def test_record_audit_denied_event(
        self,
        monkeypatch: pytest.MonkeyPatch,
        audit_sink: AdapterAuditSink,
    ) -> None:
        """_record_audit works for denied events too."""
        monkeypatch.setenv(SI_V2_ENABLE_REAL_ADAPTERS, "1")

        adapter = _ConcreteRealAdapter(audit_sink=audit_sink)
        adapter._record_audit("blocked_method", allowed=False, reason="budget exhausted")

        events = audit_sink.get_events()  # type: ignore[union-attr]
        assert len(events) == 1
        assert events[0].allowed is False

    def test_check_budget_allows_when_no_budget_set(
        self,
        monkeypatch: pytest.MonkeyPatch,
        audit_sink: AdapterAuditSink,
    ) -> None:
        """_check_budget returns True when call_budget is None."""
        monkeypatch.setenv(SI_V2_ENABLE_REAL_ADAPTERS, "1")

        adapter = _ConcreteRealAdapter(audit_sink=audit_sink, call_budget=None)
        assert adapter._check_budget("any_method") is True

    def test_check_budget_denies_when_exhausted(
        self,
        monkeypatch: pytest.MonkeyPatch,
        audit_sink: AdapterAuditSink,
    ) -> None:
        """_check_budget returns False and records denied event when exhausted."""
        monkeypatch.setenv(SI_V2_ENABLE_REAL_ADAPTERS, "1")

        budget = CallBudgetChecker(CallBudgetConfig(max_calls=1, window_seconds=60.0))
        adapter = _ConcreteRealAdapter(audit_sink=audit_sink, call_budget=budget)

        # First call — allowed
        assert adapter._check_budget("first_call") is True
        # Second call — denied
        assert adapter._check_budget("second_call") is False

        # Verify denied audit event was recorded
        events = audit_sink.get_events()  # type: ignore[union-attr]
        denied = [e for e in events if not e.allowed]
        assert len(denied) == 1
        assert "budget" in denied[0].reason.lower()


# ------------------------------------------------------------------
# RealDockerAdapterBase
# ------------------------------------------------------------------


class TestRealDockerAdapterBase:
    def test_raises_without_env(self, monkeypatch: pytest.MonkeyPatch, audit_sink: AdapterAuditSink) -> None:
        monkeypatch.delenv(SI_V2_ENABLE_REAL_ADAPTERS, raising=False)
        with pytest.raises(RuntimeError, match=SI_V2_ENABLE_REAL_ADAPTERS):
            RealDockerAdapterBase(audit_sink=audit_sink)

    def test_instantiates_with_env_1(self, monkeypatch: pytest.MonkeyPatch, audit_sink: AdapterAuditSink) -> None:
        monkeypatch.setenv(SI_V2_ENABLE_REAL_ADAPTERS, "1")
        adapter = RealDockerAdapterBase(audit_sink=audit_sink)
        assert isinstance(adapter, RealDockerAdapterBase)

    def test_build_docker_intent(self, monkeypatch: pytest.MonkeyPatch, audit_sink: AdapterAuditSink) -> None:
        """_build_docker_intent returns a typed intent dict (no execution)."""
        monkeypatch.setenv(SI_V2_ENABLE_REAL_ADAPTERS, "1")
        adapter = RealDockerAdapterBase(audit_sink=audit_sink)

        intent = adapter._build_docker_intent("my_container", ["echo", "hello"])
        assert intent["container"] == "my_container"
        assert intent["command"] == ["echo", "hello"]
        assert intent["mode"] == "readonly"

    def test_build_docker_intent_copies_list(
        self, monkeypatch: pytest.MonkeyPatch, audit_sink: AdapterAuditSink
    ) -> None:
        """The intent dict gets a copy of the command list."""
        monkeypatch.setenv(SI_V2_ENABLE_REAL_ADAPTERS, "1")
        adapter = RealDockerAdapterBase(audit_sink=audit_sink)
        orig = ["ls", "-la"]
        intent = adapter._build_docker_intent("c", orig)
        orig.append("extra")
        assert intent["command"] == ["ls", "-la"]  # unchanged

    def test_refuses_with_env_0(self, monkeypatch: pytest.MonkeyPatch, audit_sink: AdapterAuditSink) -> None:
        monkeypatch.setenv(SI_V2_ENABLE_REAL_ADAPTERS, "0")
        with pytest.raises(RuntimeError, match=SI_V2_ENABLE_REAL_ADAPTERS):
            RealDockerAdapterBase(audit_sink=audit_sink)


# ------------------------------------------------------------------
# RealFreqtradeAdapterBase
# ------------------------------------------------------------------


class TestRealFreqtradeAdapterBase:
    def test_raises_without_env(self, monkeypatch: pytest.MonkeyPatch, audit_sink: AdapterAuditSink) -> None:
        monkeypatch.delenv(SI_V2_ENABLE_REAL_ADAPTERS, raising=False)
        with pytest.raises(RuntimeError, match=SI_V2_ENABLE_REAL_ADAPTERS):
            RealFreqtradeAdapterBase(audit_sink=audit_sink)

    def test_instantiates_with_env_1(self, monkeypatch: pytest.MonkeyPatch, audit_sink: AdapterAuditSink) -> None:
        monkeypatch.setenv(SI_V2_ENABLE_REAL_ADAPTERS, "1")
        adapter = RealFreqtradeAdapterBase(audit_sink=audit_sink)
        assert isinstance(adapter, RealFreqtradeAdapterBase)

    def test_refuses_with_env_0(self, monkeypatch: pytest.MonkeyPatch, audit_sink: AdapterAuditSink) -> None:
        monkeypatch.setenv(SI_V2_ENABLE_REAL_ADAPTERS, "0")
        with pytest.raises(RuntimeError, match=SI_V2_ENABLE_REAL_ADAPTERS):
            RealFreqtradeAdapterBase(audit_sink=audit_sink)

    def test_records_audit(self, monkeypatch: pytest.MonkeyPatch, audit_sink: AdapterAuditSink) -> None:
        monkeypatch.setenv(SI_V2_ENABLE_REAL_ADAPTERS, "1")
        adapter = RealFreqtradeAdapterBase(audit_sink=audit_sink)
        adapter._record_audit("read_config", allowed=False, reason="gate disabled")
        events = audit_sink.get_events()  # type: ignore[union-attr]
        assert len(events) == 1
        assert events[0].adapter_name == "RealFreqtradeAdapterBase"


# ------------------------------------------------------------------
# RealTelegramAdapterBase
# ------------------------------------------------------------------


class TestRealTelegramAdapterBase:
    def test_raises_without_env(self, monkeypatch: pytest.MonkeyPatch, audit_sink: AdapterAuditSink) -> None:
        monkeypatch.delenv(SI_V2_ENABLE_REAL_ADAPTERS, raising=False)
        with pytest.raises(RuntimeError, match=SI_V2_ENABLE_REAL_ADAPTERS):
            RealTelegramAdapterBase(audit_sink=audit_sink)

    def test_instantiates_with_env_1(self, monkeypatch: pytest.MonkeyPatch, audit_sink: AdapterAuditSink) -> None:
        monkeypatch.setenv(SI_V2_ENABLE_REAL_ADAPTERS, "1")
        adapter = RealTelegramAdapterBase(audit_sink=audit_sink)
        assert isinstance(adapter, RealTelegramAdapterBase)

    def test_refuses_with_env_0(self, monkeypatch: pytest.MonkeyPatch, audit_sink: AdapterAuditSink) -> None:
        monkeypatch.setenv(SI_V2_ENABLE_REAL_ADAPTERS, "0")
        with pytest.raises(RuntimeError, match=SI_V2_ENABLE_REAL_ADAPTERS):
            RealTelegramAdapterBase(audit_sink=audit_sink)


# ------------------------------------------------------------------
# RealAi4tradeAdapterBase
# ------------------------------------------------------------------


class TestRealAi4tradeAdapterBase:
    def test_raises_without_env(self, monkeypatch: pytest.MonkeyPatch, audit_sink: AdapterAuditSink) -> None:
        monkeypatch.delenv(SI_V2_ENABLE_REAL_ADAPTERS, raising=False)
        with pytest.raises(RuntimeError, match=SI_V2_ENABLE_REAL_ADAPTERS):
            RealAi4tradeAdapterBase(audit_sink=audit_sink)

    def test_instantiates_with_env_1(self, monkeypatch: pytest.MonkeyPatch, audit_sink: AdapterAuditSink) -> None:
        monkeypatch.setenv(SI_V2_ENABLE_REAL_ADAPTERS, "1")
        adapter = RealAi4tradeAdapterBase(audit_sink=audit_sink)
        assert isinstance(adapter, RealAi4tradeAdapterBase)

    def test_refuses_with_env_0(self, monkeypatch: pytest.MonkeyPatch, audit_sink: AdapterAuditSink) -> None:
        monkeypatch.setenv(SI_V2_ENABLE_REAL_ADAPTERS, "0")
        with pytest.raises(RuntimeError, match=SI_V2_ENABLE_REAL_ADAPTERS):
            RealAi4tradeAdapterBase(audit_sink=audit_sink)


# ------------------------------------------------------------------
# Concrete subclass for testing RealAdapterBase
# ------------------------------------------------------------------


class _ConcreteRealAdapter(RealAdapterBase):
    """Minimal concrete subclass for testing the abstract base."""

    def __init__(
        self,
        audit_sink: AdapterAuditSink,
        call_budget: CallBudgetChecker | None = None,
        gate_flag: str = SI_V2_ENABLE_REAL_ADAPTERS,
    ) -> None:
        super().__init__(audit_sink, call_budget, gate_flag)
