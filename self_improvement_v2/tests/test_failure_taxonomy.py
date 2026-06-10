"""Tests for Failure Taxonomy and Remediation Map (#121).

Verifies:
- taxonomy file exists
- remediation map exists
- severity levels are documented
- tests load taxonomy
- quality gate can reference taxonomy IDs
"""

from __future__ import annotations

import json
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent

_TAXONOMY_PATH = _ROOT / "qa" / "failure_taxonomy.json"


def _load() -> dict[str, object]:
    with open(_TAXONOMY_PATH) as f:
        return dict(json.load(f))


class TestTaxonomyFile:
    def test_taxonomy_exists(self) -> None:
        assert _TAXONOMY_PATH.exists()

    def test_taxonomy_is_valid_json(self) -> None:
        data = _load()
        assert data is not None

    def test_taxonomy_has_schema_version(self) -> None:
        data = _load()
        assert "schema_version" in data

    def test_taxonomy_has_severity_definitions(self) -> None:
        data = _load()
        assert "severity_definitions" in data


class TestTaxonomyEntries:
    def test_has_entries(self) -> None:
        data = _load()
        entries = data.get("taxonomy", [])
        assert isinstance(entries, list)
        assert len(entries) > 0

    def test_each_entry_has_id(self) -> None:
        data = _load()
        for entry in data.get("taxonomy", []):
            assert isinstance(entry, dict)
            assert "id" in entry
            assert len(str(entry["id"])) > 0

    def test_each_entry_has_area(self) -> None:
        data = _load()
        for entry in data.get("taxonomy", []):
            assert isinstance(entry, dict)
            assert "area" in entry

    def test_each_entry_has_severity(self) -> None:
        data = _load()
        for entry in data.get("taxonomy", []):
            assert isinstance(entry, dict)
            assert "severity" in entry
            assert entry["severity"] in ("info", "warning", "blocking", "critical")

    def test_each_entry_has_remediation(self) -> None:
        data = _load()
        for entry in data.get("taxonomy", []):
            assert isinstance(entry, dict)
            assert "remediation" in entry
            assert len(str(entry["remediation"])) > 0

    def test_ids_are_unique(self) -> None:
        data = _load()
        ids = [str(e["id"]) for e in data.get("taxonomy", []) if isinstance(e, dict)]
        assert len(ids) == len(set(ids))


class TestLoader:
    def test_loader_imports(self) -> None:
        """The loader module should be importable and work."""
        import sys
        sys.path.insert(0, str(_ROOT))
        from qa.failure_taxonomy import load_taxonomy, lookup_failure, failure_ids
        tax = load_taxonomy(_TAXONOMY_PATH)
        assert "taxonomy" in tax
        entry = lookup_failure("JSON-001", tax)
        assert entry is not None
        assert entry["id"] == "JSON-001"
        ids = failure_ids(tax)
        assert len(ids) > 0
        assert "JSON-001" in ids

    def test_lookup_missing_returns_none(self) -> None:
        import sys
        sys.path.insert(0, str(_ROOT))
        from qa.failure_taxonomy import lookup_failure, load_taxonomy
        tax = load_taxonomy(_TAXONOMY_PATH)
        entry = lookup_failure("NONEXISTENT-999", tax)
        assert entry is None

    def test_failures_by_area(self) -> None:
        import sys
        sys.path.insert(0, str(_ROOT))
        from qa.failure_taxonomy import failures_by_area, load_taxonomy
        tax = load_taxonomy(_TAXONOMY_PATH)
        entries = failures_by_area("rainbow", tax)
        assert len(entries) >= 2  # RNB-001, RNB-002, RNB-003


class TestSeverityDefinitions:
    def test_severity_defs_are_valid(self) -> None:
        data = _load()
        defs = data.get("severity_definitions", {})
        assert isinstance(defs, dict)
        assert "info" in defs
        assert "warning" in defs
        assert "blocking" in defs
        assert "critical" in defs

    def test_all_entry_severities_defined(self) -> None:
        data = _load()
        entries = data.get("taxonomy", [])
        defs = data.get("severity_definitions", {})
        for entry in entries:
            if isinstance(entry, dict):
                sev = str(entry.get("severity", ""))
                assert sev in defs, f"Severity '{sev}' not defined in severity_definitions"
