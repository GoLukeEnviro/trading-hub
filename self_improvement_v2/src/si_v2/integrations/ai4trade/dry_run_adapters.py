"""Dry-run adapter implementations for the ai4trade-bot integration boundary.

In-memory only. No network calls, no imports from ai4trade-bot.
Designed for testing and forward-compatibility with real adapters.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import uuid4

from si_v2.integrations.ai4trade.protocols import (
    AdvisorySignal,
    SignalOutcome,
)


class InMemorySignalProvider:
    """In-memory implementation of SignalProvider.

    Stores signals in a dict. Returns advisory defaults when no
    signal exists for an asset. Never raises.
    """

    def __init__(self) -> None:
        self._signals: dict[str, list[AdvisorySignal]] = {}

    def add_signal(self, signal: AdvisorySignal) -> None:
        """Add a signal for testing."""
        self._signals.setdefault(signal.asset, []).append(signal)

    def get_latest_signal(self, asset: str) -> AdvisorySignal:
        """Return the most recent signal for the asset.

        Returns a neutral hold signal with baseline confidence
        if no signal exists.
        """
        signals = self._signals.get(asset)
        if signals:
            return signals[-1]
        return AdvisorySignal(
            signal_id=str(uuid4()),
            asset=asset,
            direction="hold",
            confidence=0.5,
            risk_score=0.0,
            reason="no signal from upstream",
            created_at=datetime.now(UTC),
        )

    def query_signals(
        self,
        asset: str,
        limit: int = 10,
        min_confidence: float = 0.0,
    ) -> Sequence[AdvisorySignal]:
        """Query recent signals for analysis."""
        signals = self._signals.get(asset, [])[-limit:]
        if min_confidence > 0.0:
            signals = [s for s in signals if s.confidence >= min_confidence]
        return signals


class InMemoryOutcomeProvider:
    """In-memory implementation of OutcomeProvider.

    Stores outcomes in a dict. Never raises.
    """

    def __init__(self) -> None:
        self._outcomes: dict[str, SignalOutcome] = {}

    def add_outcome(self, outcome: SignalOutcome) -> None:
        """Add an outcome for testing."""
        self._outcomes[outcome.signal_id] = outcome

    def get_outcome(self, signal_id: str) -> SignalOutcome | None:
        """Return the outcome for a signal."""
        return self._outcomes.get(signal_id)

    def query_outcomes(
        self,
        asset: str,
        label: str | None = None,
        limit: int = 50,
    ) -> Sequence[SignalOutcome]:
        """Query outcomes for signal quality analysis."""
        outcomes = [o for o in self._outcomes.values() if o.asset == asset]
        if label is not None:
            outcomes = [o for o in outcomes if o.outcome_label == label]
        return outcomes[-limit:]


class InMemoryRiskGateProvider:
    """In-memory implementation of RiskGateProvider.

    Evaluates a signal against simple risk rules.
    Configurable thresholds for testing.
    """

    def __init__(
        self,
        max_risk_score: float = 0.7,
        min_confidence: float = 0.3,
    ) -> None:
        self._max_risk_score = max_risk_score
        self._min_confidence = min_confidence

    def evaluate(self, signal: AdvisorySignal) -> tuple[bool, str]:
        """Evaluate a signal against risk rules.

        Rules:
        1. confidence >= min_confidence
        2. risk_score < max_risk_score
        3. dry_run_only must be True
        """
        if signal.confidence < self._min_confidence:
            return False, f"confidence {signal.confidence:.2f} below threshold {self._min_confidence}"
        if signal.risk_score >= self._max_risk_score:
            return False, f"risk_score {signal.risk_score:.2f} at or above threshold {self._max_risk_score}"
        if not signal.dry_run_only:
            return False, "signal is not dry_run_only"
        return True, "passed"


__all__ = [
    "InMemoryOutcomeProvider",
    "InMemoryRiskGateProvider",
    "InMemorySignalProvider",
]
