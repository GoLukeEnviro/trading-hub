# G0.1 — Canonical Governance Contract & Roadmap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the first of two A1 PRs that establish a single, machine-readable program governance layer for Trading Hub: the Accepted-on-merge ADR, the program contract + canonical roadmap (YAML + JSON schemas), a deterministic Markdown renderer, and the supporting migration — all validated by tests inside this same PR.

**Architecture:** YAML is the only authoritative source; the Markdown roadmap is a non-authoritative Derived View produced by a deterministic renderer. This PR ships the canonical files, their schemas, the renderer, and schema/renderer tests. Enforcement (full consistency validator, CI job, merge-guard/broker hooks) is deliberately deferred to G0.2. This PR performs **no runtime, Docker, trading, kill-switch, credential, service, socket, or controller mutation**.

**Tech Stack:** Python 3.11, `pyyaml`, `jsonschema` (added to dev deps), `pytest`, `ruff`.

**Spec:** [`docs/superpowers/specs/2026-07-19-canonical-program-governance-g0-design.md`](../specs/2026-07-19-canonical-program-governance-g0-design.md)

---

## Critical preconditions (read before Task 1)

- **Branch from authoritative `main` (`ff791d69`), NOT this worktree's base (`b18bbf0`).** Per spec §10.4 the worktree base is behind main. Create a fresh isolated worktree/branch from current `origin/main`. If you cannot confirm the base is `ff791d69` or newer, STOP and escalate.
- **Human-only merge.** This PR touches governance files (`AGENTS.md`, `config/governance/`, schemas). It must never be merged by any automated path (spec §10.3).
- **One issue → one branch → one PR → one report.** Open the G0.1 issue and point tracker #605 at it before implementation; repoint the tracker in a separate post-merge step, never inside this PR.
- **ADR stays `Proposed` during review.** The flip to `Accepted` happens on the exact PR head after Luke's explicit confirmation, followed by a CI/guard re-check, then merge (spec §0.2, Task 12). A merged `Proposed` ADR is forbidden.
- **No secrets, no `git add .`.** Stage every file explicitly by path (repo `AGENTS.md` rule).

---

## File Structure

| Path | Responsibility | Action |
|---|---|---|
| `docs/decisions/ADR-2026-07-19-canonical-program-governance.md` | Normative bootstrap decision | Create |
| `config/governance/program-contract.schema.json` | JSON Schema for the contract | Create |
| `config/governance/program-contract.yaml` | Authoritative machine-readable contract | Create |
| `config/governance/canonical-roadmap.schema.json` | JSON Schema for the roadmap DAG | Create |
| `config/governance/canonical-roadmap.yaml` | Authoritative roadmap (phases G0–H) | Create |
| `orchestrator/scripts/render_canonical_roadmap.py` | Deterministic YAML→Markdown renderer | Create |
| `docs/roadmap/canonical-program-roadmap.md` | Derived View (generated) | Create (via renderer) |
| `tests/test_governance_contract_schema.py` | Schema-validation tests for both YAMLs | Create |
| `tests/test_render_canonical_roadmap.py` | Renderer determinism / round-trip tests | Create |
| `pyproject.toml` | Add `jsonschema` to `[project.optional-dependencies].dev` | Modify |
| `AGENTS.md` | Add canonical-source reference block (minimal-touch) | Modify |
| `docs/proposals/README.md` | Proposal header convention | Create |
| `docs/state/current-operational-state.md` | Add governance revision fields | Modify |
| `docs/roadmap/<5 competing roadmaps>` | Add `superseded_by` frontmatter header | Modify (only genuine competitors) |
| `docs/reports/g0-1-governance-contract-<date>.md` | Evidence report | Create |

---

## Task 1: Bootstrap the branch and dev dependency

**Files:**
- Modify: `pyproject.toml:17-22`

- [ ] **Step 1: Create the isolated worktree/branch from current main**

Run:
```bash
git fetch origin
git rev-parse origin/main   # must be ff791d69… or newer; if not, STOP
git worktree add -b claude/g0-1-canonical-governance <path> origin/main
```
Expected: worktree created on a branch based on `origin/main`.

- [ ] **Step 2: Add `jsonschema` to dev dependencies**

In `pyproject.toml`, under `[project.optional-dependencies].dev`, add `"jsonschema>=4.0",`:

```toml
dev = [
    "pytest>=9.0",
    "pytest-cov>=5.0",
    "ruff>=0.15.16",
    "jsonschema>=4.0",
]
```

- [ ] **Step 3: Install and verify import**

Run: `python3 -m pip install -e ".[dev]" && python3 -c "import jsonschema, yaml; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "chore(governance): add jsonschema dev dependency for G0 schema validation"
```

---

## Task 2: Program-contract JSON schema

**Files:**
- Create: `config/governance/program-contract.schema.json`
- Test: `tests/test_governance_contract_schema.py`

- [ ] **Step 1: Write the failing test (schema loads and rejects a bad contract)**

```python
# tests/test_governance_contract_schema.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_governance_contract_schema.py -q`
Expected: FAIL (`FileNotFoundError` — schema file does not exist yet).

- [ ] **Step 3: Create the schema**

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "additionalProperties": true,
  "required": ["schema_version", "program_id", "governance_contract_revision",
               "status", "north_star", "canonical_sources", "execution",
               "authority", "forbidden_without_a3"],
  "properties": {
    "schema_version": {"const": 1},
    "program_id": {"type": "string"},
    "governance_contract_revision": {"type": "integer", "minimum": 1},
    "revision": {"type": "string"},
    "status": {"enum": ["active", "superseded"]},
    "north_star": {
      "type": "object",
      "required": ["current_target", "future_target", "live_is_currently_authorized"],
      "properties": {
        "current_target": {"type": "string"},
        "future_target": {"type": "string"},
        "live_is_currently_authorized": {"const": false}
      }
    },
    "canonical_sources": {"type": "object"},
    "execution": {
      "type": "object",
      "required": ["require_ci"],
      "properties": {
        "require_ci": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["name", "enforcement"],
            "properties": {
              "name": {"type": "string"},
              "enforcement": {"enum": ["active", "pending"]},
              "effective_after": {"type": "string"}
            },
            "allOf": [{
              "if": {"properties": {"enforcement": {"const": "pending"}}},
              "then": {"required": ["effective_after"]}
            }]
          }
        }
      }
    },
    "authority": {"type": "object"},
    "forbidden_without_a3": {"type": "array", "minItems": 1, "items": {"type": "string"}}
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_governance_contract_schema.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add config/governance/program-contract.schema.json tests/test_governance_contract_schema.py
git commit -m "feat(governance): add program-contract JSON schema with pending-CI rule"
```

---

## Task 3: Program contract YAML

**Files:**
- Create: `config/governance/program-contract.yaml`
- Test: `tests/test_governance_contract_schema.py` (extend)

- [ ] **Step 1: Add the failing test (real contract validates + safety invariants)**

```python
def test_program_contract_validates_and_holds_safety_invariants():
    schema = _load_json("program-contract.schema.json")
    contract = yaml.safe_load((GOV / "program-contract.yaml").read_text())
    jsonschema.validate(contract, schema)
    assert contract["north_star"]["live_is_currently_authorized"] is False
    assert contract["forbidden_without_a3"]  # non-empty
    ci = {e["name"]: e for e in contract["execution"]["require_ci"]}
    assert ci["governance-consistency"]["enforcement"] == "pending"
    assert ci["governance-consistency"]["effective_after"] == "G0.2"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_governance_contract_schema.py::test_program_contract_validates_and_holds_safety_invariants -q`
Expected: FAIL (`FileNotFoundError`).

- [ ] **Step 3: Create the contract** (copy the full YAML from spec §4.1, with the structured `require_ci` from spec §4.1/§4.3)

Create `config/governance/program-contract.yaml` exactly as in spec §4.1. The `execution.require_ci` block MUST be the structured form:

```yaml
  require_ci:
    - name: Main Gate
      enforcement: active
    - name: SI v2 Offline Smoke
      enforcement: active
    - name: governance-consistency
      enforcement: pending
      effective_after: G0.2
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_governance_contract_schema.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add config/governance/program-contract.yaml tests/test_governance_contract_schema.py
git commit -m "feat(governance): add machine-readable program contract"
```

---

## Task 4: Canonical-roadmap JSON schema

**Files:**
- Create: `config/governance/canonical-roadmap.schema.json`
- Test: `tests/test_governance_contract_schema.py` (extend)

- [ ] **Step 1: Add failing tests (schema valid; rejects unknown execution_class)**

```python
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_governance_contract_schema.py -k roadmap_schema -q`
Expected: FAIL (`FileNotFoundError`).

- [ ] **Step 3: Create the schema**

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "additionalProperties": false,
  "required": ["roadmap_revision", "governance_contract_revision", "phases"],
  "properties": {
    "roadmap_revision": {"type": "integer", "minimum": 1},
    "governance_contract_revision": {"type": "integer", "minimum": 1},
    "phases": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["id", "title", "status", "dependencies", "exit_gate"],
        "properties": {
          "id": {"type": "string"},
          "title": {"type": "string"},
          "status": {"enum": ["pending", "in_progress", "blocked", "complete"]},
          "dependencies": {"type": "array", "items": {"type": "string"}},
          "exit_gate": {"type": "string"},
          "issue": {"type": "integer"},
          "issues": {"type": "array", "items": {"type": "integer"}},
          "execution_class": {"enum": ["A0", "A1", "A2", "A3"]},
          "requires_external_mandate": {"type": "boolean"}
        }
      }
    }
  }
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m pytest tests/test_governance_contract_schema.py -k roadmap_schema -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add config/governance/canonical-roadmap.schema.json tests/test_governance_contract_schema.py
git commit -m "feat(governance): add canonical-roadmap JSON schema"
```

---

## Task 5: Canonical roadmap YAML (with DAG acyclicity test)

**Files:**
- Create: `config/governance/canonical-roadmap.yaml`
- Test: `tests/test_governance_contract_schema.py` (extend)

- [ ] **Step 1: Add failing tests (validates; DAG acyclic; deps resolve; contract-revision matches)**

```python
def _toposort_ok(phases):
    graph = {p["id"]: set(p["dependencies"]) for p in phases}
    ids = set(graph)
    for deps in graph.values():
        assert deps <= ids  # every dependency is a real phase
    resolved, guard = set(), 0
    while len(resolved) < len(graph) and guard <= len(graph):
        for pid, deps in graph.items():
            if pid not in resolved and deps <= resolved:
                resolved.add(pid)
        guard += 1
    return len(resolved) == len(graph)


def test_canonical_roadmap_valid_acyclic_and_revision_aligned():
    schema = _load_json("canonical-roadmap.schema.json")
    roadmap = yaml.safe_load((GOV / "canonical-roadmap.yaml").read_text())
    jsonschema.validate(roadmap, schema)
    assert _toposort_ok(roadmap["phases"])  # no cycles, deps resolvable
    contract = yaml.safe_load((GOV / "program-contract.yaml").read_text())
    assert roadmap["governance_contract_revision"] == contract["governance_contract_revision"]
    ids = [p["id"] for p in roadmap["phases"]]
    assert ids == ["G0", "A", "B", "C", "D", "E", "F", "G", "H"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_governance_contract_schema.py -k canonical_roadmap -q`
Expected: FAIL (`FileNotFoundError`).

- [ ] **Step 3: Create the roadmap** exactly as in spec §4.2 (phases G0–H, statuses, dependencies, exit gates, issue links). Set `governance_contract_revision: 1` to match the contract.

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m pytest tests/test_governance_contract_schema.py -q`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
git add config/governance/canonical-roadmap.yaml tests/test_governance_contract_schema.py
git commit -m "feat(governance): add canonical roadmap DAG (G0-H)"
```

---

## Task 6: Deterministic renderer + Derived View

**Files:**
- Create: `orchestrator/scripts/render_canonical_roadmap.py`
- Create: `docs/roadmap/canonical-program-roadmap.md` (generated)
- Test: `tests/test_render_canonical_roadmap.py`

- [ ] **Step 1: Write failing tests (idempotent render; committed file equals render; header present)**

```python
# tests/test_render_canonical_roadmap.py
import subprocess
from pathlib import Path

RENDER = "orchestrator/scripts/render_canonical_roadmap.py"
OUT = Path("docs/roadmap/canonical-program-roadmap.md")


def _render_to_string():
    return subprocess.run(
        ["python3", RENDER, "--stdout"], capture_output=True, text=True, check=True
    ).stdout


def test_render_is_deterministic():
    assert _render_to_string() == _render_to_string()


def test_render_has_do_not_edit_header():
    assert "GENERATED FROM config/governance/canonical-roadmap.yaml" in _render_to_string()
    assert "DO NOT EDIT MANUALLY" in _render_to_string()


def test_committed_markdown_matches_render():
    assert OUT.read_text() == _render_to_string()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_render_canonical_roadmap.py -q`
Expected: FAIL (renderer script missing).

- [ ] **Step 3: Implement the renderer** (deterministic: stable ordering, no timestamps)

```python
#!/usr/bin/env python3
"""Deterministic renderer: canonical-roadmap.yaml -> Derived-View Markdown.

The Markdown output carries NO authority (spec §2). Only the YAML is canonical.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import yaml

SRC = Path("config/governance/canonical-roadmap.yaml")
DST = Path("docs/roadmap/canonical-program-roadmap.md")
HEADER = (
    "<!--\n"
    "GENERATED FROM config/governance/canonical-roadmap.yaml\n"
    "DO NOT EDIT MANUALLY\n"
    "-->\n"
)


def render(data: dict) -> str:
    lines = [HEADER, "# Canonical Program Roadmap\n",
             f"Roadmap revision: {data['roadmap_revision']}  ",
             f"Governance contract revision: {data['governance_contract_revision']}\n",
             "| Phase | Title | Status | Depends on | Exit gate | Issue(s) | Class |",
             "|---|---|---|---|---|---|---|"]
    for p in data["phases"]:
        deps = ", ".join(p["dependencies"]) or "—"
        issues = p.get("issues") or ([p["issue"]] if "issue" in p else [])
        issues_s = ", ".join(f"#{i}" for i in issues) or "—"
        cls = p.get("execution_class", "—")
        lines.append(
            f"| {p['id']} | {p['title']} | {p['status']} | {deps} "
            f"| {p['exit_gate']} | {issues_s} | {cls} |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stdout", action="store_true", help="print instead of writing")
    args = ap.parse_args()
    out = render(yaml.safe_load(SRC.read_text()))
    if args.stdout:
        print(out, end="")
    else:
        DST.write_text(out)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Generate the committed Markdown**

Run: `python3 orchestrator/scripts/render_canonical_roadmap.py`
Expected: `docs/roadmap/canonical-program-roadmap.md` created.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_render_canonical_roadmap.py -q`
Expected: PASS (3 passed).

- [ ] **Step 6: Commit**

```bash
git add orchestrator/scripts/render_canonical_roadmap.py docs/roadmap/canonical-program-roadmap.md tests/test_render_canonical_roadmap.py
git commit -m "feat(governance): add deterministic roadmap renderer and Derived View"
```

---

## Task 7: Governance ADR (Proposed)

**Files:**
- Create: `docs/decisions/ADR-2026-07-19-canonical-program-governance.md`

- [ ] **Step 1: Write the ADR with `Status: Proposed`**

Include: context (contradictory authority), decision (authority classes, contract as authoritative source, proposal→ADR→config promotion, direction vs. status-reconciliation change classes, roles), the explicit **no-self-ratification** bootstrap rule (spec §0.2), and consequences. Front-matter:

```markdown
---
Status: Proposed
Owner: Luke / GoLukeEnviro
Date: 2026-07-19
---
```

- [ ] **Step 2: Verify it references the contract and roadmap paths**

Run: `grep -c "config/governance/program-contract.yaml" docs/decisions/ADR-2026-07-19-canonical-program-governance.md`
Expected: ≥ 1.

- [ ] **Step 3: Commit**

```bash
git add docs/decisions/ADR-2026-07-19-canonical-program-governance.md
git commit -m "docs(adr): add canonical program governance ADR (Proposed)"
```

---

## Task 8: AGENTS.md canonical-source reference (minimal-touch)

**Files:**
- Modify: `AGENTS.md`

- [ ] **Step 1: Add a small reference block only** (do NOT rewrite existing safety/loop content — spec §3, minimal-touch)

Add a section such as:

```markdown
## Canonical program governance

The authoritative program direction lives in `config/governance/program-contract.yaml`
and `config/governance/canonical-roadmap.yaml` (see
ADR-2026-07-19-canonical-program-governance). `docs/roadmap/canonical-program-roadmap.md`
is a generated Derived View with no independent authority. Chats, reports, and
proposals are advisory until merged, Accepted, and represented in the contract.
```

- [ ] **Step 2: Verify no substantive safety content was removed**

Run: `git diff AGENTS.md | grep '^-' | grep -v '^---'`
Expected: no removed safety lines (only additions).

- [ ] **Step 3: Commit**

```bash
git add AGENTS.md
git commit -m "docs(agents): reference canonical program contract (minimal-touch)"
```

---

## Task 9: Proposal header convention

**Files:**
- Create: `docs/proposals/README.md`

- [ ] **Step 1: Document the required proposal frontmatter** (spec §5)

```markdown
# Proposals (advisory only)

Every proposal is `docs/proposals/<id>-<name>.md` with this frontmatter:

​```yaml
authority: advisory
status: proposed        # proposed | REJECTED | DEFERRED | ACCEPTED_WITH_CHANGES | PROMOTED_TO_ADR
author: <name>
created_at: <utc>
affects_phases: [<ids>]
supersedes: null
​```

A proposal is never binding. Only `PROMOTED_TO_ADR` plus a merged Accepted ADR
and contract/roadmap update changes direction.
```

- [ ] **Step 2: Commit**

```bash
git add docs/proposals/README.md
git commit -m "docs(proposals): add advisory proposal header convention"
```

---

## Task 10: State-file governance revision fields

**Files:**
- Modify: `docs/state/current-operational-state.md`

- [ ] **Step 1: Add the decoupled revision fields** (spec §6) near the top, e.g. in a fenced block:

```yaml
governance_contract_revision: 1
roadmap_revision_observed: 1
roadmap_observed_at_utc: 2026-07-19T00:00:00Z
```

Add a one-line note that `governance_contract_revision` is strictly checked while `roadmap_revision_observed` is informational and does not force a state touch on ordinary roadmap status changes.

- [ ] **Step 2: Verify the field is present and matches the contract**

Run: `grep -n "governance_contract_revision: 1" docs/state/current-operational-state.md`
Expected: match.

- [ ] **Step 3: Commit**

```bash
git add docs/state/current-operational-state.md
git commit -m "docs(state): add decoupled governance/roadmap revision fields"
```

---

## Task 11: Supersede competing roadmaps (verify first)

**Files:**
- Modify (only genuine competitors): `docs/roadmap/implementation-roadmap.md`, `docs/roadmap/live-readiness-roadmap-rainbow-si-v2-2026-07-10.md`, `docs/roadmap/roadmap-v2-blocker-first-runtime-ownership.md`, `docs/roadmap/simplified-target-architecture-roadmap-2026-07-14.md`, `docs/roadmaps/SI_V2_CONTINUOUS_IMPLEMENTATION_ROADMAP.md`

- [ ] **Step 1: Confirm each file actually asserts program direction** (spec §11). Read each; if a file is historical evidence rather than a competing roadmap, leave it untouched and record that decision in the report (Task 13). Do NOT edit historical reports/evidence/context.

- [ ] **Step 2: Prepend the small header to each genuine competitor only**

```yaml
---
authority: historical
status: superseded
superseded_by: config/governance/canonical-roadmap.yaml
---
```

- [ ] **Step 3: Verify only headers changed**

Run: `git diff --stat docs/roadmap docs/roadmaps`
Expected: small insertions per touched file, no body rewrites.

- [ ] **Step 4: Commit**

```bash
git add docs/roadmap/<files> docs/roadmaps/<file>
git commit -m "docs(roadmap): mark competing roadmaps superseded by canonical roadmap"
```

---

## Task 12: Evidence report + full local gate

**Files:**
- Create: `docs/reports/g0-1-governance-contract-2026-07-19.md`

- [ ] **Step 1: Run the full root test suite locally**

Run: `python3 -m pytest tests -q`
Expected: PASS (existing suite + the new schema/renderer tests).

- [ ] **Step 2: Run ruff on the new Python**

Run: `ruff check orchestrator/scripts/render_canonical_roadmap.py`
Expected: no errors.

- [ ] **Step 3: Write the evidence report** documenting: the exact base SHA (`ff791d69…`), files created/modified, per-file supersede decisions (which roadmaps were competitors vs. left alone), test output, and confirmation of no runtime mutation.

- [ ] **Step 4: Commit**

```bash
git add docs/reports/g0-1-governance-contract-2026-07-19.md
git commit -m "docs(report): G0.1 governance-contract evidence"
```

---

## Task 13: Open PR; ADR acceptance flip on exact head (human-gated)

- [ ] **Step 1: Push branch and open the G0.1 PR** with the ADR still reading `Status: Proposed`. Link the G0.1 issue.

- [ ] **Step 2: Request Luke's explicit confirmation** in the PR/issue. **Do not merge.**

- [ ] **Step 3: After confirmation, on the exact same PR head**, flip the ADR to `Status: Accepted`:

```bash
# edit docs/decisions/ADR-2026-07-19-canonical-program-governance.md: Status: Accepted
git add docs/decisions/ADR-2026-07-19-canonical-program-governance.md
git commit -m "docs(adr): accept canonical program governance ADR (Luke-confirmed)"
git push
```

- [ ] **Step 4: Re-verify CI is green on the accepted head** before merge. A merged `Proposed` ADR is forbidden (spec §0.2).

- [ ] **Step 5: Human-only merge.** After merge, in a **separate** step, repoint tracker #605 to the G0.2 task (not part of this PR diff).

---

## Done criteria (spec §12, G0.1)

- Both YAMLs validate against their schemas (tests in this PR).
- Renderer is deterministic; committed Derived View equals its output.
- ADR flipped `Proposed → Accepted` on the exact PR head, re-checked, then merged.
- No runtime/Docker/trading/kill-switch/credential/service/socket/controller mutation.
- Human-only merge; tracker repointed separately post-merge.
