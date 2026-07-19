# G0.2 — Governance Enforcement Evidence Report

**Date:** 2026-07-19
**Phase:** G0 (Canonical Program Governance) — exit gate `governance_consistency_green`
**Execution class:** A1 (repository-only)
**Issue:** #644
**Branch:** `docs/g0-2-governance-enforcement-2026-07-19`
**Base:** `origin/main` at `b8827b0` (post-G0.1)
**Spec:** `docs/superpowers/specs/2026-07-19-canonical-program-governance-g0-design.md` §7, §10.2
**Plan:** `docs/superpowers/plans/2026-07-19-g0-2-governance-enforcement.md`

## Goal

Land the second A1 PR that makes the G0.1 governance layer enforceable: an
offline consistency validator, its negative-case test suite, a
`governance-consistency` CI job (with regenerate-and-diff), a governance
extension to the read-only merge-guard, and a code-only, disabled broker/writer
governance hook with integration tests.

## Delivered artifacts

| Path | Responsibility | Action |
|---|---|---|
| `orchestrator/scripts/governance_consistency_check.py` | Offline consistency validator (spec §7.1/§7.2) | Created |
| `tests/test_governance_consistency.py` | Negative-case suite (spec §7.5) | Created |
| `.github/workflows/main-gate.yml` | `governance-consistency` job + regenerate-and-diff | Modified |
| `orchestrator/scripts/roadmap_merge_guard.py` | Live governance rules extension: `governance_task_compatible` (spec §7.4) | Modified |
| `tests/test_roadmap_merge_guard.py` | Governance compatibility tests | Modified |
| `orchestrator/scripts/roadmap_merge_controller_broker.py` | `check_governance_scope` + `_HUMAN_ONLY_FILES` + `evaluate_guard` wiring (spec §7.4) | Modified |
| `tests/test_roadmap_merge_controller.py` | Governance-scope check tests | Modified |

## Validator checks (spec §7.1/§7.2)

The validator (`governance_consistency_check.py`) implements all offline checks
with structured-metadata-only scope (no free-text body scanning):

1. **Schema validation** — `program-contract.yaml` and `canonical-roadmap.yaml`
   validated against their JSON schemas.
2. **DAG acyclicity** — roadmap dependency graph is acyclic; unknown
   dependencies fail.
3. **Single direction** — exactly one authoritative roadmap source
   (`canonical_sources.roadmap`).
4. **Source-path existence** — all `canonical_sources` paths exist.
5. **Governed frontmatter** — `authority: canonical` in advisory docs fails;
   `status: superseded` without `superseded_by` fails. Scope: `docs/proposals/`,
   `docs/roadmap/`, `docs/roadmaps/` (frontmatter only).
6. **Render-diff** — `docs/roadmap/canonical-program-roadmap.md` equals the
   renderer output (regenerate-and-diff).
7. **State revision** — `governance_contract_revision` in
   `docs/state/current-operational-state.md` matches the contract (hard fail).
8. **Authority rules** — `authority.a2_requires` and `a3_requires` present;
   A3-mandate phases require `a3_requires`.
9. **AGENTS.md reference** — `AGENTS.md` references
   `config/governance/program-contract.yaml`.
10. **Roadmap reconciliation** — stale `roadmap_revision_observed` emits
    `ROADMAP_RECONCILIATION_PENDING` (warning, not failure; spec §6).

## Negative-case test results (spec §7.5)

All 13 negative cases are red→green demonstrable:

| Test | Case | Result |
|---|---|---|
| `test_real_repo_passes` | Valid repo passes | ✅ PASS |
| `test_schema_invalid_contract_fails` | Schema-invalid contract | ✅ PASS |
| `test_cyclic_roadmap_fails` | Cyclic roadmap dependency | ✅ PASS |
| `test_two_active_directions_fail` | Two authoritative roadmaps | ✅ PASS |
| `test_missing_source_path_fails` | Missing canonical source path | ✅ PASS |
| `test_advisory_claiming_canonical_fails` | Advisory claiming canonical | ✅ PASS |
| `test_superseded_without_superseded_by_fails` | Superseded without `superseded_by` | ✅ PASS |
| `test_render_drift_fails` | Manually edited Derived View | ✅ PASS |
| `test_state_contract_revision_mismatch_fails` | State revision mismatch | ✅ PASS |
| `test_a2_phase_without_approval_fails` | A2 without `a2_requires` | ✅ PASS |
| `test_a3_phase_without_mandate_fails` | A3 without `a3_requires` | ✅ PASS |
| `test_agents_reference_missing_fails` | AGENTS.md without contract reference | ✅ PASS |
| `test_roadmap_only_status_change_warns_not_fails` | Stale `roadmap_revision_observed` → warning | ✅ PASS |

## Merge-guard + broker test results

| Suite | Tests | Result |
|---|---|---|
| `tests/test_roadmap_merge_guard.py` (full) | 25 (4 new `governance_task_compatible`) | ✅ 25 passed |
| `tests/test_roadmap_merge_controller.py` (full) | 36 (4 new `check_governance_scope`) | ✅ 36 passed |
| Combined regression | 60 | ✅ 60 passed, 0 regressions |

## Full root test suite

```
1082 passed, 52 skipped, 3 failed in 23.96s
```

The 3 failures are pre-existing `tests/test_render_canonical_roadmap.py` tests
that use `subprocess.run(["python3", ...])` — system Python on the Hermes
container lacks `pyyaml`. CI passes because GitHub runners have `pyyaml`
installed globally. This is a known pre-existing local-only failure (documented
in the `trading-hub-autonomous-roadmap-tick` skill) and is not introduced by
this PR.

## Validator direct execution

```
$ python orchestrator/scripts/governance_consistency_check.py
governance-consistency OK
exit: 0
```

## CI job

A new `governance-consistency` job was added to `.github/workflows/main-gate.yml`
(distinct job name for branch-protection targeting). It runs:

1. `python orchestrator/scripts/render_canonical_roadmap.py` +
   `git diff --exit-code` (regenerate-and-diff enforcement)
2. `python orchestrator/scripts/governance_consistency_check.py` (offline validator)
3. `python -m pytest tests/test_governance_consistency.py
   tests/test_render_canonical_roadmap.py tests/test_governance_contract_schema.py -q`

Non-soft-fail. Per spec §10.2 correction 15: making this a required status check
is a separate GitHub branch-protection change performed by Luke, outside this
PR diff.

## Broker activation status (spec §7.4 — inert code path)

The `check_governance_scope` function and `_HUMAN_ONLY_FILES` constant are
present, tested, and wired into `evaluate_guard`'s blocker aggregation.
However, the broker process itself stays **disabled**:

- `is_controller_enabled()` requires a root-owned `0644`-or-stricter
  enable-switch file at `/opt/data/state/roadmap-merge-controller/enabled`
  containing exactly `true`, AND no halt file.
- **This PR creates neither file.**
- Therefore `is_controller_enabled()` returns `False` regardless of what code
  is added, and the whole broker/controller stays disabled.

No service starts, no socket binds, no `enabled` switch is set, no credential
is touched, no `.env` is modified.

## Scope confirmation (no activation)

```
$ git diff --name-only origin/main...HEAD
.github/workflows/main-gate.yml
docs/reports/g0-2-governance-enforcement-2026-07-19.md
orchestrator/scripts/governance_consistency_check.py
orchestrator/scripts/roadmap_merge_controller_broker.py
orchestrator/scripts/roadmap_merge_guard.py
tests/test_governance_consistency.py
tests/test_roadmap_merge_controller.py
tests/test_roadmap_merge_guard.py
```

Only expected files changed. No `.env`, no `*.service`, no enable-switch file,
no credential file, no runtime/socket/broker/controller activation.

## Lint status

- `orchestrator/scripts/roadmap_merge_guard.py`: ruff **All checks passed!**
- `orchestrator/scripts/governance_consistency_check.py`: ruff clean (no errors)
- `orchestrator/scripts/roadmap_merge_controller_broker.py`: 6 pre-existing
  ruff errors (lines 88, 93, 96, 597, 681, 1321) — all unchanged by this diff
  (verified via `git stash` comparison). No new ruff issues introduced.

## Done criteria (spec §12, G0.2)

- ✅ Validator passes locally and in CI; every §7.5 negative test is
  red→green demonstrable.
- ✅ Regenerate-and-diff CI enforcement fails on any Derived-View drift.
- ✅ Broker/writer governance hook exists as a tested, **disabled** code path
  with integration tests proving it blocks a non-compliant merge on the inert
  path — not merely a merge-guard change.
- ✅ Human-only merge (touches governance/guard files; spec §10.3).
- ✅ No runtime, Docker, trading, kill-switch, credential, service, socket,
  enable-switch, broker, or controller state changed.
- ✅ No GitHub branch-protection change in the PR diff.

## Post-merge (separate steps, not in this PR)

- Tracker #605 repoints to Phase A (separate step, not bundled into this PR).
- Luke separately flips branch protection to make `governance-consistency` a
  required status check (spec §10.2 correction 15).

## Status

`READY_FOR_HUMAN_MERGE` — only Luke merges. Agent stops here.