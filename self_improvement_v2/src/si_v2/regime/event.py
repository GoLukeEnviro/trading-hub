"""Pydantic model for canonical regime detection events."""

from __future__ import annotations

import math
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from si_v2.regime.label import RegimeLabel


class RegimeEvent(BaseModel):
    """A canonical regime detection event (schema v1).

    Represents a single regime determination at a point in time,
    with confidence, source attribution, and versioning metadata.
    """

    model_config = ConfigDict(
        coerce_numbers_to_str=True,
        frozen=True,
    )

    schema_version: str = Field(
        default="1",
        description="Schema version string (integer string for easy comparison).",
    )
    regime: RegimeLabel = Field(
        ...,
        description="One of: BULLISH, BEARISH, NEUTRAL, UNKNOWN",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence score in [0.0, 1.0] inclusive.",
    )
    timeframe: str = Field(
        ...,
        min_length=1,
        description="Candlestick timeframe (e.g. 15m, 1h, 4h).",
    )
    data_source: str = Field(
        ...,
        min_length=1,
        description="Data provider identifier (e.g. bitget_futures, binance_spot).",
    )
    detected_at: datetime = Field(
        ...,
        description="ISO 8601 UTC timestamp of regime determination.",
    )
    model_version: str = Field(
        ...,
        description="Semver of the regime detection model.",
    )

    @field_validator("confidence")
    @classmethod
    def _reject_nan_inf(cls, v: float) -> float:
        """Reject NaN, +inf, and -inf confidence values."""
        if math.isnan(v) or math.isinf(v):
            raise ValueError(
                f"confidence must be a finite float in [0.0, 1.0]; got {v}"
            )
        return v

    @field_validator("detected_at")
    @classmethod
    def _ensure_utc(cls, v: datetime) -> datetime:
        """Ensure detected_at is timezone-aware and in UTC."""
        if v.tzinfo is None:
            raise ValueError(
                "detected_at must be timezone-aware; use timezone.utc"
            )
        return v

    # Serialization is deterministic by default in Pydantic v2.
    # Use json.dumps(event.model_dump(), sort_keys=True) for custom control.
