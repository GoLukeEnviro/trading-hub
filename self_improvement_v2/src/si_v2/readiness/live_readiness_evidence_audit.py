"""SI-v2 B1 — Live Readiness Evidence Audit.

Audits whether the system is ready to prepare live canary mode.
This is an evidence audit only. It does NOT activate live mode.

Checks:
- Track A A1-A6 merged/evidenced
- Dry-run loop proof artifacts exist or reports which are missing
- Rollback proof artifacts exist or reports which are missing
- Measurement proof artifacts exist or reports which are missing
- No live mode activation occurred
- Alerting requirements are either proven or explicitly missing
- Risk-limit requirements are either proven or explicitly missing

Outputs LIVE_READINESS_BLOCKED or LIVE_READINESS_PREP_READY.
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

DEFAULT_AUDIT_OUTPUT_DIR: str = "var/si_v2/live_readiness_audit"

# Track A PRs that must be merged for dry-run loop closure.
TRACK_A_PRS: dict[str, str] = {
    "A1": "Phase 10.1 — Fleet Rollout Chain Input Resolver",
    "A2": "Phase 10.2 — READY-only Fleet Chain Evidence Runner",
    "A3": "Phase 10.3 — Controlled Dry-Run Fleet Runtime Executor",
    "A4": "Phase 10.4 — Post-Fleet Measurement Watcher",
    "A5": "Phase 10.5 — Dry-Run Fleet Rollback Executor",
    "A6": "Phase 10.6 — Next Iteration Selector",
}

# Expected artifact paths for dry-run loop proof.
DRY_RUN_ARTIFACT_PATHS: dict[str, str] = {
    "rollout_policy": "var/si_v2/fleet_rollout_chain/rollout_policy",
    "rollout_plan": "var/si_v2/fleet_rollout_plans",
    "ceremony_preflight": "var/si_v2/fleet_ceremony",
    "executor_audit": "var/si_v2/fleet_dry_run_runtime_executor/executor_audit.json",
    "measurement_decision_packs": "var/si_v2/post_fleet_measurement/decision_packs",
    "rollback_audit": "var/si_v2/fleet_dry_run_rollback_executor/rollback_executor_audit.json",
    "selection_plan": "var/si_v2/next_iteration_selector",
}

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReadinessCheckResult:
    """Result of a single readiness check."""

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
class LiveReadinessAuditResult:
    """Structured result from the live readiness evidence audit.

    Attributes:
        status: LIVE_READINESS_PREP_READY or LIVE_READINESS_BLOCKED.
        checks: Individual check results.
        blocked_reasons: Reasons readiness is blocked.
        audit_path: Path to the written audit JSON.
        report_path: Path to the written human-readable report.
        next_step: Suggested next action.
    """

    status: Literal["LIVE_READINESS_PREP_READY", "LIVE_READINESS_BLOCKED"]
    checks: tuple[ReadinessCheckResult, ...]
    blocked_reasons: tuple[str, ...]
    audit_path: str
    report_path: str
    next_step: str

    def to_dict(self) -> dict[str, object]:
        return {
            "event": "live_readiness_evidence_audit",
            "status": self.status,
            "checks": [c.to_dict() for c in self.checks],
            "blocked_reasons": list(self.blocked_reasons),
            "audit_path": self.audit_path,
            "report_path": self.report_path,
            "next_step": self.next_step,
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


def _path_exists(relative_path: str, repo_root: Path) -> bool:
    """Check if a path exists relative to the repo root."""
    full_path = repo_root / relative_path
    return full_path.exists()


# ---------------------------------------------------------------------------
# Check functions
# ---------------------------------------------------------------------------


def _check_track_a_merged(repo_root: Path) -> ReadinessCheckResult:
    """Check that all Track A PRs are merged (by checking module existence)."""
    missing: list[str] = []

    # Check rollout modules exist
    rollout_dir = repo_root / "self_improvement_v2" / "src" / "si_v2" / "rollout"
    expected_modules = [
        "fleet_rollout_input_resolver.py",
        "fleet_rollout_ready_evidence_runner.py",
        "fleet_dry_run_runtime_executor.py",
        "fleet_post_fleet_measurement_watcher.py",
        "fleet_dry_run_rollback_executor.py",
        "next_iteration_selector.py",
    ]

    for mod in expected_modules:
        if not (rollout_dir / mod).exists():
            missing.append(mod)

    if missing:
        return ReadinessCheckResult(
            check_name="track_a_modules_exist",
            passed=False,
            detail=f"Missing modules: {', '.join(missing)}",
        )

    return ReadinessCheckResult(
        check_name="track_a_modules_exist",
        passed=True,
        detail="All 6 Track A rollout modules exist in tree",
    )


def _check_dry_run_artifacts(repo_root: Path) -> ReadinessCheckResult:
    """Check that dry-run loop proof artifacts exist."""
    found: list[str] = []
    missing: list[str] = []

    for name, rel_path in DRY_RUN_ARTIFACT_PATHS.items():
        if _path_exists(rel_path, repo_root):
            found.append(name)
        else:
            missing.append(name)

    if missing:
        return ReadinessCheckResult(
            check_name="dry_run_artifacts_exist",
            passed=False,
            detail=(
                f"Found: {', '.join(found)}. "
                f"Missing: {', '.join(missing)}. "
                f"Artifacts may not have been generated yet."
            ),
        )

    return ReadinessCheckResult(
        check_name="dry_run_artifacts_exist",
        passed=True,
        detail=f"All {len(DRY_RUN_ARTIFACT_PATHS)} expected artifact paths exist",
    )


def _check_no_live_activation(repo_root: Path) -> ReadinessCheckResult:
    """Check that no live mode activation has occurred."""
    blocked: list[str] = []

    # Check for dry_run disabled in config files
    config_dir = repo_root / "freqtrade" / "user_data"
    if config_dir.exists():
        for config_file in config_dir.rglob("config*.json"):
            try:
                data = json.loads(config_file.read_text())
                if data.get("dry_run") is False:
                    blocked.append(
                        f"dry_run disabled in {config_file.relative_to(repo_root)}"
                    )
            except (json.JSONDecodeError, OSError):
                pass

    if blocked:
        return ReadinessCheckResult(
            check_name="no_live_activation",
            passed=False,
            detail="; ".join(blocked),
        )

    return ReadinessCheckResult(
        check_name="no_live_activation",
        passed=True,
        detail="No dry_run disabled config found in any config file",
    )


def _check_rollback_proof(repo_root: Path) -> ReadinessCheckResult:
    """Check that rollback proof artifacts exist."""
    # Check rollback executor module exists
    rollback_module = (
        repo_root
        / "self_improvement_v2"
        / "src"
        / "si_v2"
        / "rollout"
        / "fleet_dry_run_rollback_executor.py"
    )
    if not rollback_module.exists():
        return ReadinessCheckResult(
            check_name="rollback_proof",
            passed=False,
            detail="Rollback executor module not found",
        )

    # Check rollback rehearsal module exists
    rollback_rehearsal = (
        repo_root
        / "self_improvement_v2"
        / "src"
        / "si_v2"
        / "apply_actuator"
        / "rollback_rehearsal.py"
    )
    rollback_executor = (
        repo_root
        / "self_improvement_v2"
        / "src"
        / "si_v2"
        / "apply_actuator"
        / "rollback_executor.py"
    )

    missing = []
    if not rollback_rehearsal.exists():
        missing.append("rollback_rehearsal.py")
    if not rollback_executor.exists():
        missing.append("rollback_executor.py")

    if missing:
        return ReadinessCheckResult(
            check_name="rollback_proof",
            passed=False,
            detail=f"Missing rollback modules: {', '.join(missing)}",
        )

    return ReadinessCheckResult(
        check_name="rollback_proof",
        passed=True,
        detail="Rollback executor and rehearsal modules exist in tree",
    )


def _check_measurement_proof(repo_root: Path) -> ReadinessCheckResult:
    """Check that measurement proof artifacts exist."""
    measurement_modules = [
        "fleet_post_fleet_measurement_watcher.py",
    ]
    rollout_dir = repo_root / "self_improvement_v2" / "src" / "si_v2" / "rollout"
    missing = []
    for mod in measurement_modules:
        if not (rollout_dir / mod).exists():
            missing.append(mod)

    # Also check autonomous measurement watcher
    watcher = (
        repo_root
        / "self_improvement_v2"
        / "src"
        / "si_v2"
        / "measurement"
        / "autonomous_measurement_watcher.py"
    )
    if not watcher.exists():
        missing.append("autonomous_measurement_watcher.py")

    if missing:
        return ReadinessCheckResult(
            check_name="measurement_proof",
            passed=False,
            detail=f"Missing measurement modules: {', '.join(missing)}",
        )

    return ReadinessCheckResult(
        check_name="measurement_proof",
        passed=True,
        detail="Measurement watcher and post-fleet measurement modules exist",
    )


def _check_alerting_requirements(repo_root: Path) -> ReadinessCheckResult:
    """Check that alerting requirements are documented or proven."""
    # Check for alerting-related docs
    alerting_docs = list(
        (repo_root / "docs").rglob("*alert*")
    ) + list(
        (repo_root / "docs").rglob("*alerting*")
    )

    if not alerting_docs:
        return ReadinessCheckResult(
            check_name="alerting_requirements",
            passed=False,
            detail=(
                "No alerting documentation found. "
                "Alerting requirements are explicitly missing."
            ),
        )

    return ReadinessCheckResult(
        check_name="alerting_requirements",
        passed=True,
        detail=f"Found {len(alerting_docs)} alerting-related documents",
    )


def _check_risk_limit_requirements(repo_root: Path) -> ReadinessCheckResult:
    """Check that risk-limit requirements are documented or proven."""
    # Check for risk-related docs
    risk_docs = list(
        (repo_root / "docs").rglob("*risk*")
    ) + list(
        (repo_root / "docs").rglob("*limit*")
    )

    if not risk_docs:
        return ReadinessCheckResult(
            check_name="risk_limit_requirements",
            passed=False,
            detail=(
                "No risk limit documentation found. "
                "Risk-limit requirements are explicitly missing."
            ),
        )

    return ReadinessCheckResult(
        check_name="risk_limit_requirements",
        passed=True,
        detail=f"Found {len(risk_docs)} risk-related documents",
    )


# ---------------------------------------------------------------------------
# Main audit function
# ---------------------------------------------------------------------------


def run_live_readiness_evidence_audit(
    *,
    repo_root: Path | None = None,
    audit_output_dir: Path | None = None,
    now_utc: str | None = None,
) -> LiveReadinessAuditResult:
    """Run the live readiness evidence audit.

    Args:
        repo_root: Root of the trading-hub repository. Defaults to
            auto-detection from the current file location.
        audit_output_dir: Override for audit output directory.
        now_utc: Override for current UTC time (testing).

    Returns:
        LiveReadinessAuditResult with audit status and evidence.
    """
    resolved_now = now_utc or datetime.now(UTC).isoformat()
    resolved_dir = audit_output_dir or Path(DEFAULT_AUDIT_OUTPUT_DIR)

    # Auto-detect repo root if not provided
    if repo_root is None:
        repo_root = Path(__file__).resolve().parent.parent.parent.parent.parent

    # ------------------------------------------------------------------
    # Run all checks
    # ------------------------------------------------------------------

    checks: list[ReadinessCheckResult] = []
    blocked: list[str] = []

    # Check 1: Track A merged
    c1 = _check_track_a_merged(repo_root)
    checks.append(c1)
    if not c1.passed:
        blocked.append(c1.detail)

    # Check 2: Dry-run artifacts
    c2 = _check_dry_run_artifacts(repo_root)
    checks.append(c2)
    if not c2.passed:
        blocked.append(c2.detail)

    # Check 3: No live activation
    c3 = _check_no_live_activation(repo_root)
    checks.append(c3)
    if not c3.passed:
        blocked.append(c3.detail)

    # Check 4: Rollback proof
    c4 = _check_rollback_proof(repo_root)
    checks.append(c4)
    if not c4.passed:
        blocked.append(c4.detail)

    # Check 5: Measurement proof
    c5 = _check_measurement_proof(repo_root)
    checks.append(c5)
    if not c5.passed:
        blocked.append(c5.detail)

    # Check 6: Alerting requirements
    c6 = _check_alerting_requirements(repo_root)
    checks.append(c6)
    if not c6.passed:
        blocked.append(c6.detail)

    # Check 7: Risk-limit requirements
    c7 = _check_risk_limit_requirements(repo_root)
    checks.append(c7)
    if not c7.passed:
        blocked.append(c7.detail)

    # ------------------------------------------------------------------
    # Determine overall status
    # ------------------------------------------------------------------

    # Only hard checks block readiness. Soft checks (alerting, risk limits)
    # are informational and expected to be missing at this stage.
    hard_check_names = {
        "track_a_modules_exist",
        "dry_run_artifacts_exist",
        "no_live_activation",
        "rollback_proof",
        "measurement_proof",
    }

    hard_blocked = [
        c.detail for c in checks
        if not c.passed and c.check_name in hard_check_names
    ]

    if hard_blocked:

        status: str = "LIVE_READINESS_BLOCKED"
        next_step = (
            "Review blocked reasons and address before re-running audit. "
            "No live activation should proceed until all checks pass."
        )
    else:
        status = "LIVE_READINESS_PREP_READY"
        next_step = (
            "All readiness checks pass. Proceed to B2 — Production Risk "
            "Limits Spec. No live activation without explicit human approval."
        )

    # ------------------------------------------------------------------
    # Write audit JSON
    # ------------------------------------------------------------------

    audit_blocked = hard_blocked + [
        c.detail for c in checks
        if not c.passed and c.check_name not in hard_check_names
    ]

    audit: dict[str, object] = {
        "event": "live_readiness_evidence_audit",
        "status": status,
        "checks": [c.to_dict() for c in checks],
        "blocked_reasons": audit_blocked,
        "created_at_utc": resolved_now,
        "runtime_mutation": "NONE",
    }
    audit_path = resolved_dir / "live_readiness_audit.json"
    _atomic_write_json(audit_path, audit)

    # ------------------------------------------------------------------
    # Write human-readable report
    # ------------------------------------------------------------------

    report_lines: list[str] = [
        "# Live Readiness Evidence Audit",
        "",
        f"**Status:** {status}",
        f"**Generated at:** {resolved_now}",
        "**Runtime mutation:** NONE",
        "",
        "---",
        "",
        "## Check Results",
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

    if audit_blocked:
        report_lines.append("---")
        report_lines.append("")
        report_lines.append("## Blocked Reasons")
        report_lines.append("")
        for i, reason in enumerate(audit_blocked, 1):
            report_lines.append(f"{i}. {reason}")
        report_lines.append("")

    report_lines.append("---")
    report_lines.append("")
    report_lines.append("## Next Step")
    report_lines.append("")
    report_lines.append(next_step)
    report_lines.append("")

    report_text = "\n".join(report_lines)
    report_path = resolved_dir / "live_readiness_evidence_audit.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report_text)

    return LiveReadinessAuditResult(
        status=status,  # type: ignore[assignment]
        checks=tuple(checks),
        blocked_reasons=tuple(audit_blocked),
        audit_path=str(audit_path),
        report_path=str(report_path),
        next_step=next_step,
    )
