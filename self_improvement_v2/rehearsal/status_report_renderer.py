"""Deterministic status report renderer (#153).

Produces JSON and Markdown reports from a ``ValidationResult`` with stable,
testable output — never implies operational approval.

Usage::

    from rehearsal.planning_models import Verdict, Severity, ReasonCode, Finding, ValidationResult
    from rehearsal.status_report_renderer import render_json_report, render_markdown_report

    result = ValidationResult()
    # ... populate result ...

    json_str = render_json_report(result)
    md_str = render_markdown_report(result)

Timestamps are normalised to ``"2026-06-10T00:00:00Z"`` and paths to ``"./"``
for test comparisons.
"""

from __future__ import annotations

import json

from rehearsal.planning_models import (
    Finding,
    ReasonCode,
    Severity,
    ValidationResult,
    Verdict,
)

# ─────────────────────────────────────────────────────────────────────────────
# Normalisation helpers
# ─────────────────────────────────────────────────────────────────────────────

_NORMALISED_TIMESTAMP = "2026-06-10T00:00:00Z"
_NORMALISED_PATH = "./"


def _normalise_timestamp(ts: str) -> str:
    """Return the canonical test timestamp regardless of input."""
    return _NORMALISED_TIMESTAMP


def _normalise_path(p: str) -> str:
    """Normalise a filesystem path to a canonical test form.

    Real absolute paths like ``/opt/data/...`` are reduced to ``"./"``
    so that golden snapshots are machine-independent.
    """
    if not p or p == ".":
        return _NORMALISED_PATH
    return _NORMALISED_PATH


# ─────────────────────────────────────────────────────────────────────────────
# Artifact coverage matrix
# ─────────────────────────────────────────────────────────────────────────────

_COVERAGE_CATEGORIES: list[str] = [
    "#135 — Controlled Rehearsal Planning Gate",
    "#136 — Rehearsal Stop Condition Matrix",
    "#137 — Rehearsal Evidence Bundle Plan",
    "#138 — Operator Rehearsal Approval Packet",
    "#139 — Read-Only Observation Plan",
    "#140 — Rehearsal Readiness Decision Record",
    "#122 — Human Approval Gate Checklist",
    "#124 — Live Readiness Blocker Inventory",
    "#129 — Runtime Preflight Checklist",
    "#131 — External Adapter Boundary Audit",
]


def _build_coverage_matrix(
    result: ValidationResult,
) -> list[dict[str, str | bool]]:
    """Build the artifact coverage matrix from findings.

    Each row indicates whether an artifact was checked and its status.
    """
    checked_artifacts: set[str] = set()
    missing_artifacts: set[str] = set()
    for f in result.findings:
        if f.reason_code == ReasonCode.ARTIFACT_MISSING:
            # Extract issue number from message
            for part in f.message.split():
                if part.startswith("#") and part[1:].isdigit():
                    missing_artifacts.add(part)
        if f.reason_code == ReasonCode.REFERENCE_MISSING:
            for part in f.message.split():
                if part.startswith("#") and part[1:].isdigit():
                    checked_artifacts.add(part)

    rows: list[dict[str, str | bool]] = []
    for cat in _COVERAGE_CATEGORIES:
        iss = cat.split(" —")[0] if " —" in cat else cat.split(" ")[0]
        rows.append(
            {
                "artifact": cat,
                "checked": iss not in missing_artifacts,
                "status": "MISSING" if iss in missing_artifacts else "PRESENT",
            }
        )
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# Group helpers
# ─────────────────────────────────────────────────────────────────────────────


def _group_by_severity(findings: list[Finding]) -> dict[str, list[dict[str, object]]]:
    """Group findings by severity level, sorted deterministically."""
    groups: dict[str, list[dict[str, object]]] = {}
    for sev in Severity:
        groups[sev.value] = []
    for f in sorted(findings, key=lambda x: (x.severity.value, x.reason_code.value, x.check_id)):
        groups[f.severity.value].append(_finding_to_dict(f))
    # Remove empty groups
    return {k: v for k, v in groups.items() if v}


def _group_by_reason_code(findings: list[Finding]) -> dict[str, list[dict[str, object]]]:
    """Group findings by reason code, sorted deterministically."""
    groups: dict[str, list[dict[str, object]]] = {}
    for f in sorted(findings, key=lambda x: (x.reason_code.value, x.check_id)):
        rc = f.reason_code.value
        if rc not in groups:
            groups[rc] = []
        groups[rc].append(_finding_to_dict(f))
    return groups


def _remediation_suggestions(findings: list[Finding]) -> list[dict[str, str]]:
    """Collect unique remediation suggestions, sorted by reason code."""
    seen: set[str] = set()
    suggestions: list[dict[str, str]] = []
    for f in sorted(findings, key=lambda x: (x.reason_code.value, x.check_id)):
        if f.remediation and f.remediation not in seen:
            seen.add(f.remediation)
            suggestions.append(
                {
                    "reason_code": f.reason_code.value,
                    "remediation": f.remediation,
                }
            )
    return suggestions


def _finding_to_dict(f: Finding) -> dict[str, object]:
    """Convert a Finding to a deterministic JSON-safe dict."""
    return {
        "check_id": f.check_id,
        "reason_code": f.reason_code.value,
        "severity": f.severity.value,
        "verdict": f.verdict.value,
        "message": f.message,
        "field_path": f.field_path,
        "evidence": f.evidence,
        "remediation": f.remediation,
    }


# ─────────────────────────────────────────────────────────────────────────────
# JSON report
# ─────────────────────────────────────────────────────────────────────────────


def render_json_report(result: ValidationResult, normalise: bool = False) -> str:
    """Render a deterministic JSON report from a ``ValidationResult``.

    Parameters
    ----------
    result : ValidationResult
        The validation result to render.
    normalise : bool
        If ``True``, timestamps and paths are normalised for test comparisons.

    Returns
    -------
    str
        Pretty-printed JSON string with stable field order.
    """
    package_path = _normalise_path(result.package_path) if normalise else result.package_path
    timestamp = _normalise_timestamp("") if normalise else ""

    data: dict[str, object] = {
        "report_type": "planning_pipeline_validation",
        "timestamp": timestamp,
        "package_path": package_path,
        "verdict": result.verdict.value,
        "summary": {
            "total_checks": result.total_checks,
            "passed": result.passed,
            "warnings": result.warnings,
            "blocked": result.blocked,
        },
        "artifact_coverage": _build_coverage_matrix(result),
        "findings_grouped_by_severity": _group_by_severity(result.findings),
        "findings_grouped_by_reason_code": _group_by_reason_code(result.findings),
        "remediation_suggestions": _remediation_suggestions(result.findings),
        "note": "This report is generated by automated validation and does NOT imply operational approval. "
        "A PASS verdict indicates deterministic checks passed; human review is still required before any "
        "production-like execution.",
    }

    return json.dumps(data, indent=2, ensure_ascii=False)


# ─────────────────────────────────────────────────────────────────────────────
# Markdown report
# ─────────────────────────────────────────────────────────────────────────────


def render_markdown_report(result: ValidationResult, normalise: bool = False) -> str:
    """Render a deterministic Markdown report from a ``ValidationResult``.

    Parameters
    ----------
    result : ValidationResult
        The validation result to render.
    normalise : bool
        If ``True``, timestamps and paths are normalised for test comparisons.

    Returns
    -------
    str
        Markdown string with summary table, finding tables, coverage matrix,
        grouped findings, and remediation suggestions.
    """
    package_path = _normalise_path(result.package_path) if normalise else result.package_path
    verdict = result.verdict.value
    icon = {Verdict.PASS.value: "✅", Verdict.WARNING.value: "⚠️", Verdict.BLOCKED.value: "❌"}.get(
        verdict, "❓"
    )

    lines: list[str] = [
        "# Planning Pipeline Validation Report",
        "",
        f"**Package Path:** `{package_path}`",
        f"**Verdict:** {icon} **{verdict}**",
        "",
        "---",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total Checks | {result.total_checks} |",
        f"| Passed | {result.passed} |",
        f"| Warnings | {result.warnings} |",
        f"| Blocked | {result.blocked} |",
        "",
    ]

    # ── Artifact coverage matrix ──
    lines.extend([
        "---",
        "",
        "## Artifact Coverage Matrix",
        "",
        "| Artifact | Status |",
        "|----------|--------|",
    ])
    for row in _build_coverage_matrix(result):
        icon_row = "✅" if row["checked"] else "❌"
        lines.append(f"| {row['artifact']} | {icon_row} {row['status']} |")
    lines.append("")

    # ── Findings grouped by severity ──
    by_severity = _group_by_severity(result.findings)
    if by_severity:
        lines.extend([
            "---",
            "",
            "## Findings by Severity",
            "",
        ])
        for sev_name in ("BLOCKER", "MAJOR", "MINOR", "INFO"):
            sev_findings = by_severity.get(sev_name, [])
            if not sev_findings:
                continue
            icon_sev = {"BLOCKER": "🔴", "MAJOR": "🟠", "MINOR": "🟡", "INFO": "🔵"}.get(sev_name, "")
            lines.extend([
                f"### {icon_sev} {sev_name} ({len(sev_findings)})",
                "",
                "| Check ID | Reason Code | Verdict | Message |",
                "|----------|-------------|---------|---------|",
            ])
            for fd in sev_findings:
                lines.append(
                    f"| {fd['check_id']} | {fd['reason_code']} | {fd['verdict']} | {fd['message']} |"
                )
            lines.append("")

    # ── Findings grouped by reason code ──
    by_reason = _group_by_reason_code(result.findings)
    if by_reason:
        lines.extend([
            "---",
            "",
            "## Findings by Reason Code",
            "",
        ])
        for rc, rc_findings in by_reason.items():
            lines.extend([
                f"### `{rc}` ({len(rc_findings)})",
                "",
                "| Check ID | Severity | Verdict | Message |",
                "|----------|----------|---------|---------|",
            ])
            for fd in rc_findings:
                lines.append(
                    f"| {fd['check_id']} | {fd['severity']} | {fd['verdict']} | {fd['message']} |"
                )
            lines.append("")

    # ── Remediation summary ──
    suggestions = _remediation_suggestions(result.findings)
    if suggestions:
        lines.extend([
            "---",
            "",
            "## Remediation Summary",
            "",
            "| Reason Code | Remediation |",
            "|-------------|-------------|",
        ])
        for s in suggestions:
            lines.append(f"| `{s['reason_code']}` | {s['remediation']} |")
        lines.append("")

    # ── Findings table (flat, all findings) ──
    if result.findings:
        lines.extend([
            "---",
            "",
            "## All Findings",
            "",
            "| Check ID | Reason Code | Severity | Verdict | Message |",
            "|----------|-------------|----------|---------|---------|",
        ])
        for f in sorted(result.findings, key=lambda x: (x.reason_code.value, x.check_id)):
            lines.append(
                f"| {f.check_id} | {f.reason_code.value} | {f.severity.value} "
                f"| {f.verdict.value} | {f.message} |"
            )
        lines.append("")

    # ── Reference Summary ──
    lines.extend([
        "---",
        "",
        "## Reference Summary",
        "",
        "| Reference | Description |",
        "|-----------|-------------|",
        "| #135 | Controlled Rehearsal Planning Gate |",
        "| #136 | Rehearsal Stop Condition Matrix |",
        "| #137 | Rehearsal Evidence Bundle Plan |",
        "| #138 | Operator Rehearsal Approval Packet |",
        "| #139 | Read-Only Observation Plan |",
        "| #140 | Rehearsal Readiness Decision Record |",
        "| #122 | Human Approval Gate Checklist |",
        "| #124 | Live Readiness Blocker Inventory |",
        "| #129 | Runtime Preflight Checklist |",
        "| #131 | External Adapter Boundary Audit |",
        "| #144 | Rehearsal Proposal Package Schema |",
        "| #146 | Redaction Checker |",
        "| #150 | Planning Checker CLI |",
        "| #151 | Semantic Consistency Engine |",
        "| #152 | Validation Fixtures |",
        "| #153 | Status Report Renderer |",
        "| #154 | Golden Snapshot Suite |",
        "",
    ])

    # ── Disclaimer ──
    lines.extend([
        "---",
        "",
        "> **⚠️ Important:** This report is generated by automated validation and does **NOT** imply ",
        "> operational approval.  A PASS verdict means all deterministic checks passed.  Human review ",
        "> is still required before any production-like execution.  See the governance checklists for ",
        "> the full approval process.",
        "",
    ])

    return "\n".join(lines)
