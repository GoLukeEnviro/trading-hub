"""SI-v2 C1 — Human Approval Gate for Live Canary.

Validates explicit human approval state for live canary transition.
Blocks all live-canary transition workflows unless the approval marker
is present, fresh, and correctly formatted.

This module is **read-only and gate-only**. It does NOT:
- Activate live canary
- Set dry_run=false
- Create or modify exchange keys
- Modify Freqtrade runtime config
- Execute any runtime mutation
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_GATE_OUTPUT_DIR: str = "var/si_v2/live_canary_approval_gate"

# The only accepted approval marker value.
APPROVED_MARKER: str = "APPROVED_LIVE_CANARY_TRANSITION"

# Maximum age of the approval marker in days.
MAX_APPROVAL_AGE_DAYS: int = 7

# Expected approval marker document path.
DEFAULT_APPROVAL_DOC_PATH: str = (
    "docs/decisions/APPROVED_LIVE_CANARY_TRANSITION.md"
)

# Required Track B evidence references.
REQUIRED_TRACK_B_EVIDENCE: tuple[str, ...] = (
    "B1 — Live Readiness Evidence Audit",
    "B2 — Production Risk Limits Spec",
    "B3 — Incident Response and Go-Live Runbooks",
    "B4 — Production Alerting Readiness Gate",
)

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ApprovalGateCheckResult:
    """Result of a single approval gate check."""

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
class LiveCanaryApprovalGateResult:
    """Structured result from the live canary approval gate.

    Attributes:
        status: LIVE_CANARY_APPROVAL_READY or LIVE_CANARY_APPROVAL_BLOCKED.
        checks: Individual check results.
        blocked_reasons: Reasons the gate is blocked.
        gate_path: Path to the written gate JSON.
        report_path: Path to the written human-readable report.
        next_step: Suggested next action.
    """

    status: Literal[
        "LIVE_CANARY_APPROVAL_READY",
        "LIVE_CANARY_APPROVAL_BLOCKED",
    ]
    checks: tuple[ApprovalGateCheckResult, ...]
    blocked_reasons: tuple[str, ...]
    gate_path: str
    report_path: str
    next_step: str

    def to_dict(self) -> dict[str, object]:
        return {
            "event": "live_canary_approval_gate_result",
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


# ---------------------------------------------------------------------------
# Check: approval marker document exists and is readable
# ---------------------------------------------------------------------------


def _check_approval_document_exists(
    approval_doc_path: str,
    repo_root: Path,
) -> ApprovalGateCheckResult:
    """Check that the approval marker document exists and is readable."""
    doc = repo_root / approval_doc_path
    if not doc.exists():
        return ApprovalGateCheckResult(
            check_name="approval_document_exists",
            passed=False,
            detail=(
                f"Approval document not found at {approval_doc_path}. "
                f"The APPROVED_LIVE_CANARY_TRANSITION marker must be "
                f"recorded in a tracked file."
            ),
        )

    try:
        text = doc.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        return ApprovalGateCheckResult(
            check_name="approval_document_exists",
            passed=False,
            detail=f"Approval document not readable: {e}",
        )

    if len(text.strip()) < 50:
        return ApprovalGateCheckResult(
            check_name="approval_document_exists",
            passed=False,
            detail=(
                f"Approval document at {approval_doc_path} appears "
                f"to be empty or too short."
            ),
        )

    return ApprovalGateCheckResult(
        check_name="approval_document_exists",
        passed=True,
        detail=f"Approval document found at {approval_doc_path}",
    )


# ---------------------------------------------------------------------------
# Check: approval marker value is correct
# ---------------------------------------------------------------------------


def _check_approval_marker_value(
    approval_doc_path: str,
    repo_root: Path,
) -> ApprovalGateCheckResult:
    """Check that the document contains the correct approval marker."""
    doc = repo_root / approval_doc_path
    if not doc.exists():
        return ApprovalGateCheckResult(
            check_name="approval_marker_value",
            passed=False,
            detail="Approval document does not exist — cannot check marker value",
        )

    try:
        text = doc.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ApprovalGateCheckResult(
            check_name="approval_marker_value",
            passed=False,
            detail="Approval document not readable — cannot check marker value",
        )

    if APPROVED_MARKER not in text:
        return ApprovalGateCheckResult(
            check_name="approval_marker_value",
            passed=False,
            detail=(
                f"Approval marker {APPROVED_MARKER!r} not found in "
                f"{approval_doc_path}. The document must contain the "
                f"exact marker string."
            ),
        )

    return ApprovalGateCheckResult(
        check_name="approval_marker_value",
        passed=True,
        detail=f"Approval marker {APPROVED_MARKER!r} found in document",
    )


# ---------------------------------------------------------------------------
# Check: approval is not stale (> 7 days)
# ---------------------------------------------------------------------------


def _check_approval_freshness(
    approval_doc_path: str,
    repo_root: Path,
    now_utc: str,
) -> ApprovalGateCheckResult:
    """Check that the approval marker is not stale."""
    doc = repo_root / approval_doc_path
    if not doc.exists():
        return ApprovalGateCheckResult(
            check_name="approval_freshness",
            passed=False,
            detail="Approval document does not exist — cannot check freshness",
        )

    try:
        stat = doc.stat()
        mtime = datetime.fromtimestamp(stat.st_mtime, tz=UTC)
        now = datetime.fromisoformat(now_utc.replace("Z", "+00:00"))
        age_days = (now - mtime).total_seconds() / 86400
    except (ValueError, OSError) as e:
        return ApprovalGateCheckResult(
            check_name="approval_freshness",
            passed=False,
            detail=f"Cannot determine approval age: {e}",
        )

    if age_days > MAX_APPROVAL_AGE_DAYS:
        return ApprovalGateCheckResult(
            check_name="approval_freshness",
            passed=False,
            detail=(
                f"Approval is {age_days:.1f} days old (max "
                f"{MAX_APPROVAL_AGE_DAYS} days). Marker has expired "
                f"and must be renewed."
            ),
        )

    return ApprovalGateCheckResult(
        check_name="approval_freshness",
        passed=True,
        detail=f"Approval is {age_days:.1f} days old (within {MAX_APPROVAL_AGE_DAYS}-day limit)",
    )


# ---------------------------------------------------------------------------
# Check: Track B evidence references
# ---------------------------------------------------------------------------


def _check_track_b_evidence(
    approval_doc_path: str,
    repo_root: Path,
) -> ApprovalGateCheckResult:
    """Check that the approval document references all Track B evidence."""
    doc = repo_root / approval_doc_path
    if not doc.exists():
        return ApprovalGateCheckResult(
            check_name="track_b_evidence_references",
            passed=False,
            detail="Approval document does not exist — cannot check evidence refs",
        )

    try:
        text = doc.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ApprovalGateCheckResult(
            check_name="track_b_evidence_references",
            passed=False,
            detail="Approval document not readable — cannot check evidence refs",
        )

    missing: list[str] = []
    for ref in REQUIRED_TRACK_B_EVIDENCE:
        # Check for the B-number (B1, B2, B3, B4) in the text
        b_number = ref.split(" —")[0]
        if b_number not in text:
            missing.append(b_number)

    if missing:
        return ApprovalGateCheckResult(
            check_name="track_b_evidence_references",
            passed=False,
            detail=(
                f"Missing Track B evidence references in approval document: "
                f"{', '.join(missing)}. The document must reference all "
                f"completed Track B phases."
            ),
        )

    return ApprovalGateCheckResult(
        check_name="track_b_evidence_references",
        passed=True,
        detail="All Track B evidence references (B1-B4) found in approval document",
    )


# ---------------------------------------------------------------------------
# Check: no superseding approval exists
# ---------------------------------------------------------------------------


def _check_no_superseding_approval(
    approval_doc_path: str,
    repo_root: Path,
) -> ApprovalGateCheckResult:
    """Check that no superseding or conflicting approval exists."""
    # Check for any other APPROVED_* markers in the decisions directory
    decisions_dir = repo_root / "docs" / "decisions"
    if not decisions_dir.exists():
        return ApprovalGateCheckResult(
            check_name="no_superseding_approval",
            passed=True,
            detail="No decisions directory — no conflicting approvals found",
        )

    # Look for any file containing a different APPROVED_* marker
    # that might supersede or conflict with the live canary transition
    conflicting: list[str] = []
    for f in decisions_dir.iterdir():
        if f.name == Path(approval_doc_path).name:
            continue  # Skip the approval document itself
        if f.suffix == ".md":
            try:
                text = f.read_text(encoding="utf-8")
                # Look for APPROVED_ markers that are NOT the live canary one
                markers = re.findall(r"APPROVED_[A-Z_]+", text)
                for marker in markers:
                    if marker != APPROVED_MARKER and ("LIVE" in marker or "CANARY" in marker):
                        conflicting.append(f"{marker} in {f.name}")
            except (OSError, UnicodeDecodeError):
                pass

    if conflicting:
        return ApprovalGateCheckResult(
            check_name="no_superseding_approval",
            passed=False,
            detail=(
                f"Conflicting approval markers found: "
                f"{'; '.join(conflicting)}. Only "
                f"{APPROVED_MARKER!r} is valid for this gate."
            ),
        )

    return ApprovalGateCheckResult(
        check_name="no_superseding_approval",
        passed=True,
        detail="No conflicting or superseding approvals found",
    )


# ---------------------------------------------------------------------------
# Main gate function
# ---------------------------------------------------------------------------


def run_live_canary_approval_gate(
    *,
    approval_doc_path: str | None = None,
    repo_root: Path | None = None,
    gate_output_dir: Path | None = None,
    now_utc: str | None = None,
) -> LiveCanaryApprovalGateResult:
    """Run the live canary human approval gate.

    Args:
        approval_doc_path: Path to the approval marker document, relative
            to repo_root. Defaults to
            docs/decisions/APPROVED_LIVE_CANARY_TRANSITION.md.
        repo_root: Root of the trading-hub repository. Defaults to
            auto-detection from the current file location.
        gate_output_dir: Override for gate output directory.
        now_utc: Override for current UTC time (testing).

    Returns:
        LiveCanaryApprovalGateResult with gate status and evidence.
    """
    resolved_now = now_utc or datetime.now(UTC).isoformat()
    resolved_dir = gate_output_dir or Path(DEFAULT_GATE_OUTPUT_DIR)
    resolved_approval_doc = approval_doc_path or DEFAULT_APPROVAL_DOC_PATH

    # Auto-detect repo root if not provided
    if repo_root is None:
        repo_root = Path(__file__).resolve().parent.parent.parent.parent.parent

    # ------------------------------------------------------------------
    # Run all checks
    # ------------------------------------------------------------------

    checks: list[ApprovalGateCheckResult] = []
    blocked: list[str] = []

    # Check 1: Approval document exists
    c1 = _check_approval_document_exists(resolved_approval_doc, repo_root)
    checks.append(c1)
    if not c1.passed:
        blocked.append(c1.detail)

    # Check 2: Approval marker value is correct
    c2 = _check_approval_marker_value(resolved_approval_doc, repo_root)
    checks.append(c2)
    if not c2.passed:
        blocked.append(c2.detail)

    # Check 3: Approval is not stale
    c3 = _check_approval_freshness(resolved_approval_doc, repo_root, resolved_now)
    checks.append(c3)
    if not c3.passed:
        blocked.append(c3.detail)

    # Check 4: Track B evidence references
    c4 = _check_track_b_evidence(resolved_approval_doc, repo_root)
    checks.append(c4)
    if not c4.passed:
        blocked.append(c4.detail)

    # Check 5: No superseding approval
    c5 = _check_no_superseding_approval(resolved_approval_doc, repo_root)
    checks.append(c5)
    if not c5.passed:
        blocked.append(c5.detail)

    # ------------------------------------------------------------------
    # Determine overall status
    # ------------------------------------------------------------------

    if blocked:
        status: str = "LIVE_CANARY_APPROVAL_BLOCKED"
        next_step = (
            "Review blocked reasons and address before re-running gate. "
            "Live canary transition cannot proceed until all approval "
            "checks pass."
        )
    else:
        status = "LIVE_CANARY_APPROVAL_READY"
        next_step = (
            "All approval checks pass. Proceed to C2 — Live Canary Config "
            "Plan, No Activation. "
            "No live activation without explicit human approval."
        )

    # ------------------------------------------------------------------
    # Write gate JSON
    # ------------------------------------------------------------------

    gate: dict[str, object] = {
        "event": "live_canary_approval_gate_result",
        "status": status,
        "approval_doc_path": resolved_approval_doc,
        "checks": [c.to_dict() for c in checks],
        "blocked_reasons": blocked,
        "created_at_utc": resolved_now,
        "runtime_mutation": "NONE",
    }
    gate_path = resolved_dir / "live_canary_approval_gate.json"
    _atomic_write_json(gate_path, gate)

    # ------------------------------------------------------------------
    # Write human-readable report
    # ------------------------------------------------------------------

    report_lines: list[str] = [
        "# Live Canary Approval Gate",
        "",
        f"**Status:** {status}",
        f"**Approval document:** {resolved_approval_doc}",
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
    report_path = resolved_dir / "live_canary_approval_gate.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report_text)

    return LiveCanaryApprovalGateResult(
        status=status,  # type: ignore[assignment]
        checks=tuple(checks),
        blocked_reasons=tuple(blocked),
        gate_path=str(gate_path),
        report_path=str(report_path),
        next_step=next_step,
    )
