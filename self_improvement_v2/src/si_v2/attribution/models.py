"""Typed Pydantic contracts for the Performance Attribution Engine.

Defines input, fact, and result models used by the attribution pipeline.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator


class RegimeLabel(StrEnum):
    """Market regime classification labels."""

    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"
    UNKNOWN = "unknown"


class SignalContribution(BaseModel):
    """A single signal source's contribution to a trade decision.

    Attributes:
        source_id: Unique identifier for the signal source (non-empty).
        contribution_weight: Fractional weight of this source's influence
            in the decision (0 < w <= 1).
        source_confidence: Optional confidence of the source signal (0-1).
        model_or_strategy_id: Optional identifier for the specific model
            or strategy that generated the signal.
    """

    source_id: str = Field(..., min_length=1, description="Non-empty signal source identifier")
    contribution_weight: float = Field(
        ...,
        gt=0,
        le=1.0,
        description="Weight of this source's contribution (0 < w <= 1)",
    )
    source_confidence: float | None = Field(
        None,
        ge=0,
        le=1.0,
        description="Optional confidence of the source signal (0-1)",
    )
    model_or_strategy_id: str | None = Field(
        None,
        description="Optional model or strategy identifier",
    )


class AttributionInput(BaseModel):
    """Input record for trade attribution processing.

    Attributes:
        trade_id: Unique trade identifier.
        source_event_id: Identifier for the source event that triggered the trade.
        pair: Trading pair symbol (e.g. BTC/USDT).
        timeframe: Candle timeframe (e.g. 1h, 4h, 1d).
        closed_at: UTC timestamp of trade closure.
        realized_return: Realized return of the trade (finite float, documented precision).
        regime: Market regime at the time of trade.
        regime_confidence: Confidence in the regime classification (0-1).
        signal_contributions: Non-empty list of signal contributions whose weights sum to 1.0.
    """

    trade_id: str
    source_event_id: str
    pair: str
    timeframe: str
    closed_at: datetime
    realized_return: float = Field(
        ...,
        description="Realized return (finite float, typically 4-6 decimal places)",
    )
    regime: RegimeLabel
    regime_confidence: float = Field(..., ge=0, le=1.0)
    signal_contributions: list[SignalContribution] = Field(
        ...,
        min_length=1,
        description="Non-empty list of signal contributions summing to 1.0",
    )

    @field_validator("realized_return")
    @classmethod
    def _validate_realized_return(cls, v: float) -> float:
        """Ensure the return is finite."""
        import math

        if not math.isfinite(v):
            msg = f"realized_return must be finite, got {v}"
            raise ValueError(msg)
        return v

    @field_validator("signal_contributions")
    @classmethod
    def _validate_weight_sum(cls, v: list[SignalContribution]) -> list[SignalContribution]:
        """Ensure contribution weights sum to 1.0 within tolerance."""
        if not v:
            msg = "signal_contributions must be non-empty"
            raise ValueError(msg)
        total = sum(c.contribution_weight for c in v)
        if abs(total - 1.0) > 1e-9:
            msg = f"signal_contribution weights must sum to 1.0, got {total}"
            raise ValueError(msg)
        return v


class AttributionFact(BaseModel):
    """A single attributed fact derived from a trade and signal source.

    Attributes:
        fact_id: Deterministic hash from trade_id + source_id + regime.
        trade_id: Original trade identifier.
        source_id: Signal source identifier.
        strategy_or_model_id: Strategy or model identifier.
        pair: Trading pair.
        timeframe: Candle timeframe.
        regime: Market regime.
        confidence_bucket: Bucket label from regime_confidence*100:
            "0-25", "25-50", "50-75", or "75-100".
        weighted_return: Contribution-weighted portion of raw return.
        raw_trade_return: Full realized return of the trade.
        contribution_weight: Weight of this source's contribution.
        outcome_classification: WIN (positive return), LOSS (negative return),
            or BREAKEVEN (zero return).
        closed_at: UTC closure timestamp.
        provenance_hash: Hash of the provenance chain.
        schema_version: Schema version string.
    """

    fact_id: str
    trade_id: str
    source_id: str
    strategy_or_model_id: str | None
    pair: str
    timeframe: str
    regime: RegimeLabel
    confidence_bucket: str
    weighted_return: float
    raw_trade_return: float
    contribution_weight: float
    outcome_classification: str
    closed_at: datetime
    provenance_hash: str
    schema_version: str = "1.0"

    @classmethod
    def compute_fact_id(cls, trade_id: str, source_id: str, regime: RegimeLabel | str) -> str:
        """Compute a deterministic fact ID from trade_id + source_id + regime."""
        raw = f"{trade_id}:{source_id}:{regime}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @classmethod
    def compute_provenance_hash(cls, trade_id: str, source_event_id: str) -> str:
        """Compute a deterministic provenance hash."""
        raw = f"{trade_id}:{source_event_id}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _classify_outcome(realized_return: float) -> str:
        """Classify a trade return as WIN, LOSS, or BREAKEVEN."""
        if realized_return > 0:
            return "WIN"
        if realized_return < 0:
            return "LOSS"
        return "BREAKEVEN"

    @staticmethod
    def _confidence_bucket(regime_confidence: float) -> str:
        """Map regime_confidence to a bucket label."""
        pct = regime_confidence * 100
        if pct < 25:
            return "0-25"
        if pct < 50:
            return "25-50"
        if pct < 75:
            return "50-75"
        return "75-100"


class RejectionDiagnostic(BaseModel):
    """Structured diagnostic for a rejected input entry."""

    trade_id: str
    reason: str
    detail: str | None = None


class AttributionResult(BaseModel):
    """Result of processing attribution inputs through the engine.

    Attributes:
        facts: List of accepted attribution facts.
        accepted_count: Number of accepted input entries.
        rejected_count: Number of rejected input entries.
        rejection_diagnostics: Structured diagnostics for each rejection.
        input_fingerprint: Fingerprint of the input (hash of all entries).
        schema_version: Schema version string.
    """

    facts: list[AttributionFact]
    accepted_count: int
    rejected_count: int
    rejection_diagnostics: list[RejectionDiagnostic]
    input_fingerprint: str
    schema_version: str = "1.0"
