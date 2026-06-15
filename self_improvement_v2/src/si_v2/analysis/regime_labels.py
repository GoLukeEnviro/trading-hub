"""Regime labels fixture adapter for SI v2.

Provides deterministic, offline regime labels for testing and development.
All labels are synthetic — no live market data or exchange calls.
"""

from __future__ import annotations

from enum import Enum


class RegimeLabel(str, Enum):
    """Canonical regime labels used in SI v2 analysis."""

    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"
    HIGH_VOLATILITY = "high_volatility"
    LOW_VOLATILITY = "low_volatility"
    TRENDING = "trending"
    RANGING = "ranging"
    UNKNOWN = "unknown"


# Synthetic regime fixture data: (timestamp, label) pairs per source
REGIME_FIXTURES: dict[str, list[tuple[str, str]]] = {
    "freqtrade-freqforge": [
        ("2026-06-01T00:00:00Z", "bullish"),
        ("2026-06-02T00:00:00Z", "bullish"),
        ("2026-06-03T00:00:00Z", "neutral"),
        ("2026-06-04T00:00:00Z", "bearish"),
        ("2026-06-05T00:00:00Z", "bearish"),
        ("2026-06-06T00:00:00Z", "neutral"),
        ("2026-06-07T00:00:00Z", "bullish"),
    ],
    "freqtrade-freqforge-canary": [
        ("2026-06-01T00:00:00Z", "neutral"),
        ("2026-06-02T00:00:00Z", "high_volatility"),
        ("2026-06-03T00:00:00Z", "high_volatility"),
        ("2026-06-04T00:00:00Z", "neutral"),
        ("2026-06-05T00:00:00Z", "low_volatility"),
    ],
    "freqtrade-regime-hybrid": [
        ("2026-06-01T00:00:00Z", "bullish"),
        ("2026-06-02T00:00:00Z", "trending"),
        ("2026-06-03T00:00:00Z", "trending"),
        ("2026-06-04T00:00:00Z", "ranging"),
        ("2026-06-05T00:00:00Z", "ranging"),
        ("2026-06-06T00:00:00Z", "bullish"),
    ],
    "freqai-rebel": [
        ("2026-06-01T00:00:00Z", "bearish"),
        ("2026-06-02T00:00:00Z", "bearish"),
        ("2026-06-03T00:00:00Z", "high_volatility"),
        ("2026-06-04T00:00:00Z", "bearish"),
    ],
}


def get_regime_label(source_id: str, timestamp: str | None = None) -> str:
    """Get the regime label for a source, optionally at a specific timestamp.

    Args:
        source_id: Bot identifier (e.g. 'freqtrade-freqforge').
        timestamp: ISO-8601 timestamp string. If None, returns the latest label.

    Returns:
        Regime label string (one of RegimeLabel values) or 'unknown' if no data.
    """
    series = REGIME_FIXTURES.get(source_id)
    if not series:
        return RegimeLabel.UNKNOWN.value

    if timestamp is None:
        return series[-1][1]

    for ts, label in reversed(series):
        if ts <= timestamp:
            return label

    return series[0][1]


def get_fixture_summary() -> dict[str, object]:
    """Return a summary of all regime fixtures."""
    return {
        "total_sources": len(REGIME_FIXTURES),
        "total_entries": sum(len(v) for v in REGIME_FIXTURES.values()),
        "sources": {
            src: {
                "count": len(series),
                "labels": list(dict.fromkeys(label for _, label in series)),
            }
            for src, series in REGIME_FIXTURES.items()
        },
    }
