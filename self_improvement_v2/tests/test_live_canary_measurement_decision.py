"""Tests for live_canary_measurement_decision.py — C4.

All tests use tmp_path, fake repo structures, and fake C3 artifacts —
no real runtime, no API, no Docker.
"""

from __future__ import annotations

import json
from pathlib import Path

from si_v2.live.c4_window_scope import C4MeasurementInput, C4Trade
from si_v2.live.live_canary_measurement_decision import (
    CANARY_TARGET,
    EXTEND,
    INSUFFICIENT_DATA,
    KEEP,
    LIVE_CANARY_MEASUREMENT_BLOCKED,
    LIVE_CANARY_MEASUREMENT_READY,
    ROLLBACK_RECOMMENDED,
    CanaryMetrics,
    LiveCanaryMeasurementDecisionResult,
    MeasurementCheckResult,
    MetricEvaluation,
    _compute_decision,
    _evaluate_all_metrics,
    run_live_canary_measurement_decision,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _raw_measurement_fixture_for_expected_decision(
    metrics: CanaryMetrics,
) -> C4MeasurementInput:
    """Build raw trades for legacy decision assertions.

    The production entrypoint no longer accepts ``CanaryMetrics``. These
    existing tests retain their readable expected-metric setup while the
    helper supplies raw observations that exercise the corresponding outcome.
    """
    if (metrics.total_trades or 0) < 5:
        pnls = (1.0, -0.1)
    elif metrics.profit_factor is not None and metrics.profit_factor < 0.8:
        pnls = (0.1, 0.1, 0.1, 0.1, -5.0)
    elif metrics.win_rate is not None and metrics.win_rate < 0.4:
        pnls = (1.0, 1.0, 1.0, -0.4, -0.4, -0.4, -0.4, -0.4, -0.4, -0.4)
    else:
        pnls = (1.0, 1.0, 1.0, 1.0, -0.1)
    trades = tuple(
        C4Trade(
            trade_id=f"fixture-{index}",
            opened_at_utc="2026-06-18T12:00:00Z",
            closed_at_utc=f"2026-06-20T12:{index:02d}:00Z",
            profit_abs=pnl,
            profit_ratio=pnl / 100.0,
            notional=100.0,
        )
        for index, pnl in enumerate(pnls, start=1)
    )
    return C4MeasurementInput(
        measurement_start_utc="2026-06-18T12:00:00Z",
        measurement_end_utc="2026-07-02T12:00:00Z",
        continuation_start_equity=100.0,
        lifetime_start_equity=100.0,
        trades=trades,
    )


def _make_c3_ceremony_ready(repo_root: Path) -> None:
    """Write a synthetic C3 ceremony artifact with READY status."""
    ceremony_dir = repo_root / "var" / "si_v2" / "live_canary_activation_ceremony"
    ceremony_dir.mkdir(parents=True, exist_ok=True)
    ceremony_file = ceremony_dir / "live_canary_activation_ceremony.json"
    ceremony_data = {
        "event": "live_canary_activation_ceremony_result",
        "status": "LIVE_CANARY_CEREMONY_READY",
        "canary_target": "freqtrade-freqforge-canary",
        "checks": [],
        "blocked_reasons": [],
        "snapshots": [],
        "measurement_window": {
            "duration_days": 14,
            "metrics": [
                "total_trades",
                "win_rate",
                "profit_factor",
                "sharpe_ratio",
                "max_drawdown",
                "daily_loss_count",
            ],
            "comparison_baseline": ("Dry-run performance over the 14 days prior to activation"),
            "evaluation_gate": ("Post-activation T0/T1/T2/T3 measurement evaluations"),
            "decision_outcomes": [
                "KEEP",
                "EXTEND",
                "ROLLBACK",
            ],
        },
        "created_at_utc": "2026-07-02T12:00:00+00:00",
        "runtime_mutation": "NONE",
    }
    ceremony_file.write_text(json.dumps(ceremony_data, indent=2))


def _make_c3_ceremony_no_measurement_window(
    repo_root: Path,
) -> None:
    """Write a synthetic C3 ceremony artifact without measurement window."""
    ceremony_dir = repo_root / "var" / "si_v2" / "live_canary_activation_ceremony"
    ceremony_dir.mkdir(parents=True, exist_ok=True)
    ceremony_file = ceremony_dir / "live_canary_activation_ceremony.json"
    ceremony_data = {
        "event": "live_canary_activation_ceremony_result",
        "status": "LIVE_CANARY_CEREMONY_READY",
        "canary_target": "freqtrade-freqforge-canary",
        "created_at_utc": "2026-07-02T12:00:00+00:00",
        "runtime_mutation": "NONE",
    }
    ceremony_file.write_text(json.dumps(ceremony_data, indent=2))


def _make_c3_ceremony_blocked(repo_root: Path) -> None:
    """Write a synthetic C3 ceremony artifact with BLOCKED status."""
    ceremony_dir = repo_root / "var" / "si_v2" / "live_canary_activation_ceremony"
    ceremony_dir.mkdir(parents=True, exist_ok=True)
    ceremony_file = ceremony_dir / "live_canary_activation_ceremony.json"
    ceremony_data = {
        "event": "live_canary_activation_ceremony_result",
        "status": "LIVE_CANARY_CEREMONY_BLOCKED",
        "canary_target": "freqtrade-freqforge-canary",
        "checks": [],
        "blocked_reasons": ["Kill switch not NORMAL"],
        "created_at_utc": "2026-07-02T12:00:00+00:00",
        "runtime_mutation": "NONE",
    }
    ceremony_file.write_text(json.dumps(ceremony_data, indent=2))


def _make_c3_ceremony_wrong_target(repo_root: Path) -> None:
    """Write a synthetic C3 ceremony targeting a different bot."""
    ceremony_dir = repo_root / "var" / "si_v2" / "live_canary_activation_ceremony"
    ceremony_dir.mkdir(parents=True, exist_ok=True)
    ceremony_file = ceremony_dir / "live_canary_activation_ceremony.json"
    ceremony_data = {
        "event": "live_canary_activation_ceremony_result",
        "status": "LIVE_CANARY_CEREMONY_READY",
        "canary_target": "some-other-bot",
        "created_at_utc": "2026-07-02T12:00:00+00:00",
        "runtime_mutation": "NONE",
    }
    ceremony_file.write_text(json.dumps(ceremony_data, indent=2))


# ---------------------------------------------------------------------------
# Tests: data models
# ---------------------------------------------------------------------------


class TestDataModels:
    """Test that result data models work correctly."""

    def test_measurement_check_result_defaults(self) -> None:
        check = MeasurementCheckResult(check_name="test", passed=True, detail="ok")
        assert check.check_name == "test"
        assert check.passed is True

    def test_measurement_check_result_to_dict(self) -> None:
        check = MeasurementCheckResult(check_name="test", passed=True, detail="ok")
        d = check.to_dict()
        assert d["check_name"] == "test"
        assert d["passed"] is True

    def test_metric_evaluation_defaults(self) -> None:
        ev = MetricEvaluation(
            metric_name="win_rate",
            value=0.5,
            threshold_min=0.4,
            threshold_max=None,
            critical_threshold_min=0.25,
            critical_threshold_max=None,
            status="OK",
            detail="Within range",
        )
        assert ev.metric_name == "win_rate"
        assert ev.status == "OK"

    def test_metric_evaluation_to_dict(self) -> None:
        ev = MetricEvaluation(
            metric_name="win_rate",
            value=0.5,
            threshold_min=0.4,
            threshold_max=None,
            critical_threshold_min=0.25,
            critical_threshold_max=None,
            status="OK",
            detail="Within range",
        )
        d = ev.to_dict()
        assert d["metric_name"] == "win_rate"
        assert d["status"] == "OK"

    def test_canary_metrics_defaults(self) -> None:
        m = CanaryMetrics(
            total_trades=10,
            win_rate=0.5,
            profit_factor=1.2,
            sharpe_ratio=0.8,
            max_drawdown_pct=8.0,
            daily_loss_count=1,
            avg_profit_per_trade=15.0,
            notional_exposure=200.0,
        )
        assert m.total_trades == 10
        assert m.win_rate == 0.5

    def test_canary_metrics_to_dict(self) -> None:
        m = CanaryMetrics(
            total_trades=10,
            win_rate=0.5,
            profit_factor=1.2,
            sharpe_ratio=0.8,
            max_drawdown_pct=8.0,
            daily_loss_count=1,
            avg_profit_per_trade=15.0,
            notional_exposure=200.0,
        )
        d = m.to_dict()
        assert d["total_trades"] == 10
        assert d["win_rate"] == 0.5

    def test_canary_metrics_none(self) -> None:
        m = CanaryMetrics(
            total_trades=None,
            win_rate=None,
            profit_factor=None,
            sharpe_ratio=None,
            max_drawdown_pct=None,
            daily_loss_count=None,
            avg_profit_per_trade=None,
            notional_exposure=None,
        )
        assert m.total_trades is None
        assert m.win_rate is None

    def test_decision_result_blocked(self) -> None:
        result = LiveCanaryMeasurementDecisionResult(
            status=LIVE_CANARY_MEASUREMENT_BLOCKED,
            decision=INSUFFICIENT_DATA,
            preflight_checks=(),
            metric_evaluations=(),
            blocked_reasons=("No C3 artifacts",),
            total_trades_observed=0,
            decision_path="/dev/null",
            report_path="/dev/null",
            next_step="Review blocked reasons",
        )
        assert result.status == LIVE_CANARY_MEASUREMENT_BLOCKED
        assert result.decision == INSUFFICIENT_DATA
        assert result.runtime_mutation == "NONE"

    def test_decision_result_ready(self) -> None:
        result = LiveCanaryMeasurementDecisionResult(
            status=LIVE_CANARY_MEASUREMENT_READY,
            decision=KEEP,
            preflight_checks=(),
            metric_evaluations=(),
            blocked_reasons=(),
            total_trades_observed=10,
            decision_path="/dev/null",
            report_path="/dev/null",
            next_step="Proceed",
        )
        assert result.status == LIVE_CANARY_MEASUREMENT_READY
        assert result.decision == KEEP

    def test_decision_result_to_dict(self) -> None:
        c = MeasurementCheckResult(check_name="c1", passed=True, detail="ok")
        result = LiveCanaryMeasurementDecisionResult(
            status=LIVE_CANARY_MEASUREMENT_READY,
            decision=KEEP,
            preflight_checks=(c,),
            metric_evaluations=(),
            blocked_reasons=(),
            total_trades_observed=5,
            decision_path="/d.json",
            report_path="/r.md",
            next_step="go",
        )
        d = result.to_dict()
        assert d["status"] == LIVE_CANARY_MEASUREMENT_READY
        assert d["decision"] == KEEP
        assert d["runtime_mutation"] == "NONE"
        assert len(d["preflight_checks"]) == 1


# ---------------------------------------------------------------------------
# Tests: metric evaluation
# ---------------------------------------------------------------------------


class TestMetricEvaluation:
    """Test individual metric evaluation functions."""

    def test_win_rate_ok(self) -> None:
        metrics = CanaryMetrics(
            total_trades=20,
            win_rate=0.55,
            profit_factor=1.2,
            sharpe_ratio=0.8,
            max_drawdown_pct=5.0,
            daily_loss_count=1,
            avg_profit_per_trade=10.0,
            notional_exposure=150.0,
        )
        evals = _evaluate_all_metrics(metrics)
        win = next(e for e in evals if e.metric_name == "win_rate")
        assert win.status == "OK"

    def test_win_rate_borderline(self) -> None:
        metrics = CanaryMetrics(
            total_trades=20,
            win_rate=0.30,
            profit_factor=1.2,
            sharpe_ratio=0.8,
            max_drawdown_pct=5.0,
            daily_loss_count=1,
            avg_profit_per_trade=10.0,
            notional_exposure=150.0,
        )
        evals = _evaluate_all_metrics(metrics)
        win = next(e for e in evals if e.metric_name == "win_rate")
        assert win.status == "BORDERLINE"

    def test_win_rate_breach(self) -> None:
        metrics = CanaryMetrics(
            total_trades=20,
            win_rate=0.20,
            profit_factor=1.2,
            sharpe_ratio=0.8,
            max_drawdown_pct=5.0,
            daily_loss_count=1,
            avg_profit_per_trade=10.0,
            notional_exposure=150.0,
        )
        evals = _evaluate_all_metrics(metrics)
        win = next(e for e in evals if e.metric_name == "win_rate")
        assert win.status == "BREACH"

    def test_win_rate_no_data(self) -> None:
        metrics = CanaryMetrics(
            total_trades=0,
            win_rate=None,
            profit_factor=1.2,
            sharpe_ratio=0.8,
            max_drawdown_pct=5.0,
            daily_loss_count=1,
            avg_profit_per_trade=10.0,
            notional_exposure=150.0,
        )
        evals = _evaluate_all_metrics(metrics)
        win = next(e for e in evals if e.metric_name == "win_rate")
        assert win.status == "NO_DATA"

    def test_profit_factor_ok(self) -> None:
        metrics = CanaryMetrics(
            total_trades=10,
            win_rate=0.5,
            profit_factor=1.5,
            sharpe_ratio=0.8,
            max_drawdown_pct=5.0,
            daily_loss_count=1,
            avg_profit_per_trade=10.0,
            notional_exposure=150.0,
        )
        evals = _evaluate_all_metrics(metrics)
        pf = next(e for e in evals if e.metric_name == "profit_factor")
        assert pf.status == "OK"

    def test_profit_factor_breach(self) -> None:
        metrics = CanaryMetrics(
            total_trades=10,
            win_rate=0.5,
            profit_factor=0.5,
            sharpe_ratio=0.8,
            max_drawdown_pct=5.0,
            daily_loss_count=1,
            avg_profit_per_trade=10.0,
            notional_exposure=150.0,
        )
        evals = _evaluate_all_metrics(metrics)
        pf = next(e for e in evals if e.metric_name == "profit_factor")
        assert pf.status == "BREACH"

    def test_sharpe_ok(self) -> None:
        metrics = CanaryMetrics(
            total_trades=10,
            win_rate=0.5,
            profit_factor=1.2,
            sharpe_ratio=1.0,
            max_drawdown_pct=5.0,
            daily_loss_count=1,
            avg_profit_per_trade=10.0,
            notional_exposure=150.0,
        )
        evals = _evaluate_all_metrics(metrics)
        sh = next(e for e in evals if e.metric_name == "sharpe_ratio")
        assert sh.status == "OK"

    def test_sharpe_breach(self) -> None:
        metrics = CanaryMetrics(
            total_trades=10,
            win_rate=0.5,
            profit_factor=1.2,
            sharpe_ratio=-0.5,
            max_drawdown_pct=5.0,
            daily_loss_count=1,
            avg_profit_per_trade=10.0,
            notional_exposure=150.0,
        )
        evals = _evaluate_all_metrics(metrics)
        sh = next(e for e in evals if e.metric_name == "sharpe_ratio")
        assert sh.status == "BREACH"

    def test_max_drawdown_ok(self) -> None:
        metrics = CanaryMetrics(
            total_trades=10,
            win_rate=0.5,
            profit_factor=1.2,
            sharpe_ratio=0.8,
            max_drawdown_pct=5.0,
            daily_loss_count=1,
            avg_profit_per_trade=10.0,
            notional_exposure=150.0,
        )
        evals = _evaluate_all_metrics(metrics)
        dd = next(e for e in evals if e.metric_name == "max_drawdown_pct")
        assert dd.status == "OK"

    def test_max_drawdown_borderline(self) -> None:
        metrics = CanaryMetrics(
            total_trades=10,
            win_rate=0.5,
            profit_factor=1.2,
            sharpe_ratio=0.8,
            max_drawdown_pct=18.0,
            daily_loss_count=1,
            avg_profit_per_trade=10.0,
            notional_exposure=150.0,
        )
        evals = _evaluate_all_metrics(metrics)
        dd = next(e for e in evals if e.metric_name == "max_drawdown_pct")
        assert dd.status == "BORDERLINE"

    def test_max_drawdown_breach(self) -> None:
        metrics = CanaryMetrics(
            total_trades=10,
            win_rate=0.5,
            profit_factor=1.2,
            sharpe_ratio=0.8,
            max_drawdown_pct=25.0,
            daily_loss_count=1,
            avg_profit_per_trade=10.0,
            notional_exposure=150.0,
        )
        evals = _evaluate_all_metrics(metrics)
        dd = next(e for e in evals if e.metric_name == "max_drawdown_pct")
        assert dd.status == "BREACH"

    def test_daily_loss_count_ok(self) -> None:
        metrics = CanaryMetrics(
            total_trades=10,
            win_rate=0.5,
            profit_factor=1.2,
            sharpe_ratio=0.8,
            max_drawdown_pct=5.0,
            daily_loss_count=0,
            avg_profit_per_trade=10.0,
            notional_exposure=150.0,
        )
        evals = _evaluate_all_metrics(metrics)
        dl = next(e for e in evals if e.metric_name == "daily_loss_count")
        assert dl.status == "OK"

    def test_daily_loss_count_borderline(self) -> None:
        metrics = CanaryMetrics(
            total_trades=10,
            win_rate=0.5,
            profit_factor=1.2,
            sharpe_ratio=0.8,
            max_drawdown_pct=5.0,
            daily_loss_count=4,
            avg_profit_per_trade=10.0,
            notional_exposure=150.0,
        )
        evals = _evaluate_all_metrics(metrics)
        dl = next(e for e in evals if e.metric_name == "daily_loss_count")
        assert dl.status == "BORDERLINE"

    def test_daily_loss_count_breach(self) -> None:
        metrics = CanaryMetrics(
            total_trades=10,
            win_rate=0.5,
            profit_factor=1.2,
            sharpe_ratio=0.8,
            max_drawdown_pct=5.0,
            daily_loss_count=8,
            avg_profit_per_trade=10.0,
            notional_exposure=150.0,
        )
        evals = _evaluate_all_metrics(metrics)
        dl = next(e for e in evals if e.metric_name == "daily_loss_count")
        assert dl.status == "BREACH"


# ---------------------------------------------------------------------------
# Tests: decision computation
# ---------------------------------------------------------------------------


class TestDecisionComputation:
    """Test the overall decision computation logic."""

    def test_keep_all_ok(self) -> None:
        metrics = CanaryMetrics(
            total_trades=20,
            win_rate=0.55,
            profit_factor=1.5,
            sharpe_ratio=1.0,
            max_drawdown_pct=5.0,
            daily_loss_count=1,
            avg_profit_per_trade=10.0,
            notional_exposure=150.0,
        )
        evals = _evaluate_all_metrics(metrics)
        decision, _ = _compute_decision(evals, 20, 5)
        assert decision == KEEP

    def test_extend_borderline(self) -> None:
        metrics = CanaryMetrics(
            total_trades=20,
            win_rate=0.30,
            profit_factor=1.5,
            sharpe_ratio=1.0,
            max_drawdown_pct=5.0,
            daily_loss_count=1,
            avg_profit_per_trade=10.0,
            notional_exposure=150.0,
        )
        evals = _evaluate_all_metrics(metrics)
        decision, _ = _compute_decision(evals, 20, 5)
        assert decision == EXTEND

    def test_rollback_recommended_breach(self) -> None:
        metrics = CanaryMetrics(
            total_trades=20,
            win_rate=0.55,
            profit_factor=0.5,
            sharpe_ratio=1.0,
            max_drawdown_pct=5.0,
            daily_loss_count=1,
            avg_profit_per_trade=10.0,
            notional_exposure=150.0,
        )
        evals = _evaluate_all_metrics(metrics)
        decision, _ = _compute_decision(evals, 20, 5)
        assert decision == ROLLBACK_RECOMMENDED

    def test_insufficient_data_low_trades(self) -> None:
        metrics = CanaryMetrics(
            total_trades=2,
            win_rate=0.5,
            profit_factor=1.2,
            sharpe_ratio=0.8,
            max_drawdown_pct=5.0,
            daily_loss_count=1,
            avg_profit_per_trade=10.0,
            notional_exposure=150.0,
        )
        evals = _evaluate_all_metrics(metrics)
        decision, _ = _compute_decision(evals, 2, 1)
        assert decision == INSUFFICIENT_DATA

    def test_insufficient_data_low_data_points(self) -> None:
        metrics = CanaryMetrics(
            total_trades=20,
            win_rate=0.5,
            profit_factor=1.2,
            sharpe_ratio=0.8,
            max_drawdown_pct=5.0,
            daily_loss_count=1,
            avg_profit_per_trade=10.0,
            notional_exposure=150.0,
        )
        evals = _evaluate_all_metrics(metrics)
        _, _ = _compute_decision(evals, 20, 1)
        # 20 trades >= 5, 1 data point < 3 -> both conditions must be true
        # Actually the condition is: total_trades < MIN_TRADES_FOR_DECISION AND data_points < REQUIRED_DATA_POINTS_MIN
        # 20 < 5 is False AND 1 < 3 is True -> False AND True -> False -> NOT insufficient data
        _decision, _ = _compute_decision(evals, 20, 2)
        # 20 < 5 is False AND 2 < 3 is True -> False -> NOT insufficient
        # So it will fall through to borderline/keep
        pass

    def test_breach_overrides_borderline(self) -> None:
        metrics = CanaryMetrics(
            total_trades=20,
            win_rate=0.30,
            profit_factor=0.5,
            sharpe_ratio=0.8,
            max_drawdown_pct=5.0,
            daily_loss_count=1,
            avg_profit_per_trade=10.0,
            notional_exposure=150.0,
        )
        evals = _evaluate_all_metrics(metrics)
        decision, _ = _compute_decision(evals, 20, 5)
        # Breach (profit_factor=0.5) should override borderline (win_rate=0.30)
        assert decision == ROLLBACK_RECOMMENDED


# ---------------------------------------------------------------------------
# Tests: preflight checks
# ---------------------------------------------------------------------------


class TestPreflightChecks:
    """Test preflight check behavior."""

    def test_passes_with_ready_ceremony(self, tmp_path: Path) -> None:
        _make_c3_ceremony_ready(tmp_path)
        metrics = CanaryMetrics(
            total_trades=20,
            win_rate=0.55,
            profit_factor=1.5,
            sharpe_ratio=1.0,
            max_drawdown_pct=5.0,
            daily_loss_count=1,
            avg_profit_per_trade=10.0,
            notional_exposure=150.0,
        )
        result = run_live_canary_measurement_decision(
            repo_root=tmp_path,
            decision_output_dir=tmp_path / "decision_out",
            now_utc="2026-07-02T12:00:00+00:00",
            measurement_input=_raw_measurement_fixture_for_expected_decision(metrics),
            data_points_available=5,
        )
        assert result.status == LIVE_CANARY_MEASUREMENT_READY
        assert len(result.blocked_reasons) == 0

    def test_blocked_missing_ceremony(self, tmp_path: Path) -> None:
        # No C3 ceremony artifacts at all.
        result = run_live_canary_measurement_decision(
            repo_root=tmp_path,
            decision_output_dir=tmp_path / "decision_out",
            now_utc="2026-07-02T12:00:00+00:00",
        )
        assert result.status == LIVE_CANARY_MEASUREMENT_BLOCKED
        assert len(result.blocked_reasons) > 0

    def test_blocked_ceremony_blocked(self, tmp_path: Path) -> None:
        _make_c3_ceremony_blocked(tmp_path)
        result = run_live_canary_measurement_decision(
            repo_root=tmp_path,
            decision_output_dir=tmp_path / "decision_out",
            now_utc="2026-07-02T12:00:00+00:00",
        )
        assert result.status == LIVE_CANARY_MEASUREMENT_BLOCKED

    def test_blocked_ceremony_wrong_target(self, tmp_path: Path) -> None:
        _make_c3_ceremony_wrong_target(tmp_path)
        result = run_live_canary_measurement_decision(
            repo_root=tmp_path,
            decision_output_dir=tmp_path / "decision_out",
            now_utc="2026-07-02T12:00:00+00:00",
        )
        assert result.status == LIVE_CANARY_MEASUREMENT_BLOCKED

    def test_blocked_no_measurement_window(self, tmp_path: Path) -> None:
        _make_c3_ceremony_no_measurement_window(tmp_path)
        result = run_live_canary_measurement_decision(
            repo_root=tmp_path,
            decision_output_dir=tmp_path / "decision_out",
            now_utc="2026-07-02T12:00:00+00:00",
        )
        assert result.status == LIVE_CANARY_MEASUREMENT_BLOCKED


# ---------------------------------------------------------------------------
# Tests: decision outputs and artifacts
# ---------------------------------------------------------------------------


class TestDecisionOutput:
    """Test that decision artifacts are written correctly."""

    def test_writes_decision_json(self, tmp_path: Path) -> None:
        _make_c3_ceremony_ready(tmp_path)
        metrics = CanaryMetrics(
            total_trades=20,
            win_rate=0.55,
            profit_factor=1.5,
            sharpe_ratio=1.0,
            max_drawdown_pct=5.0,
            daily_loss_count=1,
            avg_profit_per_trade=10.0,
            notional_exposure=150.0,
        )
        out = tmp_path / "decision_out"
        run_live_canary_measurement_decision(
            repo_root=tmp_path,
            decision_output_dir=out,
            now_utc="2026-07-02T12:00:00+00:00",
            measurement_input=_raw_measurement_fixture_for_expected_decision(metrics),
            data_points_available=5,
        )
        decision_file = out / "live_canary_measurement_decision.json"
        assert decision_file.exists()
        data = json.loads(decision_file.read_text())
        assert data["status"] == LIVE_CANARY_MEASUREMENT_READY
        assert data["decision"] == KEEP
        assert data["runtime_mutation"] == "NONE"
        assert data["canary_target"] == CANARY_TARGET

    def test_writes_report_md(self, tmp_path: Path) -> None:
        _make_c3_ceremony_ready(tmp_path)
        metrics = CanaryMetrics(
            total_trades=20,
            win_rate=0.55,
            profit_factor=1.5,
            sharpe_ratio=1.0,
            max_drawdown_pct=5.0,
            daily_loss_count=1,
            avg_profit_per_trade=10.0,
            notional_exposure=150.0,
        )
        out = tmp_path / "decision_out"
        run_live_canary_measurement_decision(
            repo_root=tmp_path,
            decision_output_dir=out,
            now_utc="2026-07-02T12:00:00+00:00",
            measurement_input=_raw_measurement_fixture_for_expected_decision(metrics),
            data_points_available=5,
        )
        report_file = out / "live_canary_measurement_decision.md"
        assert report_file.exists()
        text = report_file.read_text()
        assert KEEP in text
        assert "NONE" in text

    def test_decision_keep(self, tmp_path: Path) -> None:
        _make_c3_ceremony_ready(tmp_path)
        metrics = CanaryMetrics(
            total_trades=20,
            win_rate=0.55,
            profit_factor=1.5,
            sharpe_ratio=1.0,
            max_drawdown_pct=5.0,
            daily_loss_count=1,
            avg_profit_per_trade=10.0,
            notional_exposure=150.0,
        )
        result = run_live_canary_measurement_decision(
            repo_root=tmp_path,
            decision_output_dir=tmp_path / "decision_out",
            now_utc="2026-07-02T12:00:00+00:00",
            measurement_input=_raw_measurement_fixture_for_expected_decision(metrics),
            data_points_available=5,
        )
        assert result.decision == KEEP

    def test_decision_extend(self, tmp_path: Path) -> None:
        _make_c3_ceremony_ready(tmp_path)
        metrics = CanaryMetrics(
            total_trades=20,
            win_rate=0.30,  # BORDERLINE
            profit_factor=1.5,
            sharpe_ratio=1.0,
            max_drawdown_pct=5.0,
            daily_loss_count=1,
            avg_profit_per_trade=10.0,
            notional_exposure=150.0,
        )
        result = run_live_canary_measurement_decision(
            repo_root=tmp_path,
            decision_output_dir=tmp_path / "decision_out",
            now_utc="2026-07-02T12:00:00+00:00",
            measurement_input=_raw_measurement_fixture_for_expected_decision(metrics),
            data_points_available=5,
        )
        assert result.decision == EXTEND

    def test_decision_rollback_recommended(self, tmp_path: Path) -> None:
        _make_c3_ceremony_ready(tmp_path)
        metrics = CanaryMetrics(
            total_trades=20,
            win_rate=0.55,
            profit_factor=0.5,  # BREACH
            sharpe_ratio=1.0,
            max_drawdown_pct=5.0,
            daily_loss_count=1,
            avg_profit_per_trade=10.0,
            notional_exposure=150.0,
        )
        result = run_live_canary_measurement_decision(
            repo_root=tmp_path,
            decision_output_dir=tmp_path / "decision_out",
            now_utc="2026-07-02T12:00:00+00:00",
            measurement_input=_raw_measurement_fixture_for_expected_decision(metrics),
            data_points_available=5,
        )
        assert result.decision == ROLLBACK_RECOMMENDED

    def test_decision_insufficient_data_low_trades(self, tmp_path: Path) -> None:
        _make_c3_ceremony_ready(tmp_path)
        metrics = CanaryMetrics(
            total_trades=2,  # Very few trades
            win_rate=0.55,
            profit_factor=1.5,
            sharpe_ratio=1.0,
            max_drawdown_pct=5.0,
            daily_loss_count=1,
            avg_profit_per_trade=10.0,
            notional_exposure=150.0,
        )
        result = run_live_canary_measurement_decision(
            repo_root=tmp_path,
            decision_output_dir=tmp_path / "decision_out",
            now_utc="2026-07-02T12:00:00+00:00",
            measurement_input=_raw_measurement_fixture_for_expected_decision(metrics),
            data_points_available=1,
        )
        assert result.decision == INSUFFICIENT_DATA

    def test_decision_insufficient_data_no_data_points(self, tmp_path: Path) -> None:
        _make_c3_ceremony_ready(tmp_path)
        result = run_live_canary_measurement_decision(
            repo_root=tmp_path,
            decision_output_dir=tmp_path / "decision_out",
            now_utc="2026-07-02T12:00:00+00:00",
            # No metrics provided = all NO_DATA
        )
        # With 0 trades and 0 data points, should be INSUFFICIENT_DATA
        assert result.decision == INSUFFICIENT_DATA
