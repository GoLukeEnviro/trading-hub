"""Tests for cron planner: CronPlanner, CronDiffPlanner."""

from __future__ import annotations

import json
from pathlib import Path

from si_v2.cron.planner import CronDiffPlanner, CronPlan, CronPlanEntry, CronPlanner
from si_v2.cron.schema import CronDefsFile, CronDefsLoader, CronJobDef, JobPhase


class TestCronPlanEntry:
    """CronPlanEntry defaults are always safe."""

    def test_enabled_defaults_to_false(self) -> None:
        """CronPlanEntry.enabled is always False by default."""
        job = CronJobDef(
            job_id="bot_a_analyze",
            bot_id="bot_a",
            phase=JobPhase.ANALYZE,
            schedule="*/15 * * * *",
            command="si_v2_analyze",
        )
        entry = CronPlanEntry(
            job_def=job,
            proposed_schedule="*/15 * * * *",
            safety_warnings=[],
        )
        assert entry.enabled is False

    def test_dry_run_only_defaults_to_true(self) -> None:
        """CronPlanEntry.dry_run_only is always True by default."""
        job = CronJobDef(
            job_id="bot_a_analyze",
            bot_id="bot_a",
            phase=JobPhase.ANALYZE,
            schedule="*/15 * * * *",
            command="si_v2_analyze",
        )
        entry = CronPlanEntry(
            job_def=job,
            proposed_schedule="*/15 * * * *",
            safety_warnings=[],
        )
        assert entry.dry_run_only is True


class TestCronPlan:
    """CronPlan container defaults."""

    def test_disabled_by_default_is_true(self) -> None:
        """disabled_by_default defaults to True."""
        plan = CronPlan(
            source_file="test.yaml",
            generated_at="2025-01-01T00:00:00+00:00",
            entries=[],
            blocked_jobs=[],
            safety_warnings=[],
        )
        assert plan.disabled_by_default is True


class TestCronPlanner:
    """CronPlanner.build_plan produces safe plans."""

    VALID_YAML = """
jobs:
  - job_id: bot_a_analyze
    bot_id: bot_a
    phase: analyze
    schedule: "*/15 * * * *"
    command: si_v2_analyze
  - job_id: bot_a_backtest
    bot_id: bot_a
    phase: backtest
    schedule: "0 */6 * * *"
    command: si_v2_backtest
  - job_id: bot_a_daily_report
    bot_id: bot_a
    phase: daily_report
    schedule: "0 8 * * *"
    command: si_v2_daily_report
  - job_id: bot_a_walkforward
    bot_id: bot_a
    phase: walkforward
    schedule: "0 2 * * 0"
    command: si_v2_walkforward
"""

    def test_no_enabled_jobs(self) -> None:
        """All plan entries have enabled=False."""
        defs = CronDefsLoader.load_from_string(self.VALID_YAML)
        planner = CronPlanner()
        plan = planner.build_plan(defs)
        for entry in plan.entries:
            assert entry.enabled is False, f"{entry.job_def.job_id} is enabled"

    def test_no_dry_run_false(self) -> None:
        """All plan entries have dry_run_only=True."""
        defs = CronDefsLoader.load_from_string(self.VALID_YAML)
        planner = CronPlanner()
        plan = planner.build_plan(defs)
        for entry in plan.entries:
            assert entry.dry_run_only is True, f"{entry.job_def.job_id} dry_run_only is False"

    def test_generated_at_is_iso(self) -> None:
        """generated_at is an ISO format timestamp."""
        defs = CronDefsLoader.load_from_string(self.VALID_YAML)
        planner = CronPlanner()
        plan = planner.build_plan(defs)
        assert "T" in plan.generated_at
        assert plan.generated_at.endswith("+00:00") or "+" in plan.generated_at

    def test_blocked_jobs_empty_for_valid(self) -> None:
        """No blocked jobs when all schedules are valid."""
        defs = CronDefsLoader.load_from_string(self.VALID_YAML)
        planner = CronPlanner()
        plan = planner.build_plan(defs)
        assert len(plan.blocked_jobs) == 0

    def test_safety_warnings_present(self) -> None:
        """Safety warnings are generated for valid plans."""
        defs = CronDefsLoader.load_from_string(self.VALID_YAML)
        planner = CronPlanner()
        plan = planner.build_plan(defs)
        assert len(plan.safety_warnings) > 0
        assert any("disabled by default" in w.lower() for w in plan.safety_warnings)

    def test_blocked_jobs_for_too_frequent(self) -> None:
        """Jobs with too-frequent schedules are blocked by planner."""
        job = CronJobDef(
            job_id="bot_a_analyze",
            bot_id="bot_a",
            phase=JobPhase.ANALYZE,
            schedule="*/1 * * * *",
            command="si_v2_analyze",
        )
        defs = CronDefsFile(jobs=[job])
        planner = CronPlanner()
        plan = planner.build_plan(defs)
        assert len(plan.blocked_jobs) == 1
        assert plan.blocked_jobs[0].blocked is True
        assert "too frequent" in plan.blocked_jobs[0].block_reason.lower()

    def test_blocked_jobs_for_every_minute(self) -> None:
        """Schedule '*' every minute is blocked by planner."""
        job = CronJobDef(
            job_id="bot_a_analyze",
            bot_id="bot_a",
            phase=JobPhase.ANALYZE,
            schedule="* * * * *",
            command="si_v2_analyze",
        )
        defs = CronDefsFile(jobs=[job])
        planner = CronPlanner()
        plan = planner.build_plan(defs)
        assert len(plan.blocked_jobs) >= 1

    def test_blocked_jobs_listed_separately(self) -> None:
        """Blocked jobs are in blocked_jobs, not in entries."""
        ok_job = CronJobDef(
            job_id="bot_a_ok",
            bot_id="bot_a",
            phase=JobPhase.ANALYZE,
            schedule="*/15 * * * *",
            command="si_v2_analyze",
        )
        bad_job = CronJobDef(
            job_id="bot_a_bad",
            bot_id="bot_a",
            phase=JobPhase.ANALYZE,
            schedule="*/1 * * * *",
            command="si_v2_analyze",
        )
        defs = CronDefsFile(jobs=[ok_job, bad_job])
        planner = CronPlanner()
        plan = planner.build_plan(defs)
        assert len(plan.entries) == 1
        assert len(plan.blocked_jobs) == 1
        assert plan.entries[0].job_def.job_id == "bot_a_ok"
        assert plan.blocked_jobs[0].job_def.job_id == "bot_a_bad"

    def test_proposed_schedule_matches_input(self) -> None:
        """proposed_schedule matches the original schedule."""
        defs = CronDefsLoader.load_from_string(self.VALID_YAML)
        planner = CronPlanner()
        plan = planner.build_plan(defs)
        for entry in plan.entries:
            assert entry.proposed_schedule == entry.job_def.schedule

    def test_entry_count(self) -> None:
        """Number of entries matches number of valid jobs."""
        defs = CronDefsLoader.load_from_string(self.VALID_YAML)
        planner = CronPlanner()
        plan = planner.build_plan(defs)
        assert len(plan.entries) == 4


class TestCronDiffPlanner:
    """CronDiffPlanner.diff produces read-only diffs."""

    def _make_plan(self) -> CronPlan:
        defs = CronDefsLoader.load_from_string("""
jobs:
  - job_id: bot_a_analyze
    bot_id: bot_a
    phase: analyze
    schedule: "*/15 * * * *"
    command: si_v2_analyze
  - job_id: bot_a_backtest
    bot_id: bot_a
    phase: backtest
    schedule: "0 */6 * * *"
    command: si_v2_backtest
""")
        planner = CronPlanner()
        return planner.build_plan(defs)

    def test_diff_no_current_jobs_file(self, tmp_path: Path) -> None:
        """When jobs.json doesn't exist, diff returns empty with warning."""
        missing_path = tmp_path / "nonexistent_jobs.json"
        plan = self._make_plan()
        diff = CronDiffPlanner().diff(plan, missing_path)
        assert len(diff.added) == 0
        assert len(diff.removed) == 0
        assert len(diff.changed) == 0
        assert len(diff.unchanged) == 0
        assert "does not exist" in " ".join(diff.proposed.safety_warnings)

    def test_diff_with_matching_current_jobs(self, tmp_path: Path) -> None:
        """Jobs present in both plan and current file appear as unchanged."""
        jobs_path = tmp_path / "jobs.json"
        jobs_path.write_text(
            json.dumps(
                [
                    {"id": "bot_a_analyze", "schedule": "*/15 * * * *"},
                    {"id": "bot_a_backtest", "schedule": "0 */6 * * *"},
                ]
            )
        )
        plan = self._make_plan()
        diff = CronDiffPlanner().diff(plan, jobs_path)
        assert len(diff.unchanged) == 2
        assert len(diff.added) == 0
        assert len(diff.removed) == 0

    def test_diff_with_added_jobs(self, tmp_path: Path) -> None:
        """New jobs appear as added."""
        jobs_path = tmp_path / "jobs.json"
        jobs_path.write_text(
            json.dumps(
                [
                    {"id": "bot_a_analyze", "schedule": "*/15 * * * *"},
                ]
            )
        )
        plan = self._make_plan()
        diff = CronDiffPlanner().diff(plan, jobs_path)
        assert len(diff.added) == 1
        assert diff.added[0].job_def.job_id == "bot_a_backtest"

    def test_diff_readonly_never_writes(self, tmp_path: Path) -> None:
        """Diff planner never writes to jobs.json."""
        jobs_path = tmp_path / "jobs.json"
        jobs_path.write_text(json.dumps([{"id": "bot_a_analyze", "schedule": "*/15 * * * *"}]))
        original_content = jobs_path.read_text()
        plan = self._make_plan()
        CronDiffPlanner().diff(plan, jobs_path)
        # Content must not change
        assert jobs_path.read_text() == original_content

    def test_diff_dict_format_current_jobs(self, tmp_path: Path) -> None:
        """jobs.json with dict format (nested jobs list) is handled."""
        jobs_path = tmp_path / "jobs.json"
        jobs_path.write_text(
            json.dumps(
                {
                    "jobs": [
                        {"id": "bot_a_analyze", "schedule": "*/15 * * * *"},
                        {"id": "bot_a_backtest", "schedule": "0 */6 * * *"},
                    ]
                }
            )
        )
        plan = self._make_plan()
        diff = CronDiffPlanner().diff(plan, jobs_path)
        assert len(diff.unchanged) == 2

    def test_diff_with_changed_schedule(self, tmp_path: Path) -> None:
        """Jobs with different schedules appear as changed."""
        jobs_path = tmp_path / "jobs.json"
        jobs_path.write_text(
            json.dumps(
                [
                    {"id": "bot_a_analyze", "schedule": "0 0 * * *"},
                ]
            )
        )
        plan = self._make_plan()
        diff = CronDiffPlanner().diff(plan, jobs_path)
        assert len(diff.changed) == 1
        assert diff.changed[0][0].job_def.job_id == "bot_a_analyze"
