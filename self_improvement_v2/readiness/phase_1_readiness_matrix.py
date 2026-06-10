"""Phase 1 Readiness Matrix.

Lists required Phase 1 artifacts with dependency status and
GREEN/YELLOW/RED readiness summary.

Missing optional artifacts produce YELLOW.
Live-readiness remains out of scope.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class ReadinessVerdict(Enum):
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"


@dataclass
class ArtifactEntry:
    group: str
    name: str
    path: str
    found: bool
    severity: str = "required"  # required / optional


@dataclass
class ReadinessMatrix:
    verdict: ReadinessVerdict
    artifacts: list[ArtifactEntry] = field(default_factory=list)
    required_found: int = 0
    required_total: int = 0
    optional_found: int = 0
    optional_total: int = 0


_REQUIRED_ARTIFACT_GROUPS: list[dict[str, object]] = [
    {
        "group": "Rainbow complete subsystem",
        "artifacts": [
            ("Validator", "src/si_v2/rainbow/validator.py"),
            ("Contract snapshot", "contracts/rainbow_signal_envelope.schema.json"),
            ("Drift guard", "src/si_v2/rainbow/drift_guard.py"),
            ("Fixture review report", "reports/rainbow/fixture_review_report.md"),
            ("Source status", "src/si_v2/rainbow/status.py"),
            ("Read-only client", "src/si_v2/rainbow/client.py"),
            ("Shadowlock events", "src/si_v2/rainbow/shadowlock_events.py"),
            ("Client fixture harness", "src/si_v2/rainbow/client_fixture_harness.py"),
        ],
    },
    {
        "group": "Source manifest",
        "artifacts": [
            ("Source manifest file", "evidence/source_manifest.json"),
        ],
    },
    {
        "group": "Evidence bundle",
        "artifacts": [
            ("Evidence bundle schema", "evidence/evidence_bundle.schema.json"),
            ("Evidence bundle builder", "src/si_v2/evidence/evidence_bundle_builder.py"),
            ("Evidence bundle output", "reports/evidence/evidence_bundle.json"),
            ("Evidence bundle integrity manifest", "evidence/evidence_bundle_integrity_manifest.json"),
        ],
    },
    {
        "group": "Regime fixtures",
        "artifacts": [
            ("Regime labels dir", "fixtures/regime-labels"),
        ],
    },
    {
        "group": "Attribution aggregation",
        "artifacts": [
            ("Offline aggregator", "src/si_v2/attribution/offline_aggregator.py"),
            ("Attribution summary output", "reports/attribution/offline_attribution_summary.json"),
            ("Attribution report", "reports/attribution/attribution_report.md"),
        ],
    },
    {
        "group": "Offline quality gate",
        "artifacts": [
            ("Quality gate CLI", "src/si_v2/cli/offline_quality_gate.py"),
            ("Quality gate report", "reports/readiness/offline_quality_gate_report.md"),
        ],
    },
    {
        "group": "Offline episode skeleton",
        "artifacts": [
            ("Episode skeleton module", "src/si_v2/episode/offline_episode.py"),
            ("Episode manifest", "episode/offline_episode_manifest.json"),
            ("Episode CLI", "run_offline_episode.py"),
        ],
    },
    {
        "group": "Episode report",
        "artifacts": [
            ("Episode report renderer", "src/si_v2/episode/offline_episode_report.py"),
            ("Episode report output", "reports/episode/offline_episode_report.md"),
        ],
    },
    {
        "group": "Governance (not yet implemented)",
        "artifacts": [
            ("Offline pipeline smoke workflow (#120)", "",),
            ("Failure taxonomy map (#121)", "",),
            ("Human approval gate checklist (#122)", "",),
            ("Implementation progress dashboard (#123)", "",),
            ("Live-readiness blocker inventory (#124)", "",),
            ("Controlled dry-run rehearsal runbook (#125)", "",),
        ],
        "severity": "optional",
    },
]


class Phase1ReadinessMatrix:
    """Generate Phase 1 readiness matrix."""

    def __init__(self, root: Path | None = None) -> None:
        self._root = root or Path("self_improvement_v2")

    def _resolve(self, *parts: str) -> Path:
        return self._root.joinpath(*parts)

    def _exists(self, rel_path: str) -> bool:
        if not rel_path:
            return False
        return self._resolve(*rel_path.split("/")).exists()

    def build(self) -> ReadinessMatrix:
        """Build the readiness matrix."""
        artifacts: list[ArtifactEntry] = []

        for group_def in _REQUIRED_ARTIFACT_GROUPS:
            group = str(group_def.get("group", ""))
            severity = str(group_def.get("severity", "required"))
            for name, path in group_def.get("artifacts", []):
                found = self._exists(str(path))
                artifacts.append(
                    ArtifactEntry(
                        group=group,
                        name=str(name),
                        path=str(path),
                        found=found,
                        severity=severity,
                    )
                )

        required = [a for a in artifacts if a.severity == "required"]
        optional = [a for a in artifacts if a.severity == "optional"]

        required_found = sum(1 for a in required if a.found)
        required_total = len(required)
        optional_found = sum(1 for a in optional if a.found)
        optional_total = len(optional)

        missing_required = required_total - required_found
        missing_optional = optional_total - optional_found

        if missing_required > 0:
            verdict = ReadinessVerdict.RED
        elif missing_optional > 0:
            verdict = ReadinessVerdict.YELLOW
        else:
            verdict = ReadinessVerdict.GREEN

        return ReadinessMatrix(
            verdict=verdict,
            artifacts=artifacts,
            required_found=required_found,
            required_total=required_total,
            optional_found=optional_found,
            optional_total=optional_total,
        )

    def generate_markdown(self) -> str:
        """Generate deterministic Markdown readiness matrix."""
        matrix = self.build()
        lines: list[str] = []

        lines.append("# Phase 1 Readiness Matrix")
        lines.append("")
        lines.append(f"**Verdict:** {matrix.verdict.value}")
        lines.append("")
        lines.append(
            f"**Required:** {matrix.required_found}/{matrix.required_total} found"
        )
        lines.append(
            f"**Optional:** {matrix.optional_found}/{matrix.optional_total} found"
        )
        lines.append("")

        current_group = ""
        for a in matrix.artifacts:
            if a.group != current_group:
                current_group = a.group
                lines.append("")
                lines.append(f"### {current_group}")
                lines.append("")
                lines.append("| Artifact | Status | Severity |")
                lines.append("|----------|--------|----------|")

            icon = "✅" if a.found else ("⚠️" if a.severity == "optional" else "❌")
            status = "Found" if a.found else ("Pending" if a.severity == "optional" else "MISSING")
            lines.append(
                f"| {a.name} | {icon} {status} | {a.severity} |"
            )

        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append(
            "*Matrix generated by Phase1ReadinessMatrix — "
            "offline, deterministic, no live-readiness assessment*"
        )

        return "\n".join(lines)
