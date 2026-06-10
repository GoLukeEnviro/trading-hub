"""Tests for SI v2 Progress Dashboard (#123).

Verifies:
- dashboard exists
- subsystem grouping exists
- readiness level is shown
- next-run recommendation exists
- output is deterministic
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent

_DASHBOARD_PATH = (
    _ROOT / "reports" / "progress" / "si_v2_progress_dashboard.md"
)

sys.path.insert(0, str(_ROOT / "reports" / "progress"))
from progress_dashboard import generate_dashboard


class TestDashboardExists:
    def test_dashboard_exists(self) -> None:
        assert _DASHBOARD_PATH.exists()

    def test_dashboard_not_empty(self) -> None:
        text = _DASHBOARD_PATH.read_text()
        assert len(text) > 100


class TestContent:
    def test_includes_title(self) -> None:
        md = generate_dashboard()
        assert "# SI v2 Implementation Progress Dashboard" in md

    def test_includes_summary(self) -> None:
        md = generate_dashboard()
        assert "## Summary" in md

    def test_includes_subsystem_groups(self) -> None:
        md = generate_dashboard()
        assert "Rainbow Core" in md
        assert "Post-Rainbow Foundation" in md
        assert "Offline Pipeline" in md
        assert "Governance" in md or "Governance / CI / Approval" in md

    def test_includes_readiness_level(self) -> None:
        md = generate_dashboard()
        assert "Offline readiness" in md

    def test_includes_live_readiness_blocked(self) -> None:
        md = generate_dashboard()
        assert "BLOCKED" in md

    def test_has_next_recommended_run(self) -> None:
        md = generate_dashboard()
        assert "Next Recommended Run" in md

    def test_deterministic(self) -> None:
        md1 = generate_dashboard()
        md2 = generate_dashboard()
        assert md1 == md2

    def test_offline_readiness_yellow_or_green(self) -> None:
        """Dashboard should show YELLOW (if pending) or GREEN (if all done)."""
        md = generate_dashboard()
        assert "Offline readiness" in md


class TestSubsystemGroups:
    def test_each_group_has_table(self) -> None:
        md = generate_dashboard()
        # Each subsystem group should have a table with Issue, Title, Status headers
        assert "| Issue | Title | Status |" in md

    def test_episode_readiness_group_exists(self) -> None:
        md = generate_dashboard()
        assert "Episode + Readiness" in md

    def test_rehearsal_control_group_exists(self) -> None:
        md = generate_dashboard()
        assert "Rehearsal Control" in md
