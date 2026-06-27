r"""Measurement On-Demand Snapshot Runner — Phase 4D.

Provides a triggerable, idempotent, read-only measurement snapshot runner
that works both as a Python API and as a CLI module. Smoke runs use
``official=False``, ``smoke=True`` and never overwrite official T0/T1/T2/T3
reports.

Usage
-----
    from si_v2.measurement.snapshot_runner import run_measurement_snapshot, MeasurementSnapshotRequest

    result = run_measurement_snapshot(
        MeasurementSnapshotRequest(
            label="SMOKE_T3_PRECHECK", ..., official=False, smoke=True,
        )
    )

CLI::

    python -m si_v2.measurement.snapshot_runner \
        --label SMOKE_T3_PRECHECK \
        --candidate-id max_open_trades_3_to_2 \
        --target-bot freqtrade-freqforge-canary \
        --smoke \
        --official false
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from si_v2.measurement.decision_engine import (
    MeasurementPoint,
    decide_measurement_point,
    evaluate_measurement_safety,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CANARY_BOT_ID: str = "freqtrade-freqforge-canary"
CONTROL_BOT_ID: str = "freqtrade-freqforge"

SMOKE_REPORT_DIR: Path = Path("docs/reports")
SMOKE_PREFIX: str = "si-v2-phase-4-measurement-smoke-"

OFFICIAL_LABELS: frozenset[str] = frozenset({"T0", "T1", "T2", "T3"})

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MeasurementSnapshotRequest:
    """Request to run a measurement snapshot."""

    label: str
    """Snapshot label (e.g. ``SMOKE_T3_PRECHECK``). Must not be ``T0``..``T3``
    for smoke runs."""

    candidate_id: str
    """Candidate identifier (e.g. ``max_open_trades_3_to_2``)."""

    target_bot: str
    """Target bot (must be ``freqtrade-freqforge-canary``)."""

    control_bot: str = CONTROL_BOT_ID
    """Control bot for comparison."""

    scheduled_timestamp_utc: str | None = None
    """Expected scheduled timestamp (for smoke runs before official time)."""

    official: bool = False
    """If True, this is an official measurement point (T0..T3)."""

    smoke: bool = True
    """If True, this is a smoke test — labelled SMOKE, no official
    report overwrite."""

    write_report: bool = True
    """Whether to write a report file."""


@dataclass(frozen=True)
class MeasurementSnapshotResult:
    """Result of a measurement snapshot run."""

    status: Literal["GREEN", "YELLOW", "RED", "BLOCKED"]
    label: str
    official: bool
    smoke: bool
    report_path: str | None
    runtime_proof_status: str
    decision: str
    blocked_reasons: tuple[str, ...]
    next_step: str
    timestamp_utc: str

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "label": self.label,
            "official": self.official,
            "smoke": self.smoke,
            "report_path": self.report_path,
            "runtime_proof_status": self.runtime_proof_status,
            "decision": self.decision,
            "blocked_reasons": list(self.blocked_reasons),
            "next_step": self.next_step,
            "timestamp_utc": self.timestamp_utc,
        }


# ---------------------------------------------------------------------------
# Report path helpers
# ---------------------------------------------------------------------------


def _build_report_path(
    label: str,
    official: bool,
    smoke: bool,
) -> Path:
    """Build a report file path. Smoke runs get a SMOKE prefix and never
    overwrite official reports."""
    now = datetime.now(UTC)
    date_str = now.strftime("%Y-%m-%d")
    if smoke:
        safe_label = label.lower().replace(" ", "_").replace("/", "_")
        return SMOKE_REPORT_DIR / f"{SMOKE_PREFIX}{safe_label}-{date_str}.md"
    # Official
    return SMOKE_REPORT_DIR / f"si-v2-phase-4-measurement-{label.lower()}-{date_str}.md"


def _check_report_overwrite(path: Path, official: bool, smoke: bool) -> str | None:
    """Check if writing to the path would overwrite an existing official report.
    Returns an error message or None."""
    if not path.exists():
        return None
    if smoke:
        return f"smoke_report_overwrite: {path} already exists — refusing to overwrite"
    return None


# ---------------------------------------------------------------------------
# Runtime data collector (read-only, mockable)
# ---------------------------------------------------------------------------


def _collect_runtime_data(
    target_bot: str,
) -> dict[str, object]:
    """Collect runtime data for the target bot.

    Returns a dict that can be overridden by calling code or tests.
    """
    # This is a placeholder — real data is collected at the call site
    # and passed via the runner. The runner processes what it receives.
    return {
        "bot_id": target_bot,
        "timestamp_utc": datetime.now(UTC).isoformat(),
    }


# ---------------------------------------------------------------------------
# Main snapshot runner
# ---------------------------------------------------------------------------


def run_measurement_snapshot(
    request: MeasurementSnapshotRequest,
    *,
    canary_point: MeasurementPoint | None = None,
    previous_point: MeasurementPoint | None = None,
    control_point: MeasurementPoint | None = None,
    previous_control: MeasurementPoint | None = None,
) -> MeasurementSnapshotResult:
    """Run a measurement snapshot — read-only, no mutation.

    Args:
        request: The snapshot request.
        canary_point: Pre-built canary MeasurementPoint. If None, the runner
            creates one from available data (may be incomplete).
        previous_point: Previous canary MeasurementPoint for comparison
            (e.g. T0 for T1).
        control_point: Current control bot MeasurementPoint.
        previous_control: Previous control bot MeasurementPoint.

    Returns:
        ``MeasurementSnapshotResult`` with status and evidence.
    """
    now = datetime.now(UTC)
    now_str = now.isoformat()
    blocked: list[str] = []

    # -- Validate label for smoke runs --
    if request.smoke and request.label in OFFICIAL_LABELS:
        return MeasurementSnapshotResult(
            status="BLOCKED",
            label=request.label,
            official=request.official,
            smoke=request.smoke,
            report_path=None,
            runtime_proof_status="BLOCKED",
            decision="",
            blocked_reasons=(f"smoke_label_collision: {request.label!r} is an official label",),
            next_step="Use a non-official label for smoke runs.",
            timestamp_utc=now_str,
        )

    # -- Validate target bot --
    if request.target_bot != CANARY_BOT_ID:
        blocked.append(f"invalid_target_bot: {request.target_bot!r} != {CANARY_BOT_ID!r}")

    # -- Build report path --
    report_path = _build_report_path(request.label, request.official, request.smoke)
    overwrite_error = _check_report_overwrite(report_path, request.official, request.smoke)
    if overwrite_error:
        blocked.append(overwrite_error)

    # -- If no canary point provided, build minimal one --
    if canary_point is None:
        canary_point = MeasurementPoint(
            label=request.label,  # type: ignore[arg-type]
            timestamp_utc=now_str,
            bot_id=request.target_bot,
            candidate_id=request.candidate_id,
            runtime_proof_status="",
            max_open_trades=None,
            dry_run=None,
            container_healthy=None,
            open_trades=None,
            closed_trades=None,
            total_profit_abs=None,
            realized_profit_abs=None,
            win_rate=None,
            drawdown_abs=None,
            errors_since_last=None,
            warnings_since_last=None,
            unexpected_restart=False,
            rollback_required=False,
        )

    # -- Run safety evaluation --
    safety = evaluate_measurement_safety(canary_point)

    # -- Run point decision if we have previous data --
    decision_str = ""
    if previous_point is not None:
        point_dec = decide_measurement_point(
            label=canary_point.label,  # type: ignore[arg-type]
            canary_previous=previous_point,
            canary_current=canary_point,
            control_previous=previous_control,
            control_current=control_point,
        )
        decision_str = f"{point_dec.verdict}/{point_dec.decision}"
    else:
        decision_str = f"{safety.verdict}/{safety.decision}"

    # -- Determine final status --
    if blocked:
        return MeasurementSnapshotResult(
            status="BLOCKED",
            label=request.label,
            official=request.official,
            smoke=request.smoke,
            report_path=None,
            runtime_proof_status=canary_point.runtime_proof_status,
            decision="",
            blocked_reasons=tuple(blocked),
            next_step="Fix blocked reasons and retry.",
            timestamp_utc=now_str,
        )

    status = safety.verdict

    # -- Write report --
    written_path: str | None = None
    if request.write_report and not blocked:
        _write_snapshot_report(
            report_path=report_path,
            request=request,
            canary_point=canary_point,
            safety=safety,
            decision_str=decision_str,
            control_point=control_point,
        )
        written_path = str(report_path)

    return MeasurementSnapshotResult(
        status=status,  # type: ignore[arg-type]
        label=request.label,
        official=request.official,
        smoke=request.smoke,
        report_path=written_path,
        runtime_proof_status=canary_point.runtime_proof_status,
        decision=decision_str,
        blocked_reasons=(),
        next_step=f"Snapshot complete. {'Official' if request.official else 'Smoke'} measurement recorded.",
        timestamp_utc=now_str,
    )


# ---------------------------------------------------------------------------
# Report writer
# ---------------------------------------------------------------------------


def _write_snapshot_report(
    report_path: Path,
    request: MeasurementSnapshotRequest,
    canary_point: MeasurementPoint,
    safety,
    decision_str: str,
    control_point: MeasurementPoint | None = None,
) -> None:
    """Write a measurement snapshot report to disk."""
    lines: list[str] = []
    lines.append(f"# SI-v2 Phase 4 — Measurement Snapshot: {request.label}")
    lines.append("")
    lines.append(f"**Date:** {canary_point.timestamp_utc}")
    lines.append(f"**Label:** {request.label}")
    lines.append(f"**Official:** {request.official}")
    lines.append(f"**Smoke:** {request.smoke}")
    lines.append(f"**Candidate:** {request.candidate_id}")
    lines.append(f"**Target Bot:** {request.target_bot}")
    lines.append("")
    lines.append("## RuntimeEffectProof")
    lines.append("")
    lines.append("| Check | Result |")
    lines.append("|-------|--------|")
    lines.append(f"| Runtime proof status | {canary_point.runtime_proof_status} |")
    lines.append(f"| max_open_trades | {canary_point.max_open_trades} |")
    lines.append(f"| dry_run | {canary_point.dry_run} |")
    lines.append(f"| Container healthy | {canary_point.container_healthy} |")
    lines.append(f"| Open trades | {canary_point.open_trades} |")
    lines.append(f"| Closed trades | {canary_point.closed_trades} |")
    lines.append(f"| Profit (abs) | {canary_point.total_profit_abs} USD |")
    lines.append(f"| Errors since last | {canary_point.errors_since_last} |")
    lines.append(f"| Warnings since last | {canary_point.warnings_since_last} |")
    if control_point:
        lines.append(f"| Control bot | {control_point.bot_id} |")
        lines.append(f"| Control profit | {control_point.total_profit_abs} USD |")
    lines.append("")
    lines.append("## Decision Engine")
    lines.append("")
    lines.append("| Field | Value |")
    lines.append("|-------|-------|")
    lines.append(f"| Safety verdict | {safety.verdict} |")
    lines.append(f"| Full decision | {decision_str} |")
    for r in safety.reasons:
        lines.append(f"| Reason | {r} |")
    lines.append(f"| Next step | {safety.next_step} |")
    lines.append("")
    lines.append("## Safety")
    lines.append("")
    lines.append(f"- rollback_required: {canary_point.rollback_required}")
    lines.append("- No apply, restart, or rollback executed")
    lines.append("")

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for the snapshot runner."""
    import argparse

    parser = argparse.ArgumentParser(description="SI-v2 Measurement Snapshot Runner")
    parser.add_argument("--label", required=True, help="Snapshot label (e.g. SMOKE_T3_PRECHECK)")
    parser.add_argument("--candidate-id", required=True, help="Candidate ID")
    parser.add_argument("--target-bot", default=CANARY_BOT_ID, help="Target bot ID")
    parser.add_argument("--control-bot", default=CONTROL_BOT_ID, help="Control bot ID")
    parser.add_argument("--official", action="store_true", help="Official measurement point")
    parser.add_argument("--smoke", action="store_true", default=True, help="Smoke test mode")
    parser.add_argument("--write-report", action="store_true", default=True, help="Write report file")
    parser.add_argument("--no-write-report", action="store_false", dest="write_report", help="Skip report writing")

    args = parser.parse_args(argv)

    request = MeasurementSnapshotRequest(
        label=args.label,
        candidate_id=args.candidate_id,
        target_bot=args.target_bot,
        control_bot=args.control_bot,
        official=args.official,
        smoke=args.smoke,
        write_report=args.write_report,
    )

    result = run_measurement_snapshot(request)
    print(json.dumps(result.to_dict(), indent=2))
    return 0 if result.status != "BLOCKED" else 1


if __name__ == "__main__":
    sys.exit(main())
