"""Offline Rainbow Fixture Review Report generator.

Loads all Rainbow fixtures, validates them through the existing validator,
and produces a deterministic Markdown report with counts and outcomes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from si_v2.rainbow.validator import (
    RainbowSignalEnvelopeValidator,
    ValidationVerdict,
)


# ── Data classes ─────────────────────────────────────────────────────────────


@dataclass
class FixtureReviewEntry:
    """Review result for a single fixture."""

    file_name: str
    expected_type: str  # valid_signal / no_signal / heartbeat / stale / malformed / partial_metadata
    verdict: str  # pass / warn / fail
    has_errors: bool
    has_warnings: bool
    error_count: int
    warning_count: int
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class FixtureReviewReport:
    """Complete fixture review report."""

    total_fixtures: int
    entries: list[FixtureReviewEntry]
    pass_count: int
    warn_count: int
    fail_count: int
    expected_fail_count: int
    unexpected_fail_count: int
    fixture_dir: str


# ── Generator ────────────────────────────────────────────────────────────────


class RainbowFixtureReviewReportGenerator:
    """Generate an offline fixture review report.

    Usage::

        gen = RainbowFixtureReviewReportGenerator(
            fixture_dir=Path("self_improvement_v2/fixtures/rainbow-signals"),
        )
        report = gen.generate()
    """

    # Fixture type classification based on file naming conventions
    _FIXTURE_TYPES: dict[str, str] = {
        "valid_long_signal.json": "valid_signal",
        "valid_short_signal.json": "valid_signal",
        "no_signal.json": "no_signal",
        "heartbeat.json": "heartbeat",
        "stale_signal.json": "stale",
        "partial_metadata_signal.json": "partial_metadata",
        "malformed_missing_required_fields.json": "malformed",
    }

    # Fixtures expected to fail validation (malformed on purpose)
    _EXPECTED_MALFORMED: frozenset[str] = frozenset(
        {"malformed_missing_required_fields.json"}
    )

    def __init__(self, fixture_dir: Path) -> None:
        self._fixture_dir = fixture_dir
        self._validator = RainbowSignalEnvelopeValidator()

    def generate(self) -> FixtureReviewReport:
        """Generate and return the fixture review report."""
        entries: list[FixtureReviewEntry] = []

        fixture_files = sorted(self._fixture_dir.glob("*.json"))

        for fixture_path in fixture_files:
            name = fixture_path.name
            envelope = self._load_fixture(fixture_path)

            result = self._validator.validate_envelope(
                envelope, source_file=name
            )

            entries.append(
                FixtureReviewEntry(
                    file_name=name,
                    expected_type=self._FIXTURE_TYPES.get(name, "unknown"),
                    verdict=result.verdict.value,
                    has_errors=len(result.errors) > 0,
                    has_warnings=len(result.warnings) > 0,
                    error_count=len(result.errors),
                    warning_count=len(result.warnings),
                    errors=result.errors,
                    warnings=result.warnings,
                )
            )

        total = len(entries)
        pass_count = sum(1 for e in entries if e.verdict == "pass")
        warn_count = sum(1 for e in entries if e.verdict == "warn")
        fail_count = sum(1 for e in entries if e.verdict == "fail")

        expected_fail_count = sum(
            1
            for e in entries
            if e.file_name in self._EXPECTED_MALFORMED
        )
        unexpected_fail_count = sum(
            1
            for e in entries
            if e.verdict == "fail"
            and e.file_name not in self._EXPECTED_MALFORMED
        )

        return FixtureReviewReport(
            total_fixtures=total,
            entries=entries,
            pass_count=pass_count,
            warn_count=warn_count,
            fail_count=fail_count,
            expected_fail_count=expected_fail_count,
            unexpected_fail_count=unexpected_fail_count,
            fixture_dir=str(self._fixture_dir),
        )

    def generate_markdown(self) -> str:
        """Generate and return a Markdown report string."""
        report = self.generate()

        lines: list[str] = []
        lines.append("# Rainbow Fixture Review Report")
        lines.append("")
        lines.append(
            f"> **Generated:** Offline — deterministic output"
        )
        lines.append(f"> **Fixture directory:** `{report.fixture_dir}`")
        lines.append(f"> **Validator:** `RainbowSignalEnvelopeValidator` (#79)")
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("## Summary")
        lines.append("")
        lines.append(
            f"| Metric | Value |"
        )
        lines.append(
            f"|--------|-------|"
        )
        lines.append(
            f"| Total fixtures | {report.total_fixtures} |"
        )
        lines.append(
            f"| Pass (PASS) | {report.pass_count} |"
        )
        lines.append(
            f"| Warn (WARN) | {report.warn_count} |"
        )
        lines.append(
            f"| Fail (FAIL) | {report.fail_count} |"
        )
        lines.append(
            f"| Expected malformed | {report.expected_fail_count} |"
        )
        lines.append(
            f"| Unexpected failures | {report.unexpected_fail_count} |"
        )
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("## Fixture Detail")
        lines.append("")
        lines.append(
            "| File | Type | Verdict | Errors | Warnings | Notes |"
        )
        lines.append(
            "|------|------|---------|--------|----------|-------|"
        )

        for entry in report.entries:
            notes = []
            if entry.expected_type == "malformed":
                notes.append("Expected malformed")
            elif entry.expected_type == "no_signal":
                notes.append("Non-actionable")
            elif entry.expected_type == "heartbeat":
                notes.append("Health signal")
            elif entry.expected_type == "stale":
                notes.append("Past expiry threshold")
            elif entry.expected_type == "partial_metadata":
                notes.append("Degraded quality")
            elif entry.expected_type == "valid_signal":
                notes.append("Valid signal")
            if entry.warnings:
                notes.extend(entry.warnings[:3])

            note_str = "; ".join(notes) if notes else "—"
            err_count = entry.error_count
            warn_count = entry.warning_count

            lines.append(
                f"| `{entry.file_name}` "
                f"| {entry.expected_type} "
                f"| {entry.verdict.upper()} "
                f"| {err_count} "
                f"| {warn_count} "
                f"| {note_str} |"
            )

        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append(
            "*Report generated deterministically by "
            "`RainbowFixtureReviewReportGenerator`.*"
        )
        lines.append(
            "*No network, Docker, Freqtrade, Telegram, "
            "or runtime calls were made.*"
        )
        lines.append("")

        return "\n".join(lines)

    # ── Internal ────────────────────────────────────────────────────────

    @staticmethod
    def _load_fixture(path: Path) -> dict[str, object]:
        """Load a single fixture JSON file."""
        import json

        with open(path) as f:
            return dict(json.load(f))
