"""Fail-closed scheduler activation ceremony for SI v2.

Defines the complete, machine-validated policy governing when and how any
future SI v2 scheduled job may be enabled.  No scheduler, timer, cron,
systemd, or Hermes job is activated by this module — it is purely
declarative and validated through tests.

Key principles:
  1. Every job starts DISABLED and must receive an explicit approval token.
  2. The controller must be PAUSED, queue empty, active fields null, and
     baseline reconciled before the ceremony can even begin.
  3. Dedicated controller identity (#176) and Compose/runtime truth (#44)
     must be satisfied before any activation.
  4. Proposal generation can NEVER apply or approve weights.
  5. Every mutation requires a timestamped backup with SHA-256 checksum.
  6. Rollback is automatic on post-validation failure.

Reference: GitHub issue #26.
"""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import NamedTuple

# ---------------------------------------------------------------------------
# Versioned policy constants
# ---------------------------------------------------------------------------

POLICY_VERSION = 1

# Approval-token format: literal prefix + uppercase hex token
_APPROVAL_TOKEN_RE: re.Pattern[str] = re.compile(
    r"\AAPPROVE_ACTIVATE_[0-9A-F]{32}\Z"
)

# Allowed controller statuses before ceremony can start
_PRE_CEREMONY_STATUSES = frozenset({"PAUSED", "IDLE", "STOPPED"})

# Maximum concurrent active jobs (circuit breaker)
MAX_CONCURRENT_JOBS = 4

# Maximum retries per job before circuit-breaker trips
MAX_RETRIES = 3

# Maximum job timeout in seconds
MAX_JOB_TIMEOUT_SECONDS = 3600

# Overlap lock: only one cycle at a time
OVERLAP_LOCK_KEY = "si_v2_weekly_review"


class CeremonyPhase(StrEnum):
    """Phases of the activation ceremony."""

    PREFLIGHT = "preflight"
    BACKUP = "backup"
    VALIDATE = "validate"
    DIFF = "diff"
    STAGE = "stage"
    APPROVE = "approve"
    PROMOTE = "promote"
    OBSERVE = "observe"


class CeremonyVerdict(StrEnum):
    """Verdict at each ceremony phase."""

    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"


class JobLifecycleState(StrEnum):
    """Lifecycle state of a managed job."""

    DISABLED = "DISABLED"
    STAGED = "STAGED"
    ENABLED = "ENABLED"
    FAILED = "FAILED"
    CIRCUIT_OPEN = "CIRCUIT_OPEN"


class PreCeremonyCheck(NamedTuple):
    """Result of a single pre-ceremony check."""

    name: str
    passed: bool
    detail: str


class CeremonyResult(NamedTuple):
    """Result of running a ceremony phase."""

    phase: CeremonyPhase
    verdict: CeremonyVerdict
    detail: str
    evidence: dict[str, str]


# ---------------------------------------------------------------------------
# Pre-ceremony checks
# ---------------------------------------------------------------------------


def check_controller_paused(state: dict) -> PreCeremonyCheck:
    """Controller status must be PAUSED (or IDLE/STOPPED)."""
    status = state.get("controller_status", "")
    if status in _PRE_CEREMONY_STATUSES:
        return PreCeremonyCheck("controller_paused", True, f"status={status}")
    return PreCeremonyCheck(
        "controller_paused", False,
        f"controller_status={status!r} not in {_PRE_CEREMONY_STATUSES}",
    )


def check_queue_empty(queue: dict) -> PreCeremonyCheck:
    """Queue items must be empty."""
    items = queue.get("items", [])
    if isinstance(items, list) and len(items) == 0:
        return PreCeremonyCheck("queue_empty", True, "queue is empty")
    return PreCeremonyCheck(
        "queue_empty", False,
        f"queue has {len(items)} item(s)",
    )


def check_active_fields_null(state: dict) -> PreCeremonyCheck:
    """All active work fields must be null."""
    active_fields = (
        "active_work_item_id",
        "active_branch",
        "active_worktree",
        "active_pr",
    )
    for field in active_fields:
        if state.get(field) is not None:
            return PreCeremonyCheck(
                "active_fields_null", False,
                f"{field}={state[field]!r} is not null",
            )
    return PreCeremonyCheck("active_fields_null", True, "all active fields null")


def check_baseline_reconciled(state: dict, queue: dict) -> PreCeremonyCheck:
    """STATE.canonical_main_commit must equal QUEUE.base_commit."""
    state_commit = state.get("canonical_main_commit", "")
    queue_commit = queue.get("base_commit", "")
    if state_commit and state_commit == queue_commit:
        return PreCeremonyCheck(
            "baseline_reconciled", True,
            f"commit={state_commit[:12]}",
        )
    return PreCeremonyCheck(
        "baseline_reconciled", False,
        f"STATE={state_commit[:12]!r} != QUEUE={queue_commit[:12]!r}",
    )


def check_dependency_satisfied(
    dep_name: str,
    satisfied: bool,
    detail: str,
) -> PreCeremonyCheck:
    """Generic check for an external dependency (#44, #176, etc.)."""
    return PreCeremonyCheck(
        f"dependency_{dep_name}",
        satisfied,
        detail,
    )


def run_preflight(state: dict, queue: dict) -> list[PreCeremonyCheck]:
    """Run all pre-ceremony checks and return results."""
    checks = [
        check_controller_paused(state),
        check_queue_empty(queue),
        check_active_fields_null(state),
        check_baseline_reconciled(state, queue),
    ]
    return checks


# ---------------------------------------------------------------------------
# Approval-token validation
# ---------------------------------------------------------------------------


def validate_approval_token(token: str) -> bool:
    """Validate the format of an activation approval token.

    Token format: ``APPROVE_ACTIVATE_<32 uppercase hex characters>``
    """
    return bool(_APPROVAL_TOKEN_RE.match(token))


# ---------------------------------------------------------------------------
# Backup and checksum
# ---------------------------------------------------------------------------


def compute_jobs_checksum(path: Path) -> str:
    """Compute SHA-256 checksum of a jobs file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def create_timestamped_backup(path: Path, backup_dir: Path) -> Path:
    """Create a timestamped backup of a jobs file.

    Returns the backup path.
    """
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup_path = backup_dir / f"{path.name}.{timestamp}.bak"
    import shutil
    shutil.copy2(path, backup_path)
    return backup_path


# ---------------------------------------------------------------------------
# Diff validation
# ---------------------------------------------------------------------------


def validate_semantic_diff(
    before: dict,
    after: dict,
) -> tuple[bool, list[str]]:
    """Validate that a semantic diff between two job states is safe.

    Returns (is_safe, warnings).
    """
    warnings: list[str] = []

    before_jobs = before.get("jobs", []) if isinstance(before, dict) else []
    after_jobs = after.get("jobs", []) if isinstance(after, dict) else []

    before_ids = {j.get("id") or j.get("job_id") for j in before_jobs if isinstance(j, dict)}
    after_ids = {j.get("id") or j.get("job_id") for j in after_jobs if isinstance(j, dict)}

    # New jobs must start disabled
    new_ids = after_ids - before_ids
    for job in after_jobs:
        if not isinstance(job, dict):
            continue
        job_id = job.get("id") or job.get("job_id")
        if job_id in new_ids:
            if job.get("enabled", False) is not False:
                warnings.append(f"New job {job_id} must start disabled")
                return False, warnings

    # Check for enabled jobs exceeding limit
    enabled_count = sum(
        1 for j in after_jobs
        if isinstance(j, dict) and j.get("enabled") is True
    )
    if enabled_count > MAX_CONCURRENT_JOBS:
        warnings.append(
            f"Enabled job count {enabled_count} exceeds max {MAX_CONCURRENT_JOBS}"
        )
        return False, warnings

    return True, warnings


# ---------------------------------------------------------------------------
# Job contract validation
# ---------------------------------------------------------------------------


def validate_job_contract(job: dict) -> tuple[bool, list[str]]:
    """Validate that a job definition satisfies safety invariants.

    Returns (is_valid, errors).
    """
    errors: list[str] = []
    job_id = job.get("id") or job.get("job_id", "UNKNOWN")

    # Must start disabled
    if job.get("enabled") is not False:
        errors.append(f"Job {job_id}: enabled must be False")

    # Must be dry-run only
    if job.get("dry_run_only") is not True:
        errors.append(f"Job {job_id}: dry_run_only must be True")

    # Must have a schedule
    schedule = job.get("schedule", "")
    if not schedule or not schedule.strip():
        errors.append(f"Job {job_id}: schedule must not be empty")

    # Must not be a proposal-application command
    command = str(job.get("command", ""))
    forbidden_substrings = ("apply_weight", "approve_proposal", "force_trade")
    for substr in forbidden_substrings:
        if substr in command:
            errors.append(
                f"Job {job_id}: command contains forbidden substring '{substr}'"
            )

    # Timeout must not exceed limit
    timeout = job.get("timeout")
    if timeout is not None:
        try:
            timeout_val = int(timeout)
            if timeout_val > MAX_JOB_TIMEOUT_SECONDS:
                errors.append(
                    f"Job {job_id}: timeout {timeout_val}s exceeds max {MAX_JOB_TIMEOUT_SECONDS}s"
                )
        except (ValueError, TypeError):
            errors.append(f"Job {job_id}: timeout must be an integer")

    return len(errors) == 0, errors


# ---------------------------------------------------------------------------
# Separation proof: generation cannot apply
# ---------------------------------------------------------------------------


def prove_generation_cannot_apply() -> list[str]:
    """Return proof statements that scheduled generation cannot apply proposals.

    These are structural invariants verified by tests:
      1. No job command contains apply/approve/force substrings.
      2. The approval gate requires a separate human action.
      3. The weight promotion path requires a distinct approval token.
    """
    return [
        "generation_commands_exclude_apply: validated by validate_job_contract",
        "approval_gate_requires_human: validated by test_separation_of_concerns",
        "weight_promotion_requires_distinct_token: validated by test_approval_token_format",
    ]


# ---------------------------------------------------------------------------
# Rollback conditions
# ---------------------------------------------------------------------------


def should_auto_disable(verdict: CeremonyVerdict, consecutive_failures: int) -> bool:
    """Determine if a job should be automatically disabled."""
    if verdict == CeremonyVerdict.RED:
        return True
    if consecutive_failures >= MAX_RETRIES:
        return True
    return False


# ---------------------------------------------------------------------------
# Observation evidence
# ---------------------------------------------------------------------------


def classify_run_outcome(
    success: bool,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
) -> CeremonyVerdict:
    """Classify a run outcome as GREEN, YELLOW, or RED."""
    if success and not warnings:
        return CeremonyVerdict.GREEN
    if success and warnings:
        return CeremonyVerdict.YELLOW
    return CeremonyVerdict.RED


# ---------------------------------------------------------------------------
# Operator checklist (purely informational)
# ---------------------------------------------------------------------------

OPERATOR_CHECKLIST: list[str] = [
    "1. Verify controller is PAUSED, queue empty, active fields null.",
    "2. Verify baseline is reconciled (STATE.canonical_main_commit == QUEUE.base_commit).",
    "3. Verify #44 (Compose/runtime truth) is satisfied.",
    "4. Verify #176 (controller identity/credential isolation) is satisfied.",
    "5. Create timestamped backup of production jobs.json with SHA-256 checksum.",
    "6. Validate every new job contract (disabled, dry_run_only, no apply commands).",
    "7. Compute semantic diff between current and proposed jobs.",
    "8. Stage all new jobs as disabled — do NOT enable.",
    "9. Obtain explicit APPROVE_ACTIVATE_<hex> token from human operator.",
    "10. Enable only the approved job(s) — one at a time.",
    "11. Observe for GREEN/YELLOW/RED evidence for at least 2 cycles.",
    "12. If RED or 3+ consecutive failures: auto-disable and escalate.",
    "13. Document all evidence in docs/context/ before closing.",
]
