"""Tests for the Offline Rainbow Fixture Review Report generator.

Verifies that the report generator:
- loads all fixtures
- runs validator against each
- counts outcomes correctly
- produces deterministic output
- marks malformed fixtures as expected
"""

from __future__ import annotations

from pathlib import Path

from si_v2.rainbow.fixture_review_report import (
    RainbowFixtureReviewReportGenerator,
)

_FIXTURE_DIR = (
    Path(__file__).resolve().parent.parent / "fixtures" / "rainbow-signals"
)


# ── Fixtures ──────────────────────────────────────────────────────────────


def _generator() -> RainbowFixtureReviewReportGenerator:
    return RainbowFixtureReviewReportGenerator(fixture_dir=_FIXTURE_DIR)


# ── Basic operation ───────────────────────────────────────────────────────


class TestReportGenerator:
    def test_generator_creates(self) -> None:
        gen = _generator()
        assert gen is not None

    def test_report_contains_all_fixtures(self) -> None:
        report = _generator().generate()
        assert report.total_fixtures == 7
        names = {e.file_name for e in report.entries}
        expected = {
            "valid_long_signal.json",
            "valid_short_signal.json",
            "no_signal.json",
            "heartbeat.json",
            "stale_signal.json",
            "partial_metadata_signal.json",
            "malformed_missing_required_fields.json",
        }
        assert names == expected

    def test_report_deterministic(self) -> None:
        report1 = _generator().generate()
        report2 = _generator().generate()
        assert report1.total_fixtures == report2.total_fixtures
        for e1, e2 in zip(report1.entries, report2.entries, strict=True):
            assert e1.file_name == e2.file_name
            assert e1.verdict == e2.verdict


# ── Outcome counts ────────────────────────────────────────────────────────


class TestOutcomeCounts:
    def test_pass_count(self) -> None:
        report = _generator().generate()
        # valid_long, valid_short, partial_metadata should pass
        assert report.pass_count == 3, (
            f"Expected 3 pass, got {report.pass_count}"
        )

    def test_warn_count(self) -> None:
        report = _generator().generate()
        # no_signal, heartbeat, stale_signal should warn
        assert report.warn_count == 3, (
            f"Expected 3 warn, got {report.warn_count}"
        )

    def test_fail_count(self) -> None:
        report = _generator().generate()
        # malformed_missing_required_fields should fail
        assert report.fail_count == 1, (
            f"Expected 1 fail, got {report.fail_count}"
        )

    def test_expected_malformed_count(self) -> None:
        report = _generator().generate()
        assert report.expected_fail_count == 1, (
            f"Expected 1 expected malformed, got "
            f"{report.expected_fail_count}"
        )

    def test_no_unexpected_failures(self) -> None:
        report = _generator().generate()
        assert report.unexpected_fail_count == 0, (
            f"Unexpected failures: {report.unexpected_fail_count}"
        )


# ── Fixture types ─────────────────────────────────────────────────────────


class TestFixtureTypes:
    def test_valid_signal_type(self) -> None:
        report = _generator().generate()
        for entry in report.entries:
            if "valid_long_signal" in entry.file_name or "valid_short_signal" in entry.file_name:
                assert entry.expected_type == "valid_signal"

    def test_malformed_type(self) -> None:
        report = _generator().generate()
        for entry in report.entries:
            if "malformed" in entry.file_name:
                assert entry.expected_type == "malformed"

    def test_heartbeat_type(self) -> None:
        report = _generator().generate()
        for entry in report.entries:
            if entry.file_name == "heartbeat.json":
                assert entry.expected_type == "heartbeat"

    def test_no_signal_type(self) -> None:
        report = _generator().generate()
        for entry in report.entries:
            if entry.file_name == "no_signal.json":
                assert entry.expected_type == "no_signal"

    def test_stale_type(self) -> None:
        report = _generator().generate()
        for entry in report.entries:
            if entry.file_name == "stale_signal.json":
                assert entry.expected_type == "stale"

    def test_partial_metadata_type(self) -> None:
        report = _generator().generate()
        for entry in report.entries:
            if entry.file_name == "partial_metadata_signal.json":
                assert entry.expected_type == "partial_metadata"


# ── Markdown output ───────────────────────────────────────────────────────


class TestMarkdownOutput:
    def test_markdown_contains_summary(self) -> None:
        md = _generator().generate_markdown()
        assert "## Summary" in md
        assert "Total fixtures" in md

    def test_markdown_contains_fixture_detail(self) -> None:
        md = _generator().generate_markdown()
        assert "## Fixture Detail" in md
        assert "valid_long_signal" in md

    def test_markdown_deterministic(self) -> None:
        md1 = _generator().generate_markdown()
        md2 = _generator().generate_markdown()
        assert md1 == md2

    def test_markdown_mentions_offline(self) -> None:
        md = _generator().generate_markdown()
        assert "Offline" in md
        assert "deterministic" in md
