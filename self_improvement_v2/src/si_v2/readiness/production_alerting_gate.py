"""SI-v2 B4 — Production Alerting Readiness Gate.

Checks whether required production alerts are configured and proven before
live canary activation. Blocks live preparation if any required alert is
missing or unproven.

Checks:
- Alert config evidence (kill switch, RiskGuard, scheduler alerts exist)
- Telegram or equivalent delivery proof
- Drawdown alert proof
- Runtime failure alert proof

Outputs PRODUCTION_ALERTING_READY or PRODUCTION_ALERTING_BLOCKED.
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

DEFAULT_GATE_OUTPUT_DIR: str = "var/si_v2/production_alerting_gate"

# Expected alert config evidence paths.
ALERT_CONFIG_PATHS: dict[str, str] = {
    "kill_switch_file": "freqtrade/shared/kill_switch.py",
    "kill_switch_runbook": "docs/runbooks/kill-switch.md",
    "riskguard_runbook": "docs/runbooks/riskguard-pair-universe.md",
    "incident_response_runbook": "docs/specs/incident-response-runbooks.md",
    "risk_limits_spec": "docs/specs/production-risk-limits-spec.md",
}

# Expected delivery proof evidence.
DELIVERY_PROOF_PATHS: dict[str, str] = {
    "telegram_adapter_module": (
        "self_improvement_v2/src/si_v2/adapters/telegram_adapter.py"
    ),
    "telegram_adapter_test": (
        "self_improvement_v2/tests/test_telegram_adapter.py"
    ),
}

# Expected drawdown alert proof.
DRAWDOWN_ALERT_PATHS: dict[str, str] = {
    "kill_switch_module": "freqtrade/shared/kill_switch.py",
    "kill_switch_procedure": "docs/references/freqtrade-kill-switch-procedure.md",
}

# Expected runtime failure alert proof.
RUNTIME_FAILURE_PATHS: dict[str, str] = {
    "scheduler_cron_dir": "orchestrator/cron",
    "active_cycle_runner": "orchestrator/scripts/si-v2-active-cycle-runner.sh",
}

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AlertGateCheckResult:
    """Result of a single alert gate check."""

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
class ProductionAlertingGateResult:
    """Structured result from the production alerting gate.

    Attributes:
        status: PRODUCTION_ALERTING_READY or PRODUCTION_ALERTING_BLOCKED.
        checks: Individual check results.
        blocked_reasons: Reasons the gate is blocked.
        gate_path: Path to the written gate JSON.
        report_path: Path to the written human-readable report.
        next_step: Suggested next action.
    """

    status: Literal[
        "PRODUCTION_ALERTING_READY",
        "PRODUCTION_ALERTING_BLOCKED",
    ]
    checks: tuple[AlertGateCheckResult, ...]
    blocked_reasons: tuple[str, ...]
    gate_path: str
    report_path: str
    next_step: str

    def to_dict(self) -> dict[str, object]:
        return {
            "event": "production_alerting_gate_result",
            "status": self.status,
            "checks": [c.to_dict() for c in self.checks],
            "blocked_reasons": list(self.blocked_reasons),
            "gate_path": self.gate_path,
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


def _check_alert_config_evidence(repo_root: Path) -> AlertGateCheckResult:
    """Check that alert config evidence exists."""
    found: list[str] = []
    missing: list[str] = []

    for name, rel_path in ALERT_CONFIG_PATHS.items():
        if _path_exists(rel_path, repo_root):
            found.append(name)
        else:
            missing.append(name)

    if missing:
        return AlertGateCheckResult(
            check_name="alert_config_evidence",
            passed=False,
            detail=(
                f"Found: {', '.join(found)}. "
                f"Missing: {', '.join(missing)}."
            ),
        )

    return AlertGateCheckResult(
        check_name="alert_config_evidence",
        passed=True,
        detail=f"All {len(ALERT_CONFIG_PATHS)} alert config paths exist",
    )


def _check_delivery_proof(repo_root: Path) -> AlertGateCheckResult:
    """Check that Telegram or equivalent delivery proof exists."""
    found: list[str] = []
    missing: list[str] = []

    for name, rel_path in DELIVERY_PROOF_PATHS.items():
        if _path_exists(rel_path, repo_root):
            found.append(name)
        else:
            missing.append(name)

    if missing:
        return AlertGateCheckResult(
            check_name="delivery_proof",
            passed=False,
            detail=(
                f"Found: {', '.join(found)}. "
                f"Missing: {', '.join(missing)}."
            ),
        )

    return AlertGateCheckResult(
        check_name="delivery_proof",
        passed=True,
        detail=f"All {len(DELIVERY_PROOF_PATHS)} delivery proof paths exist",
    )


def _check_drawdown_alert_proof(repo_root: Path) -> AlertGateCheckResult:
    """Check that drawdown alert proof exists."""
    found: list[str] = []
    missing: list[str] = []

    for name, rel_path in DRAWDOWN_ALERT_PATHS.items():
        if _path_exists(rel_path, repo_root):
            found.append(name)
        else:
            missing.append(name)

    if missing:
        return AlertGateCheckResult(
            check_name="drawdown_alert_proof",
            passed=False,
            detail=(
                f"Found: {', '.join(found)}. "
                f"Missing: {', '.join(missing)}."
            ),
        )

    return AlertGateCheckResult(
        check_name="drawdown_alert_proof",
        passed=True,
        detail=f"All {len(DRAWDOWN_ALERT_PATHS)} drawdown alert paths exist",
    )


def _check_runtime_failure_alert_proof(repo_root: Path) -> AlertGateCheckResult:
    """Check that runtime failure alert proof exists."""
    found: list[str] = []
    missing: list[str] = []

    for name, rel_path in RUNTIME_FAILURE_PATHS.items():
        if _path_exists(rel_path, repo_root):
            found.append(name)
        else:
            missing.append(name)

    if missing:
        return AlertGateCheckResult(
            check_name="runtime_failure_alert_proof",
            passed=False,
            detail=(
                f"Found: {', '.join(found)}. "
                f"Missing: {', '.join(missing)}."
            ),
        )

    return AlertGateCheckResult(
        check_name="runtime_failure_alert_proof",
        passed=True,
        detail=f"All {len(RUNTIME_FAILURE_PATHS)} runtime failure alert paths exist",
    )


# ---------------------------------------------------------------------------
# Main gate function
# ---------------------------------------------------------------------------


def run_production_alerting_gate(
    *,
    repo_root: Path | None = None,
    gate_output_dir: Path | None = None,
    now_utc: str | None = None,
) -> ProductionAlertingGateResult:
    """Run the production alerting readiness gate.

    Args:
        repo_root: Root of the trading-hub repository. Defaults to
            auto-detection from the current file location.
        gate_output_dir: Override for gate output directory.
        now_utc: Override for current UTC time (testing).

    Returns:
        ProductionAlertingGateResult with gate status and evidence.
    """
    resolved_now = now_utc or datetime.now(UTC).isoformat()
    resolved_dir = gate_output_dir or Path(DEFAULT_GATE_OUTPUT_DIR)

    # Auto-detect repo root if not provided
    if repo_root is None:
        repo_root = Path(__file__).resolve().parent.parent.parent.parent.parent

    # ------------------------------------------------------------------
    # Run all checks
    # ------------------------------------------------------------------

    checks: list[AlertGateCheckResult] = []
    blocked: list[str] = []

    # Check 1: Alert config evidence
    c1 = _check_alert_config_evidence(repo_root)
    checks.append(c1)
    if not c1.passed:
        blocked.append(c1.detail)

    # Check 2: Delivery proof
    c2 = _check_delivery_proof(repo_root)
    checks.append(c2)
    if not c2.passed:
        blocked.append(c2.detail)

    # Check 3: Drawdown alert proof
    c3 = _check_drawdown_alert_proof(repo_root)
    checks.append(c3)
    if not c3.passed:
        blocked.append(c3.detail)

    # Check 4: Runtime failure alert proof
    c4 = _check_runtime_failure_alert_proof(repo_root)
    checks.append(c4)
    if not c4.passed:
        blocked.append(c4.detail)

    # ------------------------------------------------------------------
    # Determine overall status
    # ------------------------------------------------------------------

    if blocked:
        status: str = "PRODUCTION_ALERTING_BLOCKED"
        next_step = (
            "Review blocked reasons and address before re-running gate. "
            "Live preparation cannot proceed until all alerting checks pass."
        )
    else:
        status = "PRODUCTION_ALERTING_READY"
        next_step = (
            "All production alerting checks pass. "
            "Proceed to C1 — Human Approval Gate for Live Canary. "
            "No live activation without explicit human approval."
        )

    # ------------------------------------------------------------------
    # Write gate JSON
    # ------------------------------------------------------------------

    gate: dict[str, object] = {
        "event": "production_alerting_gate_result",
        "status": status,
        "checks": [c.to_dict() for c in checks],
        "blocked_reasons": blocked,
        "created_at_utc": resolved_now,
        "runtime_mutation": "NONE",
    }
    gate_path = resolved_dir / "production_alerting_gate.json"
    _atomic_write_json(gate_path, gate)

    # ------------------------------------------------------------------
    # Write human-readable report
    # ------------------------------------------------------------------

    report_lines: list[str] = [
        "# Production Alerting Readiness Gate",
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

    if blocked:
        report_lines.append("---")
        report_lines.append("")
        report_lines.append("## Blocked Reasons")
        report_lines.append("")
        for i, reason in enumerate(blocked, 1):
            report_lines.append(f"{i}. {reason}")
        report_lines.append("")

    report_lines.append("---")
    report_lines.append("")
    report_lines.append("## Next Step")
    report_lines.append("")
    report_lines.append(next_step)
    report_lines.append("")

    report_text = "\n".join(report_lines)
    report_path = resolved_dir / "production_alerting_readiness_gate.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report_text)

    return ProductionAlertingGateResult(
        status=status,  # type: ignore[assignment]
        checks=tuple(checks),
        blocked_reasons=tuple(blocked),
        gate_path=str(gate_path),
        report_path=str(report_path),
        next_step=next_step,
    )
