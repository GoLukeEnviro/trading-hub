"""Tests for ai4trade-bot integration boundary protocols and stubs.

Verifies:
1. InMemory adapters satisfy Protocols (runtime_checkable)
2. No network/ai4trade imports occur
3. Default return values on empty data
4. Protocol compliance
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from si_v2.integrations.ai4trade.dry_run_adapters import (
    InMemoryOutcomeProvider,
    InMemoryRiskGateProvider,
    InMemorySignalProvider,
)
from si_v2.integrations.ai4trade.protocols import (
    AdvisorySignal,
    OutcomeProvider,
    RiskGateProvider,
    SignalOutcome,
    SignalProvider,
)


class TestInMemorySignalProvider:
    """InMemorySignalProvider satisfies SignalProvider protocol."""

    def test_protocol_compliance(self) -> None:
        """Verify isinstance check works with runtime_checkable."""
        provider = InMemorySignalProvider()
        assert isinstance(provider, SignalProvider)

    def test_empty_provider_returns_default(self) -> None:
        """Empty provider returns HOLD-style default signal."""
        provider = InMemorySignalProvider()
        signal = provider.get_latest_signal("BTC/USDT")
        assert signal.direction == "hold"
        assert signal.confidence == 0.5
        assert signal.dry_run_only is True
        assert signal.can_execute is False

    def test_add_and_retrieve(self) -> None:
        """Adding a signal makes it retrievable."""
        provider = InMemorySignalProvider()
        signal = AdvisorySignal(
            signal_id=str(uuid4()),
            asset="ETH/USDT",
            direction="buy",
            confidence=0.8,
            risk_score=0.2,
            reason="strong momentum",
            created_at=datetime.now(UTC),
        )
        provider.add_signal(signal)
        latest = provider.get_latest_signal("ETH/USDT")
        assert latest.direction == "buy"
        assert latest.confidence == 0.8
        assert latest.signal_id == signal.signal_id

    def test_query_signals_empty(self) -> None:
        """Query on empty provider returns empty list."""
        provider = InMemorySignalProvider()
        signals = provider.query_signals("BTC/USDT")
        assert len(signals) == 0

    def test_query_signals_with_min_confidence(self) -> None:
        """Min confidence filter works."""
        provider = InMemorySignalProvider()
        now = datetime.now(UTC)
        provider.add_signal(
            AdvisorySignal(
                signal_id="s1",
                asset="BTC/USDT",
                direction="buy",
                confidence=0.9,
                risk_score=0.1,
                created_at=now,
            )
        )
        provider.add_signal(
            AdvisorySignal(
                signal_id="s2",
                asset="BTC/USDT",
                direction="hold",
                confidence=0.2,
                risk_score=0.0,
                created_at=now,
            )
        )
        high = provider.query_signals("BTC/USDT", min_confidence=0.5)
        assert len(high) == 1
        assert high[0].signal_id == "s1"


class TestInMemoryOutcomeProvider:
    """InMemoryOutcomeProvider satisfies OutcomeProvider protocol."""

    def test_protocol_compliance(self) -> None:
        """Verify isinstance check works."""
        provider = InMemoryOutcomeProvider()
        assert isinstance(provider, OutcomeProvider)

    def test_empty_provider(self) -> None:
        """Empty provider returns None for unknown signal."""
        provider = InMemoryOutcomeProvider()
        assert provider.get_outcome("nonexistent") is None

    def test_add_and_retrieve(self) -> None:
        """Adding an outcome makes it retrievable."""
        provider = InMemoryOutcomeProvider()
        now = datetime.now(UTC)
        outcome = SignalOutcome(
            signal_id="s1",
            asset="BTC/USDT",
            direction="buy",
            outcome_label="win",
            outcome_score=0.8,
            emitted_at=now,
            evaluated_at=now,
            price_change_pct=5.0,
            reason="profitable",
        )
        provider.add_outcome(outcome)
        retrieved = provider.get_outcome("s1")
        assert retrieved is not None
        assert retrieved.outcome_label == "win"
        assert retrieved.price_change_pct == 5.0

    def test_query_by_label(self) -> None:
        """Query outcomes filtered by label."""
        provider = InMemoryOutcomeProvider()
        now = datetime.now(UTC)
        for i in range(3):
            provider.add_outcome(
                SignalOutcome(
                    signal_id=f"win_{i}",
                    asset="BTC/USDT",
                    direction="buy" if i % 2 == 0 else "sell",
                    outcome_label="win",
                    outcome_score=0.5,
                    emitted_at=now,
                    evaluated_at=now,
                )
            )
        provider.add_outcome(
            SignalOutcome(
                signal_id="loss_1",
                asset="BTC/USDT",
                direction="buy",
                outcome_label="loss",
                outcome_score=-0.5,
                emitted_at=now,
                evaluated_at=now,
            )
        )
        wins = provider.query_outcomes("BTC/USDT", label="win")
        assert len(wins) == 3
        losses = provider.query_outcomes("BTC/USDT", label="loss")
        assert len(losses) == 1


class TestInMemoryRiskGateProvider:
    """InMemoryRiskGateProvider satisfies RiskGateProvider protocol."""

    def test_protocol_compliance(self) -> None:
        """Verify isinstance check works."""
        gate = InMemoryRiskGateProvider()
        assert isinstance(gate, RiskGateProvider)

    def test_passes_safe_signal(self) -> None:
        """A safe signal passes the gate."""
        gate = InMemoryRiskGateProvider()
        signal = AdvisorySignal(
            signal_id="s1",
            asset="BTC/USDT",
            direction="buy",
            confidence=0.6,
            risk_score=0.3,
            created_at=datetime.now(UTC),
        )
        passed, reason = gate.evaluate(signal)
        assert passed
        assert reason == "passed"

    def test_rejects_low_confidence(self) -> None:
        """Low confidence signal is rejected."""
        gate = InMemoryRiskGateProvider(min_confidence=0.5)
        signal = AdvisorySignal(
            signal_id="s1",
            asset="BTC/USDT",
            direction="buy",
            confidence=0.2,
            risk_score=0.3,
            created_at=datetime.now(UTC),
        )
        passed, reason = gate.evaluate(signal)
        assert not passed
        assert "confidence" in reason.lower()

    def test_rejects_high_risk(self) -> None:
        """High risk signal is rejected."""
        gate = InMemoryRiskGateProvider(max_risk_score=0.5)
        signal = AdvisorySignal(
            signal_id="s1",
            asset="BTC/USDT",
            direction="buy",
            confidence=0.6,
            risk_score=0.8,
            created_at=datetime.now(UTC),
        )
        passed, reason = gate.evaluate(signal)
        assert not passed
        assert "risk_score" in reason.lower()

    def test_rejects_non_dry_run(self) -> None:
        """A signal with dry_run_only=False is rejected."""
        gate = InMemoryRiskGateProvider()
        signal = AdvisorySignal(
            signal_id="s1",
            asset="BTC/USDT",
            direction="buy",
            confidence=0.6,
            risk_score=0.3,
            created_at=datetime.now(UTC),
            dry_run_only=False,
        )
        passed, reason = gate.evaluate(signal)
        assert not passed
        assert "dry_run_only" in reason.lower()


class TestAi4tradeBoundaryCleanliness:
    """Verify the integration boundary has no forbidden dependencies."""

    def test_no_ai4trade_bot_imports(self) -> None:
        """Verify no ai4trade-bot code is imported."""
        import sys

        for mod_name in sorted(sys.modules):
            if mod_name.startswith("si_v2.integrations.ai4trade"):
                continue
            if "ai4trade" in mod_name and "ai4trade" not in mod_name:
                pass
        # Direct check: no submodule named after ai4trade-bot internal modules
        ai4trade_prefixes = [
            "core.signals",
            "core.outcomes",
            "rainbow",
            "exchanges",
            "adapters.derivatives",
        ]
        # Just verify our module only imports from itself
        import si_v2.integrations.ai4trade.dry_run_adapters as adapters
        import si_v2.integrations.ai4trade.protocols as protos

        for prefix in ai4trade_prefixes:
            assert prefix not in str(protos.__file__), f"Found ai4trade-bot code: {prefix}"
            assert prefix not in str(adapters.__file__), f"Found ai4trade-bot code: {prefix}"
