#!/usr/bin/env python3
"""Offline governance consistency validator (spec §7.1/§7.2).

STRUCTURED METADATA ONLY: validates the two governance YAMLs against their JSON
schemas and inspects DEFINED FRONTMATTER FIELDS of governed Markdown. It never
free-text scans document bodies, historical reports, evidence, or legacy prose.
No GitHub API access. Exit non-zero on any hard failure;
ROADMAP_RECONCILIATION_PENDING is a warning, not a failure.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import jsonschema
import yaml

GOV = Path("config/governance")
HARD_FAILURES: list[str] = []
WARNINGS: list[str] = []


def _load_yaml(p: Path):
    return yaml.safe_load(p.read_text())


def _load_json(p: Path):
    return json.loads(p.read_text())


def check_schemas() -> tuple[dict, dict]:
    contract = _load_yaml(GOV / "program-contract.yaml")
    roadmap = _load_yaml(GOV / "canonical-roadmap.yaml")
    try:
        jsonschema.validate(contract, _load_json(GOV / "program-contract.schema.json"))
    except jsonschema.ValidationError as e:
        HARD_FAILURES.append(f"contract schema: {e.message}")
    try:
        jsonschema.validate(roadmap, _load_json(GOV / "canonical-roadmap.schema.json"))
    except jsonschema.ValidationError as e:
        HARD_FAILURES.append(f"roadmap schema: {e.message}")
    return contract, roadmap


def main() -> int:
    contract, roadmap = check_schemas()
    # further checks added in later tasks (DAG, paths, frontmatter, render, revision)
    for w in WARNINGS:
        print(f"WARN {w}")
    if HARD_FAILURES:
        for f in HARD_FAILURES:
            print(f"FAIL {f}")
        return 1
    print("governance-consistency OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())