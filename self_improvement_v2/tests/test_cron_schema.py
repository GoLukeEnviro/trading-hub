"""Tests for cron schema models: CronJobDef, CronDefsFile, CronDefsLoader."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from si_v2.cron.schema import CronDefsFile, CronDefsLoader, CronJobDef, JobPhase


class TestJobPhase:
    """JobPhase enum has expected values."""

    def test_enum_values(self) -> None:
        assert JobPhase.ANALYZE.value == "analyze"
        assert JobPhase.BACKTEST.value == "backtest"
        assert JobPhase.WALKFORWARD.value == "walkforward"
        assert JobPhase.DAILY_REPORT.value == "daily_report"

    def test_enum_members(self) -> None:
        assert len(JobPhase) == 4


class TestCronJobDef:
    """CronJobDef creation and validation."""

    def test_valid_minimal(self) -> None:
        """Minimal valid CronJobDef can be created."""
        job = CronJobDef(
            job_id="bot_a_analyze",
            bot_id="bot_a",
            phase=JobPhase.ANALYZE,
            schedule="*/15 * * * *",
            command="si_v2_analyze",
        )
        assert job.job_id == "bot_a_analyze"
        assert job.bot_id == "bot_a"
        assert job.phase == JobPhase.ANALYZE
        assert job.schedule == "*/15 * * * *"
        assert job.command == "si_v2_analyze"
        assert job.enabled_default is False
        assert job.dry_run_only is True
        assert job.no_agent is False
        assert job.description == ""

    def test_valid_full(self) -> None:
        """CronJobDef with all fields."""
        job = CronJobDef(
            job_id="bot_b_backtest",
            bot_id="bot_b",
            phase=JobPhase.BACKTEST,
            schedule="0 */6 * * *",
            command="si_v2_backtest",
            enabled_default=False,
            dry_run_only=True,
            no_agent=True,
            description="Test job",
        )
        assert job.no_agent is True
        assert job.description == "Test job"

    def test_enabled_default_must_be_false(self) -> None:
        """enabled_default=True is rejected."""
        with pytest.raises(ValidationError, match="disabled by default"):
            CronJobDef(
                job_id="bot_a_analyze",
                bot_id="bot_a",
                phase=JobPhase.ANALYZE,
                schedule="*/15 * * * *",
                command="si_v2_analyze",
                enabled_default=True,
            )

    def test_dry_run_only_must_be_true(self) -> None:
        """dry_run_only=False is rejected."""
        with pytest.raises(ValidationError, match="dry-run-only"):
            CronJobDef(
                job_id="bot_a_analyze",
                bot_id="bot_a",
                phase=JobPhase.ANALYZE,
                schedule="*/15 * * * *",
                command="si_v2_analyze",
                dry_run_only=False,
            )

    def test_empty_schedule_rejected(self) -> None:
        """Empty schedule string is rejected."""
        with pytest.raises(ValidationError, match="must not be empty"):
            CronJobDef(
                job_id="bot_a_analyze",
                bot_id="bot_a",
                phase=JobPhase.ANALYZE,
                schedule="",
                command="si_v2_analyze",
            )

    def test_whitespace_schedule_rejected(self) -> None:
        """Whitespace-only schedule is rejected."""
        with pytest.raises(ValidationError, match="must not be empty"):
            CronJobDef(
                job_id="bot_a_analyze",
                bot_id="bot_a",
                phase=JobPhase.ANALYZE,
                schedule="   ",
                command="si_v2_analyze",
            )

    @pytest.mark.parametrize(
        "schedule",
        [
            "* * * * *",
            "*/1 * * * *",
            "*/2 * * * *",
            "*/3 * * * *",
            "*/4 * * * *",
        ],
    )
    def test_too_frequent_schedule_accepted_by_schema(self, schedule: str) -> None:
        """Schedules <= every 4 minutes are accepted by schema (planner handles safety)."""
        job = CronJobDef(
            job_id="bot_a_analyze",
            bot_id="bot_a",
            phase=JobPhase.ANALYZE,
            schedule=schedule,
            command="si_v2_analyze",
        )
        assert job.schedule == schedule

    @pytest.mark.parametrize(
        "schedule",
        [
            "*/5 * * * *",
            "*/10 * * * *",
            "*/15 * * * *",
            "0 * * * *",
            "0 */6 * * *",
            "0 8 * * *",
            "0 2 * * 0",
            "30 1 * * 1-5",
        ],
    )
    def test_valid_schedule_accepted(self, schedule: str) -> None:
        """Schedules with frequency >= every 5 minutes are accepted."""
        job = CronJobDef(
            job_id="bot_a_analyze",
            bot_id="bot_a",
            phase=JobPhase.ANALYZE,
            schedule=schedule,
            command="si_v2_analyze",
        )
        assert job.schedule == schedule


class TestCronDefsFile:
    """CronDefsFile container validation."""

    def test_valid_with_jobs(self) -> None:
        """Valid CronDefsFile with jobs."""
        defs = CronDefsFile(
            jobs=[
                CronJobDef(
                    job_id="bot_a_analyze",
                    bot_id="bot_a",
                    phase=JobPhase.ANALYZE,
                    schedule="*/15 * * * *",
                    command="si_v2_analyze",
                ),
            ]
        )
        assert defs.schema_version == 1
        assert len(defs.jobs) == 1

    def test_empty_jobs_list_rejected(self) -> None:
        """Empty jobs list is rejected."""
        with pytest.raises(ValidationError, match="must not be empty"):
            CronDefsFile(jobs=[])


class TestCronDefsLoader:
    """CronDefsLoader YAML parsing and validation."""

    VALID_YAML = """
jobs:
  - job_id: bot_a_analyze
    bot_id: bot_a
    phase: analyze
    schedule: "*/15 * * * *"
    command: si_v2_analyze
    enabled_default: false
    dry_run_only: true
  - job_id: bot_a_backtest
    bot_id: bot_a
    phase: backtest
    schedule: "0 */6 * * *"
    command: si_v2_backtest
"""

    def test_load_from_string_valid(self) -> None:
        """load_from_string parses valid YAML."""
        defs = CronDefsLoader.load_from_string(self.VALID_YAML)
        assert len(defs.jobs) == 2
        assert defs.jobs[0].job_id == "bot_a_analyze"
        assert defs.jobs[0].phase == JobPhase.ANALYZE
        assert defs.jobs[1].job_id == "bot_a_backtest"
        assert defs.jobs[1].phase == JobPhase.BACKTEST

    def test_load_from_string_missing_field(self) -> None:
        """Missing required field raises ValidationError."""
        bad_yaml = """
jobs:
  - job_id: bot_a_analyze
    phase: analyze
    schedule: "*/15 * * * *"
    command: si_v2_analyze
"""
        with pytest.raises(ValidationError):
            CronDefsLoader.load_from_string(bad_yaml)

    def test_load_from_string_too_frequent_accepted(self) -> None:
        """Too-frequent schedules are accepted by loader (planner handles)."""
        yaml = """
jobs:
  - job_id: bot_a_analyze
    bot_id: bot_a
    phase: analyze
    schedule: "*/1 * * * *"
    command: si_v2_analyze
"""
        defs = CronDefsLoader.load_from_string(yaml)
        assert len(defs.jobs) == 1
        assert defs.jobs[0].schedule == "*/1 * * * *"

    def test_load_from_string_empty_jobs(self) -> None:
        """Empty jobs list raises ValidationError."""
        bad_yaml = "jobs: []"
        with pytest.raises(ValidationError, match="must not be empty"):
            CronDefsLoader.load_from_string(bad_yaml)

    def test_load_from_string_empty_document(self) -> None:
        """Empty document raises ValidationError (no jobs)."""
        with pytest.raises(ValidationError):
            CronDefsLoader.load_from_string("")

    def test_load_from_string_invalid_yaml(self) -> None:
        """Invalid YAML raises YAMLError."""
        with pytest.raises(yaml.YAMLError):
            CronDefsLoader.load_from_string(": invalid yaml :")

    def test_load_valid_file(self, tmp_path: Path) -> None:
        """load reads a valid YAML file."""
        file_path = tmp_path / "jobs.yaml"
        file_path.write_text(self.VALID_YAML)
        defs = CronDefsLoader.load(file_path)
        assert len(defs.jobs) == 2

    def test_load_file_not_found(self, tmp_path: Path) -> None:
        """load raises FileNotFoundError for missing file."""
        with pytest.raises(FileNotFoundError):
            CronDefsLoader.load(tmp_path / "nonexistent.yaml")

    def test_load_from_string_phase_enum(self) -> None:
        """Phase string is correctly parsed to JobPhase enum."""
        defs = CronDefsLoader.load_from_string(self.VALID_YAML)
        assert isinstance(defs.jobs[0].phase, JobPhase)
        assert defs.jobs[0].phase == JobPhase.ANALYZE

    def test_load_from_string_bot_id_present(self) -> None:
        """Every job must have bot_id."""
        defs = CronDefsLoader.load_from_string(self.VALID_YAML)
        for job in defs.jobs:
            assert job.bot_id, f"Job {job.job_id} missing bot_id"

    def test_load_from_string_schedule_present(self) -> None:
        """Every job must have schedule."""
        defs = CronDefsLoader.load_from_string(self.VALID_YAML)
        for job in defs.jobs:
            assert job.schedule, f"Job {job.job_id} missing schedule"
