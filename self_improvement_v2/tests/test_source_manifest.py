"""Tests for the source manifest (#101).

Verifies:
- manifest is valid JSON
- contains required provider fields
- Rainbow provider is listed
- no credentials present
"""

from __future__ import annotations

import json
from pathlib import Path

_MANIFEST_PATH = Path(__file__).resolve().parent.parent / "evidence" / "source_manifest.json"


def _load() -> dict[str, object]:
    with open(_MANIFEST_PATH) as f:
        return dict(json.load(f))


class TestManifestParsing:
    def test_manifest_exists(self) -> None:
        assert _MANIFEST_PATH.exists()

    def test_manifest_is_valid_json(self) -> None:
        data = _load()
        assert "schema_version" in data
        assert "providers" in data

    def test_manifest_has_providers(self) -> None:
        data = _load()
        providers = list(data.get("providers", []))
        assert len(providers) > 0

    def test_rainbow_provider_present(self) -> None:
        data = _load()
        providers = list(data.get("providers", []))
        ids = [p.get("provider_id") for p in providers]
        assert "rainbow" in ids

    def test_rainbow_has_required_fields(self) -> None:
        data = _load()
        providers = list(data.get("providers", []))
        rainbow = next(
            (p for p in providers if p.get("provider_id") == "rainbow"),
            None,
        )
        assert rainbow is not None
        assert "source_type" in rainbow
        assert "status" in rainbow
        assert "contract_path" in rainbow
        assert "fixture_path" in rainbow

    def test_rainbow_has_validator_path(self) -> None:
        data = _load()
        providers = list(data.get("providers", []))
        rainbow = next(
            (p for p in providers if p.get("provider_id") == "rainbow"),
            None,
        )
        assert rainbow is not None
        assert "validator_path" in rainbow

    def test_no_credentials(self) -> None:
        """Manifest must not contain credentials or secrets."""
        text = _MANIFEST_PATH.read_text()
        assert "api_key" not in text
        assert "secret" not in text
        assert "token" not in text
        assert "password" not in text
