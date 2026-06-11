"""Performance Attribution Engine — explain trade outcomes by signal source and regime."""

from __future__ import annotations

from .engine import DimensionGroupMetrics, PerformanceAttributionEngine
from .models import (
    AttributionFact,
    AttributionInput,
    AttributionResult,
    RegimeLabel,
    RejectionDiagnostic,
    SignalContribution,
)

__all__ = [
    "AttributionFact",
    "AttributionInput",
    "AttributionResult",
    "DimensionGroupMetrics",
    "PerformanceAttributionEngine",
    "RegimeLabel",
    "RejectionDiagnostic",
    "SignalContribution",
]
