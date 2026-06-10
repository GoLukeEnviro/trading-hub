"""In-memory Protocol interfaces for ai4trade-bot integration boundary.

These Protocols define the edge between SI v2 and the upstream
ai4trade-bot signal intelligence layer. Only in-memory/discrete
implementations exist in Phase F — no REST clients, no code imports,
and no vendored code from the ai4trade-bot repository.

Phase H (future) will add REST API adapters that consume
ai4trade-bot's Rainbow API distribution endpoint.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field


class AdvisorySignal(BaseModel):
    """An advisory signal from the upstream intelligence layer.

    This is a simplified representation of ai4trade-bot's
    CanonicalSignalEnvelope, keeping only fields relevant to SI v2.
    """

    model_config = ConfigDict(strict=True)

    signal_id: str
    asset: str
    direction: str  # "buy", "sell", "hold"
    confidence: float = Field(ge=0.0, le=1.0)
    risk_score: float = Field(ge=0.0, le=1.0)
    source: str = ""
    reason: str = ""
    created_at: datetime
    dry_run_only: bool = Field(default=True)
    can_execute: bool = Field(default=False)


class SignalOutcome(BaseModel):
    """The outcome of a past signal — purely observational.

    Corresponds to ai4trade-bot's SignalOutcome model. SI v2 reads
    outcomes to evaluate signal quality over time.
    """

    model_config = ConfigDict(strict=True)

    signal_id: str
    asset: str
    direction: str
    outcome_label: str  # "win", "loss", "neutral", "expired", "unknown"
    outcome_score: float = Field(default=0.0, ge=-1.0, le=1.0)
    emitted_at: datetime
    evaluated_at: datetime
    entry_price: float | None = None
    outcome_price: float | None = None
    price_change_pct: float | None = None
    reason: str = ""


@runtime_checkable
class SignalProvider(Protocol):
    """Interface for receiving advisory signals from ai4trade-bot."""

    def get_latest_signal(self, asset: str) -> AdvisorySignal:
        """Return the most recent advisory signal for the given asset.

        Must never raise. Returns a HOLD-style default on any error.
        """
        ...

    def query_signals(
        self,
        asset: str,
        limit: int = 10,
        min_confidence: float = 0.0,
    ) -> Sequence[AdvisorySignal]:
        """Query recent advisory signals for analysis."""
        ...


@runtime_checkable
class OutcomeProvider(Protocol):
    """Interface for reading signal outcomes from ai4trade-bot."""

    def get_outcome(self, signal_id: str) -> SignalOutcome | None:
        """Return the outcome for a signal, or None if unknown."""
        ...

    def query_outcomes(
        self,
        asset: str,
        label: str | None = None,
        limit: int = 50,
    ) -> Sequence[SignalOutcome]:
        """Query outcomes for signal quality analysis."""
        ...


@runtime_checkable
class RiskGateProvider(Protocol):
    """Interface for evaluating risk on advisory signals.

    Wraps ai4trade-bot's RiskGate logic. SI v2 can consult this
    before accepting a signal's recommendation.
    """

    def evaluate(
        self,
        signal: AdvisorySignal,
    ) -> tuple[bool, str]:
        """Evaluate a signal against risk rules.

        Returns (passed: bool, reason: str).
        Must never raise.
        """
        ...


# Re-export models for convenience
__all__ = [
    "AdvisorySignal",
    "OutcomeProvider",
    "RiskGateProvider",
    "SignalOutcome",
    "SignalProvider",
]
