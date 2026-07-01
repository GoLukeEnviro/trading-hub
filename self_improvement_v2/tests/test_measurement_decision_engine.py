r"""Tests for the measurement decision engine (Phase 4A).

Pure Python — no subprocess, no Docker, no runtime mutation.
"""

from __future__ import annotations

import json
from typing import Literal

import pytest

from si_v2.measurement.decision_engine import (
    EXPECTED_BOT_ID,
    MeasurementDecision,
    MeasurementPoint,
    compare_canary_to_control,
    decide_final_measurement,
    decide_measurement_point,
    evaluate_measurement_safety,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_point(
    label: Literal["T0", "T1", "T2", "T3"] = "T0",
    *,
    runtime_proof_status: str = "GREEN",
    max_open_trades: int | None = 2,
    dry_run: bool | None = True,
    container_healthy: bool | None = True,
    open_trades: int | None = 0,
    closed_trades: int | None = 59,
    total_profit_abs: float | None = 3.98,
    realized_profit_abs: float | None = 3.98,
    win_rate: float | None = 0.898,
    drawdown_abs: float | None = 0.0,
    errors_since_last: int | None = 0,
    warnings_since_last: int | None = 0,
    unexpected_restart: bool = False,
    rollback_required: bool = False,
) -> MeasurementPoint:
    return MeasurementPoint(
        label=label,
        timestamp_utc="2026-06-27T18:27:00Z",
        bot_id=EXPECTED_BOT_ID,
        candidate_id="max_open_trades_3_to_2",
        runtime_proof_status=runtime_proof_status,
        max_open_trades=max_open_trades,
        dry_run=dry_run,
        container_healthy=container_healthy,
        open_trades=open_trades,
        closed_trades=closed_trades,
        total_profit_abs=total_profit_abs,
        realized_profit_abs=realized_profit_abs,
        win_rate=win_rate,
        drawdown_abs=drawdown_abs,
        errors_since_last=errors_since_last,
        warnings_since_last=warnings_since_last,
        unexpected_restart=unexpected_restart,
        rollback_required=rollback_required,
    )


def _make_control_point(
    label: Literal["T0", "T1", "T2", "T3"] = "T0",
    *,
    runtime_proof_status: str = "GREEN",
    max_open_trades: int | None = 5,
    dry_run: bool | None = True,
    container_healthy: bool | None = True,
    open_trades: int | None = 0,
    closed_trades: int | None = 78,
    total_profit_abs: float | None = 24.78,
    realized_profit_abs: float | None = 24.78,
    win_rate: float | None = 0.795,
    drawdown_abs: float | None = 0.0,
    errors_since_last: int | None = 0,
    warnings_since_last: int | None = 0,
    unexpected_restart: bool = False,
    rollback_required: bool = False,
) -> MeasurementPoint:
    return MeasurementPoint(
        label=label,
        timestamp_utc="2026-06-27T18:27:00Z",
        bot_id="freqtrade-freqforge",
        candidate_id="max_open_trades_3_to_2",
        runtime_proof_status=runtime_proof_status,
        max_open_trades=max_open_trades,
        dry_run=dry_run,
        container_healthy=container_healthy,
        open_trades=open_trades,
        closed_trades=closed_trades,
        total_profit_abs=total_profit_abs,
        realized_profit_abs=realized_profit_abs,
        win_rate=win_rate,
        drawdown_abs=drawdown_abs,
        errors_since_last=errors_since_last,
        warnings_since_last=warnings_since_last,
        unexpected_restart=unexpected_restart,
        rollback_required=rollback_required,
    )


@pytest.fixture
def t0_green() -> MeasurementPoint:
    return _make_point("T0", closed_trades=59, total_profit_abs=3.98)


@pytest.fixture
def t1_green() -> MeasurementPoint:
    return _make_point("T1", closed_trades=61, total_profit_abs=4.50, errors_since_last=0)


@pytest.fixture
def t1_yellow_no_trades() -> MeasurementPoint:
    return _make_point("T1", closed_trades=0, total_profit_abs=None)


@pytest.fixture
def control_t0() -> MeasurementPoint:
    return MeasurementPoint(
        label="T0",
        timestamp_utc="2026-06-27T18:27:00Z",
        bot_id="freqtrade-freqforge",
        candidate_id="",
        runtime_proof_status="GREEN",
        max_open_trades=3,
        dry_run=True,
        container_healthy=True,
        open_trades=0,
        closed_trades=78,
        total_profit_abs=24.78,
        realized_profit_abs=24.78,
        win_rate=0.795,
        drawdown_abs=0.0,
        errors_since_last=0,
        warnings_since_last=0,
        unexpected_restart=False,
        rollback_required=False,
    )


@pytest.fixture
def control_t1() -> MeasurementPoint:
    return MeasurementPoint(
        label="T1",
        timestamp_utc="2026-06-27T19:27:00Z",
        bot_id="freqtrade-freqforge",
        candidate_id="",
        runtime_proof_status="GREEN",
        max_open_trades=3,
        dry_run=True,
        container_healthy=True,
        open_trades=0,
        closed_trades=80,
        total_profit_abs=25.50,
        realized_profit_abs=25.50,
        win_rate=0.80,
        drawdown_abs=0.0,
        errors_since_last=0,
        warnings_since_last=0,
        unexpected_restart=False,
        rollback_required=False,
    )


# ---------------------------------------------------------------------------
# evaluate_measurement_safety
# ---------------------------------------------------------------------------


class TestEvaluateMeasurementSafety:
    def test_green_when_all_ok(self, t0_green: MeasurementPoint) -> None:
        d = evaluate_measurement_safety(t0_green)
        assert d.verdict == "GREEN"
        assert d.decision in ("CONTINUE_MEASUREMENT", "KEEP_CANARY_OVERLAY")

    def test_red_when_dry_run_false(self) -> None:
        p = _make_point(dry_run=False)
        d = evaluate_measurement_safety(p)
        assert d.verdict == "RED"
        assert any("dry_run" in r for r in d.reasons)

    def test_red_when_max_open_trades_not_2(self) -> None:
        p = _make_point(max_open_trades=3)
        d = evaluate_measurement_safety(p)
        assert d.verdict == "RED"
        assert any("max_open_trades=3" in r for r in d.reasons)

    def test_red_when_runtime_proof_not_green(self) -> None:
        p = _make_point(runtime_proof_status="RED")
        d = evaluate_measurement_safety(p)
        assert d.verdict == "RED"
        assert any("RED" in r for r in d.reasons)

    def test_red_when_container_unhealthy(self) -> None:
        p = _make_point(container_healthy=False)
        d = evaluate_measurement_safety(p)
        assert d.verdict == "RED"
        assert any("unhealthy" in r for r in d.reasons)

    def test_red_when_unexpected_restart(self) -> None:
        p = _make_point(unexpected_restart=True)
        d = evaluate_measurement_safety(p)
        assert d.verdict == "RED"
        assert any("restart" in r for r in d.reasons)

    def test_red_when_rollback_required(self) -> None:
        p = _make_point(rollback_required=True)
        d = evaluate_measurement_safety(p)
        assert d.verdict == "RED"
        assert any("rollback_required" in r for r in d.reasons)

    def test_yellow_when_no_trades(self) -> None:
        p = _make_point(closed_trades=0, total_profit_abs=None)
        d = evaluate_measurement_safety(p)
        assert d.verdict == "YELLOW"

    def test_yellow_when_errors(self) -> None:
        p = _make_point(errors_since_last=3)
        d = evaluate_measurement_safety(p)
        assert d.verdict == "YELLOW"


# ---------------------------------------------------------------------------
# compare_canary_to_control
# ---------------------------------------------------------------------------


class TestCompareCanaryToControl:
    def test_computes_profit_delta(
        self, t0_green: MeasurementPoint, t1_green: MeasurementPoint
    ) -> None:
        c = compare_canary_to_control(t0_green, t1_green)
        assert c.canary_delta_profit_abs is not None
        assert c.canary_delta_trades is not None

    def test_computes_trade_delta(self, t0_green: MeasurementPoint, t1_green: MeasurementPoint) -> None:
        c = compare_canary_to_control(t0_green, t1_green)
        assert c.canary_delta_trades is not None
        assert c.canary_delta_trades == 2  # 61 - 59

    def test_handles_none_values_safely(self) -> None:
        null = _make_point(closed_trades=None, total_profit_abs=None)
        c = compare_canary_to_control(null, null)
        assert c.canary_delta_profit_abs is None
        assert c.canary_delta_trades is None
        assert c.control_delta_profit_abs is None
        assert c.control_delta_trades is None

    def test_with_control(
        self,
        t0_green: MeasurementPoint,
        t1_green: MeasurementPoint,
        control_t0: MeasurementPoint,
        control_t1: MeasurementPoint,
    ) -> None:
        c = compare_canary_to_control(t0_green, t1_green, control_t0, control_t1)
        assert c.control_delta_profit_abs is not None
        assert c.control_delta_trades is not None
        assert c.canary_vs_control_profit_gap is not None

    def test_no_control(
        self, t0_green: MeasurementPoint, t1_green: MeasurementPoint
    ) -> None:
        c = compare_canary_to_control(t0_green, t1_green)
        assert c.control_delta_profit_abs is None
        assert c.control_delta_trades is None


# ---------------------------------------------------------------------------
# decide_measurement_point
# ---------------------------------------------------------------------------


class TestDecideMeasurementPoint:
    def test_t1_green(
        self, t0_green: MeasurementPoint, t1_green: MeasurementPoint
    ) -> None:
        d = decide_measurement_point(
            label="T1",
            canary_previous=t0_green,
            canary_current=t1_green,
        )
        assert d.verdict == "GREEN"
        assert d.decision == "CONTINUE_MEASUREMENT"

    def test_t1_yellow_no_trades(self, t0_green: MeasurementPoint) -> None:
        d = decide_measurement_point(
            label="T1",
            canary_previous=t0_green,
            canary_current=_make_point("T1", closed_trades=0, total_profit_abs=None),
        )
        assert d.verdict == "YELLOW"
        assert d.decision == "CONTINUE_MEASUREMENT"

    def test_t1_red_when_dry_run_false(self, t0_green: MeasurementPoint) -> None:
        d = decide_measurement_point(
            label="T1",
            canary_previous=t0_green,
            canary_current=_make_point("T1", dry_run=False),
        )
        assert d.verdict == "RED"
        assert d.decision == "ROLLBACK_CANARY_OVERLAY"

    def test_t2_yellow_weak_signal(self, t0_green: MeasurementPoint) -> None:
        weak = _make_point("T2", closed_trades=60, total_profit_abs=4.0, errors_since_last=2)
        d = decide_measurement_point(
            label="T2",
            canary_previous=t0_green,
            canary_current=weak,
        )
        assert d.verdict == "YELLOW"
        assert d.decision == "CONTINUE_MEASUREMENT"

    def test_t2_green_stable(
        self, t0_green: MeasurementPoint, t1_green: MeasurementPoint
    ) -> None:
        d = decide_measurement_point(
            label="T2",
            canary_previous=t1_green,
            canary_current=_make_point("T2", closed_trades=63, total_profit_abs=5.20),
        )
        assert d.verdict == "GREEN"

    def test_t2_red_runtime_failure(self, t0_green: MeasurementPoint) -> None:
        d = decide_measurement_point(
            label="T2",
            canary_previous=t0_green,
            canary_current=_make_point("T2", runtime_proof_status="RED"),
        )
        assert d.verdict == "RED"

    def test_t3_keep_canary(
        self, t0_green: MeasurementPoint
    ) -> None:
        t3 = _make_point("T3", closed_trades=65, total_profit_abs=6.0)
        d = decide_measurement_point(
            label="T3",
            canary_previous=t0_green,
            canary_current=t3,
        )
        assert d.verdict == "GREEN"
        assert d.decision == "KEEP_CANARY_OVERLAY"

    def test_t3_extend_on_yellow(self, t0_green: MeasurementPoint) -> None:
        t3 = _make_point("T3", closed_trades=0, total_profit_abs=None)
        d = decide_measurement_point(
            label="T3",
            canary_previous=t0_green,
            canary_current=t3,
        )
        assert d.verdict == "YELLOW"
        assert d.decision == "EXTEND_MEASUREMENT"

    def test_t3_rollback_on_red(self, t0_green: MeasurementPoint) -> None:
        t3 = _make_point("T3", dry_run=False)
        d = decide_measurement_point(
            label="T3",
            canary_previous=t0_green,
            canary_current=t3,
        )
        assert d.verdict == "RED"
        assert d.decision == "ROLLBACK_CANARY_OVERLAY"


# ---------------------------------------------------------------------------
# decide_final_measurement
# ---------------------------------------------------------------------------


class TestDecideFinalMeasurement:
    def test_rejects_missing_t0(self) -> None:
        d = decide_final_measurement(canary_points=[])
        assert d.verdict == "YELLOW"
        assert "incomplete_data" in d.reasons[0]

    def test_rejects_incomplete_sequence(self) -> None:
        d = decide_final_measurement(canary_points=[_make_point("T0")])
        assert d.verdict == "YELLOW"
        assert "incomplete_data" in d.reasons[0]

    def test_keep_on_stable_green_sequence(self) -> None:
        points = [
            _make_point("T0"),
            _make_point("T1", closed_trades=61, total_profit_abs=4.5),
            _make_point("T2", closed_trades=63, total_profit_abs=5.2),
            _make_point("T3", closed_trades=65, total_profit_abs=6.0),
        ]
        d = decide_final_measurement(canary_points=points)
        assert d.verdict == "GREEN"
        assert d.decision == "KEEP_CANARY_OVERLAY"

    def test_extend_on_inconclusive(self) -> None:
        points = [
            _make_point("T0"),
            _make_point("T1", closed_trades=0, total_profit_abs=None),
            _make_point("T2", closed_trades=0, total_profit_abs=None),
            _make_point("T3", closed_trades=0, total_profit_abs=None),
        ]
        d = decide_final_measurement(canary_points=points)
        assert d.verdict == "YELLOW"
        assert d.decision == "EXTEND_MEASUREMENT"

    def test_rollback_on_safety_red(self) -> None:
        points = [
            _make_point("T0"),
            _make_point("T1"),
            _make_point("T2", dry_run=False),
            _make_point("T3"),
        ]
        d = decide_final_measurement(canary_points=points)
        assert d.verdict == "RED"
        assert d.decision == "ROLLBACK_CANARY_OVERLAY"

    def test_handles_missing_control_as_not_crash(self) -> None:
        points = [
            _make_point("T0"),
            _make_point("T1", closed_trades=61, total_profit_abs=4.5),
            _make_point("T2", closed_trades=63, total_profit_abs=5.2),
            _make_point("T3", closed_trades=65, total_profit_abs=6.0),
        ]
        # Should work without control points
        d = decide_final_measurement(canary_points=points, control_points=None)
        assert d.verdict in ("GREEN", "YELLOW")

    def test_with_control_points(
        self,
        t0_green: MeasurementPoint,
        control_t0: MeasurementPoint,
        control_t1: MeasurementPoint,
    ) -> None:
        canary_points = [
            t0_green,
            _make_point("T1", closed_trades=61, total_profit_abs=4.5),
            _make_point("T2", closed_trades=63, total_profit_abs=5.2),
            _make_point("T3", closed_trades=65, total_profit_abs=6.0),
        ]
        control_points = [
            control_t0,
            control_t1,
            MeasurementPoint(
                label="T2", timestamp_utc="", bot_id="freqtrade-freqforge",
                candidate_id="", runtime_proof_status="GREEN",
                max_open_trades=3, dry_run=True, container_healthy=True,
                open_trades=0, closed_trades=82, total_profit_abs=26.0,
                realized_profit_abs=26.0, win_rate=0.80, drawdown_abs=0.0,
                errors_since_last=0, warnings_since_last=0,
                unexpected_restart=False, rollback_required=False,
            ),
            MeasurementPoint(
                label="T3", timestamp_utc="", bot_id="freqtrade-freqforge",
                candidate_id="", runtime_proof_status="GREEN",
                max_open_trades=3, dry_run=True, container_healthy=True,
                open_trades=0, closed_trades=84, total_profit_abs=26.0,
                realized_profit_abs=26.0, win_rate=0.81, drawdown_abs=0.0,
                errors_since_last=0, warnings_since_last=0,
                unexpected_restart=False, rollback_required=False,
            ),
        ]
        d = decide_final_measurement(canary_points=canary_points, control_points=control_points)
        assert d.decision == "KEEP_CANARY_OVERLAY"

    def test_final_decision_keeps_when_only_historical_noncritical_warnings_and_canary_outperforms_control(self) -> None:
        canary_points = [
            _make_point("T0", closed_trades=59, total_profit_abs=3.98),
            _make_point("T1", closed_trades=59, total_profit_abs=3.98, warnings_since_last=3),
            _make_point("T2", closed_trades=59, total_profit_abs=3.98, warnings_since_last=12),
            _make_point(
                "T3",
                closed_trades=61,
                total_profit_abs=3.98311161,
                warnings_since_last=0,
                container_healthy=None,
            ),
        ]
        control_points = [
            _make_control_point("T0", closed_trades=78, total_profit_abs=24.78),
            _make_control_point("T1", closed_trades=78, total_profit_abs=24.78),
            _make_control_point("T2", closed_trades=78, total_profit_abs=24.78),
            _make_control_point("T3", closed_trades=81, total_profit_abs=3.33600672),
        ]

        d = decide_final_measurement(
            canary_points=canary_points,
            control_points=control_points,
        )

        assert d.verdict == "GREEN"
        assert d.decision == "KEEP_CANARY_OVERLAY"
        assert any("profit_gap" in reason for reason in d.reasons)

    def test_final_decision_extends_when_canary_underperforms_control(self) -> None:
        canary_points = [
            _make_point("T0", closed_trades=59, total_profit_abs=3.98),
            _make_point("T1", closed_trades=60, total_profit_abs=3.90, warnings_since_last=3),
            _make_point("T2", closed_trades=60, total_profit_abs=3.80, warnings_since_last=12),
            _make_point("T3", closed_trades=61, total_profit_abs=3.50, container_healthy=None),
        ]
        control_points = [
            _make_control_point("T0", closed_trades=78, total_profit_abs=24.78),
            _make_control_point("T1", closed_trades=79, total_profit_abs=25.10),
            _make_control_point("T2", closed_trades=80, total_profit_abs=25.80),
            _make_control_point("T3", closed_trades=81, total_profit_abs=26.50),
        ]

        d = decide_final_measurement(
            canary_points=canary_points,
            control_points=control_points,
        )

        assert d.verdict == "YELLOW"
        assert d.decision == "EXTEND_MEASUREMENT"
        assert any("underperform" in reason for reason in d.reasons)

    def test_final_decision_rolls_back_on_rollback_required_even_if_profit_positive(self) -> None:
        canary_points = [
            _make_point("T0", closed_trades=59, total_profit_abs=3.98),
            _make_point("T1", closed_trades=61, total_profit_abs=4.50),
            _make_point("T2", closed_trades=63, total_profit_abs=5.20),
            _make_point("T3", closed_trades=65, total_profit_abs=8.00, rollback_required=True),
        ]

        d = decide_final_measurement(canary_points=canary_points)

        assert d.verdict == "RED"
        assert d.decision == "ROLLBACK_CANARY_OVERLAY"
        assert any("rollback_required" in reason for reason in d.reasons)

    def test_container_health_unknown_from_read_only_mode_is_not_hard_blocker(self) -> None:
        canary_points = [
            _make_point("T0", closed_trades=59, total_profit_abs=3.98),
            _make_point("T1", closed_trades=61, total_profit_abs=4.50),
            _make_point("T2", closed_trades=63, total_profit_abs=5.20, warnings_since_last=2),
            _make_point("T3", closed_trades=65, total_profit_abs=6.00, container_healthy=None),
        ]

        d = decide_final_measurement(canary_points=canary_points)

        assert d.decision == "KEEP_CANARY_OVERLAY"
        assert d.verdict == "GREEN"

    def test_final_decision_extends_when_runtime_proof_missing(self) -> None:
        canary_points = [
            _make_point("T0", closed_trades=59, total_profit_abs=3.98),
            _make_point("T1", closed_trades=61, total_profit_abs=4.50),
            _make_point("T2", closed_trades=63, total_profit_abs=5.20),
            _make_point("T3", closed_trades=65, total_profit_abs=6.00, runtime_proof_status=""),
        ]

        d = decide_final_measurement(canary_points=canary_points)

        assert d.verdict == "YELLOW"
        assert d.decision == "EXTEND_MEASUREMENT"
        assert any("runtime proof not checked" in reason for reason in d.reasons)

    def test_dry_run_false_remains_hard_safety_blocker(self) -> None:
        canary_points = [
            _make_point("T0"),
            _make_point("T1", closed_trades=61, total_profit_abs=4.50),
            _make_point("T2", closed_trades=63, total_profit_abs=5.20),
            _make_point("T3", closed_trades=65, total_profit_abs=6.00, dry_run=False),
        ]

        d = decide_final_measurement(canary_points=canary_points)

        assert d.verdict == "RED"
        assert d.decision == "ROLLBACK_CANARY_OVERLAY"
        assert any("dry_run" in reason for reason in d.reasons)


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


class TestSerialization:
    def test_decision_to_dict(self) -> None:
        d = MeasurementDecision(
            verdict="GREEN",
            decision="CONTINUE_MEASUREMENT",
            confidence="HIGH",
            reasons=("all good",),
            next_step="Keep measuring.",
        )
        data = d.to_dict()
        json.dumps(data)
        assert data["verdict"] == "GREEN"

    def test_point_to_dict(self, t0_green: MeasurementPoint) -> None:
        data = t0_green.to_dict()
        json.dumps(data)
        assert data["label"] == "T0"

    def test_comparison_to_dict(self, t0_green: MeasurementPoint, t1_green: MeasurementPoint) -> None:
        c = compare_canary_to_control(t0_green, t1_green)
        data = c.to_dict()
        json.dumps(data)
        assert "canary_delta_profit_abs" in data


# ---------------------------------------------------------------------------
# Confidence strictness
# ---------------------------------------------------------------------------


class TestConfidenceStrictness:
    def test_confidence_is_low_medium_high_only(self) -> None:
        for val in ("LOW", "MEDIUM", "HIGH"):
            d = MeasurementDecision(
                verdict="GREEN",
                decision="CONTINUE_MEASUREMENT",
                confidence=val,  # type: ignore[arg-type]
                reasons=(),
                next_step="test",
            )
            assert d.confidence in ("LOW", "MEDIUM", "HIGH")


# ---------------------------------------------------------------------------
# No subprocess / No Docker
# ---------------------------------------------------------------------------


class TestNoSubprocess:
    def test_no_subprocess_in_imports(self) -> None:
        """Verify the module does not import runtime-mutation or subprocess modules."""
        import inspect

        import si_v2.measurement.decision_engine as de
        source = inspect.getsource(de)
        code_lines = [line for line in source.splitlines()
                      if not line.strip().startswith(('#', '"""', "'", 'r"""'))]
        assert not any("import subprocess" in line for line in code_lines), "subprocess import detected"
        assert not any("run_canary_restart" in line for line in code_lines)
        assert not any("execute_apply" in line for line in code_lines)
        assert not any("import docker" in line for line in code_lines)

    def test_no_mutation_functions_imported(self) -> None:
        """Verify decision engine imports no runtime-mutation functions."""
        import inspect

        import si_v2.measurement.decision_engine as de
        source = inspect.getsource(de)
        assert "run_canary_restart_with_overlay" not in source
        assert "execute_canary_restart" not in source


# ---------------------------------------------------------------------------
# Next step is actionable
# ---------------------------------------------------------------------------


class TestNextStepActionable:
    def test_next_step_is_single_instruction(self, t0_green: MeasurementPoint) -> None:
        d = evaluate_measurement_safety(t0_green)
        assert len(d.next_step) > 0
        assert isinstance(d.next_step, str)
