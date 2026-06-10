"""Tests for the evidence bundle builder (#108).

Verifies:
- builder creates bundle
- bundle has required fields
- bundle references manifest and evidence records
- deterministic output
"""

from __future__ import annotations

from pathlib import Path

from si_v2.evidence.evidence_bundle_builder import (
    EvidenceBundleBuilder,
)

_MANIFEST = (
    Path(__file__).resolve().parent.parent
    / "evidence"
    / "source_manifest.json"
)
_EVIDENCE_DIR = (
    Path(__file__).resolve().parent.parent
    / "fixtures"
    / "external-evidence-records"
)
_FIXTURE_DIR = (
    Path(__file__).resolve().parent.parent
    / "fixtures"
    / "rainbow-signals"
)


def _builder() -> EvidenceBundleBuilder:
    return EvidenceBundleBuilder(
        manifest_path=_MANIFEST,
        evidence_dir=_EVIDENCE_DIR,
        fixture_dir=_FIXTURE_DIR,
    )


class TestBuilder:
    def test_builder_creates(self) -> None:
        b = _builder()
        assert b is not None

    def test_build_returns_bundle(self) -> None:
        bundle = _builder().build()
        assert bundle is not None
        assert bundle.schema_version == 1

    def test_bundle_has_source_refs(self) -> None:
        bundle = _builder().build()
        assert len(bundle.source_refs) > 0

    def test_bundle_has_evidence_refs(self) -> None:
        bundle = _builder().build()
        assert len(bundle.evidence_record_refs) > 0

    def test_bundle_has_fixture_count(self) -> None:
        bundle = _builder().build()
        assert bundle.fixture_count >= 7

    def test_bundle_has_report_refs(self) -> None:
        bundle = _builder().build()
        assert len(bundle.report_refs) > 0

    def test_bundle_status_ok(self) -> None:
        bundle = _builder().build()
        assert bundle.status == "ok"

    def test_bundle_deterministic(self) -> None:
        b1 = _builder().build()
        b2 = _builder().build()
        assert b1.to_dict() == b2.to_dict()

    def test_bundle_serializable(self) -> None:
        bundle = _builder().build()
        d = bundle.to_dict()
        import json
        json.dumps(d)  # must not raise
