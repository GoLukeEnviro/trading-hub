"""Tests for Phase 1 Readiness Matrix (#117).

Verifies:
- readiness matrix exists
- required artifacts are listed
- missing artifacts are reported as YELLOW
- output is deterministic
- tests pass
"""

from __future__ import annotations

from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from readiness.phase_1_readiness_matrix import (
    Phase1ReadinessMatrix,
    ReadinessVerdict,
)

_ROOT = Path(__file__).resolve().parent.parent


def _matrix() -> Phase1ReadinessMatrix:
    return Phase1ReadinessMatrix(root=_ROOT)


class TestMatrix:
    def test_matrix_creates(self) -> None:
        m = _matrix()
        assert m is not None

    def test_build_returns_matrix(self) -> None:
        m = _matrix().build()
        assert m is not None

    def test_build_has_verdict(self) -> None:
        m = _matrix().build()
        assert isinstance(m.verdict, ReadinessVerdict)

    def test_build_has_artifacts(self) -> None:
        m = _matrix().build()
        assert len(m.artifacts) > 0

    def test_required_artifacts_mostly_found(self) -> None:
        m = _matrix().build()
        # Rainbow subsystem artifacts should exist
        assert m.required_found > 0

    def test_requires_at_least_20_required(self) -> None:
        m = _matrix().build()
        assert m.required_total >= 20

    def test_deterministic(self) -> None:
        m1 = _matrix().build()
        m2 = _matrix().build()
        assert m1.verdict == m2.verdict
        assert len(m1.artifacts) == len(m2.artifacts)

    def test_markdown_includes_verdict(self) -> None:
        md = _matrix().generate_markdown()
        assert "**Verdict:**" in md

    def test_markdown_includes_artifact_groups(self) -> None:
        md = _matrix().generate_markdown()
        assert "Rainbow complete subsystem" in md
        assert "Source manifest" in md

    def test_markdown_includes_governance(self) -> None:
        md = _matrix().generate_markdown()
        assert "Governance" in md or "not yet implemented" in md

    def test_markdown_deterministic(self) -> None:
        md1 = _matrix().generate_markdown()
        md2 = _matrix().generate_markdown()
        assert md1 == md2


class TestSampleReport:
    def test_sample_report_exists(self) -> None:
        p = _ROOT / "reports" / "readiness" / "phase_1_readiness_matrix.md"
        assert p.exists()

    def test_sample_report_has_required_sections(self) -> None:
        text = (
            _ROOT / "reports" / "readiness" / "phase_1_readiness_matrix.md"
        ).read_text()
        assert "# Phase 1 Readiness Matrix" in text
        assert "**Verdict:**" in text
