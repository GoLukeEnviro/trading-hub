"""SI-v2 C4 — Live Canary Measurement and Decision, No Activation.

Consumes C3 ceremony artifacts, requires C3 measurement-start reference,
targets exactly freqtrade-freqforge-canary, evaluates canary metrics against
the defined C2/C3 window, and emits KEEP, EXTEND, ROLLBACK_RECOMMENDED, or
INSUFFICIENT_DATA.

This module does NOT:
- Execute rollback
- Roll out to fleet
- Mutate runtime config
- Deploy exchange keys
- Mutate strategy or expand pairs
- Perform any Docker/Cron/Scheduler action
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from si_v2.live.c4_window_scope import (
    C4MeasurementInput,
    WindowScopedMeasurement,
    build_window_scoped_measurement,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_DECISION_OUTPUT_DIR: str = "var/si_v2/live_canary_measurement_decision"

# The single approved canary target.
CANARY_TARGET: str = "freqtrade-freqforge-canary"

# C3 ceremony output paths (relative to repo root).
C3_CEREMONY_OUTPUT_DIR: str = "var/si_v2/live_canary_activation_ceremony"
C3_CEREMONY_FILENAME: str = "live_canary_activation_ceremony.json"
C3_READY_STATUS: str = "LIVE_CANARY_CEREMONY_READY"

# C2 config plan paths (for measurement window reference).
C2_PLAN_OUTPUT_DIR: str = "var/si_v2/live_canary_config_plan"
C2_PLAN_FILENAME: str = "live_canary_config_plan.json"

# Decision outcome strings.
Decision = Literal["KEEP", "EXTEND", "ROLLBACK_RECOMMENDED", "INSUFFICIENT_DATA"]
MeasurementStatus = Literal[
    "LIVE_CANARY_MEASUREMENT_READY",
    "LIVE_CANARY_MEASUREMENT_BLOCKED",
]
KEEP: Literal["KEEP"] = "KEEP"
EXTEND: Literal["EXTEND"] = "EXTEND"
ROLLBACK_RECOMMENDED: Literal["ROLLBACK_RECOMMENDED"] = "ROLLBACK_RECOMMENDED"
INSUFFICIENT_DATA: Literal["INSUFFICIENT_DATA"] = "INSUFFICIENT_DATA"

# Thresholds from B2 risk limits and C2 measurement window.
# Minimum trades needed to form a meaningful decision.
MIN_TRADES_FOR_DECISION: int = 5

# Win rate thresholds.
WIN_RATE_THRESHOLD_MIN: float = 0.40  # 40% min acceptable
WIN_RATE_THRESHOLD_CRITICAL: float = 0.25  # 25% triggers ROLLBACK

# Profit factor thresholds.
PROFIT_FACTOR_THRESHOLD_MIN: float = 1.0  # Below 1.0 = losing money
PROFIT_FACTOR_THRESHOLD_CRITICAL: float = 0.8  # 0.8 triggers ROLLBACK

# Sharpe ratio thresholds.
SHARPE_THRESHOLD_MIN: float = 0.5
SHARPE_THRESHOLD_CRITICAL: float = 0.0

# Max drawdown thresholds (percentage, positive value).
MAX_DRAWDOWN_THRESHOLD_MAX: float = 15.0  # 15% from B2
MAX_DRAWDOWN_THRESHOLD_CRITICAL: float = 20.0  # 20% triggers ROLLBACK

# Daily loss count thresholds.
DAILY_LOSS_THRESHOLD_MAX: int = 3  # Max losing days in window
DAILY_LOSS_THRESHOLD_CRITICAL: int = 5  # Triggers ROLLBACK

# Measurement window defaults (from C3).
MEASUREMENT_WINDOW_DAYS: int = 14
REQUIRED_DATA_POINTS_MIN: int = 3  # Minimum data points for EXTEND/KEEP

# Measurement status string constants.
LIVE_CANARY_MEASUREMENT_READY: str = "LIVE_CANARY_MEASUREMENT_READY"
LIVE_CANARY_MEASUREMENT_BLOCKED: str = "LIVE_CANARY_MEASUREMENT_BLOCKED"

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MeasurementCheckResult:
    """Result of a single measurement preflight check."""

    check_name: str
    passed: bool
    detail: str

    def to_dict(self) -> dict[str, object]:
        return {
            "check_name": self.check_name,
            "passed": self.passed,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class MetricEvaluation:
    """Evaluation of a single metric against its thresholds."""

    metric_name: str
    value: float | None
    threshold_min: float | None
    threshold_max: float | None
    critical_threshold_min: float | None
    critical_threshold_max: float | None
    status: Literal["OK", "BORDERLINE", "BREACH", "NO_DATA"]
    detail: str

    def to_dict(self) -> dict[str, object]:
        return {
            "metric_name": self.metric_name,
            "value": self.value,
            "threshold_min": self.threshold_min,
            "threshold_max": self.threshold_max,
            "critical_threshold_min": self.critical_threshold_min,
            "critical_threshold_max": self.critical_threshold_max,
            "status": self.status,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class CanaryMetrics:
    """Metrics from the live canary for measurement evaluation."""

    total_trades: int | None
    win_rate: float | None
    profit_factor: float | None
    sharpe_ratio: float | None
    max_drawdown_pct: float | None
    daily_loss_count: int | None
    avg_profit_per_trade: float | None
    notional_exposure: float | None
    window_trade_count: int | None = None
    """Number of trades within the measurement window (vs lifetime).
    When None, defaults to total_trades for backward compatibility."""

    def to_dict(self) -> dict[str, object]:
        return {
            "total_trades": self.total_trades,
            "win_rate": self.win_rate,
            "profit_factor": self.profit_factor,
            "sharpe_ratio": self.sharpe_ratio,
            "max_drawdown_pct": self.max_drawdown_pct,
            "daily_loss_count": self.daily_loss_count,
            "avg_profit_per_trade": self.avg_profit_per_trade,
            "notional_exposure": self.notional_exposure,
            "window_trade_count": self.window_trade_count,
        }


@dataclass(frozen=True)
class LiveCanaryMeasurementDecisionResult:
    """Structured result from the measurement and decision watcher.

    Attributes:
        status: LIVE_CANARY_MEASUREMENT_READY or
                LIVE_CANARY_MEASUREMENT_BLOCKED.
        decision: KEEP, EXTEND, ROLLBACK_RECOMMENDED, or INSUFFICIENT_DATA.
        preflight_checks: Individual preflight check results.
        metric_evaluations: Individual metric evaluation results.
        blocked_reasons: Reasons the measurement is blocked.
        total_trades_observed: Number of trades observed.
        decision_path: Path to the written decision JSON.
        report_path: Path to the written human-readable report.
        next_step: Suggested next action.
    """

    status: MeasurementStatus
    decision: Decision
    preflight_checks: tuple[MeasurementCheckResult, ...]
    metric_evaluations: tuple[MetricEvaluation, ...]
    blocked_reasons: tuple[str, ...]
    total_trades_observed: int
    decision_path: str
    report_path: str
    next_step: str
    runtime_mutation: str = "NONE"

    def to_dict(self) -> dict[str, object]:
        return {
            "event": "live_canary_measurement_decision_result",
            "status": self.status,
            "decision": self.decision,
            "preflight_checks": [c.to_dict() for c in self.preflight_checks],
            "metric_evaluations": [m.to_dict() for m in self.metric_evaluations],
            "blocked_reasons": list(self.blocked_reasons),
            "total_trades_observed": self.total_trades_observed,
            "decision_path": self.decision_path,
            "report_path": self.report_path,
            "next_step": self.next_step,
            "runtime_mutation": self.runtime_mutation,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _atomic_write_json(path: Path, data: dict[str, object]) -> None:
    """Write JSON atomically via temp file + replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp.{abs(hash(str(data)))}")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True))
    tmp.replace(path)


def _read_json_safe(path: Path) -> dict[str, object] | None:
    """Read a JSON file safely, returning None on failure."""
    if not path.exists():
        return None
    try:
        return dict(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Check: C3 ceremony artifacts exist and are READY
# ---------------------------------------------------------------------------


def _check_c3_ceremony_artifacts(
    repo_root: Path,
) -> MeasurementCheckResult:
    """Check that C3 ceremony artifacts exist with READY status."""
    ceremony_dir = repo_root / C3_CEREMONY_OUTPUT_DIR
    ceremony_file = ceremony_dir / C3_CEREMONY_FILENAME

    if not ceremony_file.exists():
        return MeasurementCheckResult(
            check_name="c3_ceremony_artifacts",
            passed=False,
            detail=(
                f"C3 ceremony artifact not found at {ceremony_file}. "
                f"The C3 ceremony must be completed with "
                f"{C3_READY_STATUS!r} before measurement can proceed."
            ),
        )

    ceremony_data = _read_json_safe(ceremony_file)
    if ceremony_data is None:
        return MeasurementCheckResult(
            check_name="c3_ceremony_artifacts",
            passed=False,
            detail=(f"C3 ceremony at {ceremony_file} is not valid JSON."),
        )

    ceremony_status = ceremony_data.get("status", "")
    raw_ceremony_status = ceremony_status if isinstance(ceremony_status, str) else str(ceremony_status)
    if raw_ceremony_status != C3_READY_STATUS:
        return MeasurementCheckResult(
            check_name="c3_ceremony_artifacts",
            passed=False,
            detail=(
                f"C3 ceremony status is {raw_ceremony_status!r}, "
                f"expected {C3_READY_STATUS!r}. Ceremony must be "
                f"READY before measurement can proceed."
            ),
        )

    # Verify target matches.
    ceremony_target = ceremony_data.get("canary_target", "")
    raw_target = ceremony_target if isinstance(ceremony_target, str) else str(ceremony_target)
    if raw_target != CANARY_TARGET:
        return MeasurementCheckResult(
            check_name="c3_ceremony_artifacts",
            passed=False,
            detail=(f"C3 ceremony targets {raw_target!r}, expected {CANARY_TARGET!r}. Mismatch — cannot proceed."),
        )

    return MeasurementCheckResult(
        check_name="c3_ceremony_artifacts",
        passed=True,
        detail=(
            f"C3 ceremony artifacts found at {ceremony_file} with status "
            f"{C3_READY_STATUS!r} and target {CANARY_TARGET!r}."
        ),
    )


# ---------------------------------------------------------------------------
# Check: C3 measurement-start reference exists
# ---------------------------------------------------------------------------


def _check_c3_measurement_start_reference(
    repo_root: Path,
) -> MeasurementCheckResult:
    """Check that the C3 ceremony artifact contains a measurement window."""
    ceremony_file = repo_root / C3_CEREMONY_OUTPUT_DIR / C3_CEREMONY_FILENAME
    if not ceremony_file.exists():
        return MeasurementCheckResult(
            check_name="c3_measurement_start_reference",
            passed=False,
            detail="C3 ceremony artifact missing — cannot check measurement start.",
        )

    ceremony_data = _read_json_safe(ceremony_file)
    if ceremony_data is None:
        return MeasurementCheckResult(
            check_name="c3_measurement_start_reference",
            passed=False,
            detail="C3 ceremony artifact invalid — cannot check measurement start.",
        )

    meas_window = ceremony_data.get("measurement_window")
    if not isinstance(meas_window, dict):
        return MeasurementCheckResult(
            check_name="c3_measurement_start_reference",
            passed=False,
            detail=("C3 ceremony artifact does not contain a valid measurement_window section. Re-run C3 ceremony."),
        )

    metrics = meas_window.get("metrics", [])
    duration = meas_window.get("duration_days")

    if not metrics:
        return MeasurementCheckResult(
            check_name="c3_measurement_start_reference",
            passed=False,
            detail="C3 measurement window has no metrics defined.",
        )

    if not duration:
        return MeasurementCheckResult(
            check_name="c3_measurement_start_reference",
            passed=False,
            detail="C3 measurement window has no duration defined.",
        )

    return MeasurementCheckResult(
        check_name="c3_measurement_start_reference",
        passed=True,
        detail=(f"C3 measurement-start reference found with {len(metrics)} metrics and {duration}-day window."),
    )


# ---------------------------------------------------------------------------
# Metric evaluation functions
# ---------------------------------------------------------------------------


def _evaluate_metric_float(
    metric_name: str,
    value: float | None,
    *,
    threshold_min: float | None = None,
    threshold_max: float | None = None,
    critical_min: float | None = None,
    critical_max: float | None = None,
) -> MetricEvaluation:
    """Evaluate a float metric against thresholds."""
    if value is None:
        return MetricEvaluation(
            metric_name=metric_name,
            value=None,
            threshold_min=threshold_min,
            threshold_max=threshold_max,
            critical_threshold_min=critical_min,
            critical_threshold_max=critical_max,
            status="NO_DATA",
            detail=f"No data available for {metric_name}.",
        )

    # Check critical thresholds first.
    if critical_min is not None and value < critical_min:
        return MetricEvaluation(
            metric_name=metric_name,
            value=value,
            threshold_min=threshold_min,
            threshold_max=threshold_max,
            critical_threshold_min=critical_min,
            critical_threshold_max=critical_max,
            status="BREACH",
            detail=(f"{metric_name} = {value:.4f} is below critical minimum {critical_min}. RECOMMEND ROLLBACK."),
        )

    if critical_max is not None and value > critical_max:
        return MetricEvaluation(
            metric_name=metric_name,
            value=value,
            threshold_min=threshold_min,
            threshold_max=threshold_max,
            critical_threshold_min=critical_min,
            critical_threshold_max=critical_max,
            status="BREACH",
            detail=(f"{metric_name} = {value:.4f} exceeds critical maximum {critical_max}. RECOMMEND ROLLBACK."),
        )

    # Check standard thresholds.
    if threshold_min is not None and value < threshold_min:
        return MetricEvaluation(
            metric_name=metric_name,
            value=value,
            threshold_min=threshold_min,
            threshold_max=threshold_max,
            critical_threshold_min=critical_min,
            critical_threshold_max=critical_max,
            status="BORDERLINE",
            detail=(f"{metric_name} = {value:.4f} is below minimum threshold {threshold_min}. Monitor closely."),
        )

    if threshold_max is not None and value > threshold_max:
        return MetricEvaluation(
            metric_name=metric_name,
            value=value,
            threshold_min=threshold_min,
            threshold_max=threshold_max,
            critical_threshold_min=critical_min,
            critical_threshold_max=critical_max,
            status="BORDERLINE",
            detail=(f"{metric_name} = {value:.4f} exceeds maximum threshold {threshold_max}. Monitor closely."),
        )

    return MetricEvaluation(
        metric_name=metric_name,
        value=value,
        threshold_min=threshold_min,
        threshold_max=threshold_max,
        critical_threshold_min=critical_min,
        critical_threshold_max=critical_max,
        status="OK",
        detail=f"{metric_name} = {value:.4f} is within acceptable range.",
    )


def _evaluate_metric_int(
    metric_name: str,
    value: int | None,
    *,
    threshold_min: int | None = None,
    threshold_max: int | None = None,
    critical_min: int | None = None,
    critical_max: int | None = None,
) -> MetricEvaluation:
    """Evaluate an integer metric against thresholds."""
    if value is None:
        return MetricEvaluation(
            metric_name=metric_name,
            value=None,
            threshold_min=(float(threshold_min) if threshold_min is not None else None),
            threshold_max=(float(threshold_max) if threshold_max is not None else None),
            critical_threshold_min=(float(critical_min) if critical_min is not None else None),
            critical_threshold_max=(float(critical_max) if critical_max is not None else None),
            status="NO_DATA",
            detail=f"No data available for {metric_name}.",
        )

    if critical_min is not None and value < critical_min:
        return MetricEvaluation(
            metric_name=metric_name,
            value=float(value),
            threshold_min=float(threshold_min) if threshold_min is not None else None,
            threshold_max=float(threshold_max) if threshold_max is not None else None,
            critical_threshold_min=(float(critical_min) if critical_min is not None else None),
            critical_threshold_max=(float(critical_max) if critical_max is not None else None),
            status="BREACH",
            detail=(f"{metric_name} = {value} is below critical minimum {critical_min}. RECOMMEND ROLLBACK."),
        )

    if critical_max is not None and value > critical_max:
        return MetricEvaluation(
            metric_name=metric_name,
            value=float(value),
            threshold_min=float(threshold_min) if threshold_min is not None else None,
            threshold_max=float(threshold_max) if threshold_max is not None else None,
            critical_threshold_min=(float(critical_min) if critical_min is not None else None),
            critical_threshold_max=(float(critical_max) if critical_max is not None else None),
            status="BREACH",
            detail=(f"{metric_name} = {value} exceeds critical maximum {critical_max}. RECOMMEND ROLLBACK."),
        )

    if threshold_min is not None and value < threshold_min:
        return MetricEvaluation(
            metric_name=metric_name,
            value=float(value),
            threshold_min=float(threshold_min) if threshold_min is not None else None,
            threshold_max=float(threshold_max) if threshold_max is not None else None,
            critical_threshold_min=(float(critical_min) if critical_min is not None else None),
            critical_threshold_max=(float(critical_max) if critical_max is not None else None),
            status="BORDERLINE",
            detail=(f"{metric_name} = {value} is below minimum threshold {threshold_min}. Monitor closely."),
        )

    if threshold_max is not None and value > threshold_max:
        return MetricEvaluation(
            metric_name=metric_name,
            value=float(value),
            threshold_min=float(threshold_min) if threshold_min is not None else None,
            threshold_max=float(threshold_max) if threshold_max is not None else None,
            critical_threshold_min=(float(critical_min) if critical_min is not None else None),
            critical_threshold_max=(float(critical_max) if critical_max is not None else None),
            status="BORDERLINE",
            detail=(f"{metric_name} = {value} exceeds maximum threshold {threshold_max}. Monitor closely."),
        )

    return MetricEvaluation(
        metric_name=metric_name,
        value=float(value),
        threshold_min=float(threshold_min) if threshold_min is not None else None,
        threshold_max=float(threshold_max) if threshold_max is not None else None,
        critical_threshold_min=(float(critical_min) if critical_min is not None else None),
        critical_threshold_max=(float(critical_max) if critical_max is not None else None),
        status="OK",
        detail=f"{metric_name} = {value} is within acceptable range.",
    )


# ---------------------------------------------------------------------------
# Main measurement and decision function
# ---------------------------------------------------------------------------


def run_live_canary_measurement_decision(
    *,
    repo_root: Path | None = None,
    decision_output_dir: Path | None = None,
    now_utc: str | None = None,
    measurement_input: C4MeasurementInput | None = None,
    data_points_available: int | None = None,
) -> LiveCanaryMeasurementDecisionResult:
    """Run the live canary measurement and decision watcher.

    Args:
        repo_root: Root of the trading-hub repository. Defaults to
            auto-detection from the current file location.
        decision_output_dir: Override for decision output directory.
        now_utc: Override for current UTC time (testing).
        measurement_input: Raw trades, explicit UTC boundaries, and equity
            baselines used to build the canonical window-scoped metrics.
            Missing or invalid input blocks instead of falling back to
            lifetime metrics.
        data_points_available: Number of measurement data points
            collected. If None, defaults to 0.

    Returns:
        LiveCanaryMeasurementDecisionResult with decision status.
    """
    resolved_now = now_utc or datetime.now(UTC).isoformat()
    resolved_dir = decision_output_dir or Path(DEFAULT_DECISION_OUTPUT_DIR)

    # Auto-detect repo root if not provided.
    if repo_root is None:
        repo_root = Path(__file__).resolve().parent.parent.parent.parent.parent

    resolved_dir.mkdir(parents=True, exist_ok=True)

    resolved_metrics = CanaryMetrics(
        total_trades=None,
        win_rate=None,
        profit_factor=None,
        sharpe_ratio=None,
        max_drawdown_pct=None,
        daily_loss_count=None,
        avg_profit_per_trade=None,
        notional_exposure=None,
    )
    scoped_measurement: WindowScopedMeasurement | None = None
    resolved_data_points = data_points_available or 0

    # ------------------------------------------------------------------
    # Run preflight checks
    # ------------------------------------------------------------------

    checks: list[MeasurementCheckResult] = []
    blocked: list[str] = []

    # Check 1: C3 ceremony artifacts exist and are READY.
    c1 = _check_c3_ceremony_artifacts(repo_root)
    checks.append(c1)
    if not c1.passed:
        blocked.append(c1.detail)

    # Check 2: C3 measurement-start reference exists.
    c2 = _check_c3_measurement_start_reference(repo_root)
    checks.append(c2)
    if not c2.passed:
        blocked.append(c2.detail)

    # Check 3: explicit raw-trade input can be scoped before evaluation.
    if measurement_input is None:
        c3 = MeasurementCheckResult(
            check_name="measurement_window_scope",
            passed=False,
            detail=(
                "measurement_window_scope: raw trades and explicit "
                "measurement_start_utc/measurement_end_utc are required; "
                "unscoped lifetime metrics are rejected."
            ),
        )
    else:
        try:
            scoped_measurement = build_window_scoped_measurement(measurement_input)
        except ValueError as exc:
            c3 = MeasurementCheckResult(
                check_name="measurement_window_scope",
                passed=False,
                detail=f"measurement_window_scope: {exc}",
            )
        else:
            scoped_metrics = scoped_measurement.metrics
            resolved_metrics = CanaryMetrics(
                total_trades=scoped_metrics.total_trades,
                win_rate=scoped_metrics.win_rate,
                profit_factor=scoped_metrics.profit_factor,
                sharpe_ratio=scoped_metrics.sharpe_ratio,
                max_drawdown_pct=scoped_metrics.max_drawdown_pct,
                daily_loss_count=scoped_metrics.daily_loss_count,
                avg_profit_per_trade=scoped_metrics.avg_profit_per_trade,
                notional_exposure=scoped_metrics.notional_exposure,
                window_trade_count=scoped_measurement.included_trade_count,
            )
            c3 = MeasurementCheckResult(
                check_name="measurement_window_scope",
                passed=True,
                detail=(
                    "Canonical window scope built before metric evaluation: "
                    f"included={scoped_measurement.included_trade_count}, "
                    f"realized={scoped_measurement.realized_trade_count}, "
                    f"method={scoped_measurement.scope_method}."
                ),
            )
    checks.append(c3)
    if not c3.passed:
        blocked.append(c3.detail)

    # ------------------------------------------------------------------
    # Determine measurement status
    # ------------------------------------------------------------------

    if blocked:
        status: MeasurementStatus = "LIVE_CANARY_MEASUREMENT_BLOCKED"
        decision: Decision = INSUFFICIENT_DATA
        next_step = (
            "Review blocked reasons and address before re-running "
            "measurement. Required C3 ceremony artifacts are missing "
            "or invalid."
        )
        total_trades = 0
        evaluations: list[MetricEvaluation] = []
    else:
        # Preflight checks pass — proceed to metric evaluation.
        status = "LIVE_CANARY_MEASUREMENT_READY"
        evaluations = _evaluate_all_metrics(resolved_metrics)
        total_trades = resolved_metrics.total_trades or 0
        decision, next_step = _compute_decision(
            evaluations=evaluations,
            total_trades=total_trades,
            data_points=resolved_data_points,
        )

    # ------------------------------------------------------------------
    # Write decision JSON
    # ------------------------------------------------------------------

    decision_payload: dict[str, object] = {
        "event": "live_canary_measurement_decision_result",
        "status": status,
        "decision": decision,
        "canary_target": CANARY_TARGET,
        "preflight_checks": [c.to_dict() for c in checks],
        "metric_evaluations": [m.to_dict() for m in evaluations],
        "blocked_reasons": blocked,
        "total_trades_observed": total_trades,
        "window_trade_count": resolved_metrics.window_trade_count,
        "measurement_scope": (scoped_measurement.to_dict() if scoped_measurement is not None else None),
        "data_points_available": resolved_data_points,
        "measurement_window_days": MEASUREMENT_WINDOW_DAYS,
        "created_at_utc": resolved_now,
        "runtime_mutation": "NONE",
    }
    decision_path = resolved_dir / "live_canary_measurement_decision.json"
    _atomic_write_json(decision_path, decision_payload)

    # ------------------------------------------------------------------
    # Write human-readable report
    # ------------------------------------------------------------------

    report_lines: list[str] = [
        "# Live Canary Measurement and Decision",
        "",
        f"**Status:** {status}",
        f"**Decision:** {decision}",
        f"**Canary target:** {CANARY_TARGET}",
        f"**Generated at:** {resolved_now}",
        f"**Total trades observed:** {total_trades}",
        f"**Data points available:** {resolved_data_points}",
        f"**Measurement window:** {MEASUREMENT_WINDOW_DAYS} days",
        "**Runtime mutation:** NONE",
        "",
        "---",
        "",
        "## Preflight Check Results",
        "",
    ]

    for c in checks:
        icon = "✅" if c.passed else "❌"
        report_lines.append(f"### {icon} {c.check_name}")
        report_lines.append("")
        report_lines.append(f"**Passed:** {c.passed}")
        report_lines.append("")
        report_lines.append(f"**Detail:** {c.detail}")
        report_lines.append("")

    if blocked:
        report_lines.append("---")
        report_lines.append("")
        report_lines.append("## Blocked Reasons")
        report_lines.append("")
        for i, reason in enumerate(blocked, 1):
            report_lines.append(f"{i}. {reason}")
            report_lines.append("")

    if not blocked:
        if scoped_measurement is not None:
            report_lines.extend(
                [
                    "---",
                    "",
                    "## Measurement Scope",
                    "",
                    f"**Start:** {scoped_measurement.measurement_start_utc}",
                    f"**End:** {scoped_measurement.measurement_end_utc}",
                    f"**Method:** {scoped_measurement.scope_method}",
                    (
                        "**Included / realized / open at end:** "
                        f"{scoped_measurement.included_trade_count} / "
                        f"{scoped_measurement.realized_trade_count} / "
                        f"{scoped_measurement.open_at_window_end_trade_count}"
                    ),
                    "**Authoritative drawdown method:** continuation",
                    (
                        "**Metric authority:** realized-window trades for trade "
                        "count, win rate, profit factor, Sharpe, daily losses, "
                        "and average PnL; open-at-window-end trades for exposure; "
                        "continuation equity for max drawdown."
                    ),
                    (
                        "**Drawdown (lifetime / window-relative / continuation):** "
                        f"{scoped_measurement.drawdown_calculations.lifetime_pct} / "
                        f"{scoped_measurement.drawdown_calculations.window_relative_pct} / "
                        f"{scoped_measurement.drawdown_calculations.continuation_pct}"
                    ),
                    "",
                ]
            )
        report_lines.append("---")
        report_lines.append("")
        report_lines.append("## Metric Evaluations")
        report_lines.append("")

        for ev in evaluations:
            icon_map = {
                "OK": "✅",
                "BORDERLINE": "⚠️",
                "BREACH": "❌",
                "NO_DATA": "⬜",
            }
            icon = icon_map.get(ev.status, "❓")
            report_lines.append(f"### {icon} {ev.metric_name}")
            report_lines.append("")
            report_lines.append(f"**Value:** {ev.value}")
            report_lines.append("")
            report_lines.append(f"**Status:** {ev.status}")
            report_lines.append("")
            if ev.threshold_min is not None:
                report_lines.append(f"**Min threshold:** {ev.threshold_min}")
                report_lines.append("")
            if ev.threshold_max is not None:
                report_lines.append(f"**Max threshold:** {ev.threshold_max}")
                report_lines.append("")
            if ev.critical_threshold_min is not None or ev.critical_threshold_max is not None:
                report_lines.append("**Critical thresholds:**")
                report_lines.append("")
                if ev.critical_threshold_min is not None:
                    report_lines.append(f"- Min: {ev.critical_threshold_min}")
                if ev.critical_threshold_max is not None:
                    report_lines.append(f"- Max: {ev.critical_threshold_max}")
                report_lines.append("")
            report_lines.append(f"**Detail:** {ev.detail}")
            report_lines.append("")

        report_lines.extend(
            [
                "---",
                "",
                "## Decision Summary",
                "",
                f"**Decision:** {decision}",
                "",
                "### KEEP",
                "",
                "All metrics are within acceptable thresholds. Continue live canary "
                "operation. Proceed to fleet rollout evaluation if fleet rollout "
                "approval marker exists.",
                "",
                "### EXTEND",
                "",
                "Some metrics are borderline. Extend the measurement window to "
                "gather more data. Re-run measurement after additional data "
                "points are collected.",
                "",
                "### ROLLBACK_RECOMMENDED",
                "",
                "One or more metrics have breached critical thresholds. The "
                "canary should be returned to dry-run mode. See the rollback "
                "plan in the C3 ceremony artifacts.",
                "",
                "### INSUFFICIENT_DATA",
                "",
                "Not enough data points or no metrics provided. Wait for more "
                "trades to accumulate before making a decision.",
                "",
            ]
        )

    report_lines.extend(
        [
            "---",
            "",
            "## Next Steps",
            "",
            f"**{next_step}**",
            "",
        ]
    )

    report_path = resolved_dir / "live_canary_measurement_decision.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(report_lines), encoding="utf-8")

    return LiveCanaryMeasurementDecisionResult(
        status=status,
        decision=decision,
        preflight_checks=tuple(checks),
        metric_evaluations=tuple(evaluations),
        blocked_reasons=tuple(blocked),
        total_trades_observed=total_trades,
        decision_path=str(decision_path),
        report_path=str(report_path),
        next_step=next_step,
    )


def _evaluate_all_metrics(
    metrics: CanaryMetrics,
) -> list[MetricEvaluation]:
    """Evaluate all metrics against defined thresholds."""
    evaluations: list[MetricEvaluation] = []

    # Win rate
    evaluations.append(
        _evaluate_metric_float(
            "win_rate",
            metrics.win_rate,
            threshold_min=WIN_RATE_THRESHOLD_MIN,
            critical_min=WIN_RATE_THRESHOLD_CRITICAL,
        )
    )

    # Profit factor
    evaluations.append(
        _evaluate_metric_float(
            "profit_factor",
            metrics.profit_factor,
            threshold_min=PROFIT_FACTOR_THRESHOLD_MIN,
            critical_min=PROFIT_FACTOR_THRESHOLD_CRITICAL,
        )
    )

    # Sharpe ratio
    evaluations.append(
        _evaluate_metric_float(
            "sharpe_ratio",
            metrics.sharpe_ratio,
            threshold_min=SHARPE_THRESHOLD_MIN,
            critical_min=SHARPE_THRESHOLD_CRITICAL,
        )
    )

    # Max drawdown
    evaluations.append(
        _evaluate_metric_float(
            "max_drawdown_pct",
            metrics.max_drawdown_pct,
            threshold_min=None,
            threshold_max=MAX_DRAWDOWN_THRESHOLD_MAX,
            critical_min=None,
            critical_max=MAX_DRAWDOWN_THRESHOLD_CRITICAL,
        )
    )

    # Daily loss count
    evaluations.append(
        _evaluate_metric_int(
            "daily_loss_count",
            metrics.daily_loss_count,
            threshold_min=None,
            threshold_max=DAILY_LOSS_THRESHOLD_MAX,
            critical_min=None,
            critical_max=DAILY_LOSS_THRESHOLD_CRITICAL,
        )
    )

    # Average profit per trade (informational, no hard threshold)
    evaluations.append(
        _evaluate_metric_float(
            "avg_profit_per_trade",
            metrics.avg_profit_per_trade,
        )
    )

    # Notional exposure (informational, no hard threshold)
    evaluations.append(
        _evaluate_metric_float(
            "notional_exposure",
            metrics.notional_exposure,
        )
    )

    return evaluations


def _compute_decision(
    evaluations: list[MetricEvaluation],
    total_trades: int,
    data_points: int,
) -> tuple[Decision, str]:
    """Compute the overall decision from metric evaluations.

    Priority:
    1. INSUFFICIENT_DATA — not enough trades or data points.
    2. ROLLBACK_RECOMMENDED — any metric in BREACH status.
    3. EXTEND — any metric in BORDERLINE status.
    4. KEEP — all metrics OK or NO_DATA.
    """
    # Check for insufficient data.
    if total_trades < MIN_TRADES_FOR_DECISION and data_points < REQUIRED_DATA_POINTS_MIN:
        return (
            INSUFFICIENT_DATA,
            (
                f"Insufficient data: {total_trades} trades observed "
                f"(min {MIN_TRADES_FOR_DECISION}) and {data_points} data "
                f"points available (min {REQUIRED_DATA_POINTS_MIN}). "
                f"Wait for more data before making a decision."
            ),
        )

    # Check for BREACH (critical threshold exceeded).
    breaches = [e for e in evaluations if e.status == "BREACH"]
    if breaches:
        breached_names = ", ".join(e.metric_name for e in breaches)
        return (
            ROLLBACK_RECOMMENDED,
            (
                f"CRITICAL BREACH detected in: {breached_names}. "
                f"Immediate rollback to dry-run mode is recommended. "
                f"Review the C3 rollback plan and execute rollback."
            ),
        )

    # Check for BORDERLINE.
    borderlines = [e for e in evaluations if e.status == "BORDERLINE"]
    if borderlines:
        borderline_names = ", ".join(e.metric_name for e in borderlines)
        return (
            EXTEND,
            (
                f"Borderline metrics detected in: {borderline_names}. "
                f"Extend measurement window to gather more data. "
                f"Re-run measurement after additional data points."
            ),
        )

    # All metrics OK or NO_DATA — KEEP.
    return (
        KEEP,
        (
            "All metrics within acceptable thresholds. Continue live canary "
            "operation. Proceed to fleet rollout evaluation when ready."
        ),
    )
