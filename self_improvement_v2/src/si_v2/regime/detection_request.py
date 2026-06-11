"""Typed regime detection request model."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class RegimeDetectionRequest(BaseModel):
    """A typed detection request containing market observations and metadata.

    This replaces bare dicts passed to the detector. All fields are validated
    at construction time, ensuring that downstream detection is deterministic
    with no implicit wall-clock or environment-dependent state.
    """

    observations: dict[str, object] = Field(
        default_factory=dict,
        description="Market observations such as RSI, SMA ratio, volume spike.",
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
    # Optional provenance fields
    request_id: str | None = Field(
        default=None,
        description="Optional unique identifier for this detection request.",
    )
    trace_id: str | None = Field(
        default=None,
        description="Optional trace identifier for distributed tracing.",
    )

    @field_validator("timeframe")
    @classmethod
    def _timeframe_non_empty(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("timeframe must be a non-empty string")
        return stripped

    @field_validator("data_source")
    @classmethod
    def _data_source_non_empty(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("data_source must be a non-empty string")
        return stripped

    @field_validator("detected_at")
    @classmethod
    def _ensure_utc(cls, v: datetime) -> datetime:
        """Ensure detected_at is timezone-aware and in UTC (zero offset)."""
        if v.tzinfo is None:
            raise ValueError(
                "detected_at must be timezone-aware; use timezone.utc"
            )
        offset = v.utcoffset()
        if offset is None or offset.total_seconds() != 0:
            raise ValueError(
                f"detected_at must have zero UTC offset; got offset={offset}"
            )
        return v

    @field_validator("observations")
    @classmethod
    def _observations_is_dict(cls, v: object) -> dict[str, object]:
        if not isinstance(v, dict):
            raise ValueError("observations must be a dict")
        return v
