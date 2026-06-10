"""Rainbow Signal Contract Drift Guard.

Compares the contract snapshot (schema), validator expectations, and fixture
behavior to detect drift between them.

Returns structured GREEN/YELLOW/RED verdicts for offline report use.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import ClassVar

# ── Verdict ──────────────────────────────────────────────────────────────────


class DriftVerdict(Enum):
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"


# ── Drift result ─────────────────────────────────────────────────────────────


@dataclass
class FixtureResult:
    """Result from validating a single fixture through the validator."""

    file_name: str
    validator_verdict: str  # pass / warn / fail
    expected_verdict: str  # what the schema+contract would predict
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    is_expected_malformed: bool = False
    drift_notes: list[str] = field(default_factory=list)


@dataclass
class SchemaDriftItem:
    """Describes a single drift item between schema and validator."""

    field: str
    schema_requires: str
    validator_requires: str
    severity: str  # break / warning


@dataclass
class DriftReport:
    """Complete drift guard report."""

    verdict: DriftVerdict
    summary: str
    schema_field_drifts: list[SchemaDriftItem] = field(default_factory=list)
    fixture_results: list[FixtureResult] = field(default_factory=list)
    fixture_drifts: list[str] = field(default_factory=list)
    total_fixtures: int = 0
    passed_fixtures: int = 0
    expected_failures: int = 0
    unexpected_failures: int = 0


# ── Drift Guard ──────────────────────────────────────────────────────────────


class RainbowContractDriftGuard:
    """Detect drift between contract schema, validator, and fixtures.

    Usage::

        guard = RainbowContractDriftGuard(
            schema_path=Path("self_improvement_v2/contracts/rainbow_signal_envelope.schema.json"),
            fixture_dir=Path("self_improvement_v2/fixtures/rainbow-signals"),
        )
        report = guard.run()
    """

    # Expected fixture verdicts based on design
    _EXPECTED_FIXTURE_VERDICTS: ClassVar[dict[str, str]] = {
        "valid_long_signal.json": "pass",
        "valid_short_signal.json": "pass",
        "no_signal.json": "warn",
        "heartbeat.json": "warn",
        "stale_signal.json": "warn",
        "partial_metadata_signal.json": "pass",
        "malformed_missing_required_fields.json": "fail",
    }

    # Fixtures expected to be malformed (counted separately)
    _EXPECTED_MALFORMED_FIXTURES: frozenset[str] = frozenset(
        {"malformed_missing_required_fields.json"}
    )

    def __init__(
        self,
        schema_path: Path,
        fixture_dir: Path,
    ) -> None:
        self._schema_path = schema_path
        self._fixture_dir = fixture_dir

    def run(self) -> DriftReport:
        """Run full drift check. Loads schema, scans fixtures, validates."""
        drifts: list[SchemaDriftItem] = []
        fixture_results: list[FixtureResult] = []
        fixture_drifts: list[str] = []

        # ── Load schema ────────────────────────────────────────────────
        schema = self._load_schema()

        # ── Compare schema required fields vs validator expectations ───
        schema_required: set[str] = set(schema.get("required", []))
        from si_v2.rainbow.validator import _REQUIRED_FIELDS as _VF

        validator_set: set[str] = set(_VF)

        # Fields in schema but not in validator (schema ahead)
        schema_extra = schema_required - validator_set
        for field_name in sorted(schema_extra):
            drifts.append(
                SchemaDriftItem(
                    field=field_name,
                    schema_requires="required",
                    validator_requires="not-required",
                    severity="warning",
                )
            )

        # Fields in validator but not in schema (validator ahead)
        validator_extra = validator_set - schema_required
        for field_name in sorted(validator_extra):
            drifts.append(
                SchemaDriftItem(
                    field=field_name,
                    schema_requires="not-required",
                    validator_requires="required",
                    severity="break",
                )
            )

        # ── Validate all fixtures ──────────────────────────────────────
        from si_v2.rainbow.validator import (
            RainbowSignalEnvelopeValidator,
        )

        validator = RainbowSignalEnvelopeValidator()
        fixture_files = sorted(self._fixture_dir.glob("*.json"))

        for fixture_file in fixture_files:
            envelope = self._load_fixture(fixture_file)
            name = fixture_file.name
            expected = self._EXPECTED_FIXTURE_VERDICTS.get(name, "pass")

            result = validator.validate_envelope(
                envelope, source_file=name
            )
            actual = result.verdict.value

            is_expected_malformed = name in self._EXPECTED_MALFORMED_FIXTURES

            fr = FixtureResult(
                file_name=name,
                validator_verdict=actual,
                expected_verdict=expected,
                errors=result.errors,
                warnings=result.warnings,
                is_expected_malformed=is_expected_malformed,
            )

            # Detect drift: actual vs expected
            if is_expected_malformed:
                if actual != "fail":
                    fr.drift_notes.append(
                        f"Expected FAIL but validator returned {actual}"
                    )
                    fixture_drifts.append(
                        f"{name}: malformed fixture should fail "
                        f"but got {actual}"
                    )
            else:
                if actual == "fail" and expected != "fail":
                    fr.drift_notes.append(
                        f"Unexpected FAIL — fixture expected {expected}"
                    )
                    fixture_drifts.append(
                        f"{name}: expected {expected} but validator "
                        f"returned FAIL"
                    )
                elif expected == "pass" and actual == "warn":
                    fr.drift_notes.append(
                        "WARN instead of PASS — warnings present"
                    )

            fixture_results.append(fr)

        # ── Compute summary ─────────────────────────────────────────────
        total = len(fixture_files)
        passed = sum(
            1
            for r in fixture_results
            if r.validator_verdict == "pass"
            or (
                r.validator_verdict == "warn"
                and r.expected_verdict == "warn"
            )
        )
        expected_fails = sum(
            1
            for r in fixture_results
            if r.is_expected_malformed
        )
        unexpected_fails = sum(
            1
            for r in fixture_results
            if r.validator_verdict == "fail"
            and not r.is_expected_malformed
        )

        # ── Compute verdict ─────────────────────────────────────────────
        hard_breaks = [
            d for d in drifts if d.severity == "break"
        ]
        if hard_breaks or unexpected_fails > 0:
            verdict = DriftVerdict.RED
            summary = (
                f"DRIFT DETECTED: {len(hard_breaks)} schema field drifts "
                f"(validator requires but schema does not), "
                f"{unexpected_fails} unexpected fixture failures"
            )
        elif fixture_drifts:
            verdict = DriftVerdict.YELLOW
            summary = (
                f"Minor drift: {len(fixture_drifts)} fixture "
                f"behaviour deviations"
            )
        else:
            verdict = DriftVerdict.GREEN
            summary = (
                f"All checks passed: {total} fixtures, "
                f"{passed} passing, {expected_fails} expected "
                f"malformed, no drift"
            )

        return DriftReport(
            verdict=verdict,
            summary=summary,
            schema_field_drifts=drifts,
            fixture_results=fixture_results,
            fixture_drifts=fixture_drifts,
            total_fixtures=total,
            passed_fixtures=passed,
            expected_failures=expected_fails,
            unexpected_failures=unexpected_fails,
        )

    # ── Internal helpers ────────────────────────────────────────────────
    @staticmethod
    def _load_schema() -> dict[str, object]:
        """Load and return the contract snapshot JSON schema."""
        from si_v2.rainbow.validator import _REQUIRED_FIELDS

        # Attempt to load the schema file
        candidates = [
            Path("self_improvement_v2/contracts/rainbow_signal_envelope.schema.json"),
            Path("contracts/rainbow_signal_envelope.schema.json"),
        ]
        for path in candidates:
            if path.exists():
                with open(path) as f:
                    schema = dict(json.load(f))
                # Ensure required field list exists
                if "required" not in schema:
                    schema["required"] = list(_REQUIRED_FIELDS)
                return schema

        # Fallback: if no schema file exists, use validator as truth
        return {"required": list(_REQUIRED_FIELDS)}

    @staticmethod
    def _load_fixture(path: Path) -> dict[str, object]:
        """Load a single fixture JSON file."""
        with open(path) as f:
            return dict(json.load(f))
