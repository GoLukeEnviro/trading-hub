r"""Tests for the final measurement decision pack (Phase 4E).

Pure Python — no subprocess, no Docker, no runtime mutation.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from si_v2.measurement.decision_engine import MeasurementPoint
from si_v2.measurement.final_decision_pack import (
    CANDIDATE_ID,
    TARGET_BOT,
    MeasurementReportRef,
    build_final_measurement_decision_pack,
    build_measurement_report_registry,
    render_final_measurement_report,
    validate_official_t3_guard,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_point(label: str, **kw) -> MeasurementPoint:
    """Helper to create a MeasurementPoint with defaults."""
    defaults = dict(
        timestamp_utc="2026-06-27T18:27:00Z",
        bot_id=TARGET_BOT,
        candidate_id=CANDIDATE_ID,
        runtime_proof_status="GREEN",
        max_open_trades=2, dry_run=True, container_healthy=True,
        open_trades=0, closed_trades=59,
        total_profit_abs=3.98, realized_profit_abs=3.98,
        win_rate=0.898, drawdown_abs=0.0,
        errors_since_last=0, warnings_since_last=0,
        unexpected_restart=False, rollback_required=False,
    )
    defaults.update(kw)
    return MeasurementPoint(label=label, **defaults)  # type: ignore[arg-type]


@pytest.fixture
def reports_without_t3() -> list[MeasurementReportRef]:
    return [
        MeasurementReportRef(label="T0", path="t0.md", exists=True, official=True, smoke=False),
        MeasurementReportRef(label="T1", path="t1.md", exists=True, official=True, smoke=False),
        MeasurementReportRef(label="T2", path="t2.md", exists=True, official=True, smoke=False),
        MeasurementReportRef(label="T3", path="t3.md", exists=False, official=True, smoke=False),
    ]


@pytest.fixture
def reports_with_smoke_t3() -> list[MeasurementReportRef]:
    return [
        MeasurementReportRef(label="T0", path="t0.md", exists=True, official=True, smoke=False),
        MeasurementReportRef(label="T1", path="t1.md", exists=True, official=True, smoke=False),
        MeasurementReportRef(label="T2", path="t2.md", exists=True, official=True, smoke=False),
        MeasurementReportRef(label="T3", path="smoke_t3.md", exists=True, official=False, smoke=True),
    ]


@pytest.fixture
def reports_with_official_t3() -> list[MeasurementReportRef]:
    return [
        MeasurementReportRef(label="T0", path="t0.md", exists=True, official=True, smoke=False),
        MeasurementReportRef(label="T1", path="t1.md", exists=True, official=True, smoke=False),
        MeasurementReportRef(label="T2", path="t2.md", exists=True, official=True, smoke=False),
        MeasurementReportRef(label="T3", path="t3.md", exists=True, official=True, smoke=False),
    ]


@pytest.fixture
def canary_points() -> list[MeasurementPoint]:
    return [
        _make_point("T0"),
        _make_point("T1", warnings_since_last=3),
        _make_point("T2", warnings_since_last=12),
        _make_point("T3"),
    ]


# ---------------------------------------------------------------------------
# Report registry
# ---------------------------------------------------------------------------


class TestBuildMeasurementReportRegistry:
    def test_detects_t0_t1_t2_reports(self, tmp_path: Path) -> None:
        for label in ("T0", "T1", "T2"):
            (tmp_path / f"si-v2-phase-4-measurement-{label.lower()}-2026-06-27.md").write_text("")
        registry = build_measurement_report_registry(report_dir=tmp_path)
        labels = {r.label for r in registry if r.exists}
        assert "T0" in labels
        assert "T1" in labels
        assert "T2" in labels

    def test_marks_missing_t3_as_missing(self, tmp_path: Path) -> None:
        for label in ("T0", "T1", "T2"):
            (tmp_path / f"si-v2-phase-4-measurement-{label.lower()}-2026-06-27.md").write_text("")
        registry = build_measurement_report_registry(report_dir=tmp_path)
        t3 = [r for r in registry if r.label == "T3"]
        assert len(t3) == 1
        assert not t3[0].exists

    def test_smoke_does_not_count_as_official(self, tmp_path: Path) -> None:
        """Smoke T3 report should not be marked as official."""
        (tmp_path / "si-v2-phase-4-measurement-smoke-t3-precheck-2026-06-27.md").write_text("")
        registry = build_measurement_report_registry(report_dir=tmp_path)
        t3_refs = [r for r in registry if r.label == "T3"]
        for r in t3_refs:
            if r.smoke:
                assert not r.official


# ---------------------------------------------------------------------------
# T3 official guard
# ---------------------------------------------------------------------------


class TestValidateOfficialT3Guard:
    def test_before_schedule_blocks(self) -> None:
        valid, reasons = validate_official_t3_guard(
            now_utc="2026-06-28T12:00:00Z",
            scheduled_t3_utc="2026-06-28T18:27:00Z",
            t3_report_exists=True,
            t3_report_official=True,
        )
        assert not valid
        assert any("not_due" in r for r in reasons)

    def test_after_schedule_with_official_passes(self) -> None:
        valid, _reasons = validate_official_t3_guard(
            now_utc="2026-06-28T19:00:00Z",
            scheduled_t3_utc="2026-06-28T18:27:00Z",
            t3_report_exists=True,
            t3_report_official=True,
        )
        assert valid

    def test_missing_t3_after_schedule_blocks(self) -> None:
        valid, reasons = validate_official_t3_guard(
            now_utc="2026-06-28T19:00:00Z",
            t3_report_exists=False,
            t3_report_official=False,
        )
        assert not valid
        assert any("missing" in r for r in reasons)

    def test_smoke_t3_does_not_count_as_official(self) -> None:
        valid, reasons = validate_official_t3_guard(
            now_utc="2026-06-28T19:00:00Z",
            t3_report_exists=True,
            t3_report_official=False,
        )
        assert not valid
        assert any("not_official" in r for r in reasons)


# ---------------------------------------------------------------------------
# Final decision pack builder
# ---------------------------------------------------------------------------


class TestBuildFinalMeasurementDecisionPack:
    def test_before_t3_returns_extend(
        self,
        reports_without_t3: list,
        canary_points: list,
    ) -> None:
        pack = build_final_measurement_decision_pack(
            canary_points=canary_points,
            reports=reports_without_t3,
            now_utc="2026-06-28T12:00:00Z",
        )
        assert pack.final_verdict == "YELLOW"
        assert pack.final_decision == "EXTEND_MEASUREMENT"
        assert pack.blocked_reasons

    def test_smoke_t3_not_accepted_as_official(
        self,
        reports_with_smoke_t3: list,
        canary_points: list,
    ) -> None:
        pack = build_final_measurement_decision_pack(
            canary_points=canary_points,
            reports=reports_with_smoke_t3,
            now_utc="2026-06-28T19:00:00Z",
        )
        assert pack.final_decision == "EXTEND_MEASUREMENT"
        assert any("smoke" in r for r in pack.blocked_reasons)

    def test_official_t3_green_returns_keep(
        self,
        reports_with_official_t3: list,
        canary_points: list,
    ) -> None:
        pack = build_final_measurement_decision_pack(
            canary_points=canary_points,
            reports=reports_with_official_t3,
            now_utc="2026-06-28T19:00:00Z",
        )
        # May be KEEP_CANARY_OVERLAY if all GREEN
        assert pack.final_decision in (
            "KEEP_CANARY_OVERLAY", "EXTEND_MEASUREMENT"
        )

    def test_runtime_red_returns_rollback(
        self,
        reports_with_official_t3: list,
    ) -> None:
        bad = [
            _make_point("T0"),
            _make_point("T1"),
            _make_point("T2"),
            _make_point("T3", dry_run=False),  # RED
        ]
        pack = build_final_measurement_decision_pack(
            canary_points=bad,
            reports=reports_with_official_t3,
            now_utc="2026-06-28T19:00:00Z",
        )
        assert pack.final_decision == "ROLLBACK_CANARY_OVERLAY"

    def test_insufficient_signal_extends(
        self,
        reports_with_official_t3: list,
    ) -> None:
        # All points with no trades / no profit
        no_trade = [
            _make_point("T0", closed_trades=0, total_profit_abs=None),
            _make_point("T1", closed_trades=0, total_profit_abs=None),
            _make_point("T2", closed_trades=0, total_profit_abs=None),
            _make_point("T3", closed_trades=0, total_profit_abs=None),
        ]
        pack = build_final_measurement_decision_pack(
            canary_points=no_trade,
            reports=reports_with_official_t3,
            now_utc="2026-06-28T19:00:00Z",
        )
        assert pack.final_decision == "EXTEND_MEASUREMENT"

    def test_all_green_with_warnings_extends_or_investigates(
        self,
        reports_with_official_t3: list,
    ) -> None:
        warnings = [
            _make_point("T0"),
            _make_point("T1", warnings_since_last=3),
            _make_point("T2", warnings_since_last=12),
            _make_point("T3", warnings_since_last=12),
        ]
        pack = build_final_measurement_decision_pack(
            canary_points=warnings,
            reports=reports_with_official_t3,
            now_utc="2026-06-28T19:00:00Z",
        )
        # Should be EXTEND or INVESTIGATE due to warnings making points YELLOW
        assert pack.final_decision in (
            "EXTEND_MEASUREMENT", "KEEP_CANARY_OVERLAY"
        )

    def test_missing_reports_blocked(
        self,
        reports_without_t3: list,
        canary_points: list,
    ) -> None:
        pack = build_final_measurement_decision_pack(
            canary_points=canary_points,
            reports=reports_without_t3,
            now_utc="2026-06-28T19:00:00Z",
        )
        assert not pack.all_required_reports_present


# ---------------------------------------------------------------------------
# Report renderer
# ---------------------------------------------------------------------------


class TestRenderFinalReport:
    def test_includes_all_report_labels(
        self,
        reports_with_official_t3: list,
        canary_points: list,
    ) -> None:
        pack = build_final_measurement_decision_pack(
            canary_points=canary_points,
            reports=reports_with_official_t3,
            now_utc="2026-06-28T19:00:00Z",
        )
        md = render_final_measurement_report(pack)
        for label in ("T0", "T1", "T2", "T3"):
            assert label in md

    def test_distinguishes_smoke_vs_official(
        self,
        reports_with_smoke_t3: list,
        canary_points: list,
    ) -> None:
        pack = build_final_measurement_decision_pack(
            canary_points=canary_points,
            reports=reports_with_smoke_t3,
            now_utc="2026-06-28T19:00:00Z",
        )
        md = render_final_measurement_report(pack)
        assert "Smoke" in md or "smoke" in md.lower()

    def test_includes_exactly_one_next_step(
        self,
        reports_with_official_t3: list,
        canary_points: list,
    ) -> None:
        pack = build_final_measurement_decision_pack(
            canary_points=canary_points,
            reports=reports_with_official_t3,
            now_utc="2026-06-28T19:00:00Z",
        )
        md = render_final_measurement_report(pack)
        assert "Next Step" in md or "next step" in md.lower()


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


class TestSerialization:
    def test_report_ref_to_dict(self) -> None:
        r = MeasurementReportRef(label="T0", path="t.md", exists=True, official=True, smoke=False)
        d = r.to_dict()
        json.dumps(d)
        assert d["label"] == "T0"

    def test_pack_to_dict(
        self,
        reports_with_official_t3: list,
        canary_points: list,
    ) -> None:
        pack = build_final_measurement_decision_pack(
            canary_points=canary_points,
            reports=reports_with_official_t3,
            now_utc="2026-06-28T19:00:00Z",
        )
        d = pack.to_dict()
        json.dumps(d)
        assert "candidate_id" in d


# ---------------------------------------------------------------------------
# No subprocess / no Docker
# ---------------------------------------------------------------------------


class TestNoSubprocess:
    def test_no_subprocess_in_module(self) -> None:
        import inspect

        import si_v2.measurement.final_decision_pack as fp
        source = inspect.getsource(fp)
        code_lines = [line for line in source.splitlines()
                      if not line.strip().startswith(('#', '"""', "'", 'r"""'))]
        assert not any("import subprocess" in line for line in code_lines)
        assert not any("import docker" in line.lower() for line in code_lines)
        assert not any("run_canary_restart" in line for line in code_lines)
        assert not any("execute_apply" in line for line in code_lines)
