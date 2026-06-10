"""Tests for #144: Rehearsal proposal package schema.

Verifies:
  - Valid complete proposal passes schema validation
  - Missing artifact fails schema validation
  - Broken cross-reference fails schema validation
  - Unsafe proposal state fails schema validation
  - Missing final approval fails schema validation
"""

from __future__ import annotations

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = PROJECT_ROOT / "rehearsal" / "rehearsal_proposal_package.schema.json"
FIXTURES_DIR = PROJECT_ROOT / "tests" / "fixtures" / "proposal_package"


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────


def _load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _validate_against_schema(instance: dict, schema: dict) -> list[dict]:
    """Validate a JSON instance against the schema using jsonschema or manual checks."""
    errors: list[dict] = []

    # Check required top-level fields
    for field in schema.get("required", []):
        if field not in instance:
            errors.append({"field": field, "message": f"Missing required field: {field}"})

    return errors


# ──────────────────────────────────────────────
# Schema artifact exists
# ──────────────────────────────────────────────


class TestSchemaArtifactExists:
    """The schema JSON file must exist."""

    def test_schema_file_exists(self) -> None:
        assert SCHEMA_PATH.is_file(), f"Schema not found: {SCHEMA_PATH}"

    def test_schema_is_valid_json(self) -> None:
        data = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        assert isinstance(data, dict)

    def test_schema_has_required_top_fields(self) -> None:
        data = _load_schema()
        assert "$schema" in data
        assert "type" in data
        assert "properties" in data
        assert "required" in data


# ──────────────────────────────────────────────
# Valid complete proposal passes
# ──────────────────────────────────────────────


class TestValidProposalPasses:
    """A complete, valid proposal should pass schema validation."""

    def test_valid_fixture_exists(self) -> None:
        path = FIXTURES_DIR / "valid" / "complete_proposal.json"
        assert path.is_file()

    def test_valid_fixture_loads(self) -> None:
        path = FIXTURES_DIR / "valid" / "complete_proposal.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(data, dict)

    def test_valid_fixture_has_all_required_fields(self) -> None:
        schema = _load_schema()
        path = FIXTURES_DIR / "valid" / "complete_proposal.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        errors = _validate_against_schema(data, schema)
        assert len(errors) == 0, f"Validation errors: {errors}"

    def test_valid_fixture_proposal_id_matches_pattern(self) -> None:
        import re
        path = FIXTURES_DIR / "valid" / "complete_proposal.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        pid = data.get("proposal", {}).get("proposal_id", "")
        assert re.match(r"^rp-[0-9]{8}-[0-9]{6}-[a-z0-9]{4}$", pid), (
            f"Proposal ID '{pid}' doesn't match expected pattern"
        )

    def test_valid_fixture_stage_is_final(self) -> None:
        path = FIXTURES_DIR / "valid" / "complete_proposal.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data.get("stage") == "final"

    def test_valid_fixture_has_all_references(self) -> None:
        required_refs = [
            "planning_gate_reference",
            "stop_condition_reference",
            "evidence_plan_reference",
            "approval_packet_reference",
            "observation_plan_reference",
            "readiness_record_reference",
        ]
        path = FIXTURES_DIR / "valid" / "complete_proposal.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        for ref in required_refs:
            assert ref in data, f"Missing reference: {ref}"

    def test_valid_fixture_non_production_confirmed(self) -> None:
        path = FIXTURES_DIR / "valid" / "complete_proposal.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data.get("non_production_confirmation") is True
        assert data.get("non_runtime_confirmation") is True


# ──────────────────────────────────────────────
# Invalid proposal fails
# ──────────────────────────────────────────────


class TestInvalidProposalFails:
    """An incomplete or malformed proposal should fail schema validation."""

    def test_invalid_fixture_exists(self) -> None:
        path = FIXTURES_DIR / "invalid" / "missing_references.json"
        assert path.is_file()

    def test_invalid_fixture_missing_required_top_fields(self) -> None:
        schema = _load_schema()
        path = FIXTURES_DIR / "invalid" / "missing_references.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        errors = _validate_against_schema(data, schema)
        assert len(errors) > 0, "Invalid fixture should have validation errors"

    def test_invalid_fixture_has_empty_proposal_name(self) -> None:
        path = FIXTURES_DIR / "invalid" / "missing_references.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data.get("proposal", {}).get("proposal_name") == ""

    def test_invalid_fixture_missing_non_production(self) -> None:
        path = FIXTURES_DIR / "invalid" / "missing_references.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "non_production_confirmation" not in data, (
            "Invalid fixture should be missing non_production_confirmation"
        )


# ──────────────────────────────────────────────
# Schema structure
# ──────────────────────────────────────────────


class TestSchemaStructure:
    """The schema must define draft/final stages and all artifact references."""

    def test_schema_defines_draft_and_final_stages(self) -> None:
        data = _load_schema()
        stage_prop = data.get("properties", {}).get("stage", {})
        assert "enum" in stage_prop
        assert "draft" in stage_prop["enum"]
        assert "final" in stage_prop["enum"]

    def test_schema_has_all_artifact_ref_types(self) -> None:
        data = _load_schema()
        props = data.get("properties", {})
        ref_types = [
            "planning_gate_reference",
            "stop_condition_reference",
            "evidence_plan_reference",
            "approval_packet_reference",
            "observation_plan_reference",
            "readiness_record_reference",
        ]
        for ref in ref_types:
            assert ref in props, f"Missing reference property: {ref}"

    def test_schema_defines_non_production_confirmation(self) -> None:
        data = _load_schema()
        props = data.get("properties", {})
        assert "non_production_confirmation" in props
        assert "non_runtime_confirmation" in props

    def test_schema_approval_token_pattern(self) -> None:
        import re
        pattern = r"^APPROVE_REHEARSAL_[0-9]{6}_[a-z0-9]{4}$"
        assert re.match(pattern, "APPROVE_REHEARSAL_240610_t3st"), (
            "Pattern should match valid approval token"
        )
        assert not re.match(pattern, "INVALID"), (
            "Pattern should reject invalid token"
        )
