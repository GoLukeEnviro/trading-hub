# Meta-Spec: G0 — Canonical Program Governance

- **Status:** Draft for review
- **Authority:** `advisory / pre-bootstrap` — this design spec is advisory input,
  not a normative source. After G0 is merged, the canonical authority is
  `config/governance/` + the Accepted ADR; this meta-spec must **not** be treated
  as a competing normative or roadmap source and is superseded as a directional
  reference once G0.1 lands.
- **Author:** Claude (brainstorming session with Luke / GoLukeEnviro)
- **Created:** 2026-07-19
- **Execution class:** A1 (repository-only, no runtime mutation)
- **Supersedes:** none
- **Related:** Phase-A state reconciliation (deferred until after G0), external repo
  analysis triage (deferred), Issues #605 (tracker), #636, #604, #496, #580

---

## 0. Purpose and scope

Trading Hub currently treats multiple documents, issues, chats, and external
analyses as if they were binding at the same time. The result is contradictory
authority: the canonical state file, competing roadmap files, and the active
tracker disagree about direction and status.

**G0 establishes a single, versioned, machine-checkable program governance
layer.** After G0, no agent may derive a new direction from a chat, an old
report, a copilot analysis, or its own plan. A direction becomes binding only
when it is merged to `main`, marked `Accepted`, and represented in the
machine-readable program contract.

This document is a **meta-spec**: it specifies the design of the governance
layer and the two A1 pull requests that implement it. It does **not** implement
anything and it does **not** authorize any runtime, Docker, trading,
kill-switch, credential, broker, or controller mutation.

### 0.1 Non-goals

- No runtime deployment of any kind (this is not Phase B).
- No activation of the roadmap merge broker or merge controller.
- No rewrite of the substantive safety content in `AGENTS.md` / `SOUL.md`.
- No editing of historical reports, evidence files, or context documents.
- No strategy selection, Gate-0 execution, or fleet reconciliation.
- No credential rotation and no incident handling for unproven credentials.

### 0.2 The bootstrap is human-ratified, not self-ratified

G0 is itself a direction change, so it needs the very instrument it creates: an
Accepted ADR. There is **no self-ratification**. An agent must never grant
itself governance authority. The bootstrap sequence is:

1. The governance ADR is authored with `Status: Proposed`. The G0.1 PR opens and
   is reviewed with the ADR in this `Proposed` state.
2. Luke explicitly confirms it in the G0.1 issue or PR.
3. **After** that confirmation, a commit on the **exact same PR head** changes the
   ADR to `Status: Accepted`; CI re-runs and the merge-guard re-checks that exact
   head before merge.
4. Only then is the PR merged. **A merged ADR that still reads `Proposed` is a
   contradiction and must never happen** — the acceptance flip and its re-check
   precede the merge, they are not a post-merge step.

The bootstrap is a one-time, human-ratified migration. It is not an exception
to the no-self-ratification rule; it is an application of it.

---

## 1. Target model

```text
Human program decision (Luke)
        ↓
Accepted ADR
        ↓
Machine-readable program contract      (config/governance/program-contract.yaml)
        ↓
Canonical roadmap (YAML, authoritative)(config/governance/canonical-roadmap.yaml)
        ↓  (rendered, non-authoritative)
Derived roadmap view (Markdown)        (docs/roadmap/canonical-program-roadmap.md)
        ↓
Active GitHub tracker task              (Issue #605, single selected task)
        ↓
One issue → one branch → one PR → one report
        ↓
Offline CI + live merge-guard enforce consistency
```

A chat, a copilot/codex analysis, or a design proposal is never automatically
binding. It becomes binding only after merge + `Accepted` + contract inclusion.

---

## 2. Authority classes

Every governed file belongs to exactly one class.

| Class | Meaning | Location |
|---|---|---|
| Normative | Safety and program rules | `AGENTS.md`, `SOUL.md`, Accepted ADRs |
| Machine-readable | Goal, phases, gates, sources, selection rules (authoritative) | `config/governance/` |
| Derived view | Human-readable render of a machine-readable source; **no own authority** | `docs/roadmap/canonical-program-roadmap.md` |
| Operational | Currently proven runtime state | `docs/state/current-operational-state.md` |
| Execution | Exactly one active task | GitHub tracker #605 |
| Evidence | Verification and implementation proof | `docs/reports/` |
| Proposal | Design idea, advisory only | `docs/proposals/` |
| Historical | No longer governing context | `docs/context/`, `docs/archive/`, superseded roadmaps |

The **Derived View** class is deliberately separate from **Machine-readable**.
The Markdown roadmap is generated from the YAML and carries no independent
authority. Only `config/governance/canonical-roadmap.yaml` is canonical.

---

## 3. Canonical files

| File | Class | Repo status | Change in G0 |
|---|---|---|---|
| `AGENTS.md` | Normative | exists | G0.1: add canonical-source/contract reference block only (minimal-touch) |
| `SOUL.md` | Normative | exists | unchanged in G0 (may gain a one-line pointer only if needed) |
| `docs/decisions/ADR-2026-07-19-canonical-program-governance.md` | Normative | new | G0.1 |
| `config/governance/program-contract.yaml` | Machine-readable | new (dir new) | G0.1 |
| `config/governance/program-contract.schema.json` | Machine-readable | new | G0.1 |
| `config/governance/canonical-roadmap.yaml` | Machine-readable | new | G0.1 |
| `config/governance/canonical-roadmap.schema.json` | Machine-readable | new | G0.1 |
| `docs/roadmap/canonical-program-roadmap.md` | Derived view | new | G0.1 (generated by the G0.1 renderer) |
| `docs/state/current-operational-state.md` | Operational | exists | G0.1: add governance revision fields (see §6) |
| `docs/proposals/` | Proposal | exists (empty) | G0.1: header convention + README |
| `orchestrator/scripts/render_canonical_roadmap.py` | Tooling | new | G0.1 (renderer ships with the file it generates) |
| `orchestrator/scripts/governance_consistency_check.py` | Tooling | new | G0.2 |
| `orchestrator/scripts/roadmap_merge_guard.py` | Tooling | exists | G0.2: extend with governance rules (broker hooks code-only) |
| `tests/test_governance_consistency.py` | Tooling | new | G0.2 |
| `.github/workflows/main-gate.yml` | CI | exists | G0.2: add `governance-consistency` required job |

Directory `config/governance/` must be created; `config/` currently holds only
`rainbow.internal.yml`.

---

## 4. Data model

### 4.1 `config/governance/program-contract.yaml`

Authoritative machine-readable contract. Must contain no volatile runtime
numbers (no cycle ids, ledger balances, bot counts, reachability counters).

```yaml
schema_version: 1
program_id: trading-hub
governance_contract_revision: 1
revision: 2026-07-19.1
status: active
north_star:
  current_target: safe_autonomous_dry_run
  future_target: externally_mandated_micro_live
  live_is_currently_authorized: false
canonical_sources:
  safety_policy:
    - AGENTS.md
    - SOUL.md
  architecture:
    - docs/decisions/
  roadmap:
    - config/governance/canonical-roadmap.yaml
  roadmap_derived_view:
    - docs/roadmap/canonical-program-roadmap.md
  runtime_truth:
    - docs/state/current-operational-state.md
  active_task:
    type: github_issue_marker
    tracker_issue: 605
    marker: roadmap-selected-task
  evidence:
    - docs/reports/
  advisory_only:
    - docs/proposals/
    - docs/context/
execution:
  one_active_task: true
  one_issue_one_branch_one_pr_one_report: true
  require_exact_main_sha: true
  require_writer_lock: true
  require_isolated_worktree: true
  require_ci:
    # Enforced from G0.1 onward:
    - name: Main Gate
      enforcement: active
    - name: SI v2 Offline Smoke
      enforcement: active
    # Declared in G0.1 but not yet enforcing: the job is created in G0.2 (§7).
    # G0.1 must not claim this check is mandatory before it exists.
    - name: governance-consistency
      enforcement: pending
      effective_after: G0.2
authority:
  direction_change_requires:
    - accepted_adr
    - program_contract_update
    - canonical_roadmap_update
    - owner_approval
  status_reconciliation_requires:
    - evidence_or_state_link
    - change_class_declared
  a2_requires:
    - scoped_approval
    - time_window
    - snapshot
    - rollback
    - action_allowlist
  a3_requires:
    - external_signed_mandate
forbidden_without_a3:
  - dry_run_false
  - live_orders
  - live_credentials
  - risk_limit_increase
  - kill_switch_bypass
```

### 4.2 `config/governance/canonical-roadmap.yaml`

The roadmap is a DAG. It contains only phases, dependencies, gates, status, and
optional issue/execution-class links. **No runtime numbers.**

```yaml
roadmap_revision: 1
governance_contract_revision: 1
phases:
  - id: G0
    title: Canonical Program Governance
    status: in_progress
    dependencies: []
    exit_gate: governance_consistency_green
  - id: A
    title: State and Tracker Reconciliation
    status: pending
    dependencies: [G0]
    exit_gate: canonical_state_reconciled
  - id: B
    title: SEC-1/SEC-3 Runtime Deployment
    status: blocked
    dependencies: [A]
    issue: 636
    execution_class: A2
    exit_gate: executor_security_runtime_green
  - id: C
    title: Gate-0 Strategy Evidence
    status: blocked
    dependencies: [A]
    issue: 604
    execution_class: A1
    exit_gate: edge_decision_recorded
  - id: D
    title: Runtime Safety Wiring
    status: blocked
    dependencies: [B, C]
    exit_gate: safety_entry_path_green
  - id: E
    title: R5B/R6 Fleet Reconciliation
    status: blocked
    dependencies: [D]
    exit_gate: canonical_four_bot_fleet_green
  - id: F
    title: R7 Dry-run Measurement
    status: blocked
    dependencies: [E]
    issue: 496
    exit_gate: sufficient_measurement_evidence
  - id: G
    title: Allocator and Execution Readiness
    status: blocked
    dependencies: [F]
    issues: [600, 601, 602]
    exit_gate: gate_3_green
  - id: H
    title: Micro-live Canary
    status: blocked
    dependencies: [G]
    issue: 603
    exit_gate: micro_live_canary_validated
    requires_external_mandate: true
```

### 4.3 Schemas

`program-contract.schema.json` and `canonical-roadmap.schema.json` (JSON Schema)
validate: allowed status values, required fields, execution classes, approval
requirements, source path shape, DAG node shape, and the absence of ambiguous
authority (e.g. exactly one authoritative roadmap source).

Each `execution.require_ci` entry is an object `{ name, enforcement }` with
optional `effective_after`. `enforcement` is `active` or `pending`; a `pending`
entry (e.g. `governance-consistency` in G0.1) must carry `effective_after` and is
not treated as a mandatory check until that phase lands (§4.1, correction 2).

---

## 5. Proposal → ADR → Config promotion

New design work never edits governance directly. Flow:

1. Author writes `docs/proposals/<id>-<name>.md` with header:

   ```yaml
   authority: advisory
   status: proposed
   author: <name>
   created_at: <utc>
   affects_phases: [<ids>]
   supersedes: null
   ```

2. The proposal is reviewed.
3. Outcome is one of: `REJECTED`, `DEFERRED`, `ACCEPTED_WITH_CHANGES`,
   `PROMOTED_TO_ADR`.
4. Only `PROMOTED_TO_ADR` produces a real architecture decision.
5. Only a merged Accepted ADR **plus** the corresponding contract/roadmap update
   changes direction.

The validator enforces that no `advisory` document claims to be `canonical`, and
that anything marked superseded carries `superseded_by`.

---

## 6. State decoupling (correction 3)

The operational state file must **not** be forced to change on every roadmap
revision. Roadmap = program planning; current operational state = proven
runtime. These are separate domains.

`docs/state/current-operational-state.md` gains machine-readable fields:

```yaml
governance_contract_revision: 1
roadmap_revision_observed: 1
roadmap_observed_at_utc: <utc>
```

Rules:

- `governance_contract_revision` **must** be compatible with the contract
  (strict check — mismatch is a hard failure).
- `roadmap_revision_observed` is **informational only**.
- A roadmap status change does **not** automatically require a state-file change.
- The state file is touched **only** when the roadmap change alters a runtime
  statement or a go/no-go statement.
- Otherwise the validator emits at most `ROADMAP_RECONCILIATION_PENDING`, which
  is a non-blocking signal, **not** a CI failure.

---

## 7. Enforcement

### 7.1 Offline CI vs. live merge-guard (correction 4)

The two responsibilities are strictly separated so CI stays reproducible and
GitHub state is still verified immediately before merge.

**Offline CI (`governance-consistency` job in Main Gate)** checks
repository-only consistency, with no GitHub API or Issue #605 dependency:

- YAML validates against JSON schemas.
- Exactly one authoritative program direction.
- Roadmap DAG is acyclic; dependency gates are self-consistent.
- All canonical source paths exist.
- Derived Markdown equals the render of the YAML (regenerate-and-diff, §7.3).
- `AGENTS.md` references the program contract.
- `current-operational-state.md` declares a compatible
  `governance_contract_revision`.
- No non-canonical document claims to be authoritative. This is checked **only
  via structured frontmatter fields** (`authority`, `status`, `superseded_by`) —
  see §7.2 scope limit. The validator does not free-text scan document bodies.
- Superseded documents carry `superseded_by` (frontmatter field).
- Contract does not contradict the safety rules in `AGENTS.md` / `SOUL.md`.
  This is a **mechanical** invariant, not semantic safety-diffing: the contract
  must contain `north_star.live_is_currently_authorized: false` and a non-empty
  `forbidden_without_a3` list, and neither may be removed or weakened without a
  declared direction change (§8.1). Any other cross-file safety semantics are
  out of scope for the offline check.

**Live merge-guard / broker (read-only, run at merge time)** checks GitHub
state:

- Tracker #605 yields exactly one active task.
- The active `roadmap-selected-task` marker is present and consistent.
- Issue/PR state, review decision, unresolved threads.
- CI conclusions and head SHA.
- Selected task is compatible with the roadmap and its dependencies are met;
  execution class matches.
- Governance files are only changed under an Accepted-ADR scope.
- Human-only files (`AGENTS.md`, governance config, schema, validator, denylist,
  merge controller) are not modified by non-human merges.

### 7.2 Validator — `orchestrator/scripts/governance_consistency_check.py`

Implements all offline checks in §7.1. Exit non-zero on any hard failure; emit
`ROADMAP_RECONCILIATION_PENDING` as a warning without failing.

**Scope limit (correction 4):** the validator inspects **only structured
metadata** — the two governance YAMLs against their JSON schemas, and the
**defined frontmatter fields** of governed Markdown files (`authority`, `status`,
`superseded_by`, and the proposal header fields in §5). It must **not** free-text
search document bodies, historical reports, evidence files, or quoted legacy
text. A document without governed frontmatter is out of scope, not a failure.
This keeps the check deterministic and prevents false positives from historical
prose that merely mentions words like "canonical" or "authoritative".

### 7.3 Renderer — `orchestrator/scripts/render_canonical_roadmap.py`

Deterministic. Reads `canonical-roadmap.yaml`, writes
`docs/roadmap/canonical-program-roadmap.md` with a fixed header:

```text
GENERATED FROM config/governance/canonical-roadmap.yaml
DO NOT EDIT MANUALLY
```

**The renderer ships in G0.1**, together with the file it generates, so that the
Derived View is genuinely generated (not hand-authored) from the moment it
exists. G0.1 runs the renderer to produce the committed Markdown.

The **regenerate-and-diff CI enforcement** is wired in G0.2: the
`governance-consistency` job runs the renderer and `git diff --exit-code` on the
output; any drift fails the job. This split keeps G0.1's generated file
byte-identical to what the G0.2 CI later regenerates.

### 7.4 Merge-guard and broker code integration — `orchestrator/scripts/roadmap_merge_guard.py` + broker/writer

The chosen option is "CI-gate + guard, broker code-only". That means **two**
code touchpoints, both delivering tested but inert governance checks:

1. **Merge-guard** `orchestrator/scripts/roadmap_merge_guard.py`: extend the
   existing read-only guard (it already parses the
   `<!-- roadmap-selected-task:NNN -->` marker and requires the `main-gate` /
   `offline-smoke` checks) with the live governance rules in §7.1.
2. **Broker / writer governance hook**: the governance check must also be present
   as an inert code path in the root-broker merge controller / governed-merge
   writer. In this worktree the governed-merge writer is
   `orchestrator/scripts/repo_writer.py`; the **root-broker merge controller from
   PR #640 is not in this worktree's base (`b18bbf0`)** — see §10.4. The
   implementer branches from current `main` (`ff791d69`), locates the actual
   broker/controller module there, and adds the governance check as a tested,
   **disabled** code path.

**Nothing is activated.** No broker service starts, no socket binds, no
`enabled` switch is set. Only extending the merge-guard would **not** satisfy the
committed broker-code integration; the broker/writer hook plus its tests are
required. G0 remains fully A1.

### 7.5 Tests — `tests/test_governance_consistency.py`

Negative cases (each must be red→green demonstrable):

- missing canonical source path;
- two active roadmaps / ambiguous authority;
- cyclic roadmap dependency;
- unknown execution class;
- A2 phase without approval requirements;
- A3 phase without external mandate;
- manually edited generated Markdown (render drift);
- advisory proposal that falsely claims `canonical`;
- `governance_contract_revision` mismatch in the state file (hard fail);
- roadmap-only status change with no runtime impact → emits
  `ROADMAP_RECONCILIATION_PENDING`, does **not** fail.

---

## 8. Change and drift rules

### 8.1 Two declared change classes (correction 6)

Not every change to `canonical-roadmap.yaml` needs a new ADR. Each governance PR
must **declare its change class**; the validator/merge-guard distinguishes them.

**Direction change — Accepted ADR required:**

- add/remove phases;
- change dependencies;
- change north star;
- weaken a gate's content;
- change authority rules;
- change A2/A3 rules;
- change safety files or controller boundaries.

**Status reconciliation — no new ADR:**

- phase `pending → active`;
- phase `active → complete`;
- add an issue link;
- add an evidence link;
- update an already-defined blocker.

### 8.2 Runtime drift

Runtime drift never automatically changes the roadmap:

```text
RUNTIME_DRIFT_DETECTED
→ update current-operational-state.md
→ block the affected phase
→ open a reconciliation issue
```

---

## 9. Roles and rights

| Role | May |
|---|---|
| Luke | set direction, gates, limits, mandates; ratify ADRs |
| Agent / colleague | analyze; write proposals and specs |
| Hermes Writer | implement the single selected task |
| Merge controller | merge only permitted A1 PRs after all checks (code present, not active in G0) |
| Runtime executor | execute only explicitly permitted A2 actions |
| No agent | self-approve A2/A3, or silently change the roadmap |

---

## 10. Execution — two A1 PRs

### 10.1 PR G0.1 — Contract and roadmap

Contents:

- governance ADR (`Status: Proposed`);
- `program-contract.yaml` + schema;
- `canonical-roadmap.yaml` + schema;
- `render_canonical_roadmap.py` (deterministic renderer, §7.3);
- generated `canonical-program-roadmap.md` (Derived View, produced by the
  renderer above — not hand-authored);
- `AGENTS.md` canonical-source reference block (minimal-touch);
- proposal header convention + `docs/proposals/README.md`;
- `superseded_by` header on genuinely competing roadmaps (§11);
- state-file governance revision fields (§6);
- **schema-validation tests** for `program-contract.yaml` and
  `canonical-roadmap.yaml` (both must validate against their schemas) and a
  **renderer determinism test** (render is idempotent and the committed Markdown
  equals the render output). G0.1 must not merge the canonical files unvalidated
  and defer all validation to G0.2 (correction 4);
- migration plan.

A1 only. No runtime.

### 10.2 PR G0.2 — Enforcement

After G0.1 is merged:

- `governance_consistency_check.py` (full offline consistency validator, §7.2);
- `test_governance_consistency.py` (negative cases, §7.5);
- `governance-consistency` job in `main-gate.yml`, including the
  regenerate-and-diff enforcement that invokes the G0.1 renderer (§7.3);
- `roadmap_merge_guard.py` governance extension (§7.4);
- **broker/writer governance hook (code-only, disabled)** in the root-broker
  merge controller from PR #640 and/or `orchestrator/scripts/repo_writer.py`
  (§7.4, §10.4), **with integration tests** proving the check runs and blocks a
  non-compliant merge on the inert path — extending
  `tests/test_roadmap_merge_guard.py` and adding a broker-governance test;
- consistency report in `docs/reports/`.

A1 only. No runtime. Concretely, **G0.2 must not**: start, restart, install, or
enable any service; create or bind any socket; touch any credential or `.env`;
create any `enabled`/enable-switch file; or activate the merge broker/controller.
The broker/controller hooks are added as inert code paths only.

**CI wiring scope (correction 15):** the G0.2 PR may add the
`governance-consistency` job to `main-gate.yml` as a non-soft-fail job, but the
PR itself cannot flip GitHub branch-protection to make it a *required* status
check — that is a separate GitHub configuration change, made by Luke, outside the
PR diff. The spec assumes that follow-up; G0.2's diff stops at defining the job.

### 10.3 Tracker lifecycle (correction 5)

G0 is two separate tasks. Each of G0.1, G0.2, and Phase A gets its **own** issue,
branch, PR, report, CI run, and **human-only merge**. Both G0.1 and G0.2 modify
governance and/or guard files (`AGENTS.md`, `config/governance/`, schemas,
validator, renderer, `roadmap_merge_guard.py`), which are human-only per §9 and
§7.1 — so neither PR is eligible for any automated merge, regardless of broker
state.

```text
G0.1 issue
→ tracker #605 points to G0.1
→ G0.1 PR
→ human merge
→ separate post-merge step: repoint tracker

G0.2 issue
→ tracker #605 points to G0.2
→ G0.2 PR
→ human merge
→ separate post-merge step: repoint tracker

Phase-A issue
→ tracker #605 points to Phase A
```

Tracker repointing is a separate step from each merge, never bundled into a PR.

### 10.4 Base-branch caveat (worktree is behind main)

This worktree's base is `b18bbf0`; local `origin/main` also reads `b18bbf0`,
while the authoritative GitHub `main` is `ff791d69`. **PR #640's root-broker
merge controller landed after `b18bbf0` and is therefore not present in this
worktree.** The implementer must:

- branch G0.1 and G0.2 from current `main` (`ff791d69`), not from this worktree's
  base, so the broker/controller files from PR #640 are available for the §7.4
  code-only hook;
- verify the exact broker/controller module path at implementation time rather
  than trusting a path from this spec, since it was authored against the older
  base. Confirmed-present files in the base are
  `orchestrator/scripts/roadmap_merge_guard.py` and
  `orchestrator/scripts/repo_writer.py`.

---

## 11. Migration of existing roadmaps (correction / precision)

Five roadmap files exist today:

- `docs/roadmap/implementation-roadmap.md`
- `docs/roadmap/live-readiness-roadmap-rainbow-si-v2-2026-07-10.md`
- `docs/roadmap/roadmap-v2-blocker-first-runtime-ownership.md`
- `docs/roadmap/simplified-target-architecture-roadmap-2026-07-14.md`
- `docs/roadmaps/SI_V2_CONTINUOUS_IMPLEMENTATION_ROADMAP.md`

Rules:

- Edit a file **only** if it is genuinely a competing roadmap (asserts program
  direction). The implementer must confirm this per file before touching it.
- For each competing roadmap, add **only** a small header, in place:

  ```yaml
  authority: historical
  status: superseded
  superseded_by: config/governance/canonical-roadmap.yaml
  ```

- Leave files where they are (traceability). No deletion, no move.
- Do **not** rewrite historical reports, evidence files, or context documents.
  Only competing roadmaps get the header.

---

## 12. Acceptance criteria

**G0.1:**

- `program-contract.yaml` and `canonical-roadmap.yaml` validate against their
  schemas (tests present in G0.1, not deferred to G0.2).
- Renderer is deterministic; committed Derived-View Markdown equals its output.
- The bootstrap ADR is flipped `Proposed → Accepted` on the **exact PR head**
  after Luke's confirmation, CI/guard re-checked on that head, and only then
  merged. No PR merges with the ADR still reading `Proposed` (§0.2).

**G0.2:**

- `governance_consistency_check.py` passes locally and in CI; every negative test
  in §7.5 is demonstrated red→green.
- The regenerate-and-diff CI enforcement fails on any Derived-View drift.
- Broker/writer governance hook exists as a tested, **disabled** code path
  (§7.4), with an integration test proving it blocks a non-compliant merge on the
  inert path — not merely a merge-guard change.

**Both PRs:**

- Tracker #605 points to exactly one task that is compatible with the roadmap.
- Both PRs are A1 and human-only; no runtime, Docker, trading, kill-switch,
  credential, service, socket, enable-switch, broker, or controller state
  changed.

---

## 13. Stop conditions

Stop and escalate to Luke if any of the following arises:

- any required action would mutate runtime, controller, broker, or credentials;
- the contract would contradict a safety rule in `AGENTS.md` / `SOUL.md`;
- the bootstrap ADR cannot be human-ratified;
- a roadmap file's status as "competing" vs. "historical evidence" is unclear;
- more than the two allowed governance PRs would be needed to reach a
  consistent state.

---

## 14. Rollback

Both PRs are A1, so rollback has no runtime consequences.

Rollback order:

1. Revert **G0.2** first (enforcement), then
2. Revert **G0.1** (contract and roadmap).
3. Reset any external tracker/issue changes separately (repointing #605,
   proposal/issue edits) — these are not part of the PR diffs and must be undone
   by hand.

---

## 15. Post-G0

After G0.2 is merged and the tracker is repointed, **Phase A** (state and
tracker reconciliation, plus triage of the external repository analysis) is the
first operational task, executed against these governance rules.
