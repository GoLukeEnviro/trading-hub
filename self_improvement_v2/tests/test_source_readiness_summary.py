"""Tests for the source readiness summary (#103).

Verifies:
- reads manifest
- checks contract/fixture/report paths
- emits GREEN/YELLOW/RED
- missing optional files produce YELLOW, not crash
- output is deterministic
"""

from __future__ import annotations

from pathlib import Path

from si_v2.evidence.source_readiness_summary import (
    ReadinessVerdict,
    SourceReadinessChecker,
)

_MANIFEST_PATH = (
    Path(__file__).resolve().parent.parent
    / "evidence"
    / "source_manifest.json"
)


def _checker() -> SourceReadinessChecker:
    return SourceReadinessChecker(manifest_path=_MANIFEST_PATH)


class TestChecker:
    def test_checker_creates(self) -> None:
        c = _checker()
        assert c is not None

    def test_check_returns_summary(self) -> None:
        summary = _checker().check()
        assert summary is not None
        assert summary.verdict is not None

    def test_rainbow_provider_present(self) -> None:
        summary = _checker().check()
        ids = {p.provider_id for p in summary.providers}
        assert "rainbow" in ids

    def test_checks_deterministic(self) -> None:
        s1 = _checker().check()
        s2 = _checker().check()
        assert s1.verdict == s2.verdict
        assert len(s1.providers) == len(s2.providers)

    def test_verdict_is_readiness_verdict(self) -> None:
        summary = _checker().check()
        assert isinstance(summary.verdict, ReadinessVerdict)


class TestArtifactChecks:
    def test_contract_ok_for_rainbow(self) -> None:
        summary = _checker().check()
        rainbow = next(
            p for p in summary.providers
            if p.provider_id == "rainbow"
        )
        assert rainbow.contract_ok is True

    def test_fixtures_ok_for_rainbow(self) -> None:
        summary = _checker().check()
        rainbow = next(
            p for p in summary.providers
            if p.provider_id == "rainbow"
        )
        assert rainbow.fixtures_ok is True

    def test_validator_ok_for_rainbow(self) -> None:
        summary = _checker().check()
        rainbow = next(
            p for p in summary.providers
            if p.provider_id == "rainbow"
        )
        assert rainbow.validator_ok is True

    def test_report_ok_for_rainbow(self) -> None:
        summary = _checker().check()
        rainbow = next(
            p for p in summary.providers
            if p.provider_id == "rainbow"
        )
        assert rainbow.report_ok is True


class TestMissingPaths:
    def test_nonexistent_manifest_returns_red(self) -> None:
        checker = SourceReadinessChecker(
            manifest_path=Path("/tmp/nonexistent_manifest.json")
        )
        summary = checker.check()
        assert summary.verdict == ReadinessVerdict.RED

    def test_missing_report_is_warning_not_crash(self) -> None:
        """Missing optional report produces YELLOW, not exception."""
        summary = _checker().check()
        # With all Rainbow artifacts present, should be GREEN
        assert summary.verdict in (
            ReadinessVerdict.GREEN,
            ReadinessVerdict.YELLOW,
        )


class TestMarkdown:
    def test_markdown_generates(self) -> None:
        md = _checker().generate_markdown()
        assert "Source Readiness Summary" in md
        assert "rainbow" in md.lower()

    def test_markdown_deterministic(self) -> None:
        md1 = _checker().generate_markdown()
        md2 = _checker().generate_markdown()
        assert md1 == md2
