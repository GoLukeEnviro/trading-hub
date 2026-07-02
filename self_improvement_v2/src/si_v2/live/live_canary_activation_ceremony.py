"""SI-v2 C3 — Live Canary Activation Ceremony, No Activation.

Builds a controlled ceremony for freqtrade-freqforge-canary using the C2
config plan. The ceremony is human-gated, canary-first, snapshot-backed,
audit-logged, rollback-capable, and measurement-starting.

This module does NOT:
- Activate live canary
- Toggle dry_run to false
- Create or modify exchange keys
- Modify Freqtrade runtime config
- Execute any runtime mutation
- Apply any config change
- Execute Docker/Cron/Scheduler actions
- Perform fleet rollout
- Mutate strategy or expand pairs
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_CEREMONY_OUTPUT_DIR: str = "var/si_v2/live_canary_activation_ceremony"

# The single approved canary target.
CANARY_TARGET: str = "freqtrade-freqforge-canary"

# C3 execution approval marker.
C3_APPROVED_MARKER: str = "APPROVED_EXECUTE_LIVE_CANARY"

# Expected C3 approval marker document path.
C3_APPROVAL_DOC_PATH: str = "docs/decisions/APPROVED_EXECUTE_LIVE_CANARY.md"

# Maximum age of the C3 approval marker in days.
MAX_APPROVAL_AGE_DAYS: int = 7

# Expected C2 config plan output.
C2_PLAN_OUTPUT_DIR: str = "var/si_v2/live_canary_config_plan"
C2_PLAN_FILENAME: str = "live_canary_config_plan.json"
C2_READY_STATUS: str = "LIVE_CANARY_CONFIG_PLAN_READY"

# Expected C1 gate output directory (references by C2).
C1_GATE_OUTPUT_DIR: str = "var/si_v2/live_canary_approval_gate"
C1_GATE_FILENAME: str = "live_canary_approval_gate.json"

# Config paths for snapshot.
CANARY_CONFIG_DIR: str = "freqforge-canary/config"
CANARY_DRYRUN_CONFIG: str = "freqforge-canary/config/config_canary_dryrun.json"

# B2 risk limits reference.
B2_RISK_LIMITS_DOC: str = "docs/specs/production-risk-limits-spec.md"

# B4 alerting gate reference.
B4_ALERTING_GATE_DOC: str = "docs/reports/production-alerting-readiness-gate.md"

# Kill switch runbook.
KILL_SWITCH_RUNBOOK: str = "docs/runbooks/kill-switch.md"
KILL_SWITCH_SRC: str = "freqtrade/shared/kill_switch.py"

# Rollback runbook.
ROLLBACK_RUNBOOK: str = "docs/context/freqforge-canary-deployment-runbook.md"

# Incident response runbook.
INCIDENT_RESPONSE_RUNBOOK: str = "docs/specs/incident-response-runbooks.md"

# Measurement window (in days) for post-activation evaluation.
MEASUREMENT_WINDOW_DAYS: int = 14

# Ceremony status string constants.
LIVE_CANARY_CEREMONY_READY: str = "LIVE_CANARY_CEREMONY_READY"
LIVE_CANARY_CEREMONY_BLOCKED: str = "LIVE_CANARY_CEREMONY_BLOCKED"

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CeremonyCheckResult:
    """Result of a single ceremony preflight check."""

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
class SnapshotArtifact:
    """A snapshot artifact created during the ceremony."""

    name: str
    path: str
    content_preview: str

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "path": self.path,
            "content_preview": self.content_preview,
        }


@dataclass(frozen=True)
class LiveCanaryActivationCeremonyResult:
    """Structured result from the live canary activation ceremony.

    Attributes:
        status: LIVE_CANARY_CEREMONY_READY or LIVE_CANARY_CEREMONY_BLOCKED.
        checks: Individual preflight check results.
        blocked_reasons: Reasons the ceremony is blocked.
        snapshots: Snapshot artifacts created.
        ceremony_path: Path to the written ceremony JSON.
        report_path: Path to the written human-readable report.
        next_step: Suggested next action.
        runtime_mutation: Always NONE.
    """

    status: Literal[
        "LIVE_CANARY_CEREMONY_READY",
        "LIVE_CANARY_CEREMONY_BLOCKED",
    ]
    checks: tuple[CeremonyCheckResult, ...]
    blocked_reasons: tuple[str, ...]
    snapshots: tuple[SnapshotArtifact, ...]
    ceremony_path: str
    report_path: str
    next_step: str
    runtime_mutation: str = "NONE"

    def to_dict(self) -> dict[str, object]:
        return {
            "event": "live_canary_activation_ceremony_result",
            "status": self.status,
            "checks": [c.to_dict() for c in self.checks],
            "blocked_reasons": list(self.blocked_reasons),
            "snapshots": [s.to_dict() for s in self.snapshots],
            "ceremony_path": self.ceremony_path,
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
    tmp = path.with_suffix(
        path.suffix + f".tmp.{abs(hash(str(data)))}"
    )
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
# Check: C3 approval marker document exists and contains correct marker
# ---------------------------------------------------------------------------


def _check_c3_approval_marker(
    repo_root: Path,
) -> CeremonyCheckResult:
    """Check that the C3 approval marker document exists and is valid."""
    doc = repo_root / C3_APPROVAL_DOC_PATH
    if not doc.exists():
        return CeremonyCheckResult(
            check_name="c3_approval_marker_document",
            passed=False,
            detail=(
                f"C3 approval document not found at {C3_APPROVAL_DOC_PATH}. "
                f"The {C3_APPROVED_MARKER!r} marker must exist before "
                f"the live canary activation ceremony can proceed."
            ),
        )

    try:
        text = doc.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        return CeremonyCheckResult(
            check_name="c3_approval_marker_document",
            passed=False,
            detail=f"C3 approval document not readable: {e}",
        )

    if len(text.strip()) < 50:
        return CeremonyCheckResult(
            check_name="c3_approval_marker_document",
            passed=False,
            detail=(
                f"C3 approval document at {C3_APPROVAL_DOC_PATH} appears "
                f"to be empty or too short."
            ),
        )

    if C3_APPROVED_MARKER not in text:
        return CeremonyCheckResult(
            check_name="c3_approval_marker_document",
            passed=False,
            detail=(
                f"Approval marker {C3_APPROVED_MARKER!r} not found in "
                f"{C3_APPROVAL_DOC_PATH}. The document must contain the "
                f"exact marker string."
            ),
        )

    return CeremonyCheckResult(
        check_name="c3_approval_marker_document",
        passed=True,
        detail=(
            f"C3 approval marker {C3_APPROVED_MARKER!r} found in "
            f"{C3_APPROVAL_DOC_PATH}"
        ),
    )


# ---------------------------------------------------------------------------
# Check: C3 approval freshness
# ---------------------------------------------------------------------------


def _check_c3_approval_freshness(
    repo_root: Path,
    now_utc: str,
) -> CeremonyCheckResult:
    """Check that the C3 approval marker is not stale."""
    doc = repo_root / C3_APPROVAL_DOC_PATH
    if not doc.exists():
        return CeremonyCheckResult(
            check_name="c3_approval_freshness",
            passed=False,
            detail="C3 approval document does not exist — cannot check freshness",
        )

    try:
        stat = doc.stat()
        mtime = datetime.fromtimestamp(stat.st_mtime, tz=UTC)
        now = datetime.fromisoformat(now_utc.replace("Z", "+00:00"))
        age_days = (now - mtime).total_seconds() / 86400
    except (ValueError, OSError) as e:
        return CeremonyCheckResult(
            check_name="c3_approval_freshness",
            passed=False,
            detail=f"Cannot determine approval age: {e}",
        )

    if age_days > MAX_APPROVAL_AGE_DAYS:
        return CeremonyCheckResult(
            check_name="c3_approval_freshness",
            passed=False,
            detail=(
                f"C3 approval is {age_days:.1f} days old (max "
                f"{MAX_APPROVAL_AGE_DAYS} days). Marker has expired "
                f"and must be renewed."
            ),
        )

    return CeremonyCheckResult(
        check_name="c3_approval_freshness",
        passed=True,
        detail=(
            f"C3 approval is {age_days:.1f} days old "
            f"(within {MAX_APPROVAL_AGE_DAYS}-day limit)"
        ),
    )


# ---------------------------------------------------------------------------
# Check: C2 config plan was READY
# ---------------------------------------------------------------------------


def _check_c2_config_plan_ready(
    repo_root: Path,
) -> CeremonyCheckResult:
    """Check that the C2 config plan was completed with READY status."""
    plan_dir = repo_root / C2_PLAN_OUTPUT_DIR
    plan_file = plan_dir / C2_PLAN_FILENAME

    if not plan_file.exists():
        return CeremonyCheckResult(
            check_name="c2_config_plan_ready",
            passed=False,
            detail=(
                f"C2 config plan result not found at {plan_file}. "
                f"The config plan must be completed and READY before "
                f"activation ceremony."
            ),
        )

    plan_data = _read_json_safe(plan_file)
    if plan_data is None:
        return CeremonyCheckResult(
            check_name="c2_config_plan_ready",
            passed=False,
            detail=(
                f"C2 config plan at {plan_file} is not valid JSON or "
                f"could not be read."
            ),
        )

    raw_status = plan_data.get("status", "")
    status = raw_status if isinstance(raw_status, str) else str(raw_status)
    if status != C2_READY_STATUS:
        return CeremonyCheckResult(
            check_name="c2_config_plan_ready",
            passed=False,
            detail=(
                f"C2 config plan status is {status!r}, expected "
                f"{C2_READY_STATUS!r}. Review blocked reasons and "
                f"re-run C2 before activation ceremony."
            ),
        )

    return CeremonyCheckResult(
        check_name="c2_config_plan_ready",
        passed=True,
        detail=(
            f"C2 config plan is READY (status: {C2_READY_STATUS!r}). "
            f"Config plan evidence at {plan_file}."
        ),
    )


# ---------------------------------------------------------------------------
# Check: C1 approval gate was READY (archived evidence)
# ---------------------------------------------------------------------------


def _check_c1_approval_gate_evidence(
    repo_root: Path,
) -> CeremonyCheckResult:
    """Check that the C1 approval gate evidence exists (archived READY)."""
    gate_dir = repo_root / C1_GATE_OUTPUT_DIR
    gate_file = gate_dir / C1_GATE_FILENAME

    if not gate_file.exists():
        return CeremonyCheckResult(
            check_name="c1_approval_gate_evidence",
            passed=False,
            detail=(
                f"C1 approval gate output not found at {gate_file}. "
                f"The C1 gate must have been run and READY before C2/C3."
            ),
        )

    gate_data = _read_json_safe(gate_file)
    if gate_data is None:
        return CeremonyCheckResult(
            check_name="c1_approval_gate_evidence",
            passed=False,
            detail=(
                f"C1 approval gate at {gate_file} is not valid JSON."
            ),
        )

    raw_status = gate_data.get("status", "")
    gate_status = raw_status if isinstance(raw_status, str) else str(raw_status)
    if "READY" not in gate_status:
        return CeremonyCheckResult(
            check_name="c1_approval_gate_evidence",
            passed=False,
            detail=(
                f"C1 approval gate status is {gate_status!r}, "
                f"expected *READY*. The C1 gate must pass before "
                f"activation ceremony."
            ),
        )

    return CeremonyCheckResult(
        check_name="c1_approval_gate_evidence",
        passed=True,
        detail=(
            f"C1 approval gate evidence found at {gate_file} "
            f"with status {gate_status!r}."
        ),
    )


# ---------------------------------------------------------------------------
# Check: B2 risk limits document exists
# ---------------------------------------------------------------------------


def _check_b2_risk_limits(
    repo_root: Path,
) -> CeremonyCheckResult:
    """Check that the B2 risk limits document exists."""
    doc = repo_root / B2_RISK_LIMITS_DOC
    if not doc.exists():
        return CeremonyCheckResult(
            check_name="b2_risk_limits_document",
            passed=False,
            detail=(
                f"B2 risk limits document not found at {B2_RISK_LIMITS_DOC}. "
                f"Risk limits document is required for activation ceremony."
            ),
        )

    return CeremonyCheckResult(
        check_name="b2_risk_limits_document",
        passed=True,
        detail=f"B2 risk limits document found at {B2_RISK_LIMITS_DOC}",
    )


# ---------------------------------------------------------------------------
# Check: B4 alerting gate document exists
# ---------------------------------------------------------------------------


def _check_b4_alerting_gate(
    repo_root: Path,
) -> CeremonyCheckResult:
    """Check that the B4 alerting gate document exists."""
    doc = repo_root / B4_ALERTING_GATE_DOC
    if not doc.exists():
        return CeremonyCheckResult(
            check_name="b4_alerting_gate_document",
            passed=False,
            detail=(
                f"B4 alerting gate document not found at "
                f"{B4_ALERTING_GATE_DOC}. Alerting gate document is "
                f"required for activation ceremony."
            ),
        )

    return CeremonyCheckResult(
        check_name="b4_alerting_gate_document",
        passed=True,
        detail=f"B4 alerting gate document found at {B4_ALERTING_GATE_DOC}",
    )


# ---------------------------------------------------------------------------
# Check: Kill switch is NORMAL
# ---------------------------------------------------------------------------


def _check_kill_switch_normal(
    repo_root: Path,
) -> CeremonyCheckResult:
    """Check that the kill switch is set to NORMAL mode."""
    ks_file = repo_root / KILL_SWITCH_SRC
    if not ks_file.exists():
        return CeremonyCheckResult(
            check_name="kill_switch_normal",
            passed=False,
            detail=(
                f"Kill switch file not found at {KILL_SWITCH_SRC}. "
                f"Cannot verify kill switch state."
            ),
        )

    try:
        text = ks_file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        return CeremonyCheckResult(
            check_name="kill_switch_normal",
            passed=False,
            detail=f"Cannot read kill switch file: {e}",
        )

    # Look for the current kill switch mode assignment.
    # Expected pattern: MODE = "NORMAL" (or HALT_NEW, EMERGENCY).
    import re as _re

    mode_match = _re.search(
        r"""MODE\s*=\s*["'](NORMAL|HALT_NEW|EMERGENCY)["']""",
        text,
    )

    if not mode_match:
        return CeremonyCheckResult(
            check_name="kill_switch_normal",
            passed=False,
            detail=(
                "Cannot determine kill switch mode. Look for "
                "MODE = 'NORMAL' / 'HALT_NEW' / 'EMERGENCY' in "
                f"{KILL_SWITCH_SRC}."
            ),
        )

    current_mode = mode_match.group(1)
    if current_mode != "NORMAL":
        return CeremonyCheckResult(
            check_name="kill_switch_normal",
            passed=False,
            detail=(
                f"Kill switch is in {current_mode!r} mode. "
                f"Must be NORMAL before activation ceremony can proceed. "
                f"See {KILL_SWITCH_RUNBOOK} for resolution steps."
            ),
        )

    return CeremonyCheckResult(
        check_name="kill_switch_normal",
        passed=True,
        detail=f"Kill switch is NORMAL (verified in {KILL_SWITCH_SRC})",
    )


# ---------------------------------------------------------------------------
# Check: Canary target config exists and is valid
# ---------------------------------------------------------------------------


def _check_canary_config_exists(
    repo_root: Path,
) -> CeremonyCheckResult:
    """Check that the canary target config directory and config exist."""
    config_dir = repo_root / CANARY_CONFIG_DIR
    if not config_dir.exists():
        return CeremonyCheckResult(
            check_name="canary_config_exists",
            passed=False,
            detail=(
                f"Canary config directory not found at {CANARY_CONFIG_DIR}. "
                f"Expected for target '{CANARY_TARGET}'."
            ),
        )

    dryrun_config = repo_root / CANARY_DRYRUN_CONFIG
    if not dryrun_config.exists():
        return CeremonyCheckResult(
            check_name="canary_config_exists",
            passed=False,
            detail=(
                f"Canary dry-run config not found at {CANARY_DRYRUN_CONFIG}. "
                f"Expected for target '{CANARY_TARGET}'."
            ),
        )

    # Verify it's valid JSON and dry_run is true.
    config_data = _read_json_safe(dryrun_config)
    if config_data is None:
        return CeremonyCheckResult(
            check_name="canary_config_exists",
            passed=False,
            detail=(
                f"Canary config at {CANARY_DRYRUN_CONFIG} is not valid JSON."
            ),
        )

    dry_run_val = config_data.get("dry_run", None)
    if dry_run_val is not True:
        return CeremonyCheckResult(
            check_name="canary_config_exists",
            passed=False,
            detail=(
                f"Canary config dry_run is {dry_run_val!r}, expected True. "
                f"The config must be in dry-run mode before activation."
            ),
        )

    return CeremonyCheckResult(
        check_name="canary_config_exists",
        passed=True,
        detail=(
            f"Canary config directory and dry-run config found "
            f"at {CANARY_DRYRUN_CONFIG}. dry_run is True."
        ),
    )


# ---------------------------------------------------------------------------
# Snapshot: Pre-activation config snapshot
# ---------------------------------------------------------------------------


def _snapshot_pre_activation_config(
    repo_root: Path,
    ceremony_dir: Path,
) -> SnapshotArtifact:
    """Create a pre-activation snapshot of the canary config."""
    dryrun_config = repo_root / CANARY_DRYRUN_CONFIG
    snapshot_path = ceremony_dir / "pre_activation_config_snapshot.json"

    if dryrun_config.exists():
        try:
            content = dryrun_config.read_text(encoding="utf-8")
        except OSError:
            content = json.dumps({"error": "Could not read config"}, indent=2)
    else:
        content = json.dumps({"error": "Config not found"}, indent=2)

    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(content)

    # Build preview (first 500 chars).
    preview = content[:500]
    if len(content) > 500:
        preview += "\n... (truncated)"

    return SnapshotArtifact(
        name="pre_activation_config_snapshot",
        path=str(snapshot_path),
        content_preview=preview,
    )


def _snapshot_kill_switch_state(
    repo_root: Path,
    ceremony_dir: Path,
) -> SnapshotArtifact:
    """Snapshot the current kill switch state."""
    ks_file = repo_root / KILL_SWITCH_SRC
    snapshot_path = ceremony_dir / "pre_activation_kill_switch_snapshot.txt"

    if ks_file.exists():
        try:
            content = ks_file.read_text(encoding="utf-8")
        except OSError:
            content = "ERROR: Could not read kill switch file"
    else:
        content = "ERROR: Kill switch file not found"

    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(content)

    preview = content[:300]
    if len(content) > 300:
        preview += "\n... (truncated)"

    return SnapshotArtifact(
        name="pre_activation_kill_switch_snapshot",
        path=str(snapshot_path),
        content_preview=preview,
    )


def _snapshot_approval_marker(
    repo_root: Path,
    ceremony_dir: Path,
) -> SnapshotArtifact:
    """Snapshot the C3 approval marker document."""
    doc = repo_root / C3_APPROVAL_DOC_PATH
    snapshot_path = ceremony_dir / "c3_approval_marker_snapshot.md"

    if doc.exists():
        try:
            content = doc.read_text(encoding="utf-8")
        except OSError:
            content = "ERROR: Could not read approval document"
    else:
        content = "ERROR: Approval document not found"

    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(content)

    preview = content[:300]
    if len(content) > 300:
        preview += "\n... (truncated)"

    return SnapshotArtifact(
        name="c3_approval_marker_snapshot",
        path=str(snapshot_path),
        content_preview=preview,
    )


# ---------------------------------------------------------------------------
# Main ceremony function
# ---------------------------------------------------------------------------


def run_live_canary_activation_ceremony(
    *,
    repo_root: Path | None = None,
    ceremony_output_dir: Path | None = None,
    now_utc: str | None = None,
    execute: bool = False,
) -> LiveCanaryActivationCeremonyResult:
    """Run the live canary activation ceremony.

    Args:
        repo_root: Root of the trading-hub repository. Defaults to
            auto-detection from the current file location.
        ceremony_output_dir: Override for ceremony output directory.
        now_utc: Override for current UTC time (testing).
        execute: If True, raises RuntimeError. The ceremony does not
            perform execution; it only prepares and validates.

    Returns:
        LiveCanaryActivationCeremonyResult with ceremony status and evidence.

    Raises:
        RuntimeError: If execute=True is passed (fail-closed).
    """
    # ------------------------------------------------------------------
    # Fail-closed: ceremony does NOT perform execution
    # ------------------------------------------------------------------
    if execute:
        raise RuntimeError(
            "FAIL_CLOSED: The live canary activation ceremony does NOT "
            "perform execution. To execute the live canary activation, "
            "use the dedicated runtime executor module. This ceremony "
            "only validates preconditions, creates snapshots, and "
            "prepares artifacts."
        )

    resolved_now = now_utc or datetime.now(UTC).isoformat()
    resolved_dir = ceremony_output_dir or Path(DEFAULT_CEREMONY_OUTPUT_DIR)

    # Auto-detect repo root if not provided.
    if repo_root is None:
        repo_root = Path(__file__).resolve().parent.parent.parent.parent.parent

    # Ensure ceremony output directory exists.
    resolved_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Run all preflight checks
    # ------------------------------------------------------------------

    checks: list[CeremonyCheckResult] = []
    blocked: list[str] = []

    # Check 1: C3 approval marker document exists and is valid.
    c1 = _check_c3_approval_marker(repo_root)
    checks.append(c1)
    if not c1.passed:
        blocked.append(c1.detail)

    # Check 2: C3 approval freshness.
    c2 = _check_c3_approval_freshness(repo_root, resolved_now)
    checks.append(c2)
    if not c2.passed:
        blocked.append(c2.detail)

    # Check 3: C2 config plan was READY.
    c3 = _check_c2_config_plan_ready(repo_root)
    checks.append(c3)
    if not c3.passed:
        blocked.append(c3.detail)

    # Check 4: C1 approval gate evidence.
    c4 = _check_c1_approval_gate_evidence(repo_root)
    checks.append(c4)
    if not c4.passed:
        blocked.append(c4.detail)

    # Check 5: B2 risk limits document exists.
    c5 = _check_b2_risk_limits(repo_root)
    checks.append(c5)
    if not c5.passed:
        blocked.append(c5.detail)

    # Check 6: B4 alerting gate document exists.
    c6 = _check_b4_alerting_gate(repo_root)
    checks.append(c6)
    if not c6.passed:
        blocked.append(c6.detail)

    # Check 7: Kill switch is NORMAL.
    c7 = _check_kill_switch_normal(repo_root)
    checks.append(c7)
    if not c7.passed:
        blocked.append(c7.detail)

    # Check 8: Canary target config exists and is valid.
    c8 = _check_canary_config_exists(repo_root)
    checks.append(c8)
    if not c8.passed:
        blocked.append(c8.detail)

    # ------------------------------------------------------------------
    # Determine overall status
    # ------------------------------------------------------------------

    if blocked:
        status: str = "LIVE_CANARY_CEREMONY_BLOCKED"
        next_step = (
            "Review blocked reasons and address before re-running the "
            "ceremony. The live canary activation ceremony cannot proceed "
            "until all preflight checks pass."
        )
    else:
        status = "LIVE_CANARY_CEREMONY_READY"
        next_step = (
            "All ceremony preflight checks pass. The ceremony artifacts "
            "have been created. To proceed with live canary activation, "
            "use the dedicated runtime executor. This ceremony module "
            "does NOT perform execution."
        )

    # ------------------------------------------------------------------
    # Create snapshot artifacts (only if all checks pass)
    # ------------------------------------------------------------------

    snapshots: list[SnapshotArtifact] = []
    if not blocked:
        snapshots.append(
            _snapshot_pre_activation_config(repo_root, resolved_dir)
        )
        snapshots.append(
            _snapshot_kill_switch_state(repo_root, resolved_dir)
        )
        snapshots.append(
            _snapshot_approval_marker(repo_root, resolved_dir)
        )

    # ------------------------------------------------------------------
    # Write ceremony JSON
    # ------------------------------------------------------------------

    ceremony: dict[str, object] = {
        "event": "live_canary_activation_ceremony_result",
        "status": status,
        "canary_target": CANARY_TARGET,
        "checks": [c.to_dict() for c in checks],
        "blocked_reasons": blocked,
        "snapshots": [s.to_dict() for s in snapshots],
        "preflight_details": {
            "c3_approval_marker": C3_APPROVED_MARKER,
            "c3_approval_doc_path": C3_APPROVAL_DOC_PATH,
            "c2_config_plan_path": str(
                repo_root / C2_PLAN_OUTPUT_DIR / C2_PLAN_FILENAME
            ),
            "c1_gate_path": str(
                repo_root / C1_GATE_OUTPUT_DIR / C1_GATE_FILENAME
            ),
            "b2_risk_limits_doc": B2_RISK_LIMITS_DOC,
            "b4_alerting_gate_doc": B4_ALERTING_GATE_DOC,
            "kill_switch_src": KILL_SWITCH_SRC,
            "canary_config": CANARY_DRYRUN_CONFIG,
        },
        "measurement_window": {
            "duration_days": MEASUREMENT_WINDOW_DAYS,
            "metrics": [
                "total_trades",
                "win_rate",
                "profit_factor",
                "sharpe_ratio",
                "max_drawdown",
                "daily_loss_count",
            ],
            "comparison_baseline": (
                "Dry-run performance over the 14 days prior to activation"
            ),
            "evaluation_gate": (
                "Post-activation T0/T1/T2/T3 measurement evaluations"
            ),
            "decision_outcomes": [
                "KEEP — Continue live canary operation",
                "EXTEND — Extend measurement window",
                "ROLLBACK — Return to dry-run mode",
            ],
        },
        "rollback_plan": {
            "description": "Steps to revert canary to dry-run if needed",
            "steps": [
                (
                    "1. Activate kill switch: set MODE = 'EMERGENCY' "
                    "in kill_switch.py to halt all trading"
                ),
                (
                    "2. Halt canary container: stop "
                    "freqtrade-freqforge-canary"
                ),
                (
                    "3. Restore dry-run config: replace live config "
                    "with preserved dry-run config"
                ),
                (
                    "4. Redeploy canary in dry-run mode"
                ),
                (
                    "5. Verify dry-run operation: check logs, DB, "
                    "and API health"
                ),
                (
                    "6. Reset kill switch to NORMAL after rollback "
                    "is confirmed"
                ),
                (
                    "7. File post-mortem report in docs/incidents/"
                ),
            ],
            "prerequisites": [
                (
                    "Dry-run config file must be preserved "
                    "(snapshot taken by this ceremony)"
                ),
                (
                    "Dry-run database must be preserved for "
                    "comparison"
                ),
                "Kill switch runbook must be accessible",
            ],
        },
        "created_at_utc": resolved_now,
        "runtime_mutation": "NONE",
    }
    ceremony_path = resolved_dir / "live_canary_activation_ceremony.json"
    _atomic_write_json(ceremony_path, ceremony)

    # ------------------------------------------------------------------
    # Write human-readable report
    # ------------------------------------------------------------------

    report_lines: list[str] = [
        "# Live Canary Activation Ceremony",
        "",
        f"**Status:** {status}",
        f"**Canary target:** {CANARY_TARGET}",
        f"**Generated at:** {resolved_now}",
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

    if snapshots:
        report_lines.append("---")
        report_lines.append("")
        report_lines.append("## Snapshot Artifacts")
        report_lines.append("")
        for s in snapshots:
            report_lines.append(f"### {s.name}")
            report_lines.append("")
            report_lines.append(f"**Path:** {s.path}")
            report_lines.append("")
            report_lines.append("**Preview:**")
            report_lines.append("")
            report_lines.append("```")
            report_lines.append(s.content_preview)
            report_lines.append("```")
            report_lines.append("")

    report_lines.extend([
        "---",
        "",
        "## Measurement Window",
        "",
        f"**Duration:** {MEASUREMENT_WINDOW_DAYS} days",
        "",
        "**Metrics:**",
        "",
    ])

    ceremony_metrics: list[str] = [
        "total_trades",
        "win_rate",
        "profit_factor",
        "sharpe_ratio",
        "max_drawdown",
        "daily_loss_count",
    ]
    for metric in ceremony_metrics:
        report_lines.append(f"- {metric}")

    report_lines.append("")
    report_lines.append(
        "**Comparison baseline:** Dry-run performance over the 14 days "
        "prior to activation"
    )
    report_lines.append("")
    report_lines.append(
        "**Evaluation gate:** Post-activation T0/T1/T2/T3 measurement "
        "evaluations"
    )
    report_lines.append("")
    report_lines.append(
        "**Decision outcomes:** KEEP / EXTEND / ROLLBACK"
    )
    report_lines.append("")

    report_lines.extend([
        "---",
        "",
        "## Rollback Plan",
        "",
        "**Description:** Steps to revert canary to dry-run if needed",
        "",
    ])

    rollback_steps: list[str] = [
        (
            "Activate kill switch: set MODE = 'EMERGENCY' "
            "in kill_switch.py to halt all trading"
        ),
        "Halt canary container",
        "Restore dry-run config from preserved snapshot",
        "Redeploy canary in dry-run mode",
        "Verify dry-run operation (logs, DB, API health)",
        "Reset kill switch to NORMAL after rollback confirmed",
        "File post-mortem report in docs/incidents/",
    ]

    for i, step in enumerate(rollback_steps, 1):
        report_lines.append(f"{i}. {step}")
        report_lines.append("")

    report_lines.extend([
        "---",
        "",
        "## Safety Notes",
        "",
        "- This ceremony does NOT perform live execution.",
        "- All checks must pass before execution is possible.",
        "- Snapshots are taken for audit and rollback purposes.",
        "- The dedicated runtime executor must be used for activation.",
        "- Kill switch must remain NORMAL throughout.",
        "- Operator must be on-call and reachable.",
        "- All B2 risk limits apply.",
        "",
    ])

    report_path = resolved_dir / "live_canary_activation_ceremony.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(report_lines))

    return LiveCanaryActivationCeremonyResult(
        status=status,
        checks=tuple(checks),
        blocked_reasons=tuple(blocked),
        snapshots=tuple(snapshots),
        ceremony_path=str(ceremony_path),
        report_path=str(report_path),
        next_step=next_step,
    )
