"""REST-backed protocol adapters for the ai4trade integration boundary.

These adapters implement the SI v2 protocols (SignalProvider, OutcomeProvider,
RiskGateProvider) using the Ai4tradeRestBoundaryClient to make HTTP calls
to a hypothetical ai4trade-bot Rainbow API server.

All adapters are fail-closed: network errors or unexpected responses return
safe defaults (HOLD signal, None outcome, False with reason).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import uuid4

from si_v2.integrations.ai4trade.protocols import (
    AdvisorySignal,
    SignalOutcome,
)
from si_v2.integrations.ai4trade.rest_boundary import Ai4tradeRestBoundaryClient


class RestSignalProvider:
    """REST-backed SignalProvider using Ai4tradeRestBoundaryClient.

    Fail-closed: returns HOLD-style default signal on any error.
    """

    def __init__(self, client: Ai4tradeRestBoundaryClient) -> None:
        self._client = client

    def get_latest_signal(self, asset: str) -> AdvisorySignal:
        """Fetch the latest advisory signal for the given asset.

        Returns a HOLD-style default on any error.
        """
        sig = self._client.get_latest_signal(asset)
        if sig is None:
            return self._default_signal(asset)
        return sig.to_advisory_signal()

    def query_signals(
        self,
        asset: str,
        limit: int = 10,
        min_confidence: float = 0.0,
    ) -> Sequence[AdvisorySignal]:
        """Query recent signals for analysis.

        Returns empty list on error. Uses latest signal as single result
        since the stub server currently only supports per-asset latest.
        """
        sig = self._client.get_latest_signal(asset)
        if sig is None:
            return []
        signals = [sig.to_advisory_signal()]
        if min_confidence > 0.0:
            signals = [s for s in signals if s.confidence >= min_confidence]
        return signals[:limit]

    @staticmethod
    def _default_signal(asset: str) -> AdvisorySignal:
        """Return a safe default HOLD signal."""
        return AdvisorySignal(
            signal_id=str(uuid4()),
            asset=asset,
            direction="hold",
            confidence=0.5,
            risk_score=0.0,
            reason="no signal from upstream (REST unavailable)",
            created_at=datetime.now(UTC),
        )


class RestOutcomeProvider:
    """REST-backed OutcomeProvider using Ai4tradeRestBoundaryClient.

    Fail-closed: returns None on any error.
    """

    def __init__(self, client: Ai4tradeRestBoundaryClient) -> None:
        self._client = client

    def get_outcome(self, signal_id: str) -> SignalOutcome | None:
        """Fetch the outcome for a signal.

        Returns None on any error.
        """
        outcome = self._client.get_outcome(signal_id)
        if outcome is None:
            return None
        return outcome.to_signal_outcome()

    def query_outcomes(
        self,
        asset: str,
        label: str | None = None,
        limit: int = 50,
    ) -> Sequence[SignalOutcome]:
        """Query outcomes for signal quality analysis.

        Returns empty list on error. Note: the REST API does not currently
        support bulk outcome queries by asset; this implementation returns
        an empty sequence. Future phases may add a dedicated endpoint.
        """
        return []


class RestRiskGateProvider:
    """REST-backed RiskGateProvider using Ai4tradeRestBoundaryClient.

    Fail-closed: returns (False, reason) on any error.
    """

    def __init__(self, client: Ai4tradeRestBoundaryClient) -> None:
        self._client = client

    def evaluate(self, signal: AdvisorySignal) -> tuple[bool, str]:
        """Evaluate a signal against risk rules via REST.

        Returns (False, reason) on any error.
        """
        result = self._client.evaluate_risk(signal)
        if result is None:
            return False, "REST risk gate unavailable"
        return result.passed, result.reason


__all__ = [
    "RestOutcomeProvider",
    "RestRiskGateProvider",
    "RestSignalProvider",
]
