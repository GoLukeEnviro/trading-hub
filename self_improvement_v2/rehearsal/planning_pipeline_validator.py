"""End-to-end planning pipeline validator (#143).

Validates a complete rehearsal planning package by:

1. Checking that ALL #135-#140 artifacts exist on disk.
2. Checking that ALL required sections/headers exist in each governance doc.
3. Checking that the #144 proposal-package schema is valid JSON.
4. Running the #151 semantic consistency engine.
5. Running the #146 redaction checker.
6. Deriving a PASS / WARNING / BLOCKED verdict.

Usage::

    from rehearsal.planning_pipeline_validator import validate_planning_package

    result = validate_planning_package(
        project_root="/path/to/self_improvement_v2",
        output_json="/path/to/report.json",   # optional
        output_md="/path/to/report.md",        # optional
    )
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from rehearsal.planning_models import (
    Finding,
    ReasonCode,
    Severity,
    ValidationResult,
    Verdict,
)
from rehearsal.redaction_checker import RedactionChecker
from rehearsal.semantic_consistency import run_semantic_consistency

# ---------------------------------------------------------------------------
# Constants — artifact file names (issues #135-#140)
# ---------------------------------------------------------------------------

REQUIRED_ARTIFACTS: dict[str, str] = {
    "#135": "controlled_rehearsal_planning_gate.md",
    "#136": "rehearsal_stop_condition_matrix.json",
    "#137": "rehearsal_evidence_bundle_plan.md",
    "#138": "operator_rehearsal_approval_packet.md",
    "#139": "read_only_observation_plan.md",
    "#140": "rehearsal_readiness_decision_record.md",
}

# Governance docs that must also exist
GOVERNANCE_ARTIFACTS: dict[str, str] = {
    "#122": "human_approval_gate_checklist.md",
    "#124": "live_readiness_blocker_inventory.md",
    "#129": "runtime_preflight_checklist.md",
    "#131": "external_adapter_boundary_audit.json",
}

# Required section headings in each governance document
# Each entry is a (file_name, list of required heading fragments)
REQUIRED_SECTIONS: dict[str, list[str]] = {
    "controlled_rehearsal_planning_gate.md": [
        "Purpose",
        "Prerequisite Dependencies",
        "Required Planning Fields",
        "Forbidden Conditions",
        "Gate Verdicts",
        "Escalation",
        "Change Log",
    ],
    "rehearsal_stop_condition_matrix.json": [
        # JSON — structural checks are schema-based; we just check it exists
    ],
    "rehearsal_evidence_bundle_plan.md": [
        "Purpose",
        "Evidence Categories",
        "Required Evidence Fields",
        "Integrity Requirements",
        "Sanitisation Rules",
        "Change Log",
    ],
    "operator_rehearsal_approval_packet.md": [
        "Proposal Reference",
        "Planning Gate Verification",
        "Allowed Actions",
        "Forbidden Actions",
        "Human Approval Fields",
        "Change Log",
    ],
    "read_only_observation_plan.md": [
        "Purpose",
        "Observation Sources",
        "Observation Rules",
        "Reporting",
        "Change Log",
    ],
    "rehearsal_readiness_decision_record.md": [
        "Proposal Reference",
        "Prerequisite Status",
        "Stop-Condition Evaluation",
        "Overall Readiness Verdict",
        "Residual Risks",
        "Change Log",
    ],
}

# Schema file
SCHEMA_FILE = "rehearsal_proposal_package.schema.json"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_paths(project_root: Path) -> dict[str, Path]:
    """Return a ``{issue: Path}`` mapping for all required artifacts."""
    rehearsal_dir = project_root / "rehearsal"
    governance_dir = project_root / "governance"

    paths: dict[str, Path] = {}
    for issue, filename in REQUIRED_ARTIFACTS.items():
        paths[issue] = rehearsal_dir / filename

    for issue, filename in GOVERNANCE_ARTIFACTS.items():
        paths[issue] = governance_dir / filename

    # Schema
    paths["#144"] = rehearsal_dir / SCHEMA_FILE

    return paths


def _read_text(path: Path) -> str | None:
    """Read a text file, returning ``None`` on failure."""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _section_matches(text: str, required: list[str]) -> dict[str, bool]:
    """Check which required section headings exist in *text*."""
    results: dict[str, bool] = {}
    for section in required:
        # Match "## N. SectionName" or "## SectionName"
        pattern = re.compile(
            r"^##\s+\d*\.?\s*" + re.escape(section) + r"\s*$",
            re.MULTILINE | re.IGNORECASE,
        )
        results[section] = bool(pattern.search(text))
    return results


# ---------------------------------------------------------------------------
# Main validation
# ---------------------------------------------------------------------------


def validate_planning_package(
    project_root: str | Path,
    output_json: str | Path | None = None,
    output_md: str | Path | None = None,
) -> ValidationResult:
    """Run the full planning pipeline validation.

    Parameters
    ----------
    project_root : str or Path
        Path to the ``self_improvement_v2`` project root.
    output_json : str or Path, optional
        If given, write a JSON report to this path.
    output_md : str or Path, optional
        If given, write a Markdown report to this path.

    Returns
    -------
    ValidationResult
        Aggregated validation result with all findings.
    """
    root = Path(project_root).resolve()
    result = ValidationResult(package_path=str(root))

    artifact_paths = _build_paths(root)
    rehearsal_dir = root / "rehearsal"

    # ------------------------------------------------------------------
    # 1. Check ALL #135-#140 artifacts exist
    # ------------------------------------------------------------------
    existing_paths_list: list[str] = []
    for issue, path in sorted(artifact_paths.items()):
        if issue.startswith("#") and not issue.startswith("#1"):
            # Only check #135-#140 and governance artifacts
            pass
        if path.exists():
            existing_paths_list.append(str(path))
        else:
            severity = Severity.BLOCKER if issue in REQUIRED_ARTIFACTS else Severity.MAJOR
            result.add(
                Finding(
                    reason_code=ReasonCode.ARTIFACT_MISSING,
                    severity=severity,
                    verdict=Verdict.BLOCKED if severity == Severity.BLOCKER else Verdict.WARNING,
                    message=f"Required artifact {issue} missing: {path.name}",
                    check_id="PP-EXISTS-001",
                    field_path=f"artifacts/{issue}",
                    evidence=f"Expected file at {path} does not exist",
                    remediation=f"Create or restore the file {path.name} for {issue}",
                )
            )

    # ------------------------------------------------------------------
    # 2. Check required sections / headers in each governance doc
    # ------------------------------------------------------------------
    for filename, required in REQUIRED_SECTIONS.items():
        if not required:
            continue
        file_path = rehearsal_dir / filename
        text = _read_text(file_path)
        if text is None:
            result.add(
                Finding(
                    reason_code=ReasonCode.ARTIFACT_UNREADABLE,
                    severity=Severity.MAJOR,
                    verdict=Verdict.WARNING,
                    message=f"Cannot read {filename} for section check",
                    check_id="PP-SECT-001",
                    field_path=f"artifacts/{filename}",
                    evidence=f"File {file_path} is unreadable or missing",
                    remediation="Ensure the file exists and is readable UTF-8 text",
                )
            )
            continue

        section_results = _section_matches(text, required)
        for section_name, found in section_results.items():
            if not found:
                result.add(
                    Finding(
                        reason_code=ReasonCode.MISSING_REQUIRED_FIELD,
                        severity=Severity.MAJOR,
                        verdict=Verdict.WARNING,
                        message=f"Missing required section '{section_name}' in {filename}",
                        check_id="PP-SECT-002",
                        field_path=f"artifacts/{filename}/sections",
                        evidence=f"Section '## {section_name}' not found in {filename}",
                        remediation=(
                            f"Add a '## {section_name}' heading to {filename}"
                        ),
                    )
                )

    # ------------------------------------------------------------------
    # 3. Check #144 schema is valid JSON
    # ------------------------------------------------------------------
    schema_path = rehearsal_dir / SCHEMA_FILE
    if schema_path.exists():
        schema_text = _read_text(schema_path)
        if schema_text is not None:
            try:
                json.loads(schema_text)
            except json.JSONDecodeError as exc:
                result.add(
                    Finding(
                        reason_code=ReasonCode.SCHEMA_INVALID,
                        severity=Severity.BLOCKER,
                        verdict=Verdict.BLOCKED,
                        message=f"Schema {SCHEMA_FILE} is not valid JSON: {exc}",
                        check_id="PP-SCHEMA-001",
                        field_path=f"artifacts/{SCHEMA_FILE}",
                        evidence=str(exc),
                        remediation="Fix the JSON syntax in the schema file",
                    )
                )

    # ------------------------------------------------------------------
    # 4. Run redaction checker (#146) on all artifacts
    # ------------------------------------------------------------------
    checker = RedactionChecker()
    for filename in list(REQUIRED_ARTIFACTS.values()) + list(GOVERNANCE_ARTIFACTS.values()):
        file_path = rehearsal_dir / filename
        if not file_path.exists():
            file_path = root / "governance" / filename
        if not file_path.exists():
            continue
        text = _read_text(file_path)
        if text is None:
            continue
        redact_findings = checker.check_artifact(text)
        for f in redact_findings:
            result.add(f)

    # ------------------------------------------------------------------
    # 5. Run semantic consistency (#151) on existing artifacts
    # ------------------------------------------------------------------
    if existing_paths_list:
        result = run_semantic_consistency(result, existing_paths_list)

    # ------------------------------------------------------------------
    # 6. Derive final verdict
    # ------------------------------------------------------------------
    result.finalize()

    # ------------------------------------------------------------------
    # 7. Write output files if requested
    # ------------------------------------------------------------------
    if output_json is not None:
        _write_json_report(result, Path(output_json))
    if output_md is not None:
        _write_md_report(result, Path(output_md))

    return result


# ---------------------------------------------------------------------------
# Report writers
# ---------------------------------------------------------------------------


def _write_json_report(result: ValidationResult, path: Path) -> None:
    """Write a JSON report to *path*."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(result.to_dict(), indent=2, sort_keys=False),
        encoding="utf-8",
    )


def _write_md_report(result: ValidationResult, path: Path) -> None:
    """Write a human-readable Markdown report to *path*."""
    verdict_icon = {
        Verdict.PASS: "✅",
        Verdict.WARNING: "⚠️",
        Verdict.BLOCKED: "❌",
    }.get(result.verdict, "❓")

    lines: list[str] = [
        "# Planning Pipeline Validation Report",
        "",
        f"**Package Path:** `{result.package_path}`",
        f"**Verdict:** {verdict_icon} **{result.verdict.value}**",
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

    if result.findings:
        lines.extend([
            "## Findings",
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

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
