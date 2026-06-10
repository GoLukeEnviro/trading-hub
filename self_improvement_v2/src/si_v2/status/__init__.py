"""Status report models for SI v2 pipeline state.

Defines the typed data model for the SI v2 status report, covering
phase progress, safety state, blockers, test baseline, and config state.
No runtime access — reads only local files and static state.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class PhaseStage(StrEnum):
    """SI v2 phase stage classification."""

    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BLOCKED = "blocked"


class SafetyComponentStatus(StrEnum):
    """Safety component readiness status."""

    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"
    NOT_DEPLOYED = "not_deployed"
    NOT_DEFINED = "not_defined"


class PhaseEntry(BaseModel):
    """Single phase entry in the status report."""

    model_config = ConfigDict(strict=True)

    name: str = Field(description="Phase name (e.g. 'Phase 0 — Stabilization')")
    stage: PhaseStage = Field(description="Current stage of this phase")
    tracker_issue: str | None = Field(
        default=None, description="GitHub issue number for tracker"
    )
    blockers: list[str] = Field(
        default_factory=list, description="Blockers preventing progress"
    )
    completed_issues: list[str] = Field(
        default_factory=list, description="Issues completed in this phase"
    )


class SafetyState(BaseModel):
    """Safety component status entry."""

    model_config = ConfigDict(strict=True)

    component: str = Field(description="Component name")
    status: SafetyComponentStatus = Field(description="Current safety status")
    contract_defined: bool = Field(
        description="Whether a safety contract exists"
    )
    deployed: bool = Field(description="Whether the component is deployed")
    notes: str | None = Field(default=None, description="Additional context")


class Blocker(BaseModel):
    """Single blocker entry."""

    model_config = ConfigDict(strict=True)

    issue: str = Field(description="Issue reference or description")
    severity: str = Field(
        description="Severity: critical, high, medium, low"
    )
    affected_component: str = Field(
        description="Component affected by this blocker"
    )
    resolution: str | None = Field(
        default=None, description="Suggested resolution"
    )


class TestBaseline(BaseModel):
    """Test suite baseline snapshot."""

    model_config = ConfigDict(strict=True)

    total: int = Field(description="Total test count")
    passed: int = Field(description="Passing tests")
    skipped: int = Field(description="Skipped tests")
    failing: int = Field(description="Failing tests")


class HeadState(BaseModel):
    """Current HEAD state of the repository."""

    model_config = ConfigDict(strict=True)

    branch: str = Field(description="Current git branch")
    commit_sha: str = Field(description="Current commit hash")
    commit_message: str = Field(description="Current commit subject")
    ahead_of_remote: int = Field(
        default=0, description="Commits ahead of remote"
    )


class SIV2StatusReport(BaseModel):
    """Complete SI v2 status report."""

    model_config = ConfigDict(strict=True)

    generated_at: str = Field(
        description="ISO 8601 timestamp of report generation"
    )
    head: HeadState = Field(description="Current HEAD state")
    phases: list[PhaseEntry] = Field(
        description="List of all phases with their stage"
    )
    safety_state: list[SafetyState] = Field(
        description="Safety component statuses"
    )
    blockers: list[Blocker] = Field(
        default_factory=list, description="Active blockers"
    )
    test_baseline: TestBaseline = Field(description="Test suite baseline")
    next_recommended_issue: str | None = Field(
        default=None,
        description="Suggested next issue to work on",
    )
