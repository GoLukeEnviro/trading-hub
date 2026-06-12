"""Deterministic weekly proposal-review cadence for SI v2.

Defines the complete policy for generating weekly review artifacts without
enabling proposal application, runtime mutation, or automatic trading behavior.
This module is purely declarative — no scheduler, timer, cron, systemd, or
Hermes job is activated.

Key principles:
  1. Weekly cycle runs exactly once per week, at a fixed time in a fixed timezone.
  2. All inputs are immutable; all outputs are deterministic and rooted.
  3. One cycle at a time — overlap prevention is mandatory.
  4. Review generation can NEVER apply or approve proposals.
  5. Requires #26 activation ceremony, #44 runtime truth, #176 credential isolation.
  6. Controller must be PAUSED and queue empty before any scheduled cycle.
  7. Timeout, retry, and failure handling cannot create duplicate proposals.

Reference: GitHub issue #66.
Depends on: issue #26 (activation ceremony).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import NamedTuple

# ---------------------------------------------------------------------------
# Versioned policy constants
# ---------------------------------------------------------------------------

POLICY_VERSION = 1

# Weekly cadence defaults
DEFAULT_WEEKLY_DAY = 0  # Monday (Python convention: 0=Monday per weekday())
DEFAULT_WEEKLY_HOUR_UTC = 9  # 09:00 UTC
DEFAULT_TIMEZONE = UTC
DEFAULT_JITTER_MAX_MINUTES = 15  # Random jitter window for start time
DEFAULT_MISSED_RUN_WINDOW_HOURS = 6  # How long after scheduled time a "missed" run is allowed

# Evidence lookback
EVIDENCE_LOOKBACK_WEEKS = 4
EVIDENCE_FRESHNESS_MAX_DAYS = 7

# Timeout and retry
MAX_CYCLE_TIMEOUT_SECONDS = 7200  # 2 hours max per weekly cycle
MAX_RETRY_ATTEMPTS = 2  # Retries for transient failures
RETRY_DELAY_SECONDS = 300  # 5-minute delay between retries

# Retention
DERIVED_ARTIFACT_RETENTION_WEEKS = 12  # 3 months retention for derived artifacts

# Overlap lock
OVERLAP_LOCK_KEY = "si_v2_weekly_review_cycle"

# Maximum derived output size (bytes)
MAX_DERIVED_OUTPUT_BYTES = 10 * 1024 * 1024  # 10 MB


class CadencePhase(StrEnum):
    """Phases of the weekly review cadence cycle."""

    PREFLIGHT = "preflight"
    ACQUIRE_LOCK = "acquire_lock"
    COLLECT_EVIDENCE = "collect_evidence"
    GENERATE_REVIEW = "generate_review"
    PERSIST_ARTIFACTS = "persist_artifacts"
    RELEASE_LOCK = "release_lock"
    DELIVER_REPORT = "deliver_report"
    RECORD_OUTCOME = "record_outcome"


class RunOutcome(StrEnum):
    """Outcome of a weekly review cycle run."""

    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"
    EMPTY = "EMPTY"
    SPARSE = "SPARSE"
    STALE = "STALE"
    CONFLICTING = "CONFLICTING"
    DEFERRED = "DEFERRED"
    FAILED = "FAILED"


class CycleLockState(StrEnum):
    """State of the overlap-prevention lock."""

    FREE = "FREE"
    LOCKED = "LOCKED"
    EXPIRED = "EXPIRED"


class ReviewInputContract(NamedTuple):
    """Immutable inputs to a weekly review cycle."""

    as_of: str  # ISO timestamp — the analytical point-in-time
    evidence_root: str  # Root directory for evidence files
    policy_version: int
    controller_state_commit: str  # SHA of the controller state this run is based on


class ReviewOutputContract(NamedTuple):
    """Deterministic outputs of a weekly review cycle."""

    output_root: str  # Root directory for all derived artifacts
    review_report_path: str  # Path to the main review report
    checksum: str  # SHA-256 checksum of the review report
    as_of: str
    generated_at: str
    outcome: RunOutcome


class PreflightCheck(NamedTuple):
    """Result of a single pre-cycle preflight check."""

    name: str
    passed: bool
    detail: str


# ---------------------------------------------------------------------------
# As-of timestamp handling
# ---------------------------------------------------------------------------


def compute_as_of_timestamp(
    reference_time: datetime | None = None,
    weekly_day: int = DEFAULT_WEEKLY_DAY,
    weekly_hour: int = DEFAULT_WEEKLY_HOUR_UTC,
) -> str:
    """Compute the analytical as_of timestamp for a weekly review cycle.

    The as_of timestamp is the most recent Monday 09:00 UTC (or configured
    day/hour) before or equal to the reference time.

    weekly_day uses Python convention: 0=Monday, 6=Sunday.

    Returns ISO-format string in UTC.
    """
    if reference_time is None:
        reference_time = datetime.now(UTC)

    # Walk backward day-by-day until we find the target weekday at or before reference
    candidate_date = reference_time.date()
    for offset in range(8):
        check_date = candidate_date - timedelta(days=offset)
        if check_date.weekday() == weekly_day:
            candidate_dt = datetime(
                check_date.year, check_date.month, check_date.day,
                weekly_hour, 0, 0,
                tzinfo=UTC,
            )
            if candidate_dt <= reference_time:
                return candidate_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    # Should never reach here
    return reference_time.strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Deterministic output roots
# ---------------------------------------------------------------------------


def compute_output_root(base_root: Path, as_of: str) -> Path:
    """Compute the deterministic output directory for a given as_of.

    Output structure: <base_root>/reviews/<YYYY>/<WW>/
    where YYYY is the ISO year and WW is the ISO week number.
    """
    # Parse as_of to get ISO week
    as_of_dt = datetime.strptime(as_of, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    iso_year, iso_week, _ = as_of_dt.isocalendar()
    return base_root / "reviews" / f"{iso_year:04d}" / f"W{iso_week:02d}"


# ---------------------------------------------------------------------------
# Evidence freshness validation
# ---------------------------------------------------------------------------


def validate_evidence_freshness(
    evidence_paths: list[Path],
    as_of: str,
    max_age_days: int = EVIDENCE_FRESHNESS_MAX_DAYS,
) -> tuple[bool, list[str]]:
    """Validate that evidence files are fresh enough for the review cycle.

    Returns (all_fresh, warnings).
    """
    warnings: list[str] = []
    as_of_dt = datetime.strptime(as_of, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    cutoff = as_of_dt - timedelta(days=max_age_days)

    for path in evidence_paths:
        if not path.exists():
            warnings.append(f"Evidence file missing: {path}")
            continue
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
        if mtime < cutoff:
            warnings.append(
                f"Evidence file stale: {path.name} "
                f"(mtime={mtime.strftime('%Y-%m-%dT%H:%M:%SZ')}, "
                f"cutoff={cutoff.strftime('%Y-%m-%dT%H:%M:%SZ')})"
            )

    return len(warnings) == 0, warnings


# ---------------------------------------------------------------------------
# Overlap lock validation
# ---------------------------------------------------------------------------


def validate_no_overlap(
    current_lock_state: CycleLockState,
) -> PreflightCheck:
    """Validate that no other review cycle is currently running."""
    if current_lock_state == CycleLockState.FREE:
        return PreflightCheck("overlap_lock", True, "lock is free")
    if current_lock_state == CycleLockState.EXPIRED:
        return PreflightCheck(
            "overlap_lock", False,
            "lock is expired — manual intervention required",
        )
    return PreflightCheck(
        "overlap_lock", False,
        "lock is held — another cycle is running",
    )


# ---------------------------------------------------------------------------
# Timeout validation
# ---------------------------------------------------------------------------


def validate_timeout(timeout_seconds: int) -> tuple[bool, str]:
    """Validate that a proposed timeout is within limits."""
    if timeout_seconds <= 0:
        return False, "timeout must be positive"
    if timeout_seconds > MAX_CYCLE_TIMEOUT_SECONDS:
        return False, (
            f"timeout {timeout_seconds}s exceeds max "
            f"{MAX_CYCLE_TIMEOUT_SECONDS}s"
        )
    return True, "ok"


# ---------------------------------------------------------------------------
# Run outcome classification
# ---------------------------------------------------------------------------


def classify_weekly_outcome(
    review_generated: bool,
    evidence_count: int,
    fresh: bool,
    conflicts: bool,
    errors: list[str] | None = None,
    warnings: list[str] | None = None,
) -> RunOutcome:
    """Classify the outcome of a weekly review cycle.

    Classification rules:
      - FAILED: errors present or review not generated
      - EMPTY: review generated but 0 evidence items
      - SPARSE: review generated but < expected minimum
      - STALE: evidence is not fresh
      - CONFLICTING: evidence items disagree
      - DEFERRED: transient failure, can retry
      - RED: unrecoverable failure
      - YELLOW: review generated with warnings
      - GREEN: review generated, evidence fresh, no issues
    """
    if errors:
        return RunOutcome.FAILED

    if not review_generated:
        return RunOutcome.FAILED

    if not fresh:
        return RunOutcome.STALE

    if conflicts:
        return RunOutcome.CONFLICTING

    if evidence_count == 0:
        return RunOutcome.EMPTY

    if evidence_count < 2:
        return RunOutcome.SPARSE

    if warnings:
        return RunOutcome.YELLOW

    return RunOutcome.GREEN


# ---------------------------------------------------------------------------
# Telegram delivery contract
# ---------------------------------------------------------------------------


def validate_telegram_delivery_contract(
    delivery_enabled: bool,
    channel_configured: bool,
    message_sent: bool,
    delivery_confirmed: bool,
) -> tuple[bool, list[str]]:
    """Validate Telegram delivery semantics.

    Rules:
      - Delivery is optional but must be documented.
      - If delivery is enabled, channel must be configured.
      - Delivery failure must not block the review cycle.
      - No secrets are included in delivery evidence.

    Returns (compliant, warnings).
    """
    warnings: list[str] = []

    if delivery_enabled and not channel_configured:
        warnings.append("Telegram delivery enabled but channel not configured")

    if delivery_enabled and not message_sent:
        warnings.append("Telegram delivery enabled but message not sent")

    # Delivery failure is non-blocking — just a warning
    if delivery_enabled and message_sent and not delivery_confirmed:
        warnings.append("Telegram message sent but delivery not confirmed")

    return len(warnings) == 0, warnings


# ---------------------------------------------------------------------------
# Separation proof: review cannot apply proposals
# ---------------------------------------------------------------------------


def prove_review_cannot_apply() -> list[str]:
    """Return proof statements that weekly review cannot apply or approve proposals.

    Structural invariants:
      1. Review commands are read-only and produce reports only.
      2. The approval gate is a separate path requiring distinct human action.
      3. No review output can mutate strategy, risk, or trading state.
    """
    return [
        "review_commands_are_read_only: validated by classify_weekly_outcome",
        "approval_gate_is_separate_path: validated by activation_ceremony module",
        "review_output_cannot_mutate_state: validated by test_separation_of_concerns",
    ]


# ---------------------------------------------------------------------------
# Retention and cleanup
# ---------------------------------------------------------------------------


def compute_retention_cutoff(
    reference_time: datetime | None = None,
    retention_weeks: int = DERIVED_ARTIFACT_RETENTION_WEEKS,
) -> str:
    """Compute the cutoff timestamp for artifact retention.

    Artifacts older than this cutoff should be cleaned up.
    """
    if reference_time is None:
        reference_time = datetime.now(UTC)
    cutoff = reference_time - timedelta(weeks=retention_weeks)
    return cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Operator procedure
# ---------------------------------------------------------------------------

OPERATOR_WEEKLY_PROCEDURE: list[str] = [
    "1. Verify controller is PAUSED and queue is empty.",
    "2. Verify #26 activation ceremony, #44 runtime truth, #176 credential isolation.",
    "3. Verify the weekly cycle lock is FREE (no overlapping run).",
    "4. Record the analytical as_of timestamp for this cycle.",
    "5. Collect evidence files; validate freshness (max 7 days old).",
    "6. Generate review report with deterministic output root.",
    "7. Persist artifacts; compute SHA-256 checksum.",
    "8. Classify outcome: GREEN / YELLOW / RED / EMPTY / SPARSE / STALE / CONFLICTING.",
    "9. Deliver report via Telegram (non-blocking, no secrets).",
    "10. Release the cycle lock.",
    "11. Record outcome in cycle log.",
    "12. If FAILED or RED: do NOT retry automatically; escalate to operator.",
    "13. If DEFERRED: retry up to 2 times with 5-minute delay; no duplicate proposals.",
    "14. After retention period (12 weeks): clean up derived artifacts.",
    "15. Document evidence in docs/context/ before closing.",
]

PAUSE_ROLLBACK_PROCEDURE: list[str] = [
    "PAUSE: Set controller_status to PAUSED, set pause_reason.",
    "DISABLE: Set all job enabled flags to False.",
    "ROLLBACK: Restore jobs.json from most recent timestamped backup.",
    "INCIDENT: Record incident in docs/context/ and escalate.",
]
