r"""Final Measurement Decision Pack — Phase 4E.

Aggregates T0/T1/T2/T3 reports and produces a guarded final decision.
No official T3 before scheduled timestamp. Smoke T3 never counts as official.

Architecture
------------
::

    build_measurement_report_registry()
        → scans report directory for T0..T3 + smoke reports

    validate_official_t3_guard()
        → rejects final decisions before scheduled T3

    build_final_measurement_decision_pack()
        → uses decide_final_measurement() from decision_engine
        → returns FinalMeasurementDecisionPack

    render_final_measurement_report()
        → markdown string with full evidence + decision
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from si_v2.measurement.decision_engine import (
    MeasurementPoint,
    decide_final_measurement,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CANDIDATE_ID: str = "max_open_trades_3_to_2"
TARGET_BOT: str = "freqtrade-freqforge-canary"
SCHEDULED_T3_UTC: str = "2026-06-28T18:27:00Z"
REPORT_DIR: Path = Path("docs/reports")

OFFICIAL_LABELS: tuple[str, ...] = ("T0", "T1", "T2", "T3")
REQUIRED_OFFICIAL: tuple[str, ...] = ("T0", "T1", "T2", "T3")

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MeasurementReportRef:
    """Reference to a single measurement report file."""

    label: str
    path: str
    exists: bool
    official: bool
    smoke: bool
    scheduled_timestamp_utc: str | None = None
    actual_timestamp_utc: str | None = None
    verdict: str | None = None
    decision: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "label": self.label,
            "path": self.path,
            "exists": self.exists,
            "official": self.official,
            "smoke": self.smoke,
            "scheduled_timestamp_utc": self.scheduled_timestamp_utc,
            "actual_timestamp_utc": self.actual_timestamp_utc,
            "verdict": self.verdict,
            "decision": self.decision,
        }


@dataclass(frozen=True)
class FinalMeasurementDecisionPack:
    """Complete final decision pack for one candidate."""

    candidate_id: str
    target_bot: str
    reports: tuple[MeasurementReportRef, ...]
    all_required_reports_present: bool
    official_t3_present: bool
    final_verdict: str
    final_decision: str
    confidence: str
    reasons: tuple[str, ...]
    next_step: str
    blocked_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "candidate_id": self.candidate_id,
            "target_bot": self.target_bot,
            "reports": [r.to_dict() for r in self.reports],
            "all_required_reports_present": self.all_required_reports_present,
            "official_t3_present": self.official_t3_present,
            "final_verdict": self.final_verdict,
            "final_decision": self.final_decision,
            "confidence": self.confidence,
            "reasons": list(self.reasons),
            "next_step": self.next_step,
            "blocked_reasons": list(self.blocked_reasons),
        }


# ---------------------------------------------------------------------------
# Report registry
# ---------------------------------------------------------------------------


def _is_smoke_report(filename: str) -> bool:
    """Detect smoke reports by their filename prefix."""
    return "smoke-" in filename.lower() or "smoke_" in filename.lower()


def _is_official_report(label: str) -> bool:
    return label in OFFICIAL_LABELS


def _guess_label_from_filename(filename: str) -> str:
    """Try to guess the label from a filename."""
    stem = Path(filename).stem.lower()
    for label in OFFICIAL_LABELS:
        if f"-{label.lower()}" in stem or f"t{label[1:]}" in stem:
            return label
    return filename


def build_measurement_report_registry(
    *,
    report_dir: Path = REPORT_DIR,
    candidate_id: str = CANDIDATE_ID,
) -> tuple[MeasurementReportRef, ...]:
    """Scan the report directory and build a registry of all measurement
    reports for the given candidate.

    Pure Python — no subprocess, no Docker, no side effects.
    """
    refs: list[MeasurementReportRef] = []
    seen_labels: set[str] = set()

    if not report_dir.exists():
        return ()

    # Scan for measurement report files
    for fpath in sorted(report_dir.glob("si-v2-phase-4-measurement-*.md")):
        fname = fpath.name
        label = _guess_label_from_filename(fname)
        is_smoke = _is_smoke_report(fname)
        is_official = _is_official_report(label) and not is_smoke

        if label in seen_labels and is_smoke:
            continue  # prefer official over smoke
        if label in seen_labels and not is_smoke:
            # Replace smoke with official
            refs = [r for r in refs if r.label != label]

        ref = MeasurementReportRef(
            label=label,
            path=str(fpath),
            exists=True,
            official=is_official,
            smoke=is_smoke,
        )
        refs.append(ref)
        seen_labels.add(label)

    # Add missing official entries
    for label in REQUIRED_OFFICIAL:
        if label not in seen_labels:
            refs.append(MeasurementReportRef(
                label=label,
                path=str(report_dir / f"si-v2-phase-4-measurement-{label.lower()}-missing.md"),
                exists=False,
                official=True,
                smoke=False,
            ))

    return tuple(sorted(refs, key=lambda r: r.label))


# ---------------------------------------------------------------------------
# T3 official guard
# ---------------------------------------------------------------------------


def validate_official_t3_guard(
    *,
    now_utc: str,
    scheduled_t3_utc: str = SCHEDULED_T3_UTC,
    t3_report_exists: bool,
    t3_report_official: bool,
) -> tuple[bool, tuple[str, ...]]:
    """Validate whether an official T3 decision can be made.

    Returns (valid, reasons). ``valid=True`` only when the scheduled time
    has passed and an official T3 report exists.
    """
    reasons: list[str] = []

    # Parse timestamps
    try:
        now = datetime.fromisoformat(now_utc.replace("Z", "+00:00"))
        scheduled = datetime.fromisoformat(scheduled_t3_utc.replace("Z", "+00:00"))
    except (ValueError, TypeError) as e:
        return False, (f"timestamp_parse_error: {e}",)

    if now < scheduled:
        reasons.append(
            f"official_t3_not_due: current time {now_utc} is before "
            f"scheduled T3 at {scheduled_t3_utc}"
        )

    if not t3_report_exists:
        reasons.append("official_t3_report_missing: no T3 report file found")

    if t3_report_exists and not t3_report_official:
        reasons.append("t3_not_official: T3 report is smoke/precheck, not official")

    return len(reasons) == 0, tuple(reasons)


# ---------------------------------------------------------------------------
# Final decision builder
# ---------------------------------------------------------------------------


def build_final_measurement_decision_pack(
    *,
    canary_points: Sequence[MeasurementPoint],
    control_points: Sequence[MeasurementPoint] | None = None,
    reports: Sequence[MeasurementReportRef],
    now_utc: str,
    scheduled_t3_utc: str = SCHEDULED_T3_UTC,
) -> FinalMeasurementDecisionPack:
    """Build the final measurement decision pack.

    This function:
    - Counts present reports
    - Validates T3 guard
    - Calls decide_final_measurement() from decision_engine
    - Returns a guarded FinalMeasurementDecisionPack
    """
    blocked: list[str] = []
    reasons: list[str] = []

    # Count present/official reports
    present = {r.label for r in reports if r.exists}
    official_t3 = any(
        r.label == "T3" and r.exists and r.official
        for r in reports
    )
    all_required = all(label in present for label in REQUIRED_OFFICIAL)

    # Validate T3 guard
    t3_valid, t3_reasons = validate_official_t3_guard(
        now_utc=now_utc,
        scheduled_t3_utc=scheduled_t3_utc,
        t3_report_exists="T3" in present,
        t3_report_official=official_t3,
    )

    if not t3_valid:
        blocked.extend(t3_reasons)

    # If no official T3, we can't make a final KEEP/ROLLBACK decision
    if not official_t3 and "T3" in present:
        # Only smoke T3 exists — not sufficient for final decision
        blocked.append("t3_only_smoke: an official T3 report is required for final decision")

    if not all_required:
        missing = [lb for lb in REQUIRED_OFFICIAL if lb not in present]
        blocked.append(f"missing_reports: {missing}")

    # Use decision engine if we have enough data
    if len(canary_points) >= 2 and not blocked:
        final_dec = decide_final_measurement(
            canary_points=canary_points,
            control_points=control_points,
        )
        reasons = list(final_dec.reasons)

        # Override if we have smoke T3 but no official T3
        if not official_t3 and final_dec.decision in ("KEEP_CANARY_OVERLAY", "ROLLBACK_CANARY_OVERLAY"):
            return FinalMeasurementDecisionPack(
                    candidate_id=CANDIDATE_ID,
                    target_bot=TARGET_BOT,
                    reports=tuple(reports),
                    all_required_reports_present=all_required,
                    official_t3_present=official_t3,
                    final_verdict="YELLOW",
                    final_decision="EXTEND_MEASUREMENT",
                    confidence="MEDIUM",
                    reasons=(*reasons, f"overridden_by_t3_guard: {final_dec.decision} requires official T3"),
                    next_step=f"Wait for official T3 at {scheduled_t3_utc}.",
                    blocked_reasons=tuple(blocked),
                )

        return FinalMeasurementDecisionPack(
            candidate_id=CANDIDATE_ID,
            target_bot=TARGET_BOT,
            reports=tuple(reports),
            all_required_reports_present=all_required,
            official_t3_present=official_t3,
            final_verdict=final_dec.verdict,
            final_decision=final_dec.decision,
            confidence=final_dec.confidence,
            reasons=tuple(reasons),
            next_step=final_dec.next_step,
            blocked_reasons=(),
        )

    # No decision engine available — return blocked/extend
    if blocked:
        return FinalMeasurementDecisionPack(
            candidate_id=CANDIDATE_ID,
            target_bot=TARGET_BOT,
            reports=tuple(reports),
            all_required_reports_present=all_required,
            official_t3_present=official_t3,
            final_verdict="YELLOW" if not any("RED" in r for r in blocked) else "RED",
            final_decision="EXTEND_MEASUREMENT",
            confidence="LOW",
            reasons=tuple(reasons) if reasons else ("insufficient_data",),
            next_step="Wait for official T3 at {scheduled_t3_utc}. Collect required measurement points.",
            blocked_reasons=tuple(blocked),
        )

    return FinalMeasurementDecisionPack(
        candidate_id=CANDIDATE_ID,
        target_bot=TARGET_BOT,
        reports=tuple(reports),
        all_required_reports_present=all_required,
        official_t3_present=official_t3,
        final_verdict="YELLOW",
        final_decision="EXTEND_MEASUREMENT",
        confidence="LOW",
        reasons=("insufficient_data_for_final_decision",),
        next_step="Collect at least T0..T2 before final decision.",
        blocked_reasons=(),
    )


# ---------------------------------------------------------------------------
# Report renderer
# ---------------------------------------------------------------------------


def render_final_measurement_report(
    pack: FinalMeasurementDecisionPack,
) -> str:
    """Render the final measurement decision pack as a markdown report."""
    lines: list[str] = []
    lines.append("# SI-v2 Phase 4 — Final Measurement Decision")
    lines.append("")
    lines.append(f"**Candidate:** {pack.candidate_id}")
    lines.append(f"**Target Bot:** {pack.target_bot}")
    lines.append(f"**Final Verdict:** {pack.final_verdict}")
    lines.append(f"**Final Decision:** {pack.final_decision}")
    lines.append(f"**Confidence:** {pack.confidence}")
    lines.append("")

    lines.append("## Report Overview")
    lines.append("")
    lines.append("| Label | Exists | Official | Smoke |")
    lines.append("|-------|--------|----------|-------|")
    for r in pack.reports:
        ok = "✅" if r.exists else "❌"
        off = "✅" if r.official else "❌"
        sm = "✅" if r.smoke else "❌"
        lines.append(f"| {r.label} | {ok} | {off} | {sm} |")
    lines.append("")

    lines.append(f"**All required reports present:** {'✅' if pack.all_required_reports_present else '❌'}")
    lines.append(f"**Official T3 present:** {'✅' if pack.official_t3_present else '❌'}")
    lines.append("")

    if pack.blocked_reasons:
        lines.append("## Blocked Reasons")
        lines.append("")
        for r in pack.blocked_reasons:
            lines.append(f"- {r}")
        lines.append("")

    lines.append("## Decision Reasons")
    lines.append("")
    for r in pack.reasons:
        lines.append(f"- {r}")
    lines.append("")

    lines.append("## Next Step")
    lines.append("")
    lines.append(pack.next_step)
    lines.append("")

    return "\n".join(lines)
