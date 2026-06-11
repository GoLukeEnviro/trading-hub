"""Canonical regime labels for SI v2 regime detection."""

from __future__ import annotations

from enum import StrEnum


class RegimeLabel(StrEnum):
    """Canonical market regime labels per #55 spec.

    Four-value vocabulary used across all regime-detection components,
    Shadowlock enrichment, attribution, and signal routing.
    """

    BULLISH = "BULLISH"
    """Strong directional upward movement."""

    BEARISH = "BEARISH"
    """Strong directional downward movement."""

    NEUTRAL = "NEUTRAL"
    """No strong directional conviction; ranging or weak trend."""

    UNKNOWN = "UNKNOWN"
    """Insufficient data to determine regime."""
