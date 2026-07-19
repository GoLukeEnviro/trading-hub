# G0.2 — Governance Enforcement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the second A1 PR that makes the G0.1 governance layer enforceable: an offline consistency validator, its negative-case test suite, a `governance-consistency` CI job (with regenerate-and-diff), a governance extension to the read-only merge-guard, and a **code-only, disabled** broker/writer governance hook with integration tests.

**Architecture:** Offline CI checks repository consistency only (no GitHub API); the live merge-guard/broker checks GitHub state at merge time. The broker/writer hook is written as an inert (disabled) code path — nothing is activated. No runtime, service, socket, credential, enable-switch, broker, or controller state is changed.

**Tech Stack:** Python 3.11, `pyyaml`, `jsonschema`, `pytest`, `ruff`, GitHub Actions.

**Spec:** [`docs/superpowers/specs/2026-07-19-canonical-program-governance-g0-design.md`](../specs/2026-07-19-canonical-program-governance-g0-design.md)
**Depends on:** G0.1 merged (contract, roadmap, schemas, renderer present on `main`).

---

## Critical preconditions (read before Task 1)

- **G0.1 must be merged first.** This plan imports the G0.1 renderer and canonical files. If they are not on `main`, STOP.
- **Branch from current `main`** (post-G0.1). Per spec §10.4 the original worktree base (`b18bbf0`) is behind main and lacks PR #640's root-broker merge controller; the broker hook (Task 6) needs it.
- **Human-only merge** (spec §10.3) — touches governance/guard files.
- **CI-scope limit (spec §10.2, correction 15):** this PR may add a non-soft-fail `governance-consistency` job, but must NOT flip GitHub branch-protection to "required" — that is a separate GitHub config change made by Luke, outside the PR diff.
- **Validator scope limit (spec §7.2):** structured metadata only (schemas + defined frontmatter fields). No free-text scanning of document bodies, historical reports, evidence, or legacy prose.
- **No `git add .`; stage by path. No secrets.**

---

## File Structure

| Path | Responsibility | Action |
|---|---|---|
| `orchestrator/scripts/governance_consistency_check.py` | Offline consistency validator (spec §7.1/§7.2) | Create |
| `tests/test_governance_consistency.py` | Negative-case suite (spec §7.5) | Create |
| `.github/workflows/main-gate.yml` | Add `governance-consistency` job + regenerate-and-diff | Modify |
| `orchestrator/scripts/roadmap_merge_guard.py` | Live governance rules extension (spec §7.4) | Modify |
| `tests/test_roadmap_merge_guard.py` | Extend for governance rules | Modify |
| `orchestrator/scripts/roadmap_merge_controller_broker.py` | Add `check_governance_scope` + wire into `evaluate_guard` (spec §7.4) | Modify |
| `tests/test_roadmap_merge_controller.py` | Governance-scope check tests | Modify |
| `docs/reports/g0-2-governance-enforcement-<date>.md` | Evidence report | Create |

---

## Task 1: Validator skeleton — schema validation of both YAMLs

**Files:**
- Create: `orchestrator/scripts/governance_consistency_check.py`
- Test: `tests/test_governance_consistency.py`

- [ ] **Step 1: Write the failing test (valid repo passes; a fixture with a schema-invalid contract fails)**

```python
# tests/test_governance_consistency.py
import shutil
import subprocess
from pathlib import Path

import pytest

CHECK = "orchestrator/scripts/governance_consistency_check.py"


def _run(cwd=None):
    return subprocess.run(["python3", CHECK], cwd=cwd, capture_output=True, text=True)


import yaml

# Files/dirs the tests mutate and the validator reads directly.
_MUTABLE = ["config/governance", "docs/roadmap", "docs/state", "AGENTS.md",
            "docs/proposals", "orchestrator/scripts"]


def _canonical_source_paths():
    """Every path listed under contract canonical_sources (spec §4.1)."""
    contract = yaml.safe_load(Path("config/governance/program-contract.yaml").read_text())
    paths = []
    for group in contract["canonical_sources"].values():
        if isinstance(group, list):
            paths.extend(group)
    return paths


def _clone_governance(tmp_path):
    """Isolated repo the validator can run against.

    Deep-copies the files the tests mutate, and ENSURES every canonical_sources
    path exists (dirs are created empty, files copied) so check_source_paths does
    not hard-fail on unrelated missing paths (e.g. SOUL.md, docs/decisions/,
    docs/reports/, docs/context/). Large evidence/context dirs are created empty
    on purpose — existence is all check_source_paths requires.
    """
    dst = tmp_path / "repo"
    for rel in _MUTABLE:
        src, target = Path(rel), dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, target) if src.is_dir() else (
            target.parent.mkdir(parents=True, exist_ok=True) or shutil.copy2(src, target))
    for rel in _canonical_source_paths():
        src, target = Path(rel), dst / rel
        if target.exists():
            continue
        if src.is_dir() or rel.endswith("/"):
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, target) if src.exists() else target.write_text("placeholder\n")
    return dst


def test_real_repo_passes():
    result = _run()
    assert result.returncode == 0, result.stdout + result.stderr


def test_schema_invalid_contract_fails(tmp_path):
    repo = _clone_governance(tmp_path)
    contract = repo / "config/governance/program-contract.yaml"
    contract.write_text("schema_version: 1\nprogram_id: x\n")  # missing required
    result = _run(cwd=repo)
    assert result.returncode != 0
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_governance_consistency.py -q`
Expected: FAIL (validator missing).

- [ ] **Step 3: Implement the validator core** (schema validation + structured error reporting; exit non-zero on hard failure)

```python
#!/usr/bin/env python3
"""Offline governance consistency validator (spec §7.1/§7.2).

STRUCTURED METADATA ONLY: validates the two governance YAMLs against their JSON
schemas and inspects DEFINED FRONTMATTER FIELDS of governed Markdown. It never
free-text scans document bodies, historical reports, evidence, or legacy prose.
No GitHub API access. Exit non-zero on any hard failure; ROADMAP_RECONCILIATION_
PENDING is a warning, not a failure.
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
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m pytest tests/test_governance_consistency.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add orchestrator/scripts/governance_consistency_check.py tests/test_governance_consistency.py
git commit -m "feat(governance): add consistency validator with schema checks"
```

---

## Task 2: DAG acyclicity, dependency resolution, exactly-one-direction

**Files:**
- Modify: `orchestrator/scripts/governance_consistency_check.py`
- Modify: `tests/test_governance_consistency.py`

- [ ] **Step 1: Add failing tests (cyclic roadmap fails; two active directions fail)**

```python
def test_cyclic_roadmap_fails(tmp_path):
    repo = _clone_governance(tmp_path)
    rm = repo / "config/governance/canonical-roadmap.yaml"
    data = __import__("yaml").safe_load(rm.read_text())
    data["phases"][1]["dependencies"].append("H")  # A depends on H -> cycle
    rm.write_text(__import__("yaml").safe_dump(data))
    assert _run(cwd=repo).returncode != 0


def test_two_active_directions_fail(tmp_path):
    repo = _clone_governance(tmp_path)
    c = repo / "config/governance/program-contract.yaml"
    data = __import__("yaml").safe_load(c.read_text())
    data["canonical_sources"]["roadmap"].append("config/governance/other-roadmap.yaml")
    c.write_text(__import__("yaml").safe_dump(data))
    assert _run(cwd=repo).returncode != 0
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_governance_consistency.py -k "cyclic or two_active" -q`
Expected: FAIL (checks not implemented).

- [ ] **Step 3: Add the checks** to the validator (append after `check_schemas`):

```python
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
        HARD_FAILURES.append(f"expected exactly one authoritative roadmap, got {len(roadmaps)}")
```

Wire both into `main()` after `check_schemas()`.

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m pytest tests/test_governance_consistency.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add orchestrator/scripts/governance_consistency_check.py tests/test_governance_consistency.py
git commit -m "feat(governance): validate DAG acyclicity and single direction"
```

---

## Task 3: Source-path existence, frontmatter authority, superseded_by

**Files:**
- Modify: `orchestrator/scripts/governance_consistency_check.py`
- Modify: `tests/test_governance_consistency.py`

- [ ] **Step 1: Add failing tests (missing source path fails; advisory doc claiming canonical fails; superseded doc without `superseded_by` fails)**

```python
def test_missing_source_path_fails(tmp_path):
    repo = _clone_governance(tmp_path)
    (repo / "AGENTS.md").unlink()
    assert _run(cwd=repo).returncode != 0


def test_advisory_claiming_canonical_fails(tmp_path):
    repo = _clone_governance(tmp_path)
    p = repo / "docs/proposals/001-x.md"
    p.write_text("---\nauthority: canonical\nstatus: proposed\n---\nbody\n")
    assert _run(cwd=repo).returncode != 0
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_governance_consistency.py -k "missing_source or advisory" -q`
Expected: FAIL.

- [ ] **Step 3: Add the checks** (frontmatter parsing only — no body scan):

```python
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
```

Note: `check_source_paths` handles the `active_task` dict entry (skip non-list groups). Wire into `main()`.

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m pytest tests/test_governance_consistency.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add orchestrator/scripts/governance_consistency_check.py tests/test_governance_consistency.py
git commit -m "feat(governance): validate source paths and frontmatter authority"
```

---

## Task 4: Render-diff, AGENTS.md reference, state revision, execution-class & mandate rules

**Files:**
- Modify: `orchestrator/scripts/governance_consistency_check.py`
- Modify: `tests/test_governance_consistency.py`

- [ ] **Step 1: Add failing tests** covering the remaining §7.5 cases:

```python
def test_render_drift_fails(tmp_path):
    repo = _clone_governance(tmp_path)
    md = repo / "docs/roadmap/canonical-program-roadmap.md"
    md.write_text(md.read_text() + "\nmanually edited\n")
    assert _run(cwd=repo).returncode != 0


def test_state_contract_revision_mismatch_fails(tmp_path):
    repo = _clone_governance(tmp_path)
    st = repo / "docs/state/current-operational-state.md"
    st.write_text(st.read_text().replace("governance_contract_revision: 1",
                                         "governance_contract_revision: 2"))
    assert _run(cwd=repo).returncode != 0


def test_a2_phase_without_approval_fails(tmp_path):
    repo = _clone_governance(tmp_path)
    c = repo / "config/governance/program-contract.yaml"
    data = __import__("yaml").safe_load(c.read_text())
    data["authority"].pop("a2_requires", None)
    c.write_text(__import__("yaml").safe_dump(data))
    assert _run(cwd=repo).returncode != 0


def test_roadmap_only_status_change_warns_not_fails(tmp_path):
    """A roadmap status change with no runtime impact -> warning, exit 0."""
    repo = _clone_governance(tmp_path)
    # bump roadmap_revision without touching state runtime statements
    rm = repo / "config/governance/canonical-roadmap.yaml"
    data = __import__("yaml").safe_load(rm.read_text())
    data["roadmap_revision"] = 2
    rm.write_text(__import__("yaml").safe_dump(data))
    result = _run(cwd=repo)
    assert result.returncode == 0
    assert "ROADMAP_RECONCILIATION_PENDING" in result.stdout
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_governance_consistency.py -k "render_drift or revision_mismatch or a2_phase or status_change_warns" -q`
Expected: FAIL.

- [ ] **Step 3: Add the checks:**

```python
def check_render(roadmap_path=GOV / "canonical-roadmap.yaml") -> None:
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "render_canonical_roadmap", "orchestrator/scripts/render_canonical_roadmap.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    expected = mod.render(_load_yaml(roadmap_path))
    actual = Path("docs/roadmap/canonical-program-roadmap.md").read_text()
    if actual != expected:
        HARD_FAILURES.append("Derived-View Markdown drifted from renderer output")


def _first_fenced_yaml(text: str) -> dict:
    """Parse the first fenced code block as YAML, tolerating an info-string line.

    A ```yaml / ```text info-string is stripped before parsing; malformed YAML
    yields {} rather than raising, so a valid repo never aborts the validator.
    """
    if "```" not in text:
        return {}
    body = text.split("```", 2)[1]
    lines = body.splitlines()
    if lines and lines[0].strip() and ":" not in lines[0]:
        lines = lines[1:]  # drop bare info-string line (e.g. "yaml", "text")
    try:
        return yaml.safe_load("\n".join(lines)) or {}
    except yaml.YAMLError:
        return {}


def check_state_revision(contract: dict) -> None:
    st = Path("docs/state/current-operational-state.md").read_text()
    fm_like = _first_fenced_yaml(st)
    observed = fm_like.get("governance_contract_revision")
    if observed != contract["governance_contract_revision"]:
        HARD_FAILURES.append(
            f"state governance_contract_revision {observed} != contract "
            f"{contract['governance_contract_revision']}")


def check_authority_rules(contract: dict, roadmap: dict) -> None:
    auth = contract["authority"]
    if not auth.get("a2_requires"):
        HARD_FAILURES.append("authority.a2_requires missing/empty")
    if not auth.get("a3_requires"):
        HARD_FAILURES.append("authority.a3_requires missing/empty")
    for p in roadmap["phases"]:
        if p.get("requires_external_mandate") and not auth.get("a3_requires"):
            HARD_FAILURES.append(f"phase {p['id']} needs mandate but a3_requires absent")


def check_agents_reference() -> None:
    if "config/governance/program-contract.yaml" not in Path("AGENTS.md").read_text():
        HARD_FAILURES.append("AGENTS.md does not reference the program contract")


def check_roadmap_reconciliation() -> None:
    st = Path("docs/state/current-operational-state.md").read_text()
    fm_like = _first_fenced_yaml(st)  # shared robust parser (info-string tolerant)
    roadmap = _load_yaml(GOV / "canonical-roadmap.yaml")
    if fm_like.get("roadmap_revision_observed") != roadmap["roadmap_revision"]:
        WARNINGS.append("ROADMAP_RECONCILIATION_PENDING")
```

Wire all into `main()`. Order: schemas → dag → single_direction → source_paths → governed_frontmatter → render → state_revision (hard) → authority_rules → agents_reference → roadmap_reconciliation (warn).

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m pytest tests/test_governance_consistency.py -q`
Expected: PASS (all §7.5 cases).

- [ ] **Step 5: Lint + commit**

```bash
ruff check orchestrator/scripts/governance_consistency_check.py
git add orchestrator/scripts/governance_consistency_check.py tests/test_governance_consistency.py
git commit -m "feat(governance): validate render-diff, state revision, authority, mandate rules"
```

---

## Task 5: CI job — `governance-consistency` (non-soft-fail, with regenerate-and-diff)

**Files:**
- Modify: `.github/workflows/main-gate.yml`

- [ ] **Step 1: Add a new job** (a distinct job name is what branch protection targets later; do NOT change branch protection here — spec §10.2 correction 15):

```yaml
  governance-consistency:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          python -m pip install -e ".[dev]"
      - name: Regenerate Derived View and check for drift
        run: |
          python orchestrator/scripts/render_canonical_roadmap.py
          git diff --exit-code docs/roadmap/canonical-program-roadmap.md
      - name: Governance consistency check
        run: |
          python orchestrator/scripts/governance_consistency_check.py
      - name: Governance tests
        run: |
          python -m pytest tests/test_governance_consistency.py tests/test_render_canonical_roadmap.py tests/test_governance_contract_schema.py -q
```

- [ ] **Step 2: Validate workflow YAML syntax**

Run: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/main-gate.yml'))"`
Expected: no error.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/main-gate.yml
git commit -m "ci(governance): add non-soft-fail governance-consistency job"
```

> **Note:** Making this a *required* status check is a separate GitHub branch-protection change performed by Luke, not part of this PR.

---

## Task 6: Merge-guard governance extension + broker code-only hook

**Confirmed broker module (spec §10.4 lookup resolved):** merging `origin/main`
(`ff791d69`) brought in PR #640's controller. The real files are:

- `orchestrator/scripts/roadmap_merge_controller_broker.py` — root-owned broker;
  already has a `GovernanceBlock(BrokerError)` exception (`message`, `blockers:
  list[str]`), a `check_denylist`/`check_paths_allowlist`/`check_a1_triggers`
  family of `check_X(...) -> list[str]` pure functions, and `evaluate_guard(...)
  -> tuple[bool, list[str]]` which is called at the merge decision point
  (`handle_merge_request`, around line 1016) and its blockers are folded into
  `MergeResponse.blockers`.
- `orchestrator/scripts/roadmap_merge_controller.py` — UID-10000 client.
- Activation is already fail-closed via `is_controller_enabled(switch_path,
  halt_path)`: requires a root:root-owned `0644`-or-stricter enable-switch file
  containing exactly `true`, AND no halt file. **This PR creates neither file**,
  so the whole controller stays disabled regardless of what code is added.

This means the governance hook does not need its own bespoke "disabled" flag —
it can follow the exact same `check_X(...) -> list[str]` convention as
`check_denylist` and be wired into the real `evaluate_guard` blocker
aggregation, and it is still inert because the broker service is never started
or enabled by this PR.

**Files:**
- Modify: `orchestrator/scripts/roadmap_merge_guard.py`
- Modify: `tests/test_roadmap_merge_guard.py`
- Modify: `orchestrator/scripts/roadmap_merge_controller_broker.py`
- Modify: `tests/test_roadmap_merge_controller.py`

- [ ] **Step 1: Write failing merge-guard test** (guard blocks a PR whose selected task is roadmap-incompatible):

```python
# in tests/test_roadmap_merge_guard.py
def test_guard_blocks_roadmap_incompatible_task():
    from orchestrator.scripts.roadmap_merge_guard import governance_task_compatible
    # selected task not present / dependencies unmet in canonical roadmap
    assert governance_task_compatible(selected_phase="B", roadmap_status={"B": "blocked"}) is False
    assert governance_task_compatible(selected_phase="G0", roadmap_status={"G0": "in_progress"}) is True
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_roadmap_merge_guard.py -k roadmap_incompatible -q`
Expected: FAIL (function missing).

- [ ] **Step 3: Implement `governance_task_compatible`** in `roadmap_merge_guard.py` (read-only; loads canonical roadmap; a task is mergeable only if its phase is `in_progress`/`pending` and dependencies are complete). Keep the existing marker/check logic intact.

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m pytest tests/test_roadmap_merge_guard.py -q`
Expected: PASS.

- [ ] **Step 5: Write the broker governance-check test** (pure function, same shape as `check_denylist`):

```python
# in tests/test_roadmap_merge_controller.py
from orchestrator.scripts.roadmap_merge_controller_broker import check_governance_scope

def test_check_governance_scope_blocks_governance_files_without_adr_scope():
    blockers = check_governance_scope(
        changed_files=["config/governance/program-contract.yaml"],
        pr_has_accepted_adr_scope=False,
        human_only_files=["AGENTS.md", "config/governance/program-contract.yaml"],
    )
    assert blockers  # non-empty: governance file changed without ADR scope


def test_check_governance_scope_allows_status_reconciliation_with_adr_scope():
    blockers = check_governance_scope(
        changed_files=["config/governance/canonical-roadmap.yaml"],
        pr_has_accepted_adr_scope=True,
        human_only_files=["AGENTS.md", "config/governance/canonical-roadmap.yaml"],
    )
    assert blockers == []
```

- [ ] **Step 6: Run to verify it fails**

Run: `python3 -m pytest tests/test_roadmap_merge_controller.py -k check_governance_scope -q`
Expected: FAIL (function missing).

- [ ] **Step 7: Implement `check_governance_scope`** in `roadmap_merge_controller_broker.py`, next to `check_denylist`/`check_paths_allowlist`, following the exact same pure-function convention (returns `list[str]`, no side effects, no GitHub calls):

```python
def check_governance_scope(
    changed_files: list[str],
    *,
    pr_has_accepted_adr_scope: bool,
    human_only_files: list[str],
) -> list[str]:
    """Governance-file change control (spec §7.1, §9).

    Returns blocker strings. Empty = no governance-scope violation. A PR that
    touches any human-only / governance file must carry an accepted-ADR scope
    marker; this mirrors check_denylist's shape and is folded into
    evaluate_guard's blockers the same way. Present, tested, callable — but
    still inert: this PR does not create the enable-switch file, so
    is_controller_enabled() keeps the whole broker disabled.
    """
    touched_governed = [f for f in changed_files if f in human_only_files]
    if touched_governed and not pr_has_accepted_adr_scope:
        return [f"GOVERNANCE_SCOPE:{f}:no_accepted_adr" for f in touched_governed]
    return []
```

- [ ] **Step 8: Wire it into `evaluate_guard`'s blocker aggregation** (append at the end of `evaluate_guard`, before the `return`):

```python
    governance_blockers = check_governance_scope(
        changed_files=snapshot.get("changed_files", []),
        pr_has_accepted_adr_scope=snapshot.get("pr_has_accepted_adr_scope", False),
        human_only_files=_HUMAN_ONLY_FILES,
    )
    blockers.extend(governance_blockers)
```

Add a module-level `_HUMAN_ONLY_FILES` list near the existing allowlist/denylist
constants: `AGENTS.md`, `config/governance/program-contract.yaml`,
`config/governance/program-contract.schema.json`,
`config/governance/canonical-roadmap.yaml`,
`config/governance/canonical-roadmap.schema.json`,
`orchestrator/scripts/governance_consistency_check.py`,
`orchestrator/scripts/roadmap_merge_guard.py`,
`orchestrator/scripts/roadmap_merge_controller_broker.py`. Add a comment above
the wiring: `# Present and active in evaluate_guard's pure logic, but the
broker process itself stays disabled: is_controller_enabled() requires an
enable-switch file this PR does not create (spec §7.4).`

- [ ] **Step 9: Run to verify it passes**

Run: `python3 -m pytest tests/test_roadmap_merge_controller.py -k governance -q`
Expected: PASS.

- [ ] **Step 10: Run the full broker/controller/guard suite (regression check)**

Run: `python3 -m pytest tests/test_roadmap_merge_guard.py tests/test_roadmap_merge_controller.py -q`
Expected: PASS, no regressions in existing `evaluate_guard`/`check_toctou` tests.

- [ ] **Step 11: Lint + commit**

```bash
ruff check orchestrator/scripts/roadmap_merge_guard.py orchestrator/scripts/roadmap_merge_controller_broker.py
git add orchestrator/scripts/roadmap_merge_guard.py tests/test_roadmap_merge_guard.py orchestrator/scripts/roadmap_merge_controller_broker.py tests/test_roadmap_merge_controller.py
git commit -m "feat(governance): extend merge-guard and wire governance-scope check into broker evaluate_guard"
```

---

## Task 7: Full gate + evidence report

**Files:**
- Create: `docs/reports/g0-2-governance-enforcement-2026-07-19.md`

- [ ] **Step 1: Run the whole root suite + the validator**

Run:
```bash
python3 -m pytest tests -q
python3 orchestrator/scripts/governance_consistency_check.py
```
Expected: all tests PASS; validator prints `governance-consistency OK` (exit 0).

- [ ] **Step 2: Confirm no activation happened** (no service/socket/enable-switch/credential change):

Run: `git diff --name-only origin/main... | grep -Ev '^(orchestrator/scripts/(governance_consistency_check|roadmap_merge_guard|roadmap_merge_controller_broker)\.py|tests/|\.github/workflows/main-gate\.yml|docs/reports/)$' || echo "only expected files changed"`
Expected: only expected files changed; no `.env`, no `*.service`, no enable-switch file created.

- [ ] **Step 3: Write the evidence report** documenting: the confirmed broker module (`roadmap_merge_controller_broker.py`, discovered via the `origin/main` merge), validator output, negative-test results (red→green), the CI job addition, and explicit confirmation that `is_controller_enabled()`'s required enable-switch file was not created — the broker remains disabled — and no branch-protection change was made.

- [ ] **Step 4: Commit**

```bash
git add docs/reports/g0-2-governance-enforcement-2026-07-19.md
git commit -m "docs(report): G0.2 governance-enforcement evidence"
```

---

## Task 8: PR + human-only merge

- [ ] **Step 1: Push branch and open the G0.2 PR.** Link the G0.2 issue (tracker #605 already repointed to G0.2 after G0.1).

- [ ] **Step 2: Ensure `main-gate` (incl. new `governance-consistency` job) and `SI v2 Offline Smoke` are green.**

- [ ] **Step 3: Request Luke's review; human-only merge** (touches governance/guard files, spec §10.3).

- [ ] **Step 4: After merge, in a separate step, repoint tracker #605 to the Phase-A task** (not part of this PR diff). Optionally, Luke flips branch protection to make `governance-consistency` a required check (separate GitHub config, spec §10.2).

---

## Done criteria (spec §12, G0.2)

- Validator passes locally and in CI; every §7.5 negative test is red→green.
- Regenerate-and-diff CI enforcement fails on any Derived-View drift.
- Broker/writer governance hook exists as a tested, **disabled** code path with an integration test proving it blocks a non-compliant merge — not merely a merge-guard change.
- Both PRs A1 and human-only; no runtime/Docker/trading/kill-switch/credential/service/socket/enable-switch/broker/controller mutation; no branch-protection change in the PR.
