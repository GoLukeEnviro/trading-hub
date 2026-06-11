"""Adapter mapping legacy v1/lowercase regime labels to canonical RegimeLabel."""

from __future__ import annotations

from si_v2.regime.label import RegimeLabel

# v1 detector labels from intelligence/regime_detector.py
_V1_LABEL_MAP: dict[str, RegimeLabel] = {
    "strong_trend_up": RegimeLabel.BULLISH,
    "weak_trend_up": RegimeLabel.BULLISH,
    "strong_trend_down": RegimeLabel.BEARISH,
    "weak_trend_down": RegimeLabel.BEARISH,
    "ranging": RegimeLabel.NEUTRAL,
    "high_volatility": RegimeLabel.NEUTRAL,
    "choppy": RegimeLabel.NEUTRAL,
}

# Legacy fixture labels (lowercase, from #109 fixture pack)
_FIXTURE_LABEL_MAP: dict[str, RegimeLabel] = {
    "bullish": RegimeLabel.BULLISH,
    "bearish": RegimeLabel.BEARISH,
    "sideways": RegimeLabel.NEUTRAL,
    "volatile": RegimeLabel.NEUTRAL,
    "unknown": RegimeLabel.UNKNOWN,
}

# Combined mapping (fixture labels take precedence for overlap)
_LABEL_MAP: dict[str, RegimeLabel] = {}
_LABEL_MAP.update(_V1_LABEL_MAP)
_LABEL_MAP.update(_FIXTURE_LABEL_MAP)


class LegacyLabelAdapter:
    """Maps legacy label strings to canonical RegimeLabel values.

    Handles both v1 detector labels (7-value vocabulary) and
    the old fixture labels (5-value lowercase vocabulary).
    Unrecognized labels map to UNKNOWN.
    """

    @staticmethod
    def to_canonical(label: str) -> RegimeLabel:
        """Map a legacy label to its canonical RegimeLabel.

        Args:
            label: A legacy regime label string (v1 detector or fixture).

        Returns:
            The corresponding canonical RegimeLabel, or UNKNOWN if
            the label is not recognised.
        """
        normalized = label.strip().lower()
        return _LABEL_MAP.get(normalized, RegimeLabel.UNKNOWN)
