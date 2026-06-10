"""Typed models for controlled runtime-probe evidence."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RuntimeProbeCommandCategory(StrEnum):
    """Allowlisted runtime-probe command categories from the Phase M plan."""

    REPO_STATUS = "repo_status"
    CONTAINER_HEALTH = "container_health"
    DRY_RUN_STATUS = "dry_run_status"
    API_HEALTH = "api_health"
    LOG_SNIPPET = "log_snippet"


class RuntimeProbeSafetyVerdict(StrEnum):
    """Safety verdict for an individual runtime-probe evidence item."""

    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"


class RedactionSummaryLine(BaseModel):
    """Single sanitized line retained in an evidence summary."""

    model_config = ConfigDict(strict=True)

    text: str = Field(min_length=1)
    placeholders: list[str] = Field(default_factory=list)


class RedactionSummary(BaseModel):
    """Typed sanitized summary emitted after fail-closed redaction."""

    model_config = ConfigDict(strict=True)

    line_count: int = Field(ge=0)
    redaction_count: int = Field(ge=0)
    redaction_applied: bool
    placeholders: list[str] = Field(default_factory=list)
    lines: list[RedactionSummaryLine] = Field(default_factory=list)


class RuntimeProbeEvidence(BaseModel):
    """Sanitized runtime-probe evidence record.

    The model intentionally stores a typed sanitized summary instead of raw
    command output. Raw output storage remains opt-in and defaults to false.
    """

    model_config = ConfigDict(strict=True)

    timestamp_utc: datetime
    probe_id: str = Field(min_length=1, pattern=r"^[a-zA-Z0-9_.-]+$")
    target: str = Field(min_length=1)
    command_category: RuntimeProbeCommandCategory
    sanitized_output_summary: RedactionSummary
    raw_output_stored: bool = False
    redaction_applied: bool
    safety_verdict: RuntimeProbeSafetyVerdict
    abort_reason: str | None = None

    @model_validator(mode="after")
    def _validate_abort_reason(self) -> RuntimeProbeEvidence:
        if self.safety_verdict == RuntimeProbeSafetyVerdict.RED and self.abort_reason is None:
            msg = "abort_reason is required when safety_verdict is RED"
            raise ValueError(msg)
        if self.safety_verdict == RuntimeProbeSafetyVerdict.GREEN and self.abort_reason is not None:
            msg = "abort_reason must be omitted when safety_verdict is GREEN"
            raise ValueError(msg)
        if self.redaction_applied != self.sanitized_output_summary.redaction_applied:
            msg = "redaction_applied must match sanitized_output_summary.redaction_applied"
            raise ValueError(msg)
        return self
