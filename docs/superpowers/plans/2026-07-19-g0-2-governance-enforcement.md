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
| `<root-broker merge controller from PR #640>` / `orchestrator/scripts/repo_writer.py` | Code-only, disabled governance hook (spec §7.4) | Modify |
| `tests/test_governance_broker_hook.py` | Integration test: inert path blocks non-compliant merge | Create |
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


def _clone_governance(tmp_path):
    """Copy the real governance tree into an isolated dir the check can target."""
    dst = tmp_path / "repo"
    for rel in ["config/governance", "docs/roadmap", "docs/state", "AGENTS.md",
                "docs/proposals", "orchestrator/scripts"]:
        src = Path(rel)
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, target)
        else:
            shutil.copy2(src, target)
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


def check_proposal_frontmatter() -> None:
    for md in Path("docs/proposals").glob("*.md"):
        if md.name == "README.md":
            continue
        fm = _frontmatter(md.read_text())
        if fm.get("authority") == "canonical":
            HARD_FAILURES.append(f"advisory doc claims canonical: {md}")
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


def check_state_revision(contract: dict) -> None:
    st = Path("docs/state/current-operational-state.md").read_text()
    fm_like = yaml.safe_load(st.split("```")[1]) if "```" in st else {}
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
    fm_like = yaml.safe_load(st.split("```")[1]) if "```" in st else {}
    roadmap = _load_yaml(GOV / "canonical-roadmap.yaml")
    if fm_like.get("roadmap_revision_observed") != roadmap["roadmap_revision"]:
        WARNINGS.append("ROADMAP_RECONCILIATION_PENDING")
```

Wire all into `main()`. Order: schemas → dag → single_direction → source_paths → proposal_frontmatter → render → state_revision (hard) → authority_rules → agents_reference → roadmap_reconciliation (warn).

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

## Task 6: Merge-guard governance extension + broker/writer code-only hook

**Files:**
- Modify: `orchestrator/scripts/roadmap_merge_guard.py`
- Modify: `tests/test_roadmap_merge_guard.py`
- Modify: `<root-broker merge controller from PR #640>` and/or `orchestrator/scripts/repo_writer.py`
- Create: `tests/test_governance_broker_hook.py`

- [ ] **Step 1: Locate the actual broker/controller module** (spec §10.4). Confirm PR #640's root-broker merge controller path on current `main`. Record the confirmed path in the report.

Run: `git grep -lE "governed_merge|merge.?broker|roadmap.?merge.?controller" -- '*.py'`
Expected: identify the controller/writer module(s).

- [ ] **Step 2: Write failing merge-guard test** (guard blocks a PR whose selected task is roadmap-incompatible):

```python
# in tests/test_roadmap_merge_guard.py
def test_guard_blocks_roadmap_incompatible_task():
    from orchestrator.scripts.roadmap_merge_guard import governance_task_compatible
    # selected task not present / dependencies unmet in canonical roadmap
    assert governance_task_compatible(selected_phase="B", roadmap_status={"B": "blocked"}) is False
    assert governance_task_compatible(selected_phase="G0", roadmap_status={"G0": "in_progress"}) is True
```

- [ ] **Step 3: Run to verify it fails**

Run: `python3 -m pytest tests/test_roadmap_merge_guard.py -k roadmap_incompatible -q`
Expected: FAIL (function missing).

- [ ] **Step 4: Implement `governance_task_compatible`** in `roadmap_merge_guard.py` (read-only; loads canonical roadmap; a task is mergeable only if its phase is `in_progress`/`pending` and dependencies are complete). Keep the existing marker/check logic intact.

- [ ] **Step 5: Write the broker hook integration test (inert path blocks non-compliant merge)**

```python
# tests/test_governance_broker_hook.py
def test_broker_governance_hook_is_disabled_but_blocks_when_invoked():
    from <broker_module> import governance_precheck  # exact path from Step 1
    # The hook exists, is disabled by default (no activation), and when explicitly
    # invoked in test returns a blocking result for a non-compliant merge.
    result = governance_precheck(pr_touches_governance=True, has_accepted_adr_scope=False)
    assert result.allowed is False
    assert result.reason  # explains governance violation
```

- [ ] **Step 6: Run to verify it fails**

Run: `python3 -m pytest tests/test_governance_broker_hook.py -q`
Expected: FAIL (hook missing).

- [ ] **Step 7: Implement the inert broker/writer hook** — a `governance_precheck(...)` function that encodes the §7.1 live-guard governance rules (governance files only under Accepted-ADR scope; human-only files not touched by automated merge). It is **not wired into any active code path / not enabled**; only defined and unit-testable. Add a clear comment: `# DISABLED in G0.2: broker is not activated (spec §7.4). Code-only governance hook.`

- [ ] **Step 8: Run all guard/hook tests**

Run: `python3 -m pytest tests/test_roadmap_merge_guard.py tests/test_governance_broker_hook.py -q`
Expected: PASS.

- [ ] **Step 9: Lint + commit**

```bash
ruff check orchestrator/scripts/roadmap_merge_guard.py
git add orchestrator/scripts/roadmap_merge_guard.py tests/test_roadmap_merge_guard.py <broker_module> tests/test_governance_broker_hook.py
git commit -m "feat(governance): extend merge-guard and add disabled broker governance hook"
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

Run: `git diff --name-only origin/main... | grep -Ev '^(orchestrator/scripts/(governance_consistency_check|roadmap_merge_guard|repo_writer)\.py|tests/|\.github/workflows/main-gate\.yml|docs/reports/|<broker_module>)$' || echo "only expected files changed"`
Expected: only expected files changed; no `.env`, no `*.service`, no `enabled` files.

- [ ] **Step 3: Write the evidence report** documenting: confirmed broker/controller module path, validator output, negative-test results (red→green), the CI job addition, and explicit confirmation that the broker remains disabled and no runtime/branch-protection change was made.

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
