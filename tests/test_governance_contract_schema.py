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
