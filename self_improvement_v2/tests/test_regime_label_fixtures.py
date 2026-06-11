"""Tests for the regime label fixture pack (#109).

Verifies:
- all fixtures parse as JSON
- required fields present
- expected regimes exist
- no secrets
- both old (lowercase) and new (uppercase #55 canonical) fixtures are valid

NOTE: The old fixture vocabulary (bullish, bearish, sideways, volatile, unknown)
is DEPRECATED. New code should use the canonical #55 uppercase labels
(BULLISH, BEARISH, NEUTRAL, UNKNOWN). See:
  docs/specs/si-v2-regime-detector-schema.md (Issue #55)
"""

from __future__ import annotations

import json
import typing
from pathlib import Path

_FIXTURE_DIR = (
    Path(__file__).resolve().parent.parent
    / "fixtures"
    / "regime-labels"
)

# All expected fixture files (legacy + canonical)
_ALL_EXPECTED: list[str] = [
    # Canonical #55 format (uppercase)
    "bullish_regime.json",
    "bearish_regime.json",
    "neutral_regime.json",
    "unknown_regime.json",
    # Legacy lowercase (backward compat)
    "legacy_bullish_regime.json",
    "legacy_bearish_regime.json",
    "legacy_unknown_regime.json",
    # Original v1 fixtures (backward compat)
    "sideways_regime.json",
    "volatile_regime.json",
]

_OLD_LABELS: set[str] = {
    "bullish", "bearish", "sideways",
    "volatile", "unknown",
}

_CANONICAL_LABELS: set[str] = {
    "BULLISH", "BEARISH", "NEUTRAL", "UNKNOWN",
}

_VALID_LABELS: set[str] = _OLD_LABELS | _CANONICAL_LABELS


class TestFixtureParsing:
    def test_fixture_dir_exists(self) -> None:
        assert _FIXTURE_DIR.exists()

    def test_all_expected_fixtures_exist(self) -> None:
        for name in _ALL_EXPECTED:
            assert (_FIXTURE_DIR / name).exists(), (
                f"Missing fixture: {name}"
            )

    def test_all_fixtures_parse_as_json(self) -> None:
        for f in _FIXTURE_DIR.glob("*.json"):
            with open(f) as fp:
                data = json.load(fp)
            assert isinstance(data, dict)

    def test_no_extra_json_files(self) -> None:
        actual = {f.name for f in _FIXTURE_DIR.glob("*.json")}
        expected = set(_ALL_EXPECTED)
        assert actual == expected, (
            f"Unexpected files: {actual - expected}"
        )

    def test_readme_exists(self) -> None:
        assert (_FIXTURE_DIR / "README.md").exists()


class TestRequiredFields:
    _REQUIRED: typing.ClassVar[list[str]] = [
        "timestamp_utc",
        "symbol_or_pair",
        "regime_label",
        "confidence",
        "source",
        "metadata",
    ]

    def test_all_fixtures_have_required_fields(self) -> None:
        for f in _FIXTURE_DIR.glob("*.json"):
            with open(f) as fp:
                data = dict(json.load(fp))
            for field in self._REQUIRED:
                assert field in data, (
                    f"{f.name} missing required field: {field}"
                )

    def test_all_fixtures_have_valid_regime_label(self) -> None:
        for f in _FIXTURE_DIR.glob("*.json"):
            with open(f) as fp:
                data = dict(json.load(fp))
            label = data.get("regime_label", "")
            assert label in _VALID_LABELS, (
                f"{f.name} has unexpected label: {label!r}"
            )


class TestRegimeDistribution:
    def test_old_labels_present(self) -> None:
        """Old lowercase fixtures still exist for backward compat."""
        labels = set()
        for f in _FIXTURE_DIR.glob("*.json"):
            with open(f) as fp:
                data = dict(json.load(fp))
            labels.add(data.get("regime_label", ""))
        for old_label in _OLD_LABELS:
            assert old_label in labels, (
                f"Old label {old_label!r} missing from fixtures"
            )

    def test_canonical_labels_present(self) -> None:
        """New uppercase #55 canonical labels are present."""
        labels = set()
        for f in _FIXTURE_DIR.glob("*.json"):
            with open(f) as fp:
                data = dict(json.load(fp))
            labels.add(data.get("regime_label", ""))
        for canonical in _CANONICAL_LABELS:
            assert canonical in labels, (
                f"Canonical label {canonical!r} missing from fixtures"
            )


class TestNoCredentials:
    def test_no_secrets_in_fixtures(self) -> None:
        for f in _FIXTURE_DIR.glob("*.json"):
            text = f.read_text()
            assert "api_key" not in text
            assert "secret" not in text
            assert "token" not in text
            assert "password" not in text
