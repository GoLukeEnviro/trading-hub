"""Pydantic models for the ai4trade REST API boundary.

These DTOs represent the REST contract that a future ai4trade-bot
Rainbow API server would serve. They are owned by SI v2 and do not
import from ai4trade-bot. Mapping methods convert between these DTOs
and the existing SI v2 boundary models in protocols.py.

Phase J: stub server only — no production REST calls.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from si_v2.integrations.ai4trade.protocols import AdvisorySignal, SignalOutcome


class SignalResponse(BaseModel):
    """REST API response model for a signal."""

    model_config = ConfigDict(coerce_numbers_to_str=True)

    asset: str
    signal_id: str
    direction: str  # "buy", "sell", "hold"
    confidence: float = Field(ge=0.0, le=1.0)
    risk_score: float = Field(ge=0.0, le=1.0)
    source: str = ""
    reason: str = ""
    created_at: datetime
    dry_run_only: bool = True
    can_execute: bool = False

    def to_advisory_signal(self) -> AdvisorySignal:
        """Convert to the SI v2 boundary model."""
        return AdvisorySignal(
            signal_id=self.signal_id,
            asset=self.asset,
            direction=self.direction,
            confidence=self.confidence,
            risk_score=self.risk_score,
            source=self.source,
            reason=self.reason,
            created_at=self.created_at,
            dry_run_only=self.dry_run_only,
            can_execute=self.can_execute,
        )

    @classmethod
    def from_advisory_signal(cls, signal: AdvisorySignal) -> SignalResponse:
        """Convert from the SI v2 boundary model."""
        return cls(
            signal_id=signal.signal_id,
            asset=signal.asset,
            direction=signal.direction,
            confidence=signal.confidence,
            risk_score=signal.risk_score,
            source=signal.source,
            reason=signal.reason,
            created_at=signal.created_at,
            dry_run_only=signal.dry_run_only,
            can_execute=signal.can_execute,
        )


class OutcomeResponse(BaseModel):
    """REST API response model for a signal outcome."""

    model_config = ConfigDict(coerce_numbers_to_str=True)

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

    def to_signal_outcome(self) -> SignalOutcome:
        """Convert to the SI v2 boundary model."""
        return SignalOutcome(
            signal_id=self.signal_id,
            asset=self.asset,
            direction=self.direction,
            outcome_label=self.outcome_label,
            outcome_score=self.outcome_score,
            emitted_at=self.emitted_at,
            evaluated_at=self.evaluated_at,
            entry_price=self.entry_price,
            outcome_price=self.outcome_price,
            price_change_pct=self.price_change_pct,
            reason=self.reason,
        )

    @classmethod
    def from_signal_outcome(cls, outcome: SignalOutcome) -> OutcomeResponse:
        """Convert from the SI v2 boundary model."""
        return cls(
            signal_id=outcome.signal_id,
            asset=outcome.asset,
            direction=outcome.direction,
            outcome_label=outcome.outcome_label,
            outcome_score=outcome.outcome_score,
            emitted_at=outcome.emitted_at,
            evaluated_at=outcome.evaluated_at,
            entry_price=outcome.entry_price,
            outcome_price=outcome.outcome_price,
            price_change_pct=outcome.price_change_pct,
            reason=outcome.reason,
        )


class RiskGateRequest(BaseModel):
    """REST API request model for risk evaluation."""

    model_config = ConfigDict(strict=True)

    signal: AdvisorySignal


class RiskGateResponse(BaseModel):
    """REST API response model for risk evaluation."""

    model_config = ConfigDict(strict=True)

    passed: bool
    reason: str


class HealthResponse(BaseModel):
    """REST API response model for health check."""

    model_config = ConfigDict(coerce_numbers_to_str=True)

    status: str
    version: str
    signal_count: int


class ApiErrorResponse(BaseModel):
    """REST API response model for errors."""

    model_config = ConfigDict(strict=True)

    error: str
    detail: str | None = None


__all__ = [
    "ApiErrorResponse",
    "HealthResponse",
    "OutcomeResponse",
    "RiskGateRequest",
    "RiskGateResponse",
    "SignalResponse",
]
