"""Tests for Evidence Bundle Integrity Manifest (#115).

Verifies:
- integrity manifest exists
- evidence bundle files are listed
- JSON parses successfully
- tests pass
"""

from __future__ import annotations

import json
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent

_MANIFEST_PATH = (
    _ROOT / "evidence" / "evidence_bundle_integrity_manifest.json"
)


def _load() -> dict[str, object]:
    with open(_MANIFEST_PATH) as f:
        return dict(json.load(f))


class TestManifestExists:
    def test_manifest_exists(self) -> None:
        assert _MANIFEST_PATH.exists()

    def test_manifest_is_valid_json(self) -> None:
        data = _load()
        assert data is not None

    def test_manifest_has_schema_version(self) -> None:
        data = _load()
        assert "schema_version" in data

    def test_manifest_has_created_by(self) -> None:
        data = _load()
        assert "created_by" in data

    def test_manifest_has_files(self) -> None:
        data = _load()
        assert "files" in data
        files = list(data.get("files", []))
        assert len(files) > 0

    def test_manifest_has_file_count(self) -> None:
        data = _load()
        assert "file_count" in data
        assert isinstance(data["file_count"], int)

    def test_file_count_matches(self) -> None:
        data = _load()
        files = list(data.get("files", []))
        assert data["file_count"] == len(files)


class TestFileEntries:
    def test_each_entry_has_file_field(self) -> None:
        data = _load()
        for entry in data.get("files", []):
            assert isinstance(entry, dict)
            assert "file" in entry

    def test_each_entry_has_sha256_field(self) -> None:
        data = _load()
        for entry in data.get("files", []):
            assert isinstance(entry, dict)
            assert "sha256" in entry
            assert len(str(entry["sha256"])) == 64  # SHA-256 hex

    def test_each_entry_has_size_bytes(self) -> None:
        data = _load()
        for entry in data.get("files", []):
            assert isinstance(entry, dict)
            assert "size_bytes" in entry
            assert isinstance(entry["size_bytes"], int)

    def test_referenced_files_exist(self) -> None:
        data = _load()
        for entry in data.get("files", []):
            file_rel = str(entry.get("file", ""))
            if file_rel:
                p = _ROOT / file_rel
                assert p.exists(), f"Referenced file not found: {file_rel}"


class TestNoSecrets:
    def test_manifest_no_secrets(self) -> None:
        text = _MANIFEST_PATH.read_text()
        assert "api_key" not in text
        assert "secret" not in text
        assert "token" not in text
        assert "password" not in text
