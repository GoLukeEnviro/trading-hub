"""Deterministic threshold-based regime detector."""

from __future__ import annotations

from datetime import UTC, datetime

from si_v2.regime.event import RegimeEvent
from si_v2.regime.label import RegimeLabel


class ThresholdRegimeDetector:
    """Deterministic regime detector using simple RSI thresholds.

    Same input always produces the same output. Falls back to UNKNOWN
    with confidence 0.0 when input is empty, malformed, or insufficient.
    """

    def __init__(
        self,
        rsi_bullish_threshold: float = 70.0,
        rsi_bearish_threshold: float = 30.0,
        model_version: str = "v1.0.0",
        data_source: str = "threshold_detector",
        schema_version: str = "1",
    ) -> None:
        """Initialize detector with configurable thresholds.

        Args:
            rsi_bullish_threshold: RSI value above which regime is BULLISH.
            rsi_bearish_threshold: RSI value below which regime is BEARISH.
            model_version: Semver string for the detection model.
            data_source: Identifier for this detector.
            schema_version: Schema version for produced events.
        """
        self._rsi_bullish = rsi_bullish_threshold
        self._rsi_bearish = rsi_bearish_threshold
        self._model_version = model_version
        self._data_source = data_source
        self._schema_version = schema_version

    def detect(self, observations: dict) -> RegimeEvent:
        """Detect market regime from a dictionary of observations.

        Args:
            observations: Dict with at minimum an 'rsi' key (float).
                          May also contain 'sma_ratio', 'volume_spike',
                          and other market indicators.

        Returns:
            A RegimeEvent with the detected regime label.

        Deterministic: identical input always produces identical output.
        """
        now = datetime.now(UTC)

        # Empty/malformed input → UNKNOWN
        if not isinstance(observations, dict) or "rsi" not in observations:
            return RegimeEvent(
                schema_version=self._schema_version,
                regime=RegimeLabel.UNKNOWN,
                confidence=0.0,
                timeframe="unknown",
                data_source=self._data_source,
                detected_at=now,
                model_version=self._model_version,
            )

        rsi_value = observations["rsi"]

        # Non-numeric RSI → UNKNOWN
        if not isinstance(rsi_value, (int, float)):
            return RegimeEvent(
                schema_version=self._schema_version,
                regime=RegimeLabel.UNKNOWN,
                confidence=0.0,
                timeframe="unknown",
                data_source=self._data_source,
                detected_at=now,
                model_version=self._model_version,
            )

        from math import isinf, isnan

        if isnan(rsi_value) or isinf(rsi_value):
            return RegimeEvent(
                schema_version=self._schema_version,
                regime=RegimeLabel.UNKNOWN,
                confidence=0.0,
                timeframe="unknown",
                data_source=self._data_source,
                detected_at=now,
                model_version=self._model_version,
            )

        if rsi_value > self._rsi_bullish:
            regime = RegimeLabel.BULLISH
            confidence = min(1.0, (rsi_value - self._rsi_bullish) / 30.0 + 0.7)
        elif rsi_value < self._rsi_bearish:
            regime = RegimeLabel.BEARISH
            confidence = min(1.0, (self._rsi_bearish - rsi_value) / 30.0 + 0.7)
        else:
            regime = RegimeLabel.NEUTRAL
            confidence = 0.5

        # Infer a reasonable timeframe from the observation context (best-effort)
        timeframe = str(observations.get("timeframe", "1h"))

        return RegimeEvent(
            schema_version=self._schema_version,
            regime=regime,
            confidence=round(confidence, 4),
            timeframe=timeframe,
            data_source=self._data_source,
            detected_at=now,
            model_version=self._model_version,
        )
