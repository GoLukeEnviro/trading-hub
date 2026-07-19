import json
from pathlib import Path

import jsonschema
import pytest
import yaml

GOV = Path("config/governance")


def _load_json(name):
    return json.loads((GOV / name).read_text())


def test_contract_schema_is_valid_jsonschema():
    schema = _load_json("program-contract.schema.json")
    jsonschema.Draft202012Validator.check_schema(schema)


def test_contract_schema_rejects_missing_north_star():
    schema = _load_json("program-contract.schema.json")
    bad = {"schema_version": 1, "program_id": "trading-hub"}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_program_contract_validates_and_holds_safety_invariants():
    schema = _load_json("program-contract.schema.json")
    contract = yaml.safe_load((GOV / "program-contract.yaml").read_text())
    jsonschema.validate(contract, schema)
    assert contract["north_star"]["live_is_currently_authorized"] is False
    assert contract["forbidden_without_a3"]  # non-empty
    ci = {e["name"]: e for e in contract["execution"]["require_ci"]}
    assert ci["governance-consistency"]["enforcement"] == "pending"
    assert ci["governance-consistency"]["effective_after"] == "G0.2"


def test_roadmap_schema_is_valid_jsonschema():
    schema = _load_json("canonical-roadmap.schema.json")
    jsonschema.Draft202012Validator.check_schema(schema)


def test_roadmap_schema_rejects_unknown_execution_class():
    schema = _load_json("canonical-roadmap.schema.json")
    bad = {"roadmap_revision": 1, "governance_contract_revision": 1,
           "phases": [{"id": "X", "title": "x", "status": "pending",
                       "dependencies": [], "exit_gate": "g",
                       "execution_class": "A9"}]}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)
