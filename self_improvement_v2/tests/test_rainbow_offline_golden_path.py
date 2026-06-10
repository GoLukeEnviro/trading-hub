"""Offline Golden Path test for the Rainbow evidence flow.

Exercises the full offline pipeline:
1. Load Rainbow fixtures
2. Validate with #79 validator
3. Generate fixture review report
4. Map audit events via #81 Shadowlock event mapper
5. Check source readiness summary
6. Check client fixture harness

All steps are deterministic and offline.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from si_v2.rainbow.validator import (
    RainbowSignalEnvelopeValidator,
)

_FIXTURE_DIR = (
    Path(__file__).resolve().parent.parent
    / "fixtures"
    / "rainbow-signals"
)
_FIXTURE_REVIEW_REPORT = (
    Path(__file__).resolve().parent.parent
    / "reports"
    / "rainbow"
    / "fixture_review_report.md"
)
_DRIFT_REPORT = (
    Path(__file__).resolve().parent.parent
    / "reports"
    / "rainbow"
    / "contract_drift_report.md"
)

validator = RainbowSignalEnvelopeValidator()


def _load_fixture(name: str) -> dict[str, object]:
    path = _FIXTURE_DIR / name
    with open(path) as f:
        return dict(json.load(f))


# ── Step 1: Load fixtures ────────────────────────────────────────────────


class TestStep1LoadFixtures:
    def test_fixture_dir_exists(self) -> None:
        assert _FIXTURE_DIR.exists()

    def test_all_fixtures_parsable(self) -> None:
        for f in sorted(_FIXTURE_DIR.glob("*.json")):
            with open(f) as fp:
                data = json.load(fp)
            assert isinstance(data, dict)


# ── Step 2: Validate with #79 validator ──────────────────────────────────


class TestStep2Validator:
    def test_validator_importable(self) -> None:
        from si_v2.rainbow.validator import (
            RainbowSignalEnvelopeValidator,
        )

        assert RainbowSignalEnvelopeValidator

    def test_valid_long_passes(self) -> None:
        env = _load_fixture("valid_long_signal.json")
        result = validator.validate_envelope(env)
        assert result.verdict.value == "pass"

    def test_valid_short_passes(self) -> None:
        env = _load_fixture("valid_short_signal.json")
        result = validator.validate_envelope(env)
        assert result.verdict.value == "pass"

    def test_malformed_fails_closed(self) -> None:
        env = _load_fixture("malformed_missing_required_fields.json")
        result = validator.validate_envelope(env)
        assert result.verdict.value == "fail"

    def test_stale_detected(self) -> None:
        env = _load_fixture("stale_signal.json")
        result = validator.validate_envelope(env)
        assert result.verdict.value in ("warn", "fail")


# ── Step 3: Generate fixture review report ───────────────────────────────


class TestStep3FixtureReview:
    def test_report_generator_importable(self) -> None:
        from si_v2.rainbow.fixture_review_report import (
            RainbowFixtureReviewReportGenerator,
        )

        assert RainbowFixtureReviewReportGenerator

    def test_generator_runs(self) -> None:
        from si_v2.rainbow.fixture_review_report import (
            RainbowFixtureReviewReportGenerator,
        )

        gen = RainbowFixtureReviewReportGenerator(
            fixture_dir=_FIXTURE_DIR
        )
        report = gen.generate()
        assert report.total_fixtures == 7

    def test_report_file_exists(self) -> None:
        assert _FIXTURE_REVIEW_REPORT.exists()


# ── Step 4: Map audit events via #81 Shadowlock mapper ───────────────────


class TestStep4ShadowlockEvents:
    def test_event_mapper_importable(self) -> None:
        from si_v2.rainbow.shadowlock_events import (
            RainbowShadowlockEventMapper,
        )

        assert RainbowShadowlockEventMapper

    def test_all_fixtures_mapped(self) -> None:
        from si_v2.rainbow.shadowlock_events import (
            RainbowShadowlockEventMapper,
        )

        envelopes = []
        vrs = []
        for f in sorted(_FIXTURE_DIR.glob("*.json")):
            env = _load_fixture(f.name)
            envelopes.append(env)
            vr_result = validator.validate_envelope(env)
            vrs.append(
                {
                    "verdict": vr_result.verdict.value,
                    "errors": vr_result.errors,
                    "warnings": vr_result.warnings,
                }
            )
        events = RainbowShadowlockEventMapper.map_fixture_batch(
            envelopes, vrs
        )
        assert len(events) == 7

    def test_preview_report_exists(self) -> None:
        preview_path = (
            Path(__file__).resolve().parent.parent
            / "reports"
            / "rainbow"
            / "shadowlock_event_preview.md"
        )
        assert preview_path.exists()


# ── Step 5: Check client fixture harness ─────────────────────────────────


class TestStep5ClientFixtureHarness:
    def test_harness_importable(self) -> None:
        from si_v2.rainbow.client_fixture_harness import (
            RainbowClientFixtureHarness,
        )

        assert RainbowClientFixtureHarness

    def test_harness_runs(self) -> None:
        from si_v2.rainbow.client_fixture_harness import (
            RainbowClientFixtureHarness,
        )

        harness = RainbowClientFixtureHarness(
            fixture_dir=_FIXTURE_DIR
        )
        result = harness.run()
        assert result.total_fixtures == 7
        assert result.valid_signals >= 1


# ── Step 6: Check source readiness summary ───────────────────────────────


class TestStep6ReadinessSummary:
    def test_readiness_importable(self) -> None:
        from si_v2.evidence.source_readiness_summary import (
            SourceReadinessChecker,
        )

        assert SourceReadinessChecker

    def test_readiness_check_runs(self) -> None:
        from si_v2.evidence.source_readiness_summary import (
            SourceReadinessChecker,
        )

        checker = SourceReadinessChecker()
        summary = checker.check()
        assert len(summary.providers) >= 1


# ── Step 7: Check drift guard ────────────────────────────────────────────


class TestStep7DriftGuard:
    def test_drift_report_exists(self) -> None:
        assert _DRIFT_REPORT.exists()

    def test_drift_guard_importable(self) -> None:
        from si_v2.rainbow.drift_guard import (
            RainbowContractDriftGuard,
        )

        assert RainbowContractDriftGuard
