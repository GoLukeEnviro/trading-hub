"""Offline Episode Skeleton.

Loads manifest, source manifest, evidence bundle, and quality gate
output to produce a deterministic episode result.

Missing optional artifacts produce YELLOW-style results, never crash.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class EpisodeVerdict(Enum):
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"


@dataclass
class EpisodeArtifact:
    name: str
    path: str
    found: bool
    severity: str = "required"


@dataclass
class EpisodeResult:
    verdict: EpisodeVerdict
    manifest_loaded: bool
    source_manifest_loaded: bool
    evidence_bundle_found: bool
    quality_gate_found: bool
    quality_gate_verdict: str = "unknown"
    artifacts: list[EpisodeArtifact] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "verdict": self.verdict.value,
            "manifest_loaded": self.manifest_loaded,
            "source_manifest_loaded": self.source_manifest_loaded,
            "evidence_bundle_found": self.evidence_bundle_found,
            "quality_gate_found": self.quality_gate_found,
            "quality_gate_verdict": self.quality_gate_verdict,
            "artifacts": [
                {"name": a.name, "path": a.path, "found": a.found, "severity": a.severity}
                for a in self.artifacts
            ],
            "errors": self.errors,
            "warnings": self.warnings,
        }


class OfflineEpisode:
    """Run an offline episode by loading and verifying all required artifacts."""

    def __init__(
        self,
        root: Path | None = None,
    ) -> None:
        self._root = root or Path("self_improvement_v2")

    def _resolve(self, *parts: str) -> Path:
        return self._root.joinpath(*parts)

    def _load_json(self, rel_path: str) -> dict[str, object] | None:
        p = self._resolve(*rel_path.split("/"))
        if not p.exists():
            return None
        try:
            with open(p) as f:
                return dict(json.load(f))
        except (json.JSONDecodeError, OSError):
            return None

    def run(self) -> EpisodeResult:
        """Execute the offline episode and return a deterministic result."""
        errors: list[str] = []
        warnings: list[str] = []
        artifacts: list[EpisodeArtifact] = []

        # 1. Load offline episode manifest (#104)
        manifest_path = "episode/offline_episode_manifest.json"
        manifest = self._load_json(manifest_path)
        manifest_loaded = manifest is not None
        artifacts.append(
            EpisodeArtifact(
                name="Offline episode manifest",
                path=manifest_path,
                found=manifest_loaded,
                severity="required",
            )
        )
        if not manifest_loaded:
            errors.append(f"Episode manifest not found: {manifest_path}")

        # 2. Load source manifest (#101)
        src_manifest_path = "evidence/source_manifest.json"
        src_manifest = self._load_json(src_manifest_path)
        src_manifest_loaded = src_manifest is not None
        artifacts.append(
            EpisodeArtifact(
                name="Source manifest",
                path=src_manifest_path,
                found=src_manifest_loaded,
                severity="required",
            )
        )
        if not src_manifest_loaded:
            errors.append(f"Source manifest not found: {src_manifest_path}")

        # 3. Load or reference evidence bundle output (#108)
        bundle_path = "reports/evidence/evidence_bundle.json"
        bundle = self._load_json(bundle_path)
        bundle_found = bundle is not None
        artifacts.append(
            EpisodeArtifact(
                name="Evidence bundle output",
                path=bundle_path,
                found=bundle_found,
                severity="required",
            )
        )
        if not bundle_found:
            errors.append(f"Evidence bundle not found: {bundle_path}")

        # 4. Load or reference quality gate output (#112)
        qg_path = "reports/readiness/offline_quality_gate_report.md"
        qg_found = self._resolve(*qg_path.split("/")).exists()
        qg_verdict = "unknown"
        if qg_found:
            try:
                text = self._resolve(*qg_path.split("/")).read_text()
                for line in text.splitlines():
                    if "Verdict:" in line:
                        qg_verdict = line.split("Verdict:")[-1].strip().strip("*").strip().lower()
                        break
            except OSError:
                qg_verdict = "unknown"
        artifacts.append(
            EpisodeArtifact(
                name="Offline quality gate report",
                path=qg_path,
                found=qg_found,
                severity="required",
            )
        )
        if not qg_found:
            errors.append(f"Quality gate report not found: {qg_path}")

        # 5. Optional: golden path test exists (optional artifact)
        golden_path = "tests/test_rainbow_offline_golden_path.py"
        golden_found = self._resolve(*golden_path.split("/")).exists()
        artifacts.append(
            EpisodeArtifact(
                name="Golden path test file",
                path=golden_path,
                found=golden_found,
                severity="optional",
            )
        )
        if not golden_found:
            warnings.append(f"Golden path test not found: {golden_path}")

        # 6. Optional: attribution summary exists
        attr_path = "reports/attribution/offline_attribution_summary.json"
        attr_found = self._load_json(attr_path) is not None
        artifacts.append(
            EpisodeArtifact(
                name="Attribution summary output",
                path=attr_path,
                found=attr_found,
                severity="optional",
            )
        )
        if not attr_found:
            warnings.append(f"Attribution summary not found: {attr_path}")

        # Determine verdict
        if errors:
            verdict = EpisodeVerdict.RED
        elif warnings:
            verdict = EpisodeVerdict.YELLOW
        else:
            verdict = EpisodeVerdict.GREEN

        return EpisodeResult(
            verdict=verdict,
            manifest_loaded=manifest_loaded,
            source_manifest_loaded=src_manifest_loaded,
            evidence_bundle_found=bundle_found,
            quality_gate_found=qg_found,
            quality_gate_verdict=qg_verdict,
            artifacts=artifacts,
            errors=errors,
            warnings=warnings,
        )
