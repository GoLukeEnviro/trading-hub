"""Normalized Evidence Bundle Builder.

Reads local source manifest and evidence artifacts to produce a
deterministic JSON bundle for offline SI v2 pipeline consumption.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class EvidenceBundle:
    """Normalized evidence bundle."""
    schema_version: int = 1
    provider_id: str = "rainbow"
    source_refs: list[str] = field(default_factory=list)
    evidence_record_refs: list[str] = field(default_factory=list)
    fixture_count: int = 0
    report_refs: list[str] = field(default_factory=list)
    status: str = "ok"
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "provider_id": self.provider_id,
            "source_refs": self.source_refs,
            "evidence_record_refs": self.evidence_record_refs,
            "fixture_count": self.fixture_count,
            "report_refs": self.report_refs,
            "status": self.status,
            "errors": self.errors,
        }


class EvidenceBundleBuilder:
    """Build a normalized evidence bundle from local artifacts."""

    def __init__(
        self,
        manifest_path: Path | None = None,
        evidence_dir: Path | None = None,
        fixture_dir: Path | None = None,
        report_dir: Path | None = None,
    ) -> None:
        self._manifest_path = manifest_path or Path(
            "self_improvement_v2/evidence/source_manifest.json"
        )
        self._evidence_dir = evidence_dir or Path(
            "self_improvement_v2/fixtures/external-evidence-records"
        )
        self._fixture_dir = fixture_dir or Path(
            "self_improvement_v2/fixtures/rainbow-signals"
        )
        self._report_dir = report_dir or Path(
            "self_improvement_v2/reports/rainbow"
        )

    def build(self) -> EvidenceBundle:
        """Build and return an evidence bundle."""
        errors: list[str] = []
        source_refs: list[str] = []
        evidence_refs: list[str] = []
        report_refs: list[str] = []

        # Source manifest
        if self._manifest_path.exists():
            source_refs.append(str(self._manifest_path))
        else:
            errors.append(
                f"Manifest not found: {self._manifest_path}"
            )

        # Evidence records
        if self._evidence_dir.exists():
            for f in sorted(self._evidence_dir.glob("*.json")):
                evidence_refs.append(str(f))

        # Fixtures
        fixture_count = 0
        if self._fixture_dir.exists():
            fixture_count = len(
                list(self._fixture_dir.glob("*.json"))
            )
            source_refs.append(str(self._fixture_dir))

        # Reports
        if self._report_dir.exists():
            for f in sorted(self._report_dir.glob("*.md")):
                report_refs.append(str(f))

        status = "degraded" if errors else "ok"

        return EvidenceBundle(
            source_refs=source_refs,
            evidence_record_refs=evidence_refs,
            fixture_count=fixture_count,
            report_refs=report_refs,
            status=status,
            errors=errors,
        )
