"""Test cron generator: spec generation from jobs.yaml."""

from __future__ import annotations

from pathlib import Path

from si_v2.cron.generator import generate_cron_specs

CRON_DEFS_PATH = Path(__file__).resolve().parent.parent / "cron_defs" / "jobs.yaml"


class TestCronGenerator:
    """Tests for the cron job generator."""

    def test_generates_specs(self) -> None:
        """Generator produces cron specs from jobs.yaml."""
        specs = generate_cron_specs(CRON_DEFS_PATH)
        assert len(specs) > 0

    def test_sixteen_jobs_generated(self) -> None:
        """4 bots x 4 schedules = 16 jobs."""
        specs = generate_cron_specs(CRON_DEFS_PATH)
        assert len(specs) == 16

    def test_spec_has_required_keys(self) -> None:
        """Each spec has schedule, script, deliver, workdir."""
        specs = generate_cron_specs(CRON_DEFS_PATH)
        for spec in specs:
            assert "schedule" in spec
            assert "script" in spec
            assert "deliver" in spec
            assert "workdir" in spec

    def test_spec_has_bot_id(self) -> None:
        """Each spec includes bot_id."""
        specs = generate_cron_specs(CRON_DEFS_PATH)
        bot_ids = {spec["bot_id"] for spec in specs}
        assert bot_ids == {"freqforge", "freqforge_canary", "regime_hybrid", "rebel"}

    def test_spec_has_task(self) -> None:
        """Each spec includes a task name."""
        specs = generate_cron_specs(CRON_DEFS_PATH)
        tasks = {spec["task"] for spec in specs}
        assert "analyze" in tasks
        assert "backtest" in tasks
        assert "daily_report" in tasks
        assert "walkforward" in tasks

    def test_missing_yaml_returns_empty(self) -> None:
        """Missing jobs.yaml returns empty list."""
        specs = generate_cron_specs("/nonexistent/path/jobs.yaml")
        assert specs == []

    def test_schedule_values(self) -> None:
        """Schedule values are valid cron expressions."""
        specs = generate_cron_specs(CRON_DEFS_PATH)
        for spec in specs:
            schedule = spec["schedule"]
            assert isinstance(schedule, str)
            assert len(schedule.split()) == 5
