"""Automated Attribution Reports — deterministic, read-only performance summaries.

Generates Markdown and JSON reports from the source_regime_stats SQLite cache
with period filtering, sample-count awareness, and safety constraints.
"""

from __future__ import annotations

from .cli import build_parser, main
from .models import (
    AttributionReport,
    ReportRequest,
    ReportSection,
    ReportWarning,
)
from .renderers import JSONRenderer, MarkdownRenderer
from .report_builder import AttributionReportBuilder

__all__ = [
    "AttributionReport",
    "AttributionReportBuilder",
    "JSONRenderer",
    "MarkdownRenderer",
    "ReportRequest",
    "ReportSection",
    "ReportWarning",
    "build_parser",
    "main",
]
