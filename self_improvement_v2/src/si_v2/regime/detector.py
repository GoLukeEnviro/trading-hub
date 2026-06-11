"""Deterministic threshold-based regime detector."""

from __future__ import annotations

import math

from pydantic import BaseModel, Field, field_validator

from si_v2.regime.detection_request import RegimeDetectionRequest
from si_v2.regime.event import RegimeEvent
from si_v2.regime.label import RegimeLabel


class ThresholdRegimeDetector(BaseModel):
    """Deterministic regime detector using simple RSI thresholds.

    Same input always produces the same output. Falls back to UNKNOWN
    with confidence 0.0 when input is empty, malformed, or insufficient.

    Configuration is validated at construction time:
      - rsi_bullish_threshold: finite, in (0, 100)
      - rsi_bearish_threshold: finite, in (0, 100)
      - bearish threshold < bullish threshold
    """

    rsi_bullish_threshold: float = Field(
        default=70.0,
        ge=0.0,
        le=100.0,
        description="RSI value above which regime is BULLISH.",
    )
    rsi_bearish_threshold: float = Field(
        default=30.0,
        ge=0.0,
        le=100.0,
        description="RSI value below which regime is BEARISH.",
    )
    model_version: str = Field(
        default="v1.0.0",
        description="Semver string for the detection model.",
    )
    data_source: str = Field(
        default="threshold_detector",
        description="Identifier for this detector.",
    )
    schema_version: str = Field(
        default="1",
        description="Schema version for produced events.",
    )

    @field_validator("rsi_bullish_threshold", "rsi_bearish_threshold")
    @classmethod
    def _reject_nan_inf(cls, v: float) -> float:
        """Reject NaN, +inf, and -inf threshold values."""
        if math.isnan(v) or math.isinf(v):
            raise ValueError(
                f"RSI threshold must be a finite float in [0, 100]; got {v}"
            )
        return v

    @field_validator("rsi_bullish_threshold")
    @classmethod
    def _validate_bullish_threshold(cls, v: float) -> float:
        if not (0.0 <= v <= 100.0):
            raise ValueError(
                f"rsi_bullish_threshold must be in [0, 100]; got {v}"
            )
        return v

    @field_validator("rsi_bearish_threshold")
    @classmethod
    def _validate_bearish_threshold(cls, v: float) -> float:
        if not (0.0 <= v <= 100.0):
            raise ValueError(
                f"rsi_bearish_threshold must be in [0, 100]; got {v}"
            )
        return v

    def _validate_threshold_order(self) -> None:
        """Validate that bearish < bullish after both are set."""
        if self.rsi_bearish_threshold >= self.rsi_bullish_threshold:
            raise ValueError(
                f"rsi_bearish_threshold ({self.rsi_bearish_threshold}) must be "
                f"strictly less than rsi_bullish_threshold "
                f"({self.rsi_bullish_threshold})"
            )

    def __init__(self, **data) -> None:
        super().__init__(**data)
        self._validate_threshold_order()

    def detect(self, request: RegimeDetectionRequest) -> RegimeEvent:
        """Detect market regime from a typed detection request.

        Args:
            request: A RegimeDetectionRequest with observations and metadata.

        Returns:
            A RegimeEvent with the detected regime label.

        Deterministic: identical request always produces identical output.
        """
        observations = request.observations

        # Empty/malformed input → UNKNOWN
        if not observations or "rsi" not in observations:
            return RegimeEvent(
                schema_version=self.schema_version,
                regime=RegimeLabel.UNKNOWN,
                confidence=0.0,
                timeframe=request.timeframe,
                data_source=request.data_source,
                detected_at=request.detected_at,
                model_version=self.model_version,
            )

        rsi_value = observations["rsi"]

        # H5: Reject bool explicitly (bool is subclass of int)
        if isinstance(rsi_value, bool):
            return RegimeEvent(
                schema_version=self.schema_version,
                regime=RegimeLabel.UNKNOWN,
                confidence=0.0,
                timeframe=request.timeframe,
                data_source=request.data_source,
                detected_at=request.detected_at,
                model_version=self.model_version,
            )

        # Non-numeric RSI → UNKNOWN
        if not isinstance(rsi_value, (int, float)):
            return RegimeEvent(
                schema_version=self.schema_version,
                regime=RegimeLabel.UNKNOWN,
                confidence=0.0,
                timeframe=request.timeframe,
                data_source=request.data_source,
                detected_at=request.detected_at,
                model_version=self.model_version,
            )

        if math.isnan(rsi_value) or math.isinf(rsi_value):
            return RegimeEvent(
                schema_version=self.schema_version,
                regime=RegimeLabel.UNKNOWN,
                confidence=0.0,
                timeframe=request.timeframe,
                data_source=request.data_source,
                detected_at=request.detected_at,
                model_version=self.model_version,
            )

        # H5: Reject values outside 0-100
        if rsi_value < 0.0 or rsi_value > 100.0:
            return RegimeEvent(
                schema_version=self.schema_version,
                regime=RegimeLabel.UNKNOWN,
                confidence=0.0,
                timeframe=request.timeframe,
                data_source=request.data_source,
                detected_at=request.detected_at,
                model_version=self.model_version,
            )

        if rsi_value > self.rsi_bullish_threshold:
            regime = RegimeLabel.BULLISH
            confidence = min(1.0, (rsi_value - self.rsi_bullish_threshold) / 30.0 + 0.7)
        elif rsi_value < self.rsi_bearish_threshold:
            regime = RegimeLabel.BEARISH
            confidence = min(1.0, (self.rsi_bearish_threshold - rsi_value) / 30.0 + 0.7)
        else:
            regime = RegimeLabel.NEUTRAL
            confidence = 0.5

        return RegimeEvent(
            schema_version=self.schema_version,
            regime=regime,
            confidence=round(confidence, 4),
            timeframe=request.timeframe,
            data_source=request.data_source,
            detected_at=request.detected_at,
            model_version=self.model_version,
        )
