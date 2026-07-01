r"""Measurement Decision Engine — Phase 4A.

Translates T0/T1/T2/T3 snapshots into actionable decisions:
KEEP / ROLLBACK / EXTEND / INVESTIGATE.

This module is **read-only**. It imports no runtime-mutation functions,
calls no subprocess, and touches no Docker.

Usage
-----
    point = MeasurementPoint(label="T1", ...)
    decision = evaluate_measurement_safety(point)

    comparison = compare_canary_to_control(
        canary_previous=prev, canary_current=curr,
        control_previous=ctrl_prev, control_current=ctrl_curr,
    )

    verdict = decide_measurement_point(
        label="T1",
        canary_previous=prev, canary_current=curr,
        control_previous=ctrl_prev, control_current=ctrl_curr,
    )

    final = decide_final_measurement(
        canary_points=[t0, t1, t2, t3],
        control_points=[c_t0, c_t1, c_t2, c_t3],
    )
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MeasurementPoint:
    """A single measurement snapshot at a labelled point in time."""

    label: Literal["T0", "T1", "T2", "T3"]
    timestamp_utc: str
    bot_id: str
    candidate_id: str
    runtime_proof_status: str
    max_open_trades: int | None
    dry_run: bool | None
    container_healthy: bool | None
    open_trades: int | None
    closed_trades: int | None
    total_profit_abs: float | None
    realized_profit_abs: float | None
    win_rate: float | None
    drawdown_abs: float | None
    errors_since_last: int | None
    warnings_since_last: int | None
    unexpected_restart: bool
    rollback_required: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "label": self.label,
            "timestamp_utc": self.timestamp_utc,
            "bot_id": self.bot_id,
            "candidate_id": self.candidate_id,
            "runtime_proof_status": self.runtime_proof_status,
            "max_open_trades": self.max_open_trades,
            "dry_run": self.dry_run,
            "container_healthy": self.container_healthy,
            "open_trades": self.open_trades,
            "closed_trades": self.closed_trades,
            "total_profit_abs": self.total_profit_abs,
            "realized_profit_abs": self.realized_profit_abs,
            "win_rate": self.win_rate,
            "drawdown_abs": self.drawdown_abs,
            "errors_since_last": self.errors_since_last,
            "warnings_since_last": self.warnings_since_last,
            "unexpected_restart": self.unexpected_restart,
            "rollback_required": self.rollback_required,
        }


@dataclass(frozen=True)
class MeasurementComparison:
    """Delta and gap analysis between canary and control at one point."""

    canary_delta_profit_abs: float | None
    canary_delta_trades: int | None
    control_delta_profit_abs: float | None
    control_delta_trades: int | None
    canary_vs_control_profit_gap: float | None
    canary_vs_control_trade_gap: int | None
    notes: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "canary_delta_profit_abs": self.canary_delta_profit_abs,
            "canary_delta_trades": self.canary_delta_trades,
            "control_delta_profit_abs": self.control_delta_profit_abs,
            "control_delta_trades": self.control_delta_trades,
            "canary_vs_control_profit_gap": self.canary_vs_control_profit_gap,
            "canary_vs_control_trade_gap": self.canary_vs_control_trade_gap,
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class MeasurementDecision:
    """Structured decision from the engine."""

    verdict: Literal["GREEN", "YELLOW", "RED"]
    decision: Literal[
        "CONTINUE_MEASUREMENT",
        "KEEP_CANARY_OVERLAY",
        "ROLLBACK_CANARY_OVERLAY",
        "EXTEND_MEASUREMENT",
        "INVESTIGATE_READ_ONLY",
    ]
    confidence: Literal["LOW", "MEDIUM", "HIGH"]
    reasons: tuple[str, ...]
    next_step: str

    def to_dict(self) -> dict[str, object]:
        return {
            "verdict": self.verdict,
            "decision": self.decision,
            "confidence": self.confidence,
            "reasons": list(self.reasons),
            "next_step": self.next_step,
        }


# ---------------------------------------------------------------------------
# Safety evaluation
# ---------------------------------------------------------------------------

# Expected values for the running canary apply
EXPECTED_BOT_ID: str = "freqtrade-freqforge-canary"
EXPECTED_MAX_OPEN_TRADES: int = 2


def _hard_safety_reasons(point: MeasurementPoint) -> list[str]:
    """Return hard blockers that must force rollback or block final KEEP."""
    reasons: list[str] = []

    if point.dry_run is False:
        reasons.append("RED: dry_run is False — live trading risk")
    if point.runtime_proof_status not in ("GREEN", ""):
        reasons.append(f"RED: runtime_proof_status is {point.runtime_proof_status!r}")
    if point.max_open_trades is not None and point.max_open_trades != EXPECTED_MAX_OPEN_TRADES:
        reasons.append(
            f"RED: max_open_trades={point.max_open_trades} "
            f"(expected {EXPECTED_MAX_OPEN_TRADES})"
        )
    if point.container_healthy is False:
        reasons.append("RED: container is unhealthy")
    if point.unexpected_restart:
        reasons.append("RED: unexpected restart detected")
    if point.rollback_required:
        reasons.append("RED: rollback_required is True")

    return reasons


def _point_warning_reasons(point: MeasurementPoint) -> list[str]:
    """Return non-red warning/unknown reasons for one measurement point."""
    warnings: list[str] = []

    if point.errors_since_last is not None and point.errors_since_last > 0:
        warnings.append(f"YELLOW: {point.errors_since_last} error(s) since last snapshot")
    if point.warnings_since_last is not None and point.warnings_since_last > 0:
        warnings.append(f"YELLOW: {point.warnings_since_last} warning(s) since last snapshot")
    if point.closed_trades is None or point.closed_trades == 0:
        warnings.append("YELLOW: no closed trades yet — insufficient signal")
    if point.total_profit_abs is None:
        warnings.append("YELLOW: profit data unavailable")
    if point.container_healthy is None:
        warnings.append("UNKNOWN: container health not collected in read-only mode")
    if point.runtime_proof_status == "":
        warnings.append("UNKNOWN: runtime proof not checked")

    return warnings


def evaluate_measurement_safety(point: MeasurementPoint) -> MeasurementDecision:
    """Evaluate whether a single measurement point is safe.

    Returns RED on any safety or runtime violation.
    Returns YELLOW on missing data or warnings.
    Returns GREEN if all safety criteria pass.
    """
    reasons = _hard_safety_reasons(point)

    if reasons:
        return MeasurementDecision(
            verdict="RED",
            decision="ROLLBACK_CANARY_OVERLAY",
            confidence="HIGH",
            reasons=tuple(reasons),
            next_step="Immediate safety rollback required. Remove overlay and restart canary with base config only.",
        )

    warnings = _point_warning_reasons(point)

    if warnings:
        return MeasurementDecision(
            verdict="YELLOW",
            decision="CONTINUE_MEASUREMENT" if point.label in ("T1", "T2") else "EXTEND_MEASUREMENT",
            confidence="MEDIUM",
            reasons=tuple(warnings),
            next_step="Continue measurement. Monitor warnings. Do not rollback or apply.",
        )

    return MeasurementDecision(
        verdict="GREEN",
        decision="CONTINUE_MEASUREMENT" if point.label in ("T1", "T2") else "KEEP_CANARY_OVERLAY",
        confidence="HIGH",
        reasons=(f"GREEN: all safety criteria pass for {point.label}",),
        next_step="Continue measurement to next point.",
    )


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------


def compare_canary_to_control(
    canary_previous: MeasurementPoint,
    canary_current: MeasurementPoint,
    control_previous: MeasurementPoint | None = None,
    control_current: MeasurementPoint | None = None,
) -> MeasurementComparison:
    """Compute deltas and gaps between canary and control.

    All ``None`` values are propagated safely (no division by zero).
    """
    notes: list[str] = []

    # Canary deltas
    canary_profit_delta: float | None = None
    canary_trade_delta: int | None = None

    if (
        canary_current.total_profit_abs is not None
        and canary_previous.total_profit_abs is not None
    ):
        canary_profit_delta = round(
            canary_current.total_profit_abs - canary_previous.total_profit_abs, 2
        )

    if (
        canary_current.closed_trades is not None
        and canary_previous.closed_trades is not None
    ):
        canary_trade_delta = canary_current.closed_trades - canary_previous.closed_trades

    # Control deltas
    control_profit_delta: float | None = None
    control_trade_delta: int | None = None

    if (
        control_current is not None
        and control_previous is not None
        and control_current.total_profit_abs is not None
        and control_previous.total_profit_abs is not None
    ):
        control_profit_delta = round(
            control_current.total_profit_abs - control_previous.total_profit_abs, 2
        )

    if (
        control_current is not None
        and control_previous is not None
        and control_current.closed_trades is not None
        and control_previous.closed_trades is not None
    ):
        control_trade_delta = control_current.closed_trades - control_previous.closed_trades

    # Gap analysis
    profit_gap: float | None = None
    trade_gap: int | None = None

    if canary_profit_delta is not None and control_profit_delta is not None:
        profit_gap = round(canary_profit_delta - control_profit_delta, 2)
        if abs(profit_gap) > 0.01:
            notes.append(f"profit_gap: canary={canary_profit_delta:+.2f} vs control={control_profit_delta:+.2f}")

    if canary_trade_delta is not None and control_trade_delta is not None:
        trade_gap = canary_trade_delta - control_trade_delta
        if trade_gap != 0:
            notes.append(f"trade_gap: canary={canary_trade_delta:+d} vs control={control_trade_delta:+d}")

    if not notes:
        notes.append("no significant gap between canary and control")

    return MeasurementComparison(
        canary_delta_profit_abs=canary_profit_delta,
        canary_delta_trades=canary_trade_delta,
        control_delta_profit_abs=control_profit_delta,
        control_delta_trades=control_trade_delta,
        canary_vs_control_profit_gap=profit_gap,
        canary_vs_control_trade_gap=trade_gap,
        notes=tuple(notes),
    )


# ---------------------------------------------------------------------------
# Point decision
# ---------------------------------------------------------------------------


def decide_measurement_point(
    *,
    label: Literal["T1", "T2", "T3"],
    canary_previous: MeasurementPoint,
    canary_current: MeasurementPoint,
    control_previous: MeasurementPoint | None = None,
    control_current: MeasurementPoint | None = None,
) -> MeasurementDecision:
    """Evaluate one measurement point (T1/T2/T3).

    Wraps safety evaluation + comparison into a single decision.
    """
    safety = evaluate_measurement_safety(canary_current)

    # If safety is RED, return immediately
    if safety.verdict == "RED":
        return safety

    # Compute comparison
    comparison = compare_canary_to_control(
        canary_previous=canary_previous,
        canary_current=canary_current,
        control_previous=control_previous,
        control_current=control_current,
    )

    all_reasons: list[str] = list(safety.reasons)

    # Add comparison notes
    for note in comparison.notes:
        if note not in all_reasons:
            all_reasons.append(note)

    # T1 — stability check; profit not required
    if label == "T1":
        if safety.verdict == "YELLOW":
            return MeasurementDecision(
                verdict="YELLOW",
                decision="CONTINUE_MEASUREMENT",
                confidence="MEDIUM",
                reasons=tuple(all_reasons),
                next_step="T1 YELLOW — continue to T2. Monitor warnings. No rollback.",
            )
        return MeasurementDecision(
            verdict="GREEN",
            decision="CONTINUE_MEASUREMENT",
            confidence="HIGH",
            reasons=tuple(all_reasons),
            next_step="T1 GREEN — proceed to T2. No action required.",
        )

    # T2 — first effect signal
    if label == "T2":
        if safety.verdict == "YELLOW":
            return MeasurementDecision(
                verdict="YELLOW",
                decision="CONTINUE_MEASUREMENT",
                confidence="MEDIUM",
                reasons=tuple(all_reasons),
                next_step="T2 YELLOW — proceed to T3. Mark candidate as uncertain.",
            )
        return MeasurementDecision(
            verdict="GREEN",
            decision="CONTINUE_MEASUREMENT",
            confidence="HIGH",
            reasons=tuple(all_reasons),
            next_step="T2 GREEN — proceed to T3. Signal appears stable.",
        )

    # T3 — final decision
    if safety.verdict == "YELLOW":
        return MeasurementDecision(
            verdict="YELLOW",
            decision="EXTEND_MEASUREMENT",
            confidence="MEDIUM",
            reasons=tuple(all_reasons),
            next_step="T3 YELLOW — extend measurement by 24h or investigate root cause.",
        )

    return MeasurementDecision(
        verdict="GREEN",
        decision="KEEP_CANARY_OVERLAY",
        confidence="HIGH",
        reasons=tuple(all_reasons),
        next_step="T3 GREEN — keep canary overlay. Prepare next candidate for research.",
    )


# ---------------------------------------------------------------------------
# Final decision
# ---------------------------------------------------------------------------


def decide_final_measurement(
    *,
    canary_points: Sequence[MeasurementPoint],
    control_points: Sequence[MeasurementPoint] | None = None,
) -> MeasurementDecision:
    """Evaluate the entire measurement sequence (T0..T3).

    Requires all 4 canary points. Missing control data is accepted
    (lowers confidence to MEDIUM). Final KEEP decisions distinguish
    hard safety blockers from historical non-critical warnings.
    """
    reasons: list[str] = []

    if len(canary_points) < 4:
        return MeasurementDecision(
            verdict="YELLOW",
            decision="EXTEND_MEASUREMENT",
            confidence="LOW",
            reasons=(
                f"incomplete_data: {len(canary_points)} canary points "
                f"(expected 4: T0..T3)",
            ),
            next_step="Collect all 4 measurement points before final decision.",
        )

    canary_by_label = {p.label: p for p in canary_points}
    if set(canary_by_label) != {"T0", "T1", "T2", "T3"}:
        return MeasurementDecision(
            verdict="YELLOW",
            decision="EXTEND_MEASUREMENT",
            confidence="LOW",
            reasons=(f"invalid_labels: expected T0..T3, got {sorted(canary_by_label)}",),
            next_step="Ensure T0..T3 are all present before final decision.",
        )

    ordered_canary_points = [canary_by_label[label] for label in ("T0", "T1", "T2", "T3")]

    hard_reasons: list[str] = []
    inconclusive_reasons: list[str] = []
    soft_reasons: list[str] = []
    point_summaries: list[str] = []

    for point in ordered_canary_points:
        point_hard_reasons = _hard_safety_reasons(point)
        if point_hard_reasons:
            hard_reasons.extend(f"{point.label}: {reason}" for reason in point_hard_reasons)
            point_summaries.append(f"{point.label}: RED — {point_hard_reasons[0]}")
            continue

        point_inconclusive = False
        point_soft = False

        if point.errors_since_last is not None and point.errors_since_last > 0:
            inconclusive_reasons.append(
                f"{point.label}: YELLOW — {point.errors_since_last} error(s) since last snapshot"
            )
            point_inconclusive = True
        elif point.warnings_since_last is not None and point.warnings_since_last > 0:
            soft_reasons.append(
                f"{point.label}: SOFT_WARNING — {point.warnings_since_last} warning(s) since last snapshot"
            )
            point_soft = True

        if point.container_healthy is None:
            soft_reasons.append(
                f"{point.label}: UNKNOWN — container health not collected in read-only mode"
            )
            point_soft = True
        if point.runtime_proof_status == "":
            inconclusive_reasons.append(
                f"{point.label}: UNKNOWN — runtime proof not checked"
            )
            point_inconclusive = True

        if point_inconclusive:
            point_summaries.append(f"{point.label}: YELLOW")
        elif point_soft:
            point_summaries.append(f"{point.label}: GREEN_WITH_SOFT_WARNINGS")
        else:
            point_summaries.append(f"{point.label}: GREEN")

    if hard_reasons:
        return MeasurementDecision(
            verdict="RED",
            decision="ROLLBACK_CANARY_OVERLAY",
            confidence="HIGH",
            reasons=tuple(hard_reasons),
            next_step="Safety violation detected. Rollback canary overlay immediately.",
        )

    t0 = canary_by_label["T0"]
    t3 = canary_by_label["T3"]

    comparison: MeasurementComparison | None = None
    control_comparison_available = False
    control_by_label: dict[str, MeasurementPoint] = {}
    if control_points and len(control_points) >= 4:
        control_by_label = {p.label: p for p in control_points}
        if {"T0", "T1", "T2", "T3"}.issubset(control_by_label):
            comparison = compare_canary_to_control(
                canary_previous=t0,
                canary_current=t3,
                control_previous=control_by_label["T0"],
                control_current=control_by_label["T3"],
            )
            control_comparison_available = True

    if t0.closed_trades is None or t3.closed_trades is None:
        inconclusive_reasons.append("incomplete_canary_trade_data: missing T0/T3 closed trade counts")
    if t0.total_profit_abs is None or t3.total_profit_abs is None:
        inconclusive_reasons.append("incomplete_canary_profit_data: missing T0/T3 total profit")

    canary_profit_delta: float | None = None
    canary_trade_delta: int | None = None
    if comparison is not None:
        canary_profit_delta = comparison.canary_delta_profit_abs
        canary_trade_delta = comparison.canary_delta_trades
    elif t0.total_profit_abs is not None and t3.total_profit_abs is not None:
        canary_profit_delta = round(t3.total_profit_abs - t0.total_profit_abs, 2)
    if t0.closed_trades is not None and t3.closed_trades is not None:
        canary_trade_delta = t3.closed_trades - t0.closed_trades

    if canary_profit_delta is None:
        inconclusive_reasons.append("incomplete_canary_profit_delta: unable to compute T0→T3 profit delta")
    if canary_trade_delta is None:
        inconclusive_reasons.append("incomplete_canary_trade_delta: unable to compute T0→T3 trade delta")
    elif canary_trade_delta <= 0:
        inconclusive_reasons.append(
            "insufficient_canary_closures: no new closed canary trades across the final measurement window"
        )

    if control_comparison_available and comparison is not None:
        for note in comparison.notes:
            reasons.append(f"comparison: {note}")

        if comparison.control_delta_profit_abs is None:
            inconclusive_reasons.append(
                "incomplete_control_profit_delta: unable to compute control T0→T3 profit delta"
            )
        if comparison.control_delta_trades is None:
            inconclusive_reasons.append(
                "incomplete_control_trade_delta: unable to compute control T0→T3 trade delta"
            )
        if (
            comparison.canary_vs_control_profit_gap is not None
            and comparison.canary_vs_control_profit_gap < 0
        ):
            inconclusive_reasons.append(
                "underperform: canary profit delta "
                f"{comparison.canary_delta_profit_abs:+.2f} is below control "
                f"{comparison.control_delta_profit_abs:+.2f}"
            )

    if inconclusive_reasons:
        return MeasurementDecision(
            verdict="YELLOW",
            decision="EXTEND_MEASUREMENT",
            confidence="MEDIUM" if control_comparison_available else "LOW",
            reasons=tuple([
                *point_summaries,
                *soft_reasons,
                *reasons,
                *inconclusive_reasons,
            ]),
            next_step="Measurement inconclusive. Extend window or investigate root cause.",
        )

    summary_reasons = list(point_summaries)
    summary_reasons.extend(soft_reasons)
    summary_reasons.extend(reasons)
    if not control_comparison_available:
        summary_reasons.append("comparison: control baseline unavailable; KEEP based on canary-only safety and progression")

    return MeasurementDecision(
        verdict="GREEN",
        decision="KEEP_CANARY_OVERLAY",
        confidence="MEDIUM" if soft_reasons or not control_comparison_available else "HIGH",
        reasons=tuple(summary_reasons),
        next_step="Final safety and measurement evidence are sufficient. Keep canary overlay and prepare the next candidate review.",
    )
