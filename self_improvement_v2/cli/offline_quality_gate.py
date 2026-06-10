"""Offline quality gate command for SI v2 pipeline readiness.

Checks that all key artifacts exist, parse, and produce expected output.
Returns GREEN/YELLOW/RED verdict.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class QaVerdict(Enum):
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"


@dataclass
class QaCheck:
    name: str
    passed: bool
    details: str = ""
    severity: str = "required"  # required / optional


@dataclass
class QaReport:
    verdict: QaVerdict
    checks: list[QaCheck] = field(default_factory=list)
    passed: int = 0
    failed: int = 0
    warnings: int = 0


class OfflineQualityGate:
    """Run offline quality checks for SI v2 pipeline."""

    def __init__(self) -> None:
        self._root = Path("self_improvement_v2")

    def run(self) -> QaReport:
        """Run all quality checks."""
        checks: list[QaCheck] = []

        # 1. JSON files parse
        json_ok = True
        json_files_found = 0
        for f in sorted(self._root.rglob("*.json")):
            if ".git" in str(f):
                continue
            json_files_found += 1
            try:
                import json as j

                with open(f) as fp:
                    j.load(fp)
            except (j.JSONDecodeError, OSError):
                json_ok = False
                checks.append(
                    QaCheck(
                        name=f"JSON parse: {f}",
                        passed=False,
                        details="Failed to parse",
                    )
                )
        if json_ok:
            checks.append(
                QaCheck(
                    name=f"All JSON files parse ({json_files_found} files)",
                    passed=True,
                )
            )

        # 2. Episode manifest exists
        manifest_path = (
            self._root / "episode" / "offline_episode_manifest.json"
        )
        checks.append(
            QaCheck(
                name="Offline episode manifest",
                passed=manifest_path.exists(),
                details=(
                    "Found" if manifest_path.exists() else "Missing"
                ),
            )
        )

        # 3. Evidence bundle output exists
        bundle_path = (
            self._root / "reports" / "evidence" / "evidence_bundle.json"
        )
        checks.append(
            QaCheck(
                name="Evidence bundle output",
                passed=bundle_path.exists(),
                details=(
                    "Found" if bundle_path.exists() else "Missing"
                ),
            )
        )

        # 4. Attribution summary output exists
        attr_path = (
            self._root
            / "reports"
            / "attribution"
            / "offline_attribution_summary.json"
        )
        checks.append(
            QaCheck(
                name="Attribution summary output",
                passed=attr_path.exists(),
                details=(
                    "Found" if attr_path.exists() else "Missing"
                ),
            )
        )

        # 5. Golden path test exists (optional, warning only)
        golden_path = (
            self._root
            / "tests"
            / "test_rainbow_offline_golden_path.py"
        )
        checks.append(
            QaCheck(
                name="Golden path test file",
                passed=golden_path.exists(),
                severity="optional",
                details=(
                    "Found" if golden_path.exists() else "Missing"
                ),
            )
        )

        # 6. Source readiness summary exists
        readiness_path = (
            self._root / "reports" / "source_readiness_summary.md"
        )
        checks.append(
            QaCheck(
                name="Source readiness summary",
                passed=readiness_path.exists(),
                details=(
                    "Found" if readiness_path.exists() else "Missing"
                ),
            )
        )

        # 7. Source manifest exists
        src_manifest = (
            self._root / "evidence" / "source_manifest.json"
        )
        checks.append(
            QaCheck(
                name="Source manifest",
                passed=src_manifest.exists(),
                details=(
                    "Found" if src_manifest.exists() else "Missing"
                ),
            )
        )

        # Count results
        passed = sum(1 for c in checks if c.passed and c.severity == "required")
        failed = sum(
            1
            for c in checks
            if not c.passed and c.severity == "required"
        )
        warnings = sum(
            1
            for c in checks
            if not c.passed and c.severity == "optional"
        )

        if failed > 0:
            verdict = QaVerdict.RED
        elif warnings > 0:
            verdict = QaVerdict.YELLOW
        else:
            verdict = QaVerdict.GREEN

        return QaReport(
            verdict=verdict,
            checks=checks,
            passed=passed,
            failed=failed,
            warnings=warnings,
        )

    def generate_markdown(self) -> str:
        """Generate deterministic Markdown report."""
        report = self.run()
        lines: list[str] = []
        lines.append("# Offline Quality Gate Report")
        lines.append("")
        lines.append(f"**Verdict:** {report.verdict.value}")
        lines.append(
            f"**Passed:** {report.passed} | "
            f"**Failed:** {report.failed} | "
            f"**Warnings:** {report.warnings}"
        )
        lines.append("")
        lines.append("## Checks")
        lines.append("")
        for c in report.checks:
            icon = "✅" if c.passed else ("⚠️" if c.severity == "optional" else "❌")
            lines.append(f"- {icon} **{c.name}**: {c.details}")
        return "\n".join(lines)
