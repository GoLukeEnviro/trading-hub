"""Tests for status/report.py — render_markdown and generate_report.

Tests cover:
- render_markdown with various report states
- generate_report with mocked I/O
- Edge cases: empty blockers, no phases, safety state variations
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from _pytest.monkeypatch import MonkeyPatch

from si_v2.status import (
    Blocker,
    HeadState,
    PhaseEntry,
    PhaseStage,
    SafetyComponentStatus,
    SafetyState,
    SIV2StatusReport,
    TestBaseline,
)
from si_v2.status.report import generate_report, render_markdown


# ======================================================================
# render_markdown — pure function
# ======================================================================

class TestRenderMarkdown:
    def _make_report(self, **overrides: Any) -> SIV2StatusReport:
        defaults: dict = {
            "generated_at": "2026-06-29T12:00:00",
            "head": HeadState(
                branch="main", commit_sha="abc1234",
                commit_message="test commit", ahead_of_remote=0,
            ),
            "phases": [
                PhaseEntry(
                    name="Phase 0", stage=PhaseStage.COMPLETED,
                    tracker_issue="#1", completed_issues=["#1"],
                    blockers=[],
                ),
            ],
            "safety_state": [
                SafetyState(
                    component="dry_run", status=SafetyComponentStatus.GREEN,
                    contract_defined=True, deployed=True,
                    notes="All bots dry_run=True",
                ),
            ],
            "blockers": [
                Blocker(
                    issue="#43", severity="critical",
                    affected_component="FleetRiskManager",
                    resolution="Fix logic",
                ),
            ],
            "test_baseline": TestBaseline(total=100, passed=95, skipped=3, failing=2),
            "next_recommended_issue": "#43 — Fix FleetRiskManager",
        }
        defaults.update(overrides)
        return SIV2StatusReport(**defaults)

    def test_render_minimal(self) -> None:
        report = self._make_report()
        output = render_markdown(report)
        assert "SI v2 Status Report" in output
        assert "main" in output
        assert "abc1234" in output
        assert "test commit" in output

    def test_render_phases(self) -> None:
        report = self._make_report()
        output = render_markdown(report)
        assert "Phase 0" in output
        assert "COMPLETED" in output or "✅" in output

    def test_render_safety_state(self) -> None:
        report = self._make_report()
        output = render_markdown(report)
        assert "dry_run" in output
        assert "GREEN" in output or "🟢" in output

    def test_render_blockers(self) -> None:
        report = self._make_report()
        output = render_markdown(report)
        assert "#43" in output
        assert "critical" in output
        assert "FleetRiskManager" in output

    def test_render_test_baseline(self) -> None:
        report = self._make_report()
        output = render_markdown(report)
        assert "100" in output
        assert "95" in output
        assert "2" in output  # failing

    def test_render_no_blockers(self) -> None:
        report = self._make_report(blockers=[])
        output = render_markdown(report)
        assert "Active Blockers" not in output

    def test_render_no_phases(self) -> None:
        report = self._make_report(phases=[])
        output = render_markdown(report)
        assert "Phases" in output  # section header still present

    def test_render_ahead_of_remote(self) -> None:
        head = HeadState(
            branch="feature", commit_sha="def5678",
            commit_message="wip", ahead_of_remote=3,
        )
        report = self._make_report(head=head)
        output = render_markdown(report)
        assert "Ahead of remote" in output
        assert "3" in output

    def test_render_no_next_issue(self) -> None:
        report = self._make_report(next_recommended_issue="")
        output = render_markdown(report)
        assert "Next Recommended Issue" not in output

    def test_deterministic_output(self) -> None:
        """Same report produces same markdown."""
        report = self._make_report()
        output1 = render_markdown(report)
        output2 = render_markdown(report)
        assert output1 == output2


# ======================================================================
# generate_report — I/O mocked
# ======================================================================

class TestGenerateReport:
    def test_generates_with_mocked_git(self, monkeypatch: MonkeyPatch) -> None:
        """generate_report should work with mocked subprocess."""
        import subprocess

        def mock_run(*args: Any, **kwargs: Any) -> Any:
            cmd = args[0] if args else kwargs.get("args", [])
            cmd_str = " ".join(cmd) if isinstance(cmd, list) else str(cmd)

            class MockResult:
                stdout = ""
                returncode = 0

            if "rev-parse --abbrev-ref HEAD" in cmd_str:
                MockResult.stdout = "main\n"
            elif "rev-parse --short HEAD" in cmd_str:
                MockResult.stdout = "abc1234\n"
            elif "log --oneline -1" in cmd_str:
                MockResult.stdout = "abc1234 test commit\n"
            elif "rev-list --count" in cmd_str:
                MockResult.stdout = "0\n"
            elif "pytest" in cmd_str or "--collect-only" in cmd_str:
                MockResult.stdout = "100 items collected\n"
            else:
                MockResult.stdout = ""
            return MockResult()

        monkeypatch.setattr(subprocess, "run", mock_run)

        report = generate_report()
        assert report.head.branch == "main"
        assert report.head.commit_sha == "abc1234"
        assert report.test_baseline.total == 100
        assert len(report.phases) > 0
        assert len(report.safety_state) > 0
        assert len(report.blockers) > 0

    def test_generates_with_git_failure(self, monkeypatch: MonkeyPatch) -> None:
        """When git fails, report should still generate with fallback values."""
        import subprocess

        def mock_run(*args: Any, **kwargs: Any) -> Any:
            raise subprocess.TimeoutExpired(cmd=["git"], timeout=30, output="")

        monkeypatch.setattr(subprocess, "run", mock_run)

        report = generate_report()
        assert report.head.branch == "main"  # fallback
        assert report.head.commit_sha == "unknown"
        assert report.test_baseline.total > 0  # fallback value

    def test_generated_at_is_set(self, monkeypatch: MonkeyPatch) -> None:
        import subprocess

        def mock_run(*args: Any, **kwargs: Any) -> Any:
            class MockResult:
                stdout = ""
                returncode = 0
            return MockResult()

        monkeypatch.setattr(subprocess, "run", mock_run)
        report = generate_report()
        assert report.generated_at is not None
        assert "T" in report.generated_at
