"""Tests for the SI v2 status report module."""

from __future__ import annotations

import json

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


class TestModels:
    """Test the pydantic models serialize and validate correctly."""

    def test_head_state_defaults(self) -> None:
        h = HeadState(
            branch="main",
            commit_sha="abc1234",
            commit_message="test commit",
        )
        assert h.branch == "main"
        assert h.ahead_of_remote == 0  # default

    def test_phase_entry_defaults(self) -> None:
        p = PhaseEntry(name="Phase 0", stage=PhaseStage.IN_PROGRESS)
        assert p.blockers == []
        assert p.completed_issues == []
        assert p.tracker_issue is None

    def test_phase_entry_with_blockers(self) -> None:
        p = PhaseEntry(
            name="Phase 0",
            stage=PhaseStage.BLOCKED,
            blockers=["Blocker A", "Blocker B"],
            completed_issues=["#1", "#2"],
            tracker_issue="#99",
        )
        assert len(p.blockers) == 2
        assert len(p.completed_issues) == 2
        assert p.tracker_issue == "#99"

    def test_safety_state_defaults(self) -> None:
        s = SafetyState(
            component="RiskGuard",
            status=SafetyComponentStatus.GREEN,
            contract_defined=True,
            deployed=False,
        )
        assert s.notes is None
        assert s.deployed is False

    def test_safety_state_with_notes(self) -> None:
        s = SafetyState(
            component="Test",
            status=SafetyComponentStatus.YELLOW,
            contract_defined=False,
            deployed=True,
            notes="Some issue",
        )
        assert s.notes == "Some issue"

    def test_blocker_defaults(self) -> None:
        b = Blocker(
            issue="#43",
            severity="critical",
            affected_component="FleetRiskManager",
        )
        assert b.resolution is None

    def test_blocker_with_resolution(self) -> None:
        b = Blocker(
            issue="#43",
            severity="critical",
            affected_component="FleetRiskManager",
            resolution="Fix it",
        )
        assert b.resolution == "Fix it"

    def test_test_baseline(self) -> None:
        tb = TestBaseline(total=457, passed=456, skipped=1, failing=0)
        assert tb.total == 457
        assert tb.passed == 456
        assert tb.skipped == 1
        assert tb.failing == 0
        assert tb.passed + tb.skipped + tb.failing == tb.total

    def test_full_report_serialization(self) -> None:
        """Verify the full report model round-trips through JSON."""
        report = SIV2StatusReport(
            generated_at="2026-06-10T10:00:00+00:00",
            head=HeadState(
                branch="main",
                commit_sha="abc1234",
                commit_message="test",
            ),
            phases=[
                PhaseEntry(
                    name="Phase 0",
                    stage=PhaseStage.IN_PROGRESS,
                    tracker_issue="#48",
                ),
            ],
            safety_state=[
                SafetyState(
                    component="RiskGuard",
                    status=SafetyComponentStatus.GREEN,
                    contract_defined=True,
                    deployed=False,
                ),
            ],
            blockers=[
                Blocker(
                    issue="#43",
                    severity="critical",
                    affected_component="FleetRiskManager",
                ),
            ],
            test_baseline=TestBaseline(
                total=457, passed=456, skipped=1, failing=0
            ),
            next_recommended_issue="#43",
        )
        # Serialize to JSON
        data = json.loads(report.model_dump_json())
        assert data["generated_at"] == "2026-06-10T10:00:00+00:00"
        assert data["head"]["branch"] == "main"
        assert data["head"]["commit_sha"] == "abc1234"
        assert data["phases"][0]["name"] == "Phase 0"
        assert data["phases"][0]["stage"] == "in_progress"
        assert data["safety_state"][0]["component"] == "RiskGuard"
        assert data["safety_state"][0]["status"] == "GREEN"
        assert data["blockers"][0]["issue"] == "#43"
        assert data["test_baseline"]["total"] == 457
        assert data["next_recommended_issue"] == "#43"
        # Deserialize back
        restored = SIV2StatusReport.model_validate_json(report.model_dump_json())
        assert restored.head.commit_sha == "abc1234"


class TestPhaseStage:
    """Test PhaseStage enum behavior."""

    def test_all_values_present(self) -> None:
        values = {v.value for v in PhaseStage}
        assert values == {"not_started", "in_progress", "completed", "blocked"}

    def test_in_progress_is_not_completed(self) -> None:
        assert PhaseStage.IN_PROGRESS != PhaseStage.COMPLETED

    def test_blocked_is_not_in_progress(self) -> None:
        assert PhaseStage.BLOCKED != PhaseStage.IN_PROGRESS


class TestSafetyComponentStatus:
    """Test SafetyComponentStatus enum behavior."""

    def test_green_yellow_red(self) -> None:
        assert SafetyComponentStatus.GREEN.value == "GREEN"
        assert SafetyComponentStatus.YELLOW.value == "YELLOW"
        assert SafetyComponentStatus.RED.value == "RED"
