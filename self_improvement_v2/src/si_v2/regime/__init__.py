"""Regime detection and shadowlock enrichment package."""

from __future__ import annotations

from si_v2.regime.detection_request import RegimeDetectionRequest
from si_v2.regime.detector import ThresholdRegimeDetector
from si_v2.regime.event import RegimeEvent
from si_v2.regime.label import RegimeLabel
from si_v2.regime.legacy_adapter import LegacyLabelAdapter
from si_v2.regime.shadowlock_enrichment import (
    DuplicateConflictError,
    ExtractRegimeFn,
    ShadowlockEnrichmentWriter,
)

__all__ = [
    "DuplicateConflictError",
    "ExtractRegimeFn",
    "LegacyLabelAdapter",
    "RegimeDetectionRequest",
    "RegimeEvent",
    "RegimeLabel",
    "ShadowlockEnrichmentWriter",
    "ThresholdRegimeDetector",
]
