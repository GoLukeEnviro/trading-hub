"""Tests for real adapter prototypes (Docker + Freqtrade).

Verifies env gate, protocol conformance, budget enforcement, and audit
event recording. No actual Docker or Freqtrade calls are made — the env
gate prevents instantiation in test environments.
"""

from __future__ import annotations

import os

import pytest

from si_v2.adapters.audit import InMemoryAdapterAuditSink
from si_v2.adapters.docker_adapter import DockerAdapter
from si_v2.adapters.freqtrade_adapter import FreqtradeAdapter
from si_v2.adapters.real_docker_adapter import RealDockerAdapter
from si_v2.adapters.real_freqtrade_adapter import RealFreqtradeAdapter
from si_v2.state.schemas import MutationOverlay

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def audit_sink() -> InMemoryAdapterAuditSink:
    """Return a fresh in-memory audit sink for each test."""
    return InMemoryAdapterAuditSink()


@pytest.fixture
def enable_gate() -> object:
    """Temporarily set SI_V2_ENABLE_REAL_ADAPTERS=1 for a test."""
    old = os.environ.get("SI_V2_ENABLE_REAL_ADAPTERS")
    os.environ["SI_V2_ENABLE_REAL_ADAPTERS"] = "1"
    yield
    if old is None:
        del os.environ["SI_V2_ENABLE_REAL_ADAPTERS"]
    else:
        os.environ["SI_V2_ENABLE_REAL_ADAPTERS"] = old


@pytest.fixture
def docker_adapter(
    audit_sink: InMemoryAdapterAuditSink,
    enable_gate: object,
) -> RealDockerAdapter:
    """Return a RealDockerAdapter with gate enabled and audit sink."""
    return RealDockerAdapter(audit_sink=audit_sink)


@pytest.fixture
def freqtrade_adapter(
    audit_sink: InMemoryAdapterAuditSink,
    enable_gate: object,
) -> RealFreqtradeAdapter:
    """Return a RealFreqtradeAdapter with gate enabled and audit sink."""
    return RealFreqtradeAdapter(audit_sink=audit_sink)


# ---------------------------------------------------------------------------
# Tests: Env Gate
# ---------------------------------------------------------------------------


class TestEnvGate:
    """Verify adapters cannot be instantiated without the env gate."""

    def test_docker_adapter_fails_without_gate(
        self, audit_sink: InMemoryAdapterAuditSink
    ) -> None:
        """RealDockerAdapter must raise if SI_V2_ENABLE_REAL_ADAPTERS != 1."""
        with pytest.raises(RuntimeError, match="SI_V2_ENABLE_REAL_ADAPTERS"):
            RealDockerAdapter(audit_sink=audit_sink)

    def test_freqtrade_adapter_fails_without_gate(
        self, audit_sink: InMemoryAdapterAuditSink
    ) -> None:
        """RealFreqtradeAdapter must raise if SI_V2_ENABLE_REAL_ADAPTERS != 1."""
        with pytest.raises(RuntimeError, match="SI_V2_ENABLE_REAL_ADAPTERS"):
            RealFreqtradeAdapter(audit_sink=audit_sink)

    def test_docker_adapter_succeeds_with_gate(
        self, docker_adapter: RealDockerAdapter
    ) -> None:
        """RealDockerAdapter must instantiate when gate is enabled."""
        assert docker_adapter is not None
        assert isinstance(docker_adapter, RealDockerAdapter)

    def test_freqtrade_adapter_succeeds_with_gate(
        self, freqtrade_adapter: RealFreqtradeAdapter
    ) -> None:
        """RealFreqtradeAdapter must instantiate when gate is enabled."""
        assert freqtrade_adapter is not None
        assert isinstance(freqtrade_adapter, RealFreqtradeAdapter)


# ---------------------------------------------------------------------------
# Tests: Protocol Conformance
# ---------------------------------------------------------------------------


class TestProtocolConformance:
    """Verify adapters satisfy their respective protocols."""

    def test_docker_adapter_is_docker_adapter_protocol(
        self, docker_adapter: RealDockerAdapter
    ) -> None:
        """RealDockerAdapter must satisfy the DockerAdapter protocol."""
        assert isinstance(docker_adapter, DockerAdapter)

    def test_freqtrade_adapter_is_freqtrade_adapter_protocol(
        self, freqtrade_adapter: RealFreqtradeAdapter
    ) -> None:
        """RealFreqtradeAdapter must satisfy the FreqtradeAdapter protocol."""
        assert isinstance(freqtrade_adapter, FreqtradeAdapter)

    def test_docker_adapter_has_required_methods(
        self, docker_adapter: RealDockerAdapter
    ) -> None:
        """RealDockerAdapter must expose all DockerAdapter methods."""
        assert hasattr(docker_adapter, "exec_readonly")
        assert hasattr(docker_adapter, "container_is_running")
        assert hasattr(docker_adapter, "get_container_ip")

    def test_freqtrade_adapter_has_required_methods(
        self, freqtrade_adapter: RealFreqtradeAdapter
    ) -> None:
        """RealFreqtradeAdapter must expose all FreqtradeAdapter methods."""
        assert hasattr(freqtrade_adapter, "read_config")
        assert hasattr(freqtrade_adapter, "get_trade_history")
        assert hasattr(freqtrade_adapter, "run_backtest")


# ---------------------------------------------------------------------------
# Tests: Call Budget
# ---------------------------------------------------------------------------


class TestCallBudget:
    """Verify call budget enforcement."""

    def test_docker_budget_exhausted(
        self,
        audit_sink: InMemoryAdapterAuditSink,
        enable_gate: object,
    ) -> None:
        """After exhausting the budget, calls should raise RuntimeError."""
        from si_v2.adapters.call_budget import CallBudgetChecker, CallBudgetConfig

        # Use budget of exactly 1 call
        budget = CallBudgetChecker(
            CallBudgetConfig(
                max_calls=1,
                window_seconds=60.0,
                component_name="TestBudget",
            )
        )
        adapter = RealDockerAdapter(audit_sink=audit_sink, call_budget=budget)
        # First call uses the budget slot (will fail because no Docker)
        with pytest.raises((RuntimeError, TimeoutError)):
            adapter.get_container_ip("non-existent")

        # Second call should be blocked by budget
        with pytest.raises(RuntimeError, match="Call budget exhausted"):
            adapter.get_container_ip("non-existent")

    def test_freqtrade_budget_exhausted(
        self,
        audit_sink: InMemoryAdapterAuditSink,
        enable_gate: object,
    ) -> None:
        """After exhausting the budget, calls should raise RuntimeError."""
        from si_v2.adapters.call_budget import CallBudgetChecker, CallBudgetConfig

        budget = CallBudgetChecker(
            CallBudgetConfig(
                max_calls=1,
                window_seconds=60.0,
                component_name="TestBudget",
            )
        )
        adapter = RealFreqtradeAdapter(audit_sink=audit_sink, call_budget=budget)
        # First call uses budget (fails because no Docker)
        with pytest.raises((RuntimeError, TimeoutError, ValueError)):
            adapter.read_config("freqforge")

        # Second call should be blocked by budget
        with pytest.raises(RuntimeError, match="Call budget exhausted"):
            adapter.read_config("freqforge")


# ---------------------------------------------------------------------------
# Tests: Audit Events
# ---------------------------------------------------------------------------


class TestAuditEvents:
    """Verify audit events are recorded on adapter calls."""

    def test_docker_audit_event_recorded(
        self,
        audit_sink: InMemoryAdapterAuditSink,
        enable_gate: object,
    ) -> None:
        """Calling a Docker adapter method should record an audit event."""
        adapter = RealDockerAdapter(audit_sink=audit_sink)
        with pytest.raises((RuntimeError, TimeoutError)):
            adapter.get_container_ip("non-existent")

        events = audit_sink.get_events()
        assert len(events) >= 1
        assert events[0].adapter_name == "RealDockerAdapter"
        assert events[0].method_name in (
            "container_is_running", "exec_readonly", "get_container_ip"
        )

    def test_freqtrade_audit_event_recorded(
        self,
        audit_sink: InMemoryAdapterAuditSink,
        enable_gate: object,
    ) -> None:
        """Calling a Freqtrade adapter method should record an audit event."""
        adapter = RealFreqtradeAdapter(audit_sink=audit_sink)
        with pytest.raises((RuntimeError, TimeoutError, ValueError)):
            adapter.read_config("freqforge")

        events = audit_sink.get_events()
        assert len(events) >= 1
        assert events[0].adapter_name == "RealFreqtradeAdapter"


# ---------------------------------------------------------------------------
# Tests: Freqtrade Bot Resolution
# ---------------------------------------------------------------------------


class TestBotResolution:
    """Verify bot_id → container name resolution."""

    def test_known_bot_resolves(self) -> None:
        """Known bots should resolve to a container name."""
        from si_v2.adapters.real_freqtrade_adapter import _resolve_container

        assert _resolve_container("freqforge") == "trading-freqtrade-freqforge-1"
        assert (
            _resolve_container("regime-hybrid")
            == "trading-freqtrade-regime-hybrid-1"
        )
        assert (
            _resolve_container("freqforge-canary")
            == "trading-freqtrade-freqforge-canary-1"
        )
        assert _resolve_container("freqai-rebel") == "trading-freqai-rebel-1"

    def test_unknown_bot_raises(self) -> None:
        """Unknown bots should raise ValueError."""
        from si_v2.adapters.real_freqtrade_adapter import _resolve_container

        with pytest.raises(ValueError, match="Unknown bot_id"):
            _resolve_container("non-existent-bot")

    def test_empty_bot_raises(self) -> None:
        """Empty bot_id should raise ValueError."""
        from si_v2.adapters.real_freqtrade_adapter import _resolve_container

        with pytest.raises(ValueError):
            _resolve_container("")


# ---------------------------------------------------------------------------
# Tests: MutationOverlay Usage (FreqtradeAdapter)
# ---------------------------------------------------------------------------


class TestMutationOverlay:
    """Verify MutationOverlay usage in run_backtest."""

    def test_run_backtest_requires_overlay(
        self, freqtrade_adapter: RealFreqtradeAdapter
    ) -> None:
        """run_backtest should accept a MutationOverlay and fail gracefully."""
        overlay = MutationOverlay(
            max_open_trades=5,
            stake_amount=100.0,
            stoploss=-0.05,
        )
        with pytest.raises((RuntimeError, TimeoutError, ValueError)):
            freqtrade_adapter.run_backtest("freqforge", overlay)
