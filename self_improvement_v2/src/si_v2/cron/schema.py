"""Pydantic schemas for SI v2 cron job definitions.

Defines the data models and loader for reading and validating cron job
definitions from YAML files. All jobs are disabled and dry-run-only by
default — this is enforced at the schema level.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, field_validator, model_validator


class JobPhase(StrEnum):
    """Phase identifier for a cron job execution phase."""

    ANALYZE = "analyze"
    BACKTEST = "backtest"
    WALKFORWARD = "walkforward"
    DAILY_REPORT = "daily_report"


class CronJobDef(BaseModel):
    """Definition of a single SI v2 cron job.

    Job IDs are auto-generated from bot_id + phase. All jobs are
    disabled by default and run in dry-run mode only.
    """

    model_config = ConfigDict()

    job_id: str
    bot_id: str
    phase: JobPhase
    schedule: str
    command: str
    enabled_default: bool = False
    dry_run_only: bool = True
    no_agent: bool = False
    description: str = ""

    @field_validator("schedule")
    @classmethod
    def schedule_must_not_be_empty(cls, v: str) -> str:
        """Reject empty or whitespace-only schedules."""
        if not v or not v.strip():
            raise ValueError("schedule must not be empty")
        return v.strip()

    @field_validator("enabled_default")
    @classmethod
    def enabled_must_be_false(cls, v: bool) -> bool:
        """Enforce that jobs are disabled by default."""
        if bool(v) is not False:
            raise ValueError("ALL cron jobs must be disabled by default (enabled_default=False)")
        return v

    @field_validator("dry_run_only")
    @classmethod
    def dry_run_must_be_true(cls, v: bool) -> bool:
        """Enforce that jobs are dry-run-only by default."""
        if bool(v) is not True:
            raise ValueError("ALL cron jobs must be dry-run-only by default (dry_run_only=True)")
        return v


class CronDefsFile(BaseModel):
    """Container for a validated cron job definitions file."""

    model_config = ConfigDict()

    schema_version: int = 1
    jobs: list[CronJobDef]

    @model_validator(mode="after")
    def validate_no_empty_jobs_list(self) -> CronDefsFile:
        """Reject empty jobs list."""
        if not self.jobs:
            raise ValueError("jobs list must not be empty — at least one job definition required")
        return self


class CronDefsLoader:
    """Reads jobs.yaml, validates against CronDefsFile schema.

    This is a pure loader — it performs no side effects and does not
    install or activate any cron jobs.
    """

    @staticmethod
    def load(path: Path) -> CronDefsFile:
        """Load and validate a YAML cron definitions file.

        Args:
            path: Path to the YAML file.

        Returns:
            Validated CronDefsFile instance.

        Raises:
            FileNotFoundError: If the file does not exist.
            yaml.YAMLError: If the file is not valid YAML.
            ValidationError: If the schema validation fails.
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Cron definitions file not found: {path}")
        with open(path) as f:
            content = f.read()
        return CronDefsLoader.load_from_string(content)

    @staticmethod
    def load_from_string(content: str) -> CronDefsFile:
        """Load and validate cron definitions from a YAML string.

        Args:
            content: YAML string content.

        Returns:
            Validated CronDefsFile instance.

        Raises:
            yaml.YAMLError: If the content is not valid YAML.
            ValidationError: If the schema validation fails.
        """
        data = yaml.safe_load(content)
        if data is None:
            data = {}
        return CronDefsFile.model_validate(data)
