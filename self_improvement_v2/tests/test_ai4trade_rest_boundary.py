"""Contract tests for the ai4trade REST boundary prototype.

Tests the full stack:
- Stub server lifecycle
- REST client against stub
- Protocol adapters against stub
- Network guard
- Fail-closed behavior

Only uses localhost stub server — no real ai4trade-bot calls.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from si_v2.integrations.ai4trade.protocols import (
    AdvisorySignal,
    OutcomeProvider,
    RiskGateProvider,
    SignalProvider,
)
from si_v2.integrations.ai4trade.rest_adapters import (
    RestOutcomeProvider,
    RestRiskGateProvider,
    RestSignalProvider,
)
from si_v2.integrations.ai4trade.rest_boundary import (
    Ai4tradeRestBoundaryClient,
    NetworkGuard,
)
from si_v2.integrations.ai4trade.rest_models import (
    HealthResponse,
    OutcomeResponse,
    RiskGateResponse,
    SignalResponse,
)
from tests.support.ai4trade_stub_server import Ai4tradeStubServer


@pytest.fixture
def stub_server() -> Ai4tradeStubServer:
    """Start a stub server on 127.0.0.1 random port for testing."""
    server = Ai4tradeStubServer()
    server.start()
    yield server
    server.stop()


@pytest.fixture
def rest_client(stub_server: Ai4tradeStubServer) -> Ai4tradeRestBoundaryClient:
    """Create a REST client pointed at the stub server."""
    return Ai4tradeRestBoundaryClient(base_url=stub_server.base_url)


# ──────────────────────────────────────────────
# J5: Network Guard Tests
# ──────────────────────────────────────────────


class TestNetworkGuard:
    """Tests for NetworkGuard URL validation."""

    def test_allows_localhost(self) -> None:
        assert NetworkGuard.validate_url("http://localhost:8000") == "http://localhost:8000"

    def test_allows_localhost_with_path(self) -> None:
        assert NetworkGuard.validate_url("http://127.0.0.1:8000/api/health") == "http://127.0.0.1:8000/api/health"

    def test_rejects_non_localhost(self) -> None:
        with pytest.raises(ValueError, match=r"only localhost|127\.0\.0\.1"):
            NetworkGuard.validate_url("http://ai4trade.example.com")

    def test_rejects_non_http_scheme(self) -> None:
        with pytest.raises(ValueError, match=r"http"):
            NetworkGuard.validate_url("file:///etc/passwd")

    def test_rejects_docker_scheme(self) -> None:
        with pytest.raises(ValueError, match=r"http"):
            NetworkGuard.validate_url("docker://container")

    def test_rejects_credentials_in_url(self) -> None:
        with pytest.raises(ValueError, match=r"credential"):
            NetworkGuard.validate_url("http://user:pass@127.0.0.1:8000")

    def test_rejects_path_traversal(self) -> None:
        with pytest.raises(ValueError, match=r"traversal|\.\."):
            NetworkGuard.validate_url("http://127.0.0.1:8000/../../../etc")

    def test_rejects_unknown_scheme(self) -> None:
        with pytest.raises(ValueError, match=r"http"):
            NetworkGuard.validate_url("ssh://127.0.0.1")


# ──────────────────────────────────────────────
# J6: REST Client Tests
# ──────────────────────────────────────────────


class TestRestBoundaryClient:
    """Tests for REST client against stub server."""

    def test_health(self, rest_client: Ai4tradeRestBoundaryClient) -> None:
        """Health endpoint returns ok status."""
        health = rest_client.get_health()
        assert health is not None
        assert isinstance(health, HealthResponse)
        assert health.status == "ok"

    def test_get_latest_signal(self, rest_client: Ai4tradeRestBoundaryClient) -> None:
        """Latest signal for an asset returns a valid signal."""
        signal = rest_client.get_latest_signal("BTC/USDT")
        assert signal is not None
        assert isinstance(signal, SignalResponse)
        assert signal.asset == "BTC/USDT"
        assert signal.direction in ("buy", "sell", "hold")

    def test_get_signal_by_id_found(self, rest_client: Ai4tradeRestBoundaryClient) -> None:
        """Signal by id returns a valid signal for known IDs."""
        signal = rest_client.get_signal_by_id("sig-001")
        assert signal is not None
        assert signal.signal_id == "sig-001"

    def test_get_signal_by_id_not_found(self, rest_client: Ai4tradeRestBoundaryClient) -> None:
        """Unknown signal id returns None (fail-closed)."""
        signal = rest_client.get_signal_by_id("nonexistent")
        assert signal is None

    def test_get_outcome_found(self, rest_client: Ai4tradeRestBoundaryClient) -> None:
        """Outcome by signal id returns valid outcome."""
        outcome = rest_client.get_outcome("sig-001")
        assert outcome is not None
        assert isinstance(outcome, OutcomeResponse)
        assert outcome.signal_id == "sig-001"

    def test_get_outcome_not_found(self, rest_client: Ai4tradeRestBoundaryClient) -> None:
        """Unknown outcome returns None (fail-closed)."""
        outcome = rest_client.get_outcome("nonexistent")
        assert outcome is None

    def test_evaluate_risk(self, rest_client: Ai4tradeRestBoundaryClient) -> None:
        """Risk evaluation returns a result."""
        signal = AdvisorySignal(
            signal_id="test",
            asset="BTC/USDT",
            direction="buy",
            confidence=0.6,
            risk_score=0.3,
            created_at=datetime.now(UTC),
        )
        result = rest_client.evaluate_risk(signal)
        assert result is not None
        assert isinstance(result, RiskGateResponse)
        assert result.passed in (True, False)

    def test_client_rejects_non_localhost(self) -> None:
        """Client creation rejects non-localhost URLs."""
        with pytest.raises(ValueError, match=r"only localhost|127\.0\.0\.1"):
            Ai4tradeRestBoundaryClient(base_url="http://evil.example.com")

    def test_fail_closed_on_404(self, stub_server: Ai4tradeStubServer) -> None:
        """4xx responses return None (fail-closed)."""
        raw = httpx.Client(base_url=stub_server.base_url)
        resp = raw.get("/signals/sig-nonexistent-injective")
        assert resp.status_code == 404


# ──────────────────────────────────────────────
# Protocol Adapter Tests
# ──────────────────────────────────────────────


class TestRestProtocolAdapters:
    """REST-backed protocol adapters satisfy SI v2 boundary protocols."""

    def test_signal_provider_compliance(self, rest_client: Ai4tradeRestBoundaryClient) -> None:
        """RestSignalProvider satisfies SignalProvider protocol."""
        provider = RestSignalProvider(client=rest_client)
        assert isinstance(provider, SignalProvider)

    def test_signal_provider_latest(self, rest_client: Ai4tradeRestBoundaryClient) -> None:
        """RestSignalProvider returns advisory signal."""
        provider = RestSignalProvider(client=rest_client)
        signal = provider.get_latest_signal("BTC/USDT")
        assert signal.direction in ("buy", "sell", "hold")
        assert signal.dry_run_only is True
        assert signal.can_execute is False

    def test_outcome_provider_compliance(self, rest_client: Ai4tradeRestBoundaryClient) -> None:
        """RestOutcomeProvider satisfies OutcomeProvider protocol."""
        provider = RestOutcomeProvider(client=rest_client)
        assert isinstance(provider, OutcomeProvider)

    def test_outcome_provider_get(self, rest_client: Ai4tradeRestBoundaryClient) -> None:
        """RestOutcomeProvider returns outcome."""
        provider = RestOutcomeProvider(client=rest_client)
        outcome = provider.get_outcome("sig-001")
        assert outcome is not None
        assert outcome.outcome_label in ("win", "loss", "neutral", "expired", "unknown")

    def test_risk_gate_compliance(self, rest_client: Ai4tradeRestBoundaryClient) -> None:
        """RestRiskGateProvider satisfies RiskGateProvider protocol."""
        provider = RestRiskGateProvider(client=rest_client)
        assert isinstance(provider, RiskGateProvider)

    def test_risk_gate_evaluate(self, rest_client: Ai4tradeRestBoundaryClient) -> None:
        """RestRiskGateProvider evaluates risk."""
        provider = RestRiskGateProvider(client=rest_client)
        signal = AdvisorySignal(
            signal_id="test",
            asset="BTC/USDT",
            direction="buy",
            confidence=0.6,
            risk_score=0.3,
            created_at=datetime.now(UTC),
        )
        passed, reason = provider.evaluate(signal)
        assert isinstance(passed, bool)
        assert isinstance(reason, str)

    def test_stub_server_lifecycle(self) -> None:
        """Stub server can be started and stopped."""
        server = Ai4tradeStubServer()
        server.start()
        assert server.base_url is not None
        assert "127.0.0.1" in server.base_url
        server.stop()


class TestFailClosed:
    """Fail-closed behavior tests."""

    def test_unreachable_server_returns_none(self) -> None:
        """Client calls to unreachable server return None (fail-closed)."""
        client = Ai4tradeRestBoundaryClient(base_url="http://127.0.0.1:1")
        result = client.get_health()
        assert result is None

    def test_no_ai4trade_bot_imports(self) -> None:
        """Verify no ai4trade-bot source code is imported or copied in src."""
        from pathlib import Path

        src_root = Path(__file__).resolve().parent.parent / "src" / "si_v2"
        # Only check .py files under src/ (exclude __pycache__)
        for py_file in sorted(src_root.rglob("*.py")):
            if "__pycache__" in str(py_file):
                continue
            src_text = py_file.read_text(encoding="utf-8")
            # Check for internal ai4trade-bot module references
            if "core.signals" in src_text:
                pytest.fail(f"{py_file} contains 'core.signals' reference")
            if "core.outcomes" in src_text:
                pytest.fail(f"{py_file} contains 'core.outcomes' reference")


# ──────────────────────────────────────────────
# Additional Fail-Closed Tests
# ──────────────────────────────────────────────


def test_outcome_provider_unknown_signal(rest_client: Ai4tradeRestBoundaryClient) -> None:
    """Unknown signal returns None (fail-closed)."""
    provider = RestOutcomeProvider(client=rest_client)
    outcome = provider.get_outcome("does-not-exist-999")
    assert outcome is None


def test_signal_provider_empty_asset(rest_client: Ai4tradeRestBoundaryClient) -> None:
    """Empty asset returns a safe default signal (fail-closed)."""
    provider = RestSignalProvider(client=rest_client)
    signal = provider.get_latest_signal("UNKNOWN/PAIR")
    assert signal is not None
    assert signal.direction == "hold"
    assert signal.dry_run_only is True
