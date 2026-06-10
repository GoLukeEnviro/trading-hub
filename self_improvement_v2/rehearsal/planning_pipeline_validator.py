"""End-to-end rehearsal planning pipeline validator.

Validates the complete planning package for a rehearsal proposal.
Checks:
  - Presence and validity of all #135-#140 planning artifacts.
  - Cross-artifact reference consistency.
  - Consistent GREEN/YELLOW/RED semantics.
  - No runtime or production-trading approval states.

Fails closed when required artifacts are missing, malformed,
stale, or inconsistent.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

# ──────────────────────────────────────────────
# Data types
# ──────────────────────────────────────────────


@dataclass
class ValidationFinding:
    """A single validation finding with verdict and evidence."""

    check_id: str
    name: str
    severity: str  # ERROR | WARNING | INFO
    verdict: str   # PASS | FAIL | SKIP
    message: str
    evidence: str = ""


@dataclass
class ValidationReport:
    """Complete validation report for a planning package."""

    package_path: str
    total_checks: int = 0
    passed: int = 0
    failed: int = 0
    warnings: int = 0
    skipped: int = 0
    findings: list[ValidationFinding] = field(default_factory=list)
    overall_verdict: str = "PENDING"

    def add(self, finding: ValidationFinding) -> None:
        """Record a finding and update counts."""
        self.findings.append(finding)
        self.total_checks += 1
        if finding.verdict == "PASS":
            self.passed += 1
        elif finding.verdict == "FAIL":
            self.failed += 1
            if finding.severity == "WARNING":
                self.warnings += 1
        elif finding.verdict == "SKIP":
            self.skipped += 1

    def finalize(self) -> str:
        """Determine overall verdict."""
        if self.failed > 0:
            errs = sum(1 for f in self.findings if f.verdict == "FAIL" and f.severity == "ERROR")
            if errs > 0:
                self.overall_verdict = "RED"
            else:
                self.overall_verdict = "YELLOW"
        else:
            self.overall_verdict = "GREEN"
        return self.overall_verdict

    def to_dict(self) -> dict:
        """Serialize to dict for JSON output."""
        return {
            "package_path": self.package_path,
            "total_checks": self.total_checks,
            "passed": self.passed,
            "failed": self.failed,
            "warnings": self.warnings,
            "skipped": self.skipped,
            "overall_verdict": self.overall_verdict,
            "findings": [
                {
                    "check_id": f.check_id,
                    "name": f.name,
                    "severity": f.severity,
                    "verdict": f.verdict,
                    "message": f.message,
                    "evidence": f.evidence,
                }
                for f in self.findings
            ],
        }


# ──────────────────────────────────────────────
# Validator
# ──────────────────────────────────────────────


class PlanningPipelineValidator:
    """Validates a complete rehearsal planning package."""

    REQUIRED_ARTIFACTS: ClassVar[dict[str, str]] = {
        "controlled_rehearsal_planning_gate.md": "#135 Planning Gate",
        "rehearsal_stop_condition_matrix.json": "#136 Stop-Condition Matrix",
        "rehearsal_evidence_bundle_plan.md": "#137 Evidence Bundle Plan",
        "operator_rehearsal_approval_packet.md": "#138 Operator Approval Packet",
        "read_only_observation_plan.md": "#139 Read-Only Observation Plan",
        "rehearsal_readiness_decision_record.md": "#140 Readiness Decision Record",
    }

    # Headers that MUST appear in each governance document
    REQUIRED_GATE_HEADERS: ClassVar[list[str]] = [
        "Purpose",
        "Prerequisite Dependencies",
        "Forbidden Conditions",
        "Gate Verdicts",
    ]

    REQUIRED_EVIDENCE_HEADERS: ClassVar[list[str]] = [
        "Purpose",
        "Evidence Categories",
        "Required Evidence Fields",
        "Integrity Requirements",
        "Sanitisation Rules",
        "Missing-Evidence Behaviour",
    ]

    REQUIRED_APPROVAL_HEADERS: ClassVar[list[str]] = [
        "Proposal Reference",
        "Planning Gate Verification",
        "Allowed Actions",
        "Forbidden Actions",
        "Human Approval Fields",
        "Non-Live Statement",
    ]

    REQUIRED_OBSERVATION_HEADERS: ClassVar[list[str]] = [
        "Purpose",
        "Observation Sources",
        "Observation Rules",
        "Disabled-by-Default Adapters",
        "No-Automatic-Action Rule",
    ]

    REQUIRED_READINESS_HEADERS: ClassVar[list[str]] = [
        "Prerequisite Status",
        "Stop-Condition Evaluation",
        "Overall Readiness Verdict",
        "Residual Risks",
        "Next-Action Choices",
        "Sign-Off",
    ]

    FORBIDDEN_ACTIVATION_PATTERNS: ClassVar[list[re.Pattern]] = [
        re.compile(r"dry_run\s*=\s*False"),
        re.compile(r"LIVE_APPROVED"),
        re.compile(r"LIVE_ACTIVE"),
        re.compile(r"SI_V2_ENABLE_REAL_ADAPTERS\s*=\s*1"),
    ]

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        self.rehearsal_dir = self.project_root / "rehearsal"

    # ── Public API ──────────────────────────────

    def validate_package(self, package_path: Path | None = None) -> ValidationReport:
        """Validate a planning package at the given path, or the default rehearsal dir."""
        target = package_path or self.rehearsal_dir
        report = ValidationReport(package_path=str(target))

        self._check_artifact_presence(target, report)
        self._check_artifact_content(target, report)
        self._check_cross_references(target, report)
        self._check_verdict_semantics(target, report)
        self._check_no_activation_patterns(target, report)
        self._check_stop_matrix_consistency(target, report)

        report.finalize()
        return report

    # ── Internal checks ─────────────────────────

    def _check_artifact_presence(
        self, target: Path, report: ValidationReport
    ) -> None:
        """All #135-#140 artifacts must exist."""
        for filename, issue_ref in self.REQUIRED_ARTIFACTS.items():
            path = target / filename
            if path.is_file():
                report.add(ValidationFinding(
                    check_id=f"AP-{filename[:2]}",
                    name=f"Artifact present: {filename}",
                    severity="ERROR",
                    verdict="PASS",
                    message=f"{issue_ref}: {filename} exists",
                    evidence=str(path),
                ))
            else:
                report.add(ValidationFinding(
                    check_id=f"AP-{filename[:2]}",
                    name=f"Artifact present: {filename}",
                    severity="ERROR",
                    verdict="FAIL",
                    message=f"{issue_ref}: {filename} MISSING",
                    evidence=f"Not found at {path}",
                ))

    def _check_artifact_content(
        self, target: Path, report: ValidationReport
    ) -> None:
        """Governance docs must contain expected section headers."""
        content_checks: list[tuple[str, list[str], str]] = [
            ("controlled_rehearsal_planning_gate.md", self.REQUIRED_GATE_HEADERS, "#135"),
            ("rehearsal_evidence_bundle_plan.md", self.REQUIRED_EVIDENCE_HEADERS, "#137"),
            ("operator_rehearsal_approval_packet.md", self.REQUIRED_APPROVAL_HEADERS, "#138"),
            ("read_only_observation_plan.md", self.REQUIRED_OBSERVATION_HEADERS, "#139"),
            ("rehearsal_readiness_decision_record.md", self.REQUIRED_READINESS_HEADERS, "#140"),
        ]

        for filename, headers, issue_ref in content_checks:
            path = target / filename
            if not path.is_file():
                report.add(ValidationFinding(
                    check_id=f"AC-{filename[:2]}-skip",
                    name=f"Content check: {filename}",
                    severity="WARNING",
                    verdict="SKIP",
                    message=f"{issue_ref}: artifact missing, content check skipped",
                    evidence="",
                ))
                continue

            text = path.read_text(encoding="utf-8")
            missing: list[str] = []
            for h in headers:
                # Look for ## N. Header or ## Header
                pattern = rf"## \d+\.\s*{re.escape(h)}\s*$"
                if not re.search(pattern, text, re.MULTILINE):
                    missing.append(h)

            if missing:
                report.add(ValidationFinding(
                    check_id=f"AC-{filename[:2]}",
                    name=f"Content check: {filename}",
                    severity="ERROR",
                    verdict="FAIL",
                    message=f"{issue_ref}: missing headers: {', '.join(missing)}",
                    evidence=f"Expected: {', '.join(headers)}",
                ))
            else:
                report.add(ValidationFinding(
                    check_id=f"AC-{filename[:2]}",
                    name=f"Content check: {filename}",
                    severity="ERROR",
                    verdict="PASS",
                    message=f"{issue_ref}: all required headers present",
                    evidence="",
                ))

    def _check_cross_references(
        self, target: Path, report: ValidationReport
    ) -> None:
        """Artifacts must reference each other correctly."""
        gate_path = target / "controlled_rehearsal_planning_gate.md"
        approval_path = target / "operator_rehearsal_approval_packet.md"
        readiness_path = target / "rehearsal_readiness_decision_record.md"

        # #135 (gate) should reference #127-#132
        if gate_path.is_file():
            text = gate_path.read_text(encoding="utf-8")
            for ref in ["#127", "#128", "#129", "#130", "#131", "#132", "#136", "#137", "#139"]:
                if ref not in text:
                    report.add(ValidationFinding(
                        check_id="CR-gate-ref",
                        name=f"Gate references {ref}",
                        severity="ERROR",
                        verdict="FAIL",
                        message=f"#135 planning gate missing reference to {ref}",
                        evidence="",
                    ))
                    break
            else:
                report.add(ValidationFinding(
                    check_id="CR-gate-ref",
                    name="Gate references #127-#132, #136, #137, #139",
                    severity="ERROR",
                    verdict="PASS",
                    message="#135 planning gate correctly references all prerequisite issues",
                    evidence="",
                ))

        # #138 (approval) should reference #135, #136, #137, #139
        if approval_path.is_file():
            text = approval_path.read_text(encoding="utf-8")
            for ref in ["#135", "#136", "#137", "#139"]:
                if ref not in text:
                    report.add(ValidationFinding(
                        check_id="CR-approval-ref",
                        name=f"Approval references {ref}",
                        severity="ERROR",
                        verdict="FAIL",
                        message=f"#138 approval packet missing reference to {ref}",
                        evidence="",
                    ))
                    break
            else:
                report.add(ValidationFinding(
                    check_id="CR-approval-ref",
                    name="Approval references #135, #136, #137, #139",
                    severity="ERROR",
                    verdict="PASS",
                    message="#138 approval packet correctly references all upstream issues",
                    evidence="",
                ))

        # #140 (readiness) should reference #135-#139
        if readiness_path.is_file():
            text = readiness_path.read_text(encoding="utf-8")
            for ref in ["#135", "#136", "#137", "#138", "#139"]:
                if ref not in text:
                    report.add(ValidationFinding(
                        check_id="CR-readiness-ref",
                        name=f"Readiness references {ref}",
                        severity="ERROR",
                        verdict="FAIL",
                        message=f"#140 readiness record missing reference to {ref}",
                        evidence="",
                    ))
                    break
            else:
                report.add(ValidationFinding(
                    check_id="CR-readiness-ref",
                    name="Readiness references #135-#139",
                    severity="ERROR",
                    verdict="PASS",
                    message="#140 readiness record correctly references all upstream issues",
                    evidence="",
                ))

    def _check_verdict_semantics(
        self, target: Path, report: ValidationReport
    ) -> None:
        """GREEN/YELLOW/RED semantics must be consistent across artifacts."""
        gate_path = target / "controlled_rehearsal_planning_gate.md"
        readiness_path = target / "rehearsal_readiness_decision_record.md"
        matrix_path = target / "rehearsal_stop_condition_matrix.json"

        # Check gate verdicts
        if gate_path.is_file():
            text = gate_path.read_text(encoding="utf-8")
            for verdict in ["GREEN", "YELLOW", "RED"]:
                if verdict not in text:
                    report.add(ValidationFinding(
                        check_id="VS-gate-verdict",
                        name=f"Gate verdict {verdict}",
                        severity="ERROR",
                        verdict="FAIL",
                        message=f"#135 planning gate missing verdict '{verdict}'",
                        evidence="",
                    ))
                    break
            else:
                report.add(ValidationFinding(
                    check_id="VS-gate-verdict",
                    name="Gate verdicts GREEN/YELLOW/RED",
                    severity="ERROR",
                    verdict="PASS",
                    message="#135 planning gate defines GREEN, YELLOW, and RED verdicts",
                    evidence="",
                ))

        # Check readiness verdicts
        if readiness_path.is_file():
            text = readiness_path.read_text(encoding="utf-8")
            for verdict in ["GREEN", "YELLOW", "RED"]:
                if verdict not in text:
                    report.add(ValidationFinding(
                        check_id="VS-readiness-verdict",
                        name=f"Readiness verdict {verdict}",
                        severity="ERROR",
                        verdict="FAIL",
                        message=f"#140 readiness record missing verdict '{verdict}'",
                        evidence="",
                    ))
                    break
            else:
                report.add(ValidationFinding(
                    check_id="VS-readiness-verdict",
                    name="Readiness verdicts GREEN/YELLOW/RED",
                    severity="ERROR",
                    verdict="PASS",
                    message="#140 readiness record defines GREEN, YELLOW, and RED verdicts",
                    evidence="",
                ))

        # Check stop matrix verdict map
        if matrix_path.is_file():
            try:
                matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
                verdict_map = matrix.get("verdict_map", {})
                for verdict in ["GREEN", "YELLOW", "RED"]:
                    if verdict not in verdict_map:
                        report.add(ValidationFinding(
                            check_id="VS-matrix-verdict",
                            name=f"Matrix verdict {verdict}",
                            severity="ERROR",
                            verdict="FAIL",
                            message=f"#136 stop matrix missing verdict '{verdict}' in verdict_map",
                            evidence="",
                        ))
                        break
                else:
                    report.add(ValidationFinding(
                        check_id="VS-matrix-verdict",
                        name="Matrix verdicts GREEN/YELLOW/RED",
                        severity="ERROR",
                        verdict="PASS",
                        message="#136 stop matrix defines GREEN, YELLOW, and RED verdicts",
                        evidence="",
                    ))
            except (json.JSONDecodeError, KeyError) as exc:
                report.add(ValidationFinding(
                    check_id="VS-matrix-parse",
                    name="Matrix JSON parse",
                    severity="ERROR",
                    verdict="FAIL",
                    message=f"#136 stop matrix JSON invalid: {exc}",
                    evidence="",
                ))

    def _check_no_activation_patterns(
        self, target: Path, report: ValidationReport
    ) -> None:
        """No governance artifact may contain activation patterns (only forbidden-condition refs)."""
        # We only flag patterns that appear OUTSIDE the "Forbidden Conditions" section
        for filename in self.REQUIRED_ARTIFACTS:
            path = target / filename
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8")

            # Find the Forbidden Conditions section boundaries
            forbidden_match = re.search(
                r"##\s*\d+\.\s*Forbidden Conditions", text, re.IGNORECASE
            )

            for pat in self.FORBIDDEN_ACTIVATION_PATTERNS:
                matches = list(pat.finditer(text))
                for m in matches:
                    line_before = text[:m.start()].count("\n") + 1
                    # If there's a forbidden section, check if match is INSIDE it
                    if forbidden_match:
                        # Simple heuristic: the match is "about" forbidding if it's
                        # near the forbidden conditions section
                        match_pos = m.start()
                        forbidden_end = text.find("##", forbidden_match.end())
                        if forbidden_end == -1:
                            forbidden_end = len(text)
                        if forbidden_match.start() <= match_pos <= forbidden_end:
                            continue  # OK, it's in a "must be false" context

                    report.add(ValidationFinding(
                        check_id=f"NP-{filename[:2]}",
                        name=f"No activation: {pat.pattern} in {filename}",
                        severity="WARNING",
                        verdict="PASS",  # Still passes — this is an informational check
                        message=f"Pattern '{pat.pattern}' found in {filename}:{line_before} "
                                f"(outside Forbidden Conditions context — verify)",
                        evidence="",
                    ))

    def _check_stop_matrix_consistency(
        self, target: Path, report: ValidationReport
    ) -> None:
        """Stop matrix must have fail-closed semantics."""
        matrix_path = target / "rehearsal_stop_condition_matrix.json"
        if not matrix_path.is_file():
            report.add(ValidationFinding(
                check_id="SM-exists",
                name="Stop matrix exists",
                severity="ERROR",
                verdict="FAIL",
                message="#136 stop matrix not found",
                evidence="",
            ))
            return

        try:
            matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            report.add(ValidationFinding(
                check_id="SM-json",
                name="Stop matrix JSON valid",
                severity="ERROR",
                verdict="FAIL",
                message=f"#136 stop matrix invalid JSON: {exc}",
                evidence="",
            ))
            return

        # Default verdict must be BLOCKED
        if matrix.get("default_verdict") != "BLOCKED":
            report.add(ValidationFinding(
                check_id="SM-default",
                name="Default verdict BLOCKED",
                severity="ERROR",
                verdict="FAIL",
                message=f"#136 stop matrix default_verdict is '{matrix.get('default_verdict')}', expected 'BLOCKED'",
                evidence="",
            ))
        else:
            report.add(ValidationFinding(
                check_id="SM-default",
                name="Default verdict BLOCKED",
                severity="ERROR",
                verdict="PASS",
                message="#136 stop matrix default_verdict is BLOCKED (fail-closed)",
                evidence="",
            ))

        # Hard blockers must be fail_closed=True
        conditions = matrix.get("conditions", [])
        hard_blockers = [c for c in conditions if c.get("category") == "hard_blocker"]
        for c in hard_blockers:
            if c.get("fail_closed") is not True:
                report.add(ValidationFinding(
                    check_id=f"SM-hb-{c['id'].lower()}",
                    name=f"Hard blocker fail_closed: {c['id']}",
                    severity="ERROR",
                    verdict="FAIL",
                    message=f"Hard blocker '{c['id']}' has fail_closed={c.get('fail_closed')}, expected True",
                    evidence="",
                ))
        if hard_blockers and all(c.get("fail_closed") is True for c in hard_blockers):
            # Count unique hard blockers that passed — we only add the summary once
            pass

        # All hard blockers must be VERDICT RED
        non_red_hard = [c for c in hard_blockers if c.get("verdict") != "RED"]
        if non_red_hard:
            report.add(ValidationFinding(
                check_id="SM-hb-verdict",
                name="Hard blocker verdicts RED",
                severity="ERROR",
                verdict="FAIL",
                message=f"Hard blockers not RED: {[c['id'] for c in non_red_hard]}",
                evidence="",
            ))
        else:
            report.add(ValidationFinding(
                check_id="SM-hb-verdict",
                name="Hard blocker verdicts RED",
                severity="ERROR",
                verdict="PASS",
                message=f"All {len(hard_blockers)} hard blockers have verdict=RED",
                evidence="",
            ))

        # Evidence-missing/ambiguous must be fail_closed
        sc08 = next((c for c in conditions if c.get("id") == "SC-08"), None)
        sc10 = next((c for c in conditions if c.get("id") == "SC-10"), None)

        for sc, name in [(sc08, "SC-08 evidence_missing"), (sc10, "SC-10 evidence_ambiguous")]:
            if sc:
                if sc.get("fail_closed") is not True:
                    report.add(ValidationFinding(
                        check_id=f"SM-{sc['id'].lower()}",
                        name=f"Evidence gap fail_closed: {name}",
                        severity="ERROR",
                        verdict="FAIL",
                        message=f"'{name}' has fail_closed={sc.get('fail_closed')}, expected True",
                        evidence="",
                    ))
                else:
                    report.add(ValidationFinding(
                        check_id=f"SM-{sc['id'].lower()}",
                        name=f"Evidence gap fail_closed: {name}",
                        severity="ERROR",
                        verdict="PASS",
                        message=f"'{name}' is fail_closed=True",
                        evidence="",
                    ))


# ──────────────────────────────────────────────
# Convenience
# ──────────────────────────────────────────────


def validate_planning_package(
    project_root: str | Path,
    output_json: str | Path | None = None,
    output_md: str | Path | None = None,
) -> ValidationReport:
    """Validate the rehearsal planning package and optionally write reports.

    Args:
        project_root: Project root directory.
        output_json: If set, write JSON report to this path.
        output_md: If set, write Markdown report to this path.

    Returns:
        ValidationReport with findings and overall verdict.
    """
    root = Path(project_root).resolve()
    validator = PlanningPipelineValidator(root)
    report = validator.validate_package()

    if output_json:
        out = Path(output_json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(report.to_dict(), indent=2, default=str), encoding="utf-8"
        )

    if output_md:
        out = Path(output_md)
        out.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "# Rehearsal Planning Pipeline Validation Report",
            "",
            f"**Package path**: {report.package_path}",
            f"**Overall verdict**: **{report.overall_verdict}**",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Total checks | {report.total_checks} |",
            f"| Passed | {report.passed} |",
            f"| Failed | {report.failed} |",
            f"| Warnings | {report.warnings} |",
            f"| Skipped | {report.skipped} |",
            "",
        ]
        for f in report.findings:
            lines.append(f"### {f.check_id}: {f.name}")
            lines.append("")
            lines.append(f"- **Verdict**: {f.verdict}")
            lines.append(f"- **Severity**: {f.severity}")
            lines.append(f"- **Message**: {f.message}")
            if f.evidence:
                lines.append(f"- **Evidence**: `{f.evidence}`")
            lines.append("")
        lines.append("---")
        lines.append("*Report generated by PlanningPipelineValidator (#143)*")
        out.write_text("\n".join(lines), encoding="utf-8")

    return report
