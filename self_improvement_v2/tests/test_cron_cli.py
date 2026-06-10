"""Tests for cron CLI commands — all dry-run only."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from si_v2.cron.cli import CronCLI

if TYPE_CHECKING:
    import pytest


class TestCronCLIValidate:
    """CronCLI.cmd_validate — validates YAML files."""

    VALID_YAML = """
jobs:
  - job_id: bot_a_analyze
    bot_id: bot_a
    phase: analyze
    schedule: "*/15 * * * *"
    command: si_v2_analyze
"""

    INVALID_YAML_MISSING_FIELD = """
jobs:
  - job_id: bot_a_analyze
    phase: analyze
    schedule: "*/15 * * * *"
    command: si_v2_analyze
"""

    def test_validate_valid_file(self, tmp_path: Path) -> None:
        """Valid YAML returns 0."""
        file_path = tmp_path / "jobs.yaml"
        file_path.write_text(self.VALID_YAML)
        rc = CronCLI.cmd_validate(file_path)
        assert rc == 0

    def test_validate_invalid_file(self, tmp_path: Path) -> None:
        """Invalid YAML returns 1."""
        file_path = tmp_path / "jobs.yaml"
        file_path.write_text(self.INVALID_YAML_MISSING_FIELD)
        rc = CronCLI.cmd_validate(file_path)
        assert rc == 1

    def test_validate_nonexistent_file(self, tmp_path: Path) -> None:
        """Non-existent file returns 1."""
        rc = CronCLI.cmd_validate(tmp_path / "nonexistent.yaml")
        assert rc == 1

    def test_validate_empty_yaml(self, tmp_path: Path) -> None:
        """Empty jobs list returns 1."""
        file_path = tmp_path / "jobs.yaml"
        file_path.write_text("jobs: []")
        rc = CronCLI.cmd_validate(file_path)
        assert rc == 1


class TestCronCLIRenderPlan:
    """CronCLI.cmd_render_plan — renders dry-run plans."""

    VALID_YAML = """
jobs:
  - job_id: bot_a_analyze
    bot_id: bot_a
    phase: analyze
    schedule: "*/15 * * * *"
    command: si_v2_analyze
"""

    def test_render_plan_stdout(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """Render plan to stdout works."""
        file_path = tmp_path / "jobs.yaml"
        file_path.write_text(self.VALID_YAML)
        rc = CronCLI.cmd_render_plan(file_path, output_json=None)
        assert rc == 0
        captured = capsys.readouterr()
        assert "bot_a_analyze" in captured.out
        assert "enabled" in captured.out or "entries" in captured.out

    def test_render_plan_to_file(self, tmp_path: Path) -> None:
        """Render plan to output JSON file."""
        file_path = tmp_path / "jobs.yaml"
        file_path.write_text(self.VALID_YAML)
        output_path = tmp_path / "self_improvement_v2" / "plan.json"
        rc = CronCLI.cmd_render_plan(file_path, output_json=output_path)
        assert rc == 0
        assert output_path.exists()
        data = json.loads(output_path.read_text())
        assert "entries" in data

    def test_render_plan_all_jobs_disabled(self, tmp_path: Path) -> None:
        """All jobs in rendered plan have enabled=False."""
        file_path = tmp_path / "jobs.yaml"
        file_path.write_text(self.VALID_YAML)
        output_path = tmp_path / "self_improvement_v2" / "plan.json"
        CronCLI.cmd_render_plan(file_path, output_json=output_path)
        data = json.loads(output_path.read_text())
        for entry in data.get("entries", []):
            assert entry.get("enabled") is False

    def test_render_plan_nonexistent_file(self, tmp_path: Path) -> None:
        """Non-existent file returns 1."""
        rc = CronCLI.cmd_render_plan(tmp_path / "nonexistent.yaml")
        assert rc == 1

    def test_render_plan_refuses_outside_path(self, tmp_path: Path) -> None:
        """Output path outside self_improvement_v2/ is rejected."""
        file_path = tmp_path / "jobs.yaml"
        file_path.write_text(self.VALID_YAML)
        output_path = tmp_path / "outside" / "plan.json"
        rc = CronCLI.cmd_render_plan(file_path, output_json=output_path)
        assert rc == 1


class TestCronCLIDiffReadonly:
    """CronCLI.cmd_diff_readonly — read-only diff, never writes."""

    VALID_YAML = """
jobs:
  - job_id: bot_a_analyze
    bot_id: bot_a
    phase: analyze
    schedule: "*/15 * * * *"
    command: si_v2_analyze
"""

    def test_diff_no_current_jobs(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """Diff without current jobs file still returns 0."""
        file_path = tmp_path / "jobs.yaml"
        file_path.write_text(self.VALID_YAML)
        rc = CronCLI.cmd_diff_readonly(file_path, current_jobs=tmp_path / "nonexistent.json")
        assert rc == 0

    def test_diff_with_current_jobs(self, tmp_path: Path) -> None:
        """Diff with a valid jobs.json works."""
        file_path = tmp_path / "jobs.yaml"
        file_path.write_text(self.VALID_YAML)
        jobs_path = tmp_path / "jobs.json"
        jobs_path.write_text(
            json.dumps(
                [
                    {"id": "bot_a_analyze", "schedule": "*/15 * * * *"},
                ]
            )
        )
        rc = CronCLI.cmd_diff_readonly(file_path, current_jobs=jobs_path)
        assert rc == 0

    def test_diff_reads_but_never_writes(self, tmp_path: Path) -> None:
        """The diff command never modifies jobs.json."""
        file_path = tmp_path / "jobs.yaml"
        file_path.write_text(self.VALID_YAML)
        jobs_path = tmp_path / "jobs.json"
        original = json.dumps([{"id": "bot_a_analyze", "schedule": "*/15 * * * *"}])
        jobs_path.write_text(original)
        CronCLI.cmd_diff_readonly(file_path, current_jobs=jobs_path)
        assert jobs_path.read_text() == original

    def test_diff_nonexistent_source(self, tmp_path: Path) -> None:
        """Non-existent source file returns 1."""
        rc = CronCLI.cmd_diff_readonly(tmp_path / "nonexistent.yaml")
        assert rc == 1


class TestNoForbiddenCommands:
    """Verify the CLI module has no apply/install/write/delete commands."""

    def test_no_apply_method(self) -> None:
        """CronCLI has no cmd_apply method."""
        assert not hasattr(CronCLI, "cmd_apply")

    def test_no_install_method(self) -> None:
        """CronCLI has no cmd_install method."""
        assert not hasattr(CronCLI, "cmd_install")

    def test_no_write_method(self) -> None:
        """CronCLI has no cmd_write method."""
        assert not hasattr(CronCLI, "cmd_write")

    def test_no_enable_method(self) -> None:
        """CronCLI has no cmd_enable method."""
        assert not hasattr(CronCLI, "cmd_enable")

    def test_no_disable_method(self) -> None:
        """CronCLI has no cmd_disable method."""
        assert not hasattr(CronCLI, "cmd_disable")

    def test_no_delete_method(self) -> None:
        """CronCLI has no cmd_delete method."""
        assert not hasattr(CronCLI, "cmd_delete")

    def test_no_reactivate_method(self) -> None:
        """CronCLI has no cmd_reactivate method."""
        assert not hasattr(CronCLI, "cmd_reactivate")
