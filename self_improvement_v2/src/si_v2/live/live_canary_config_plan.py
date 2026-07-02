"""SI-v2 C2 — Live Canary Config Plan, No Activation.

Selects exactly one canary target (freqtrade-freqforge-canary), requires C1
approval gate status before READY, documents planned live config deltas
without applying them, documents exchange-key boundaries, risk limits from
B2, alerting gate from B4, rollback references, and measurement window.

This module is **read-only and plan-only**. It does NOT:
- Activate live canary
- Toggle dry_run to false
- Create or modify exchange keys
- Modify Freqtrade runtime config
- Execute any runtime mutation
- Apply any config change
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

DEFAULT_PLAN_OUTPUT_DIR: str = "var/si_v2/live_canary_config_plan"

# The single approved canary target.
CANARY_TARGET: str = "freqtrade-freqforge-canary"

# Expected C1 gate output path (relative to repo root).
C1_GATE_OUTPUT_DIR: str = "var/si_v2/live_canary_approval_gate"

# Expected C1 gate JSON filename.
C1_GATE_FILENAME: str = "live_canary_approval_gate.json"

# Expected C1 READY status.
C1_READY_STATUS: str = "LIVE_CANARY_APPROVAL_READY"

# B2 risk limits reference.
B2_RISK_LIMITS_DOC: str = "docs/specs/production-risk-limits-spec.md"

# B4 alerting gate reference.
B4_ALERTING_GATE_DOC: str = "docs/reports/production-alerting-readiness-gate.md"

# Rollback reference.
ROLLBACK_RUNBOOK: str = "docs/context/freqforge-canary-deployment-runbook.md"

# Kill switch runbook.
KILL_SWITCH_RUNBOOK: str = "docs/runbooks/kill-switch.md"

# Incident response runbook.
INCIDENT_RESPONSE_RUNBOOK: str = "docs/specs/incident-response-runbooks.md"

# Measurement window (in days) for post-activation evaluation.
MEASUREMENT_WINDOW_DAYS: int = 14

# Planned live config deltas (dry_run -> live).
# These are documented but NOT applied by this module.
PLANNED_CONFIG_DELTAS: dict[str, object] = {
    "dry_run": {
        "current": True,
        "planned": False,
        "description": "Switch from dry-run to live execution mode",
        "config_key": "dry_run",
        "config_file": "freqforge-canary/config/config_canary_dryrun.json",
        "new_config_file": "freqforge-canary/config/config_canary_live.json",
        "notes": (
            "A new config file config_canary_live.json will be created as a "
            "copy of config_canary_dryrun.json with dry_run set to false. "
            "The dry-run config is preserved for rollback."
        ),
    },
    "stake_amount": {
        "current": 25.0,
        "planned": 25.0,
        "description": "Stake amount per trade (unchanged from dry-run)",
        "config_key": "stake_amount",
        "notes": (
            "Stake amount remains at 25 USDT per trade. This is within the "
            "B2 risk limit of 500 USDT max per bot and 200 USDT max notional "
            "per position."
        ),
    },
    "max_open_trades": {
        "current": 3,
        "planned": 3,
        "description": "Max open trades (unchanged from dry-run)",
        "config_key": "max_open_trades",
        "notes": (
            "Max open trades remains at 3. This is within the B2 risk limit "
            "of 3 max open trades per bot."
        ),
    },
    "dry_run_wallet": {
        "current": 500,
        "planned": None,
        "description": "Dry-run wallet removed in live mode",
        "config_key": "dry_run_wallet",
        "notes": (
            "The dry_run_wallet field is removed in live mode. Real exchange "
            "balance is used instead. B2 risk limit caps live capital at "
            "500 USDT per bot."
        ),
    },
    "exchange_api": {
        "current": "No API keys (dry-run)",
        "planned": "Bitget API keys required",
        "description": "Exchange API key configuration for live trading",
        "config_key": "exchange.key",
        "notes": (
            "Live mode requires Bitget API keys with read-only and trade "
            "permissions. Keys are configured via environment variables or "
            "Freqtrade exchange sandbox. API keys are NEVER stored in config "
            "files. Exchange key boundaries: only Bitget spot/futures, only "
            "whitelisted pairs, no withdrawal permissions."
        ),
    },
    "db_url": {
        "current": "sqlite:////freqtrade/user_data/tradesv3.freqforge_canary.dryrun.sqlite",
        "planned": "sqlite:////freqtrade/user_data/tradesv3.freqforge_canary.live.sqlite",
        "description": "Separate live database to preserve dry-run history",
        "config_key": "db_url",
        "notes": (
            "A new live database file is used to keep dry-run trade history "
            "intact for comparison. The dry-run DB is preserved for rollback "
            "and post-mortem analysis."
        ),
    },
    "stoploss": {
        "current": -0.09,
        "planned": -0.09,
        "description": "Stoploss (unchanged from dry-run)",
        "config_key": "stoploss",
        "notes": (
            "Stoploss remains at -9%. This is within the B2 risk limit of "
            "15% max drawdown per bot."
        ),
    },
}

# Exchange key boundaries (documented, not applied).
EXCHANGE_KEY_BOUNDARIES: dict[str, object] = {
    "exchange": "Bitget",
    "key_permissions_required": [
        "read_only: balance, orders, positions",
        "trade: place, cancel, modify orders",
    ],
    "key_permissions_forbidden": [
        "withdraw",
        "transfer",
        "api_key_management",
    ],
    "key_storage": (
        "API keys are configured via environment variables (FREQTRADE__EXCHANGE__KEY "
        "and FREQTRADE__EXCHANGE__SECRET) or Freqtrade exchange sandbox. "
        "Keys are NEVER stored in config files or version control."
    ),
    "key_rotation": (
        "API keys should be rotated before live activation and after any "
        "security incident. Rotation is a manual operator action."
    ),
    "ip_restriction": (
        "Bitget API keys should be restricted to the trading server IP "
        "address where possible."
    ),
    "max_capital_per_bot_usd": 500,
    "whitelisted_pairs": [
        "BTC/USDT:USDT",
        "ETH/USDT:USDT",
        "SOL/USDT:USDT",
        "LINK/USDT:USDT",
        "DOT/USDT:USDT",
        "ATOM/USDT:USDT",
        "UNI/USDT:USDT",
        "AAVE/USDT:USDT",
    ],
}

# B2 risk limits summary.
B2_RISK_LIMITS: dict[str, object] = {
    "document": B2_RISK_LIMITS_DOC,
    "max_capital_per_bot_usd": 500,
    "max_open_trades_per_bot": 3,
    "max_daily_loss_per_bot_usd": 50,
    "max_notional_per_position_usd": 200,
    "max_drawdown_per_bot_percent": 15,
    "max_drawdown_fleet_percent": 10,
    "kill_switch_on_drawdown_breach": "EMERGENCY",
}

# B4 alerting gate summary.
B4_ALERTING_GATE: dict[str, object] = {
    "document": B4_ALERTING_GATE_DOC,
    "checks": [
        "alert_config_evidence",
        "delivery_proof",
        "drawdown_alert_proof",
        "runtime_failure_alert_proof",
    ],
    "required_status": "PRODUCTION_ALERTING_READY",
}

# Rollback references.
ROLLBACK_REFERENCES: dict[str, object] = {
    "deployment_runbook": ROLLBACK_RUNBOOK,
    "kill_switch_runbook": KILL_SWITCH_RUNBOOK,
    "incident_response_runbook": INCIDENT_RESPONSE_RUNBOOK,
    "rollback_steps": [
        "1. Activate kill switch: EMERGENCY mode to halt all trading",
        "2. Stop canary container: use docker action to halt freqtrade-freqforge-canary",
        "3. Remove canary container: use docker action to rm freqtrade-freqforge-canary",
        "4. Restore dry-run config: use preserved config_canary_dryrun.json",
        "5. Restart in dry-run mode: redeploy canary container via compose orchestration",
        "6. Verify dry-run operation: check logs, DB, and API health",
        "7. File incident report in docs/incidents/",
    ],
    "rollback_precondition": (
        "The dry-run config file (config_canary_dryrun.json) must be preserved "
        "and unmodified. The dry-run database must be preserved."
    ),
}

# Measurement window.
MEASUREMENT_WINDOW: dict[str, object] = {
    "duration_days": MEASUREMENT_WINDOW_DAYS,
    "metrics": [
        "total_trades",
        "win_rate",
        "profit_factor",
        "sharpe_ratio",
        "max_drawdown",
        "avg_profit_per_trade",
        "daily_loss",
        "notional_exposure",
    ],
    "comparison_baseline": "dry-run performance from preceding 14 days",
    "evaluation_gate": "C4 — Live Canary Measurement and Decision",
    "decision_outcomes": ["KEEP", "EXTEND", "ROLLBACK"],
}


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConfigPlanCheckResult:
    """Result of a single config plan check."""

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
class LiveCanaryConfigPlanResult:
    """Structured result from the live canary config plan.

    Attributes:
        status: LIVE_CANARY_CONFIG_PLAN_READY or LIVE_CANARY_CONFIG_PLAN_BLOCKED.
        checks: Individual check results.
        blocked_reasons: Reasons the plan is blocked.
        plan_path: Path to the written plan JSON.
        report_path: Path to the written human-readable report.
        next_step: Suggested next action.
    """

    status: Literal[
        "LIVE_CANARY_CONFIG_PLAN_READY",
        "LIVE_CANARY_CONFIG_PLAN_BLOCKED",
    ]
    checks: tuple[ConfigPlanCheckResult, ...]
    blocked_reasons: tuple[str, ...]
    plan_path: str
    report_path: str
    next_step: str

    def to_dict(self) -> dict[str, object]:
        return {
            "event": "live_canary_config_plan_result",
            "status": self.status,
            "checks": [c.to_dict() for c in self.checks],
            "blocked_reasons": list(self.blocked_reasons),
            "plan_path": self.plan_path,
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


# ---------------------------------------------------------------------------
# Check: C1 approval gate status
# ---------------------------------------------------------------------------


def _check_c1_approval_gate(
    repo_root: Path,
) -> ConfigPlanCheckResult:
    """Check that the C1 approval gate passed with READY status."""
    gate_dir = repo_root / C1_GATE_OUTPUT_DIR
    gate_file = gate_dir / C1_GATE_FILENAME

    if not gate_file.exists():
        return ConfigPlanCheckResult(
            check_name="c1_approval_gate_status",
            passed=False,
            detail=(
                f"C1 approval gate output not found at {C1_GATE_OUTPUT_DIR}/"
                f"{C1_GATE_FILENAME}. Run the C1 approval gate before "
                f"proceeding to C2."
            ),
        )

    try:
        gate_data = json.loads(gate_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return ConfigPlanCheckResult(
            check_name="c1_approval_gate_status",
            passed=False,
            detail=f"C1 gate output not readable: {e}",
        )

    status = gate_data.get("status", "")
    if status != C1_READY_STATUS:
        return ConfigPlanCheckResult(
            check_name="c1_approval_gate_status",
            passed=False,
            detail=(
                f"C1 approval gate status is '{status}', expected "
                f"'{C1_READY_STATUS}'. Address C1 blockers before "
                f"proceeding to C2."
            ),
        )

    return ConfigPlanCheckResult(
        check_name="c1_approval_gate_status",
        passed=True,
        detail=f"C1 approval gate status is '{C1_READY_STATUS}'",
    )


# ---------------------------------------------------------------------------
# Check: Canary target is valid
# ---------------------------------------------------------------------------


def _check_canary_target(
    repo_root: Path,
) -> ConfigPlanCheckResult:
    """Check that the canary target exists and is valid."""
    # Check that the canary config directory exists
    canary_config_dir = repo_root / "freqforge-canary" / "config"
    if not canary_config_dir.exists():
        return ConfigPlanCheckResult(
            check_name="canary_target_valid",
            passed=False,
            detail=(
                f"Canary target '{CANARY_TARGET}' config directory not found "
                f"at {canary_config_dir}. The canary bot must be deployed "
                f"before config planning."
            ),
        )

    # Check that the dry-run config exists
    dryrun_config = canary_config_dir / "config_canary_dryrun.json"
    if not dryrun_config.exists():
        return ConfigPlanCheckResult(
            check_name="canary_target_valid",
            passed=False,
            detail=(
                f"Canary dry-run config not found at {dryrun_config}. "
                f"The config file is required for delta planning."
            ),
        )

    return ConfigPlanCheckResult(
        check_name="canary_target_valid",
        passed=True,
        detail=(
            f"Canary target '{CANARY_TARGET}' is valid. Config directory "
            f"and dry-run config file exist."
        ),
    )


# ---------------------------------------------------------------------------
# Check: B2 risk limits document exists
# ---------------------------------------------------------------------------


def _check_b2_risk_limits(
    repo_root: Path,
) -> ConfigPlanCheckResult:
    """Check that the B2 risk limits document exists."""
    doc = repo_root / B2_RISK_LIMITS_DOC
    if not doc.exists():
        return ConfigPlanCheckResult(
            check_name="b2_risk_limits_document",
            passed=False,
            detail=(
                f"B2 risk limits document not found at {B2_RISK_LIMITS_DOC}. "
                f"The document is required for config planning."
            ),
        )

    return ConfigPlanCheckResult(
        check_name="b2_risk_limits_document",
        passed=True,
        detail=f"B2 risk limits document found at {B2_RISK_LIMITS_DOC}",
    )


# ---------------------------------------------------------------------------
# Check: B4 alerting gate document exists
# ---------------------------------------------------------------------------


def _check_b4_alerting_gate(
    repo_root: Path,
) -> ConfigPlanCheckResult:
    """Check that the B4 alerting gate document exists."""
    doc = repo_root / B4_ALERTING_GATE_DOC
    if not doc.exists():
        return ConfigPlanCheckResult(
            check_name="b4_alerting_gate_document",
            passed=False,
            detail=(
                f"B4 alerting gate document not found at "
                f"{B4_ALERTING_GATE_DOC}. The document is required for "
                f"config planning."
            ),
        )

    return ConfigPlanCheckResult(
        check_name="b4_alerting_gate_document",
        passed=True,
        detail=f"B4 alerting gate document found at {B4_ALERTING_GATE_DOC}",
    )


# ---------------------------------------------------------------------------
# Check: Rollback references exist
# ---------------------------------------------------------------------------


def _check_rollback_references(
    repo_root: Path,
) -> ConfigPlanCheckResult:
    """Check that rollback reference documents exist."""
    missing: list[str] = []
    for ref_key, ref_path in [
        ("deployment_runbook", ROLLBACK_RUNBOOK),
        ("kill_switch_runbook", KILL_SWITCH_RUNBOOK),
        ("incident_response_runbook", INCIDENT_RESPONSE_RUNBOOK),
    ]:
        doc = repo_root / ref_path
        if not doc.exists():
            missing.append(f"{ref_key}: {ref_path}")

    if missing:
        return ConfigPlanCheckResult(
            check_name="rollback_references",
            passed=False,
            detail=(
                f"Missing rollback reference documents: "
                f"{'; '.join(missing)}"
            ),
        )

    return ConfigPlanCheckResult(
        check_name="rollback_references",
        passed=True,
        detail="All rollback reference documents exist",
    )


# ---------------------------------------------------------------------------
# Check: No live config already applied
# ---------------------------------------------------------------------------


def _check_no_live_config_applied(
    repo_root: Path,
) -> ConfigPlanCheckResult:
    """Check that no live config has already been applied."""
    canary_config_dir = repo_root / "freqforge-canary" / "config"
    live_config = canary_config_dir / "config_canary_live.json"

    if live_config.exists():
        return ConfigPlanCheckResult(
            check_name="no_live_config_applied",
            passed=False,
            detail=(
                f"Live config file already exists at {live_config}. "
                f"A config plan may have already been applied or a previous "
                f"attempt was made. Review before proceeding."
            ),
        )

    return ConfigPlanCheckResult(
        check_name="no_live_config_applied",
        passed=True,
        detail="No live config file found — config plan has not been applied",
    )


# ---------------------------------------------------------------------------
# Main plan function
# ---------------------------------------------------------------------------


def run_live_canary_config_plan(
    *,
    repo_root: Path | None = None,
    plan_output_dir: Path | None = None,
    now_utc: str | None = None,
) -> LiveCanaryConfigPlanResult:
    """Run the live canary config plan.

    Args:
        repo_root: Root of the trading-hub repository. Defaults to
            auto-detection from the current file location.
        plan_output_dir: Override for plan output directory.
        now_utc: Override for current UTC time (testing).

    Returns:
        LiveCanaryConfigPlanResult with plan status and evidence.
    """
    resolved_now = now_utc or datetime.now(UTC).isoformat()
    resolved_dir = plan_output_dir or Path(DEFAULT_PLAN_OUTPUT_DIR)

    # Auto-detect repo root if not provided
    if repo_root is None:
        repo_root = Path(__file__).resolve().parent.parent.parent.parent.parent

    # ------------------------------------------------------------------
    # Run all checks
    # ------------------------------------------------------------------

    checks: list[ConfigPlanCheckResult] = []
    blocked: list[str] = []

    # Check 1: C1 approval gate status
    c1 = _check_c1_approval_gate(repo_root)
    checks.append(c1)
    if not c1.passed:
        blocked.append(c1.detail)

    # Check 2: Canary target is valid
    c2 = _check_canary_target(repo_root)
    checks.append(c2)
    if not c2.passed:
        blocked.append(c2.detail)

    # Check 3: B2 risk limits document exists
    c3 = _check_b2_risk_limits(repo_root)
    checks.append(c3)
    if not c3.passed:
        blocked.append(c3.detail)

    # Check 4: B4 alerting gate document exists
    c4 = _check_b4_alerting_gate(repo_root)
    checks.append(c4)
    if not c4.passed:
        blocked.append(c4.detail)

    # Check 5: Rollback references exist
    c5 = _check_rollback_references(repo_root)
    checks.append(c5)
    if not c5.passed:
        blocked.append(c5.detail)

    # Check 6: No live config already applied
    c6 = _check_no_live_config_applied(repo_root)
    checks.append(c6)
    if not c6.passed:
        blocked.append(c6.detail)

    # ------------------------------------------------------------------
    # Determine overall status
    # ------------------------------------------------------------------

    if blocked:
        status: str = "LIVE_CANARY_CONFIG_PLAN_BLOCKED"
        next_step = (
            "Review blocked reasons and address before re-running plan. "
            "Live canary config planning cannot proceed until all checks pass."
        )
    else:
        status = "LIVE_CANARY_CONFIG_PLAN_READY"
        next_step = (
            "All config plan checks pass. The config plan is documented and "
            "ready for review. Proceed to C3 — Live Canary Activation "
            "Ceremony. No live activation without explicit human approval."
        )

    # ------------------------------------------------------------------
    # Write plan JSON
    # ------------------------------------------------------------------

    plan: dict[str, object] = {
        "event": "live_canary_config_plan_result",
        "status": status,
        "canary_target": CANARY_TARGET,
        "checks": [c.to_dict() for c in checks],
        "blocked_reasons": blocked,
        "planned_config_deltas": PLANNED_CONFIG_DELTAS,
        "exchange_key_boundaries": EXCHANGE_KEY_BOUNDARIES,
        "b2_risk_limits": B2_RISK_LIMITS,
        "b4_alerting_gate": B4_ALERTING_GATE,
        "rollback_references": ROLLBACK_REFERENCES,
        "measurement_window": MEASUREMENT_WINDOW,
        "created_at_utc": resolved_now,
        "runtime_mutation": "NONE",
    }
    plan_path = resolved_dir / "live_canary_config_plan.json"
    _atomic_write_json(plan_path, plan)

    # ------------------------------------------------------------------
    # Write human-readable report
    # ------------------------------------------------------------------

    report_lines: list[str] = [
        "# Live Canary Config Plan",
        "",
        f"**Status:** {status}",
        f"**Canary target:** {CANARY_TARGET}",
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

    report_lines.extend([
        "---",
        "",
        "## Planned Config Deltas",
        "",
        "The following config changes are **documented but not applied**. "
        "They represent the planned delta between dry-run and live mode.",
        "",
    ])

    for delta_key, delta in PLANNED_CONFIG_DELTAS.items():
        assert isinstance(delta, dict)
        report_lines.append(f"### {delta_key}")
        report_lines.append("")
        report_lines.append(f"**Description:** {delta.get('description', '')}")
        report_lines.append("")
        report_lines.append(f"**Current:** {delta.get('current', '')}")
        report_lines.append("")
        report_lines.append(f"**Planned:** {delta.get('planned', '')}")
        report_lines.append("")
        notes = delta.get("notes", "")
        if notes:
            report_lines.append(f"**Notes:** {notes}")
            report_lines.append("")

    report_lines.extend([
        "---",
        "",
        "## Exchange Key Boundaries",
        "",
        f"**Exchange:** {EXCHANGE_KEY_BOUNDARIES.get('exchange', '')}",
        "",
        "**Required permissions:**",
        "",
    ])

    for perm in EXCHANGE_KEY_BOUNDARIES.get("key_permissions_required", []):
        report_lines.append(f"- {perm}")

    report_lines.append("")
    report_lines.append("**Forbidden permissions:**")
    report_lines.append("")

    for perm in EXCHANGE_KEY_BOUNDARIES.get("key_permissions_forbidden", []):
        report_lines.append(f"- {perm}")

    report_lines.append("")
    report_lines.append(
        f"**Key storage:** {EXCHANGE_KEY_BOUNDARIES.get('key_storage', '')}"
    )
    report_lines.append("")
    report_lines.append(
        f"**Key rotation:** {EXCHANGE_KEY_BOUNDARIES.get('key_rotation', '')}"
    )
    report_lines.append("")
    report_lines.append(
        f"**IP restriction:** {EXCHANGE_KEY_BOUNDARIES.get('ip_restriction', '')}"
    )
    report_lines.append("")
    report_lines.append(
        f"**Max capital per bot:** "
        f"{EXCHANGE_KEY_BOUNDARIES.get('max_capital_per_bot_usd', '')} USDT"
    )
    report_lines.append("")

    report_lines.extend([
        "---",
        "",
        "## B2 Risk Limits",
        "",
        f"**Document:** {B2_RISK_LIMITS.get('document', '')}",
        "",
        f"**Max capital per bot:** {B2_RISK_LIMITS.get('max_capital_per_bot_usd', '')} USDT",
        "",
        f"**Max open trades per bot:** {B2_RISK_LIMITS.get('max_open_trades_per_bot', '')}",
        "",
        f"**Max daily loss per bot:** {B2_RISK_LIMITS.get('max_daily_loss_per_bot_usd', '')} USDT",
        "",
        f"**Max notional per position:** {B2_RISK_LIMITS.get('max_notional_per_position_usd', '')} USDT",
        "",
        f"**Max drawdown per bot:** {B2_RISK_LIMITS.get('max_drawdown_per_bot_percent', '')}%",
        "",
        f"**Max drawdown fleet:** {B2_RISK_LIMITS.get('max_drawdown_fleet_percent', '')}%",
        "",
        f"**Kill switch on drawdown breach:** {B2_RISK_LIMITS.get('kill_switch_on_drawdown_breach', '')}",
        "",
        "---",
        "",
        "## B4 Alerting Gate",
        "",
        f"**Document:** {B4_ALERTING_GATE.get('document', '')}",
        "",
        "**Checks:**",
        "",
    ])

    for check_name in B4_ALERTING_GATE.get("checks", []):
        report_lines.append(f"- {check_name}")

    report_lines.append("")
    report_lines.append(
        f"**Required status:** {B4_ALERTING_GATE.get('required_status', '')}"
    )
    report_lines.append("")

    report_lines.extend([
        "---",
        "",
        "## Rollback References",
        "",
        f"**Deployment runbook:** {ROLLBACK_REFERENCES.get('deployment_runbook', '')}",
        "",
        f"**Kill switch runbook:** {ROLLBACK_REFERENCES.get('kill_switch_runbook', '')}",
        "",
        f"**Incident response runbook:** {ROLLBACK_REFERENCES.get('incident_response_runbook', '')}",
        "",
        "**Rollback steps:**",
        "",
    ])

    for step in ROLLBACK_REFERENCES.get("rollback_steps", []):
        report_lines.append(f"- {step}")

    report_lines.append("")
    report_lines.append(
        f"**Precondition:** {ROLLBACK_REFERENCES.get('rollback_precondition', '')}"
    )
    report_lines.append("")

    report_lines.extend([
        "---",
        "",
        "## Measurement Window",
        "",
        f"**Duration:** {MEASUREMENT_WINDOW.get('duration_days', '')} days",
        "",
        "**Metrics:**",
        "",
    ])

    for metric in MEASUREMENT_WINDOW.get("metrics", []):
        report_lines.append(f"- {metric}")

    report_lines.append("")
    report_lines.append(
        f"**Comparison baseline:** "
        f"{MEASUREMENT_WINDOW.get('comparison_baseline', '')}"
    )
    report_lines.append("")
    report_lines.append(
        f"**Evaluation gate:** "
        f"{MEASUREMENT_WINDOW.get('evaluation_gate', '')}"
    )
    report_lines.append("")
    report_lines.append(
        f"**Decision outcomes:** "
        f"{', '.join(MEASUREMENT_WINDOW.get('decision_outcomes', []))}"
    )
    report_lines.append("")

    report_path = resolved_dir / "live_canary_config_plan.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(report_lines))

    return LiveCanaryConfigPlanResult(
        status=status,
        checks=tuple(checks),
        blocked_reasons=tuple(blocked),
        plan_path=str(plan_path),
        report_path=str(report_path),
        next_step=next_step,
    )
