"""Negative-case suite for the offline governance consistency validator.

Covers spec §7.5 cases. Each case must be red→green demonstrable.
"""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

CHECK = "orchestrator/scripts/governance_consistency_check.py"

# Files/dirs the tests mutate and the validator reads directly.
_MUTABLE = [
    "config/governance",
    "docs/roadmap",
    "docs/state",
    "AGENTS.md",
    "docs/proposals",
    "orchestrator/scripts",
]


def _run(cwd=None):
    """Run the validator against ``cwd`` (defaults to the real repo root)."""
    repo = cwd or Path(__file__).resolve().parents[1]
    return subprocess.run(
        [sys.executable, str(repo / CHECK)],
        cwd=repo,
        capture_output=True,
        text=True,
    )


def _canonical_source_paths():
    """Every path listed under contract canonical_sources (spec §4.1)."""
    contract = yaml.safe_load(
        Path("config/governance/program-contract.yaml").read_text()
    )
    paths = []
    for group in contract["canonical_sources"].values():
        if isinstance(group, list):
            paths.extend(group)
    return paths


def _clone_governance(tmp_path):
    """Isolated repo the validator can run against.

    Deep-copies the files the tests mutate, and ENSURES every canonical_sources
    path exists (dirs are created empty, files copied) so check_source_paths
    does not hard-fail on unrelated missing paths (e.g. SOUL.md,
    docs/decisions/, docs/reports/, docs/context/). Large evidence/context
    dirs are created empty on purpose — existence is all check_source_paths
    requires.
    """
    dst = tmp_path / "repo"
    for rel in _MUTABLE:
        src, target = Path(rel), dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, target)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, target)
    for rel in _canonical_source_paths():
        src, target = Path(rel), dst / rel
        if target.exists():
            continue
        if src.is_dir() or rel.endswith("/"):
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            if src.exists():
                shutil.copy2(src, target)
            else:
                target.write_text("placeholder\n")
    return dst


# ── Task 1: schema validation ──────────────────────────────────────────────


def test_real_repo_passes():
    result = _run()
    assert result.returncode == 0, result.stdout + result.stderr


def test_schema_invalid_contract_fails(tmp_path):
    repo = _clone_governance(tmp_path)
    contract = repo / "config/governance/program-contract.yaml"
    contract.write_text("schema_version: 1\nprogram_id: x\n")  # missing required
    result = _run(cwd=repo)
    assert result.returncode != 0


# ── Task 2: DAG acyclicity, single direction ───────────────────────────────


def test_cyclic_roadmap_fails(tmp_path):
    repo = _clone_governance(tmp_path)
    rm = repo / "config/governance/canonical-roadmap.yaml"
    data = yaml.safe_load(rm.read_text())
    # A depends on H -> introduces a cycle (A->H->G->F->E->D->B->A)
    data["phases"][1]["dependencies"].append("H")
    rm.write_text(yaml.safe_dump(data))
    assert _run(cwd=repo).returncode != 0


def test_two_active_directions_fail(tmp_path):
    repo = _clone_governance(tmp_path)
    c = repo / "config/governance/program-contract.yaml"
    data = yaml.safe_load(c.read_text())
    data["canonical_sources"]["roadmap"].append(
        "config/governance/other-roadmap.yaml"
    )
    c.write_text(yaml.safe_dump(data))
    assert _run(cwd=repo).returncode != 0