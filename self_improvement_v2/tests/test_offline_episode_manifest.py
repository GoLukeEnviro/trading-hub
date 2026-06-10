"""Tests for the offline episode manifest (#104).

Verifies:
- manifest is valid JSON
- lists input files, output reports, and required checks
- referenced core fixtures exist
"""

from __future__ import annotations

import json
from pathlib import Path

_MANIFEST_PATH = (
    Path(__file__).resolve().parent.parent
    / "episode"
    / "offline_episode_manifest.json"
)


def _load() -> dict[str, object]:
    with open(_MANIFEST_PATH) as f:
        return dict(json.load(f))


class TestManifestParsing:
    def test_manifest_exists(self) -> None:
        assert _MANIFEST_PATH.exists()

    def test_manifest_is_valid_json(self) -> None:
        data = _load()
        assert "manifest_version" in data
        assert "input_files" in data
        assert "output_reports" in data
        assert "required_checks" in data

    def test_has_input_files(self) -> None:
        data = _load()
        inputs = data.get("input_files", {})
        assert isinstance(inputs, dict)
        assert len(inputs) > 0

    def test_has_output_reports(self) -> None:
        data = _load()
        reports = list(data.get("output_reports", []))
        assert len(reports) > 0

    def test_has_required_checks(self) -> None:
        data = _load()
        checks = list(data.get("required_checks", []))
        assert len(checks) > 0

    def test_has_components(self) -> None:
        data = _load()
        components = data.get("components", {})
        assert isinstance(components, dict)
        assert len(components) > 0


class TestCoreFilesExist:
    def test_validator_path_exists(self) -> None:
        data = _load()
        components = dict(data.get("components", {}))
        vp = str(components.get("validator", ""))
        assert Path(vp).exists(), f"Validator path not found: {vp}"

    def test_contract_path_exists(self) -> None:
        data = _load()
        inputs = dict(data.get("input_files", {}))
        contracts = list(inputs.get("contracts", []))
        cp = str(contracts[0]) if contracts else ""
        assert cp and Path(cp).exists(), (
            f"Contract path not found: {cp}"
        )

    def test_fixtures_path_exists(self) -> None:
        data = _load()
        inputs = dict(data.get("input_files", {}))
        fixtures = list(inputs.get("fixtures", []))
        fp = str(fixtures[0]) if fixtures else ""
        assert fp and Path(fp).exists(), (
            f"Fixtures path not found: {fp}"
        )

    def test_evidence_schema_exists(self) -> None:
        data = _load()
        inputs = dict(data.get("input_files", {}))
        schemas = list(inputs.get("evidence_schema", []))
        sp = str(schemas[0]) if schemas else ""
        assert sp and Path(sp).exists(), (
            f"Evidence schema not found: {sp}"
        )

    def test_no_credentials(self) -> None:
        text = _MANIFEST_PATH.read_text()
        assert "api_key" not in text
        assert "secret" not in text
        assert "token" not in text
