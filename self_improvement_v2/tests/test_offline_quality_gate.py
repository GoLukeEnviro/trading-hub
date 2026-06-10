"""Tests for the offline quality gate (#112).

Verifies:
- runs all checks
- all JSON files parse
- key artifacts exist
- returns GREEN/YELLOW/RED
- deterministic
"""

from __future__ import annotations

from si_v2.cli.offline_quality_gate import (
    OfflineQualityGate,
    QaVerdict,
)


def _gate() -> OfflineQualityGate:
    return OfflineQualityGate()


class TestGate:
    def test_gate_creates(self) -> None:
        g = _gate()
        assert g is not None

    def test_run_returns_report(self) -> None:
        report = _gate().run()
        assert report is not None
        assert report.verdict is not None

    def test_has_checks(self) -> None:
        report = _gate().run()
        assert len(report.checks) > 0

    def test_json_parse_check_passes(self) -> None:
        report = _gate().run()
        for c in report.checks:
            if "JSON" in c.name:
                assert c.passed, f"JSON check failed: {c.details}"

    def test_episode_manifest_check(self) -> None:
        report = _gate().run()
        for c in report.checks:
            if "episode" in c.name.lower():
                assert c.passed
                return

    def test_source_manifest_check(self) -> None:
        report = _gate().run()
        for c in report.checks:
            if "source manifest" in c.name.lower():
                assert c.passed
                return

    def test_verdict_is_qaverdict(self) -> None:
        report = _gate().run()
        assert isinstance(report.verdict, QaVerdict)

    def test_deterministic(self) -> None:
        r1 = _gate().run()
        r2 = _gate().run()
        assert r1.verdict == r2.verdict
        assert len(r1.checks) == len(r2.checks)
        for c1, c2 in zip(r1.checks, r2.checks, strict=True):
            assert c1.passed == c2.passed


class TestMarkdown:
    def test_markdown_generates(self) -> None:
        md = _gate().generate_markdown()
        assert "Quality Gate" in md
        assert "Verdict:" in md

    def test_markdown_deterministic(self) -> None:
        md1 = _gate().generate_markdown()
        md2 = _gate().generate_markdown()
        assert md1 == md2
