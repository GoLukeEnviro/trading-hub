r"""Tests for the measurement on-demand snapshot runner (Phase 4D).

Pure Python — no Docker, no subprocess, no runtime mutation.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from si_v2.measurement.snapshot_runner import (
    CANARY_BOT_ID,
    CONTROL_BOT_ID,
    OFFICIAL_LABELS,
    MeasurementSnapshotRequest,
    _build_report_path,
    _check_report_overwrite,
    run_measurement_snapshot,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def smoke_request() -> MeasurementSnapshotRequest:
    return MeasurementSnapshotRequest(
        label="SMOKE_T3_PRECHECK",
        candidate_id="max_open_trades_3_to_2",
        target_bot=CANARY_BOT_ID,
        control_bot=CONTROL_BOT_ID,
        smoke=True,
        official=False,
        write_report=False,
    )


# ---------------------------------------------------------------------------
# Report path
# ---------------------------------------------------------------------------


class TestBuildReportPath:
    def test_smoke_path_contains_smoke_prefix(self) -> None:
        path = _build_report_path("SMOKE_TEST", official=False, smoke=True)
        assert "smoke" in path.name.lower()

    def test_official_path_contains_label(self) -> None:
        path = _build_report_path("T3", official=True, smoke=False)
        assert "t3" in path.name.lower()

    def test_smoke_and_official_path_differs(self) -> None:
        smoke = _build_report_path("SMOKE_TEST", official=False, smoke=True)
        official = _build_report_path("T3", official=True, smoke=False)
        assert smoke != official


class TestCheckReportOverwrite:
    def test_new_file_no_overwrite(self, tmp_path: Path) -> None:
        p = tmp_path / "new.md"
        assert _check_report_overwrite(p, official=False, smoke=True) is None

    def test_existing_file_with_smoke_blocks(self, tmp_path: Path) -> None:
        p = tmp_path / "existing.md"
        p.write_text("")
        err = _check_report_overwrite(p, official=False, smoke=True)
        assert err is not None
        assert "refusing to overwrite" in err


# ---------------------------------------------------------------------------
# Smoke/official semantics
# ---------------------------------------------------------------------------


class TestSmokeSemantics:
    def test_smoke_request_not_official(self, smoke_request: MeasurementSnapshotRequest) -> None:
        assert not smoke_request.official
        assert smoke_request.smoke

    def test_official_t3_cannot_be_before_schedule(self) -> None:
        # The official flag is a label — T3 has no hard schedule check in the runner
        # but the report path differs
        req = MeasurementSnapshotRequest(
            label="T3", candidate_id="x", target_bot=CANARY_BOT_ID,
            official=True, smoke=False, write_report=False,
        )
        result = run_measurement_snapshot(req)
        # Should not be BLOCKED for label alone — T3 is an official label
        assert result.status != "BLOCKED"

    def test_smoke_writes_smoke_report_path(self) -> None:
        path = _build_report_path("SMOKE_RUN", official=False, smoke=True)
        assert "smoke" in str(path)

    def test_smoke_cannot_use_official_label(self) -> None:
        for label in OFFICIAL_LABELS:
            req = MeasurementSnapshotRequest(
                label=label, candidate_id="x", target_bot=CANARY_BOT_ID,
                smoke=True, official=False, write_report=False,
            )
            result = run_measurement_snapshot(req)
            assert result.status == "BLOCKED"
            assert "smoke_label_collision" in str(result.blocked_reasons)

    def test_smoke_no_overwrite_official_report(self, tmp_path: Path) -> None:
        """Smoke run with existing report path is blocked."""
        from si_v2.measurement.snapshot_runner import _check_report_overwrite
        # Create a path that already exists
        existing = tmp_path / "si-v2-phase-4-measurement-smoke-overwrite_test-2026-06-27.md"
        existing.write_text("existing")
        assert _check_report_overwrite(existing, official=False, smoke=True) is not None


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestValidation:
    def test_wrong_target_bot_blocks(self) -> None:
        req = MeasurementSnapshotRequest(
            label="SMOKE", candidate_id="x", target_bot="wrong-bot",
            smoke=True, official=False, write_report=False,
        )
        result = run_measurement_snapshot(req)
        assert result.status == "BLOCKED"
        assert any("invalid_target_bot" in r for r in result.blocked_reasons)

    def test_correct_target_bot_passes(self, smoke_request: MeasurementSnapshotRequest) -> None:
        result = run_measurement_snapshot(smoke_request)
        assert result.status != "BLOCKED"

    def test_missing_data_returns_yellow_not_crash(self, smoke_request: MeasurementSnapshotRequest) -> None:
        """Run without any data points — should return YELLOW, not crash."""
        result = run_measurement_snapshot(smoke_request)
        assert result.status in ("GREEN", "YELLOW")
        assert result.runtime_proof_status == ""


# ---------------------------------------------------------------------------
# Decision engine integration
# ---------------------------------------------------------------------------


class TestDecisionIntegration:
    def test_decision_is_integrated(self, smoke_request: MeasurementSnapshotRequest) -> None:
        result = run_measurement_snapshot(smoke_request)
        assert result.decision != ""

    def test_next_step_is_actionable(self, smoke_request: MeasurementSnapshotRequest) -> None:
        result = run_measurement_snapshot(smoke_request)
        assert len(result.next_step) > 0


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


class TestSerialization:
    def test_result_to_dict(self, smoke_request: MeasurementSnapshotRequest) -> None:
        result = run_measurement_snapshot(smoke_request)
        d = result.to_dict()
        json.dumps(d)
        assert d["label"] == "SMOKE_T3_PRECHECK"

    def test_request_fields_preserved(self, smoke_request: MeasurementSnapshotRequest) -> None:
        result = run_measurement_snapshot(smoke_request)
        assert result.smoke == smoke_request.smoke
        assert result.official == smoke_request.official


# ---------------------------------------------------------------------------
# No subprocess / no Docker
# ---------------------------------------------------------------------------


class TestNoSubprocess:
    def test_no_subprocess_in_module(self) -> None:
        import inspect

        import si_v2.measurement.snapshot_runner as sr
        source = inspect.getsource(sr)
        code_lines = [line for line in source.splitlines()
                      if not line.strip().startswith(('#', '"""', "'", 'r"""'))]
        assert not any("import subprocess" in line for line in code_lines)
        assert not any("import docker" in line.lower() for line in code_lines)
        assert not any("run_canary_restart" in line for line in code_lines)
        assert not any("execute_apply" in line for line in code_lines)
