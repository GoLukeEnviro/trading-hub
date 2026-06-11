"""Typed Pydantic contracts for Automated Attribution Reports.

Defines the report request, structure, section, and warning models.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class ReportWarningType(StrEnum):
    """Enum of warning types that can appear in an attribution report."""

    LOW_SAMPLE = "LOW_SAMPLE"
    UNKNOWN_REGIME = "UNKNOWN_REGIME"
    NEGATIVE_EXPECTANCY = "NEGATIVE_EXPECTANCY"
    DRAWDOWN = "DRAWDOWN"
    UNSUFFICIENT_DATA = "UNSUFFICIENT_DATA"


class WarningSeverity(StrEnum):
    """Severity level for report warnings."""

    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class ReportWarning(BaseModel):
    """A single warning in an attribution report.

    Attributes:
        type: Classification of the warning.
        message: Human-readable warning description.
        severity: Severity level.
    """

    type: ReportWarningType
    message: str
    severity: WarningSeverity


class ReportSection(BaseModel):
    """A single section of an attribution report.

    Attributes:
        title: Section heading.
        content: Markdown-formatted section content.
        data: Structured dict for JSON serialization.
    """

    title: str
    content: str = Field(default="", description="Markdown-formatted section body")
    data: dict[str, object] = Field(
        default_factory=dict,
        description="Structured data for JSON output",
    )


class ReportRequest(BaseModel):
    """Input parameters for generating an attribution report.

    Attributes:
        source_regime_stats_db_path: Path to the source_regime_stats SQLite DB.
        period_start: Optional start of the reporting period (UTC, inclusive).
        period_end: Optional end of the reporting period (UTC, inclusive).
        generated_at: Explicit timestamp when the report is generated (UTC).
        min_sample_count: Minimum sample count required for ranking inclusion
            (default 5).
    """

    source_regime_stats_db_path: str
    period_start: datetime | None = None
    period_end: datetime | None = None
    generated_at: datetime
    min_sample_count: int = Field(default=5, ge=1)


class AttributionReport(BaseModel):
    """Complete attribution report output.

    Attributes:
        report_id: Deterministic report identifier.
        schema_version: Schema version string.
        source_fingerprint: Fingerprint of the source cache.
        period_start: Start of the reporting period (UTC).
        period_end: End of the reporting period (UTC).
        generated_at: Timestamp when the report was generated (UTC).
        sections: Ordered list of report sections.
        warnings: List of warnings generated during report building.
    """

    report_id: str
    schema_version: str = "1.0"
    source_fingerprint: str = ""
    period_start: datetime | None = None
    period_end: datetime | None = None
    generated_at: datetime
    sections: list[ReportSection] = Field(default_factory=list)
    warnings: list[ReportWarning] = Field(default_factory=list)
