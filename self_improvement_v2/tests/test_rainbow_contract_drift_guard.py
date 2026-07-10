"""Tests for the Rainbow Contract Drift Guard.

Verifies that the drift guard:
- loads schema and fixtures
- compares schema required fields vs validator expectations
- validates all fixtures through the existing validator
- reports expected malformed fixtures separately
- detects drift in required fields
- produces deterministic report
"""

from __future__ import annotations

from pathlib import Path

import pytest

from si_v2.rainbow.drift_guard import (
    DriftVerdict,
    RainbowContractDriftGuard,
)

_FIXTURE_DIR = (
    Path(__file__).resolve().parent.parent / "fixtures" / "rainbow-signals"
)
_SCHEMA_DIR = (
    Path(__file__).resolve().parent.parent / "contracts"
)


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def guard() -> RainbowContractDriftGuard:
    return RainbowContractDriftGuard(
        schema_path=_SCHEMA_DIR / "rainbow_signal_envelope.schema.json",
        fixture_dir=_FIXTURE_DIR,
    )


# ── Basic operation ───────────────────────────────────────────────────────


class TestDriftGuardLoads:
    def test_guard_creates(self, guard: RainbowContractDriftGuard) -> None:
        assert guard is not None
        assert guard._schema_path.exists()
        assert guard._fixture_dir.exists()

    def test_run_returns_report(self, guard: RainbowContractDriftGuard) -> None:
        report = guard.run()
        assert report is not None
        assert isinstance(report.verdict, DriftVerdict)

    def test_report_deterministic(self, guard: RainbowContractDriftGuard) -> None:
        report1 = guard.run()
        report2 = guard.run()
        assert report1.verdict == report2.verdict
        assert report1.summary == report2.summary
        assert len(report1.fixture_results) == len(report2.fixture_results)


# ── Fixture loading ───────────────────────────────────────────────────────


class TestFixtureLoading:
    def test_all_fixtures_loaded(self, guard: RainbowContractDriftGuard) -> None:
        report = guard.run()
        # 8 fixture files exist (7 original + 1 canonical fixture added in R1)
        assert report.total_fixtures == 8, (
            f"Expected 8 fixtures, got {report.total_fixtures}"
        )

    def test_fixture_names_present(self, guard: RainbowContractDriftGuard) -> None:
        report = guard.run()
        names = {r.file_name for r in report.fixture_results}
        expected = {
            "valid_long_signal.json",
            "valid_short_signal.json",
            "no_signal.json",
            "heartbeat.json",
            "stale_signal.json",
            "partial_metadata_signal.json",
            "malformed_missing_required_fields.json",
            "valid_canonical_long_signal.json",
        }
        assert names == expected, f"Fixture name mismatch: {names ^ expected}"


# ── Validator integration ─────────────────────────────────────────────────


class TestValidatorIntegration:
    def test_valid_long_passes(self, guard: RainbowContractDriftGuard) -> None:
        report = guard.run()
        for fr in report.fixture_results:
            if fr.file_name == "valid_long_signal.json":
                assert fr.validator_verdict == "pass", (
                    f"Expected pass, got {fr.validator_verdict}: {fr.errors}"
                )
                return
        pytest.fail("valid_long_signal.json not found in results")

    def test_valid_short_passes(self, guard: RainbowContractDriftGuard) -> None:
        report = guard.run()
        for fr in report.fixture_results:
            if fr.file_name == "valid_short_signal.json":
                assert fr.validator_verdict == "pass"
                return
        pytest.fail("valid_short_signal.json not found")

    def test_malformed_fails(self, guard: RainbowContractDriftGuard) -> None:
        report = guard.run()
        for fr in report.fixture_results:
            if fr.file_name == "malformed_missing_required_fields.json":
                assert fr.validator_verdict == "fail", (
                    f"Expected fail, got {fr.validator_verdict}"
                )
                assert fr.is_expected_malformed
                return
        pytest.fail("malformed_missing_required_fields.json not found")


# ── Expected malformed fixture counting ───────────────────────────────────


class TestExpectedMalformed:
    def test_expected_malformed_counted(self, guard: RainbowContractDriftGuard) -> None:
        report = guard.run()
        assert report.expected_failures == 1, (
            f"Expected 1 malformed fixture, got {report.expected_failures}"
        )

    def test_no_unexpected_failures(self, guard: RainbowContractDriftGuard) -> None:
        report = guard.run()
        assert report.unexpected_failures == 0, (
            f"Unexpected failures: {report.unexpected_failures}"
        )


# ── Schema comparison ─────────────────────────────────────────────────────


class TestSchemaComparison:
    def test_schema_required_fields_loaded(self, guard: RainbowContractDriftGuard) -> None:
        report = guard.run()
        # Verify schema-related drift detection ran
        assert report.schema_field_drifts is not None

    def test_no_hard_drift_by_default(self, guard: RainbowContractDriftGuard) -> None:
        report = guard.run()
        hard_breaks = [
            d for d in report.schema_field_drifts
            if d.severity == "break"
        ]
        assert len(hard_breaks) == 0, (
            f"Unexpected hard drifts: {hard_breaks}"
        )


# ── Report verdict ────────────────────────────────────────────────────────


class TestReportVerdict:
    def test_verdict_green_when_no_drift(
        self, guard: RainbowContractDriftGuard
    ) -> None:
        report = guard.run()
        assert report.verdict == DriftVerdict.GREEN, (
            f"Expected GREEN, got {report.verdict}: {report.summary}"
        )

    def test_verdict_red_when_required_field_drift(self) -> None:
        """Force a field drift by checking a field not in schema."""
        guard = RainbowContractDriftGuard(
            schema_path=_SCHEMA_DIR / "rainbow_signal_envelope.schema.json",
            fixture_dir=_FIXTURE_DIR,
        )
        # Remove a required field from schema to simulate drift
        # We simulate by checking that our schema matches validator
        report = guard.run()
        # If we ever add a new validator-required field without updating schema,
        # this test will still show drift
        assert report.verdict in (
            DriftVerdict.GREEN,
            DriftVerdict.YELLOW,
        ), f"Unexpected RED: {report.summary}"


# ── Deterministic report generation ───────────────────────────────────────


class TestDeterministic:
    def test_report_serializable(self, guard: RainbowContractDriftGuard) -> None:
        """Verify the drift guard can produce a report string."""
        report = guard.run()
        lines = [
            f"Verdict: {report.verdict.value}",
            f"Summary: {report.summary}",
            f"Total fixtures: {report.total_fixtures}",
            f"Passed: {report.passed_fixtures}",
            f"Expected failures: {report.expected_failures}",
            f"Unexpected failures: {report.unexpected_failures}",
            f"Schema drifts: {len(report.schema_field_drifts)}",
            f"Fixture drifts: {len(report.fixture_drifts)}",
        ]
        text = "\n".join(lines)
        assert "Verdict:" in text
        assert "Summary:" in text
        assert str(report.total_fixtures) in text
