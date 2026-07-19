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


def check_dag(roadmap: dict) -> None:
    graph = {p["id"]: set(p["dependencies"]) for p in roadmap["phases"]}
    ids = set(graph)
    for pid, deps in graph.items():
        for d in deps - ids:
            HARD_FAILURES.append(f"phase {pid} depends on unknown {d}")
    resolved, guard = set(), 0
    while len(resolved) < len(graph) and guard <= len(graph):
        for pid, deps in graph.items():
            if pid not in resolved and deps <= resolved:
                resolved.add(pid)
        guard += 1
    if len(resolved) != len(graph):
        HARD_FAILURES.append("roadmap DAG has a cycle")


def check_single_direction(contract: dict) -> None:
    roadmaps = contract["canonical_sources"].get("roadmap", [])
    if len(roadmaps) != 1:
        HARD_FAILURES.append(
            f"expected exactly one authoritative roadmap, got {len(roadmaps)}"
        )


def _frontmatter(text: str) -> dict:
    if not text.startswith("---"):
        return {}
    _, _, rest = text.partition("---")
    fm, _, _ = rest.partition("---")
    try:
        return yaml.safe_load(fm) or {}
    except yaml.YAMLError:
        return {}


def check_source_paths(contract: dict) -> None:
    for group in contract["canonical_sources"].values():
        paths = group if isinstance(group, list) else []
        for rel in paths:
            if not Path(rel).exists():
                HARD_FAILURES.append(f"canonical source path missing: {rel}")


def check_governed_frontmatter() -> None:
    """Frontmatter-only checks across governed Markdown (spec §7.1/§7.2).

    Scope: proposals plus the roadmap dirs G0.1 stamps as superseded. No body
    scan, no historical reports/evidence/context.
    """
    scan_dirs = ["docs/proposals", "docs/roadmap", "docs/roadmaps"]
    for d in scan_dirs:
        if not Path(d).is_dir():
            continue
        for md in Path(d).glob("*.md"):
            if md.name == "README.md":
                continue
            fm = _frontmatter(md.read_text())
            if not fm:
                continue  # no governed frontmatter -> out of scope, not a failure
            if fm.get("authority") == "canonical":
                HARD_FAILURES.append(f"advisory/historical doc claims canonical: {md}")
            if fm.get("status") == "superseded" and not fm.get("superseded_by"):
                HARD_FAILURES.append(f"superseded doc lacks superseded_by: {md}")


def main() -> int:
    contract, roadmap = check_schemas()
    check_dag(roadmap)
    check_single_direction(contract)
    check_source_paths(contract)
    check_governed_frontmatter()
    # further checks added in later tasks (render, state revision, authority, mandate)
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