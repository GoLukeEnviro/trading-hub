"""SI v2 planning automation — core typed models.

Typed finding, severity, status, stage, reason-code, and
validation-result dataclasses shared by the validator, checker CLI,
report renderers, and golden-snapshot suite.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

    JSONDict = Mapping[str, object]
else:
    JSONDict = dict

# ──────────────────────────────────────────────
# Enums
# ──────────────────────────────────────────────


@enum.unique
class Verdict(enum.StrEnum):
    """Final verdict for a validation subject."""

    PASS = "PASS"
    WARNING = "WARNING"
    BLOCKED = "BLOCKED"


@enum.unique
class Stage(enum.StrEnum):
    """Proposal package life-cycle stage."""

    DRAFT = "draft"
    FINAL = "final"


@enum.unique
class Severity(enum.StrEnum):
    """Severity of a single validation finding."""

    BLOCKER = "BLOCKER"
    MAJOR = "MAJOR"
    MINOR = "MINOR"
    INFO = "INFO"


@enum.unique
class ReasonCode(enum.StrEnum):
    """Machine-readable reason codes for validation findings."""

    # Schema
    SCHEMA_INVALID = "SCHEMA_INVALID"
    MISSING_REQUIRED_FIELD = "MISSING_REQUIRED_FIELD"
    FIELD_PATTERN_MISMATCH = "FIELD_PATTERN_MISMATCH"
    INVALID_ENUM_VALUE = "INVALID_ENUM_VALUE"

    # Artifact presence
    ARTIFACT_MISSING = "ARTIFACT_MISSING"
    ARTIFACT_EMPTY = "ARTIFACT_EMPTY"
    ARTIFACT_UNREADABLE = "ARTIFACT_UNREADABLE"

    # Cross-references
    REFERENCE_MISSING = "REFERENCE_MISSING"
    REFERENCE_STALE = "REFERENCE_STALE"
    REFERENCE_ORPHAN = "REFERENCE_ORPHAN"
    ID_DUPLICATE = "ID_DUPLICATE"
    ID_MISMATCH = "ID_MISMATCH"

    # Semantic consistency
    CONTRADICTORY_VERDICT = "CONTRADICTORY_VERDICT"
    MISSING_FINAL_APPROVAL = "MISSING_FINAL_APPROVAL"
    NON_PRODUCTION_NOT_CONFIRMED = "NON_PRODUCTION_NOT_CONFIRMED"
    NON_RUNTIME_NOT_CONFIRMED = "NON_RUNTIME_NOT_CONFIRMED"
    STOP_MATRIX_NOT_BLOCKED = "STOP_MATRIX_NOT_BLOCKED"
    HARD_BLOCKER_NOT_RED = "HARD_BLOCKER_NOT_RED"

    # Redaction / path safety
    UNSAFE_PATH = "UNSAFE_PATH"
    UNSAFE_CONTENT = "UNSAFE_CONTENT"
    MISSING_REDACTION = "MISSING_REDACTION"

    # Policy regression
    GOLDEN_MISMATCH = "GOLDEN_MISMATCH"
    UNEXPECTED_PASS = "UNEXPECTED_PASS"
    UNEXPECTED_FAIL = "UNEXPECTED_FAIL"

    # Internal
    INTERNAL_ERROR = "INTERNAL_ERROR"


# ──────────────────────────────────────────────
# Dataclasses
# ──────────────────────────────────────────────


@dataclass(frozen=True)
class Finding:
    """A single deterministic validation finding."""

    reason_code: ReasonCode
    severity: Severity
    verdict: Verdict
    message: str
    check_id: str = ""
    field_path: str = ""
    evidence: str = ""
    remediation: str = ""


@dataclass
class ValidationResult:
    """Aggregated result of running the planning pipeline."""

    package_path: str = ""
    total_checks: int = 0
    passed: int = 0
    warnings: int = 0
    blocked: int = 0
    findings: list[Finding] = field(default_factory=list)
    verdict: Verdict = Verdict.PASS

    def add(self, finding: Finding) -> None:
        """Record a finding and update counts."""
        self.findings.append(finding)
        self.total_checks += 1
        if finding.verdict == Verdict.PASS:
            self.passed += 1
        elif finding.verdict == Verdict.WARNING:
            self.warnings += 1
        elif finding.verdict == Verdict.BLOCKED:
            self.blocked += 1

    def finalize(self) -> Verdict:
        """Derive overall verdict from findings."""
        if any(f.verdict == Verdict.BLOCKED for f in self.findings):
            self.verdict = Verdict.BLOCKED
        elif any(f.verdict == Verdict.WARNING for f in self.findings):
            self.verdict = Verdict.WARNING
        else:
            self.verdict = Verdict.PASS
        return self.verdict

    def to_dict(self) -> dict[str, object]:
        """Serialize to JSON-safe dict (deterministic order)."""
        return {
            "package_path": self.package_path,
            "total_checks": self.total_checks,
            "passed": self.passed,
            "warnings": self.warnings,
            "blocked": self.blocked,
            "verdict": str(self.verdict),
            "findings": [
                {
                    "check_id": f.check_id,
                    "reason_code": str(f.reason_code),
                    "severity": str(f.severity),
                    "verdict": str(f.verdict),
                    "message": f.message,
                    "field_path": f.field_path,
                    "evidence": f.evidence,
                    "remediation": f.remediation,
                }
                for f in self.findings
            ],
        }


@dataclass
class PlanningPackage:
    """Loaded and parsed planning proposal package."""

    package_id: str
    stage: Stage
    proposal_name: str
    proposed_by: str
    rehearsal_mode: str
    artifact_paths: dict[str, str] = field(default_factory=dict)
    raw: dict[str, object] = field(default_factory=dict)
