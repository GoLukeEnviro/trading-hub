"""Tests for the regime label fixture pack (#109).

Verifies:
- all fixtures parse as JSON
- required fields present
- expected regimes exist
- no secrets
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

_EXPECTED_FIXTURES: list[str] = [
    "bullish_regime.json",
    "bearish_regime.json",
    "sideways_regime.json",
    "volatile_regime.json",
    "unknown_regime.json",
]


class TestFixtureParsing:
    def test_fixture_dir_exists(self) -> None:
        assert _FIXTURE_DIR.exists()

    def test_all_expected_fixtures_exist(self) -> None:
        for name in _EXPECTED_FIXTURES:
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
        expected = set(_EXPECTED_FIXTURES)
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

    def test_all_fixtures_have_regime_label(self) -> None:
        for f in _FIXTURE_DIR.glob("*.json"):
            with open(f) as fp:
                data = dict(json.load(fp))
            label = data.get("regime_label", "")
            assert label in (
                "bullish", "bearish", "sideways",
                "volatile", "unknown"
            ), f"{f.name} has unexpected label: {label}"


class TestRegimeDistribution:
    def test_all_five_regimes_present(self) -> None:
        labels = set()
        for f in _FIXTURE_DIR.glob("*.json"):
            with open(f) as fp:
                data = dict(json.load(fp))
            labels.add(data.get("regime_label", ""))
        expected = {
            "bullish", "bearish", "sideways",
            "volatile", "unknown"
        }
        assert labels == expected, (
            f"Missing regimes: {expected - labels}"
        )


class TestNoCredentials:
    def test_no_secrets_in_fixtures(self) -> None:
        for f in _FIXTURE_DIR.glob("*.json"):
            text = f.read_text()
            assert "api_key" not in text
            assert "secret" not in text
            assert "token" not in text
            assert "password" not in text
