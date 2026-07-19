---
Status: Accepted
Owner: Luke / GoLukeEnviro
Date: 2026-07-19
---

# ADR-2026-07-19: Canonical Program Governance

## 1. Context

Trading Hub has accumulated multiple documents, GitHub issues, chat
conversations, and external analyses that are all, in practice, treated as if
they could be binding at the same time. Nothing in the repository has ever
declared which of these sources wins when they disagree. In G0 preparation
this stopped being a theoretical risk: the canonical operational-state file
(`docs/state/current-operational-state.md`), competing roadmap documents, and
the active GitHub tracker issue (#605) have independently drifted and
disagreed about both *direction* (what phase comes next, what depends on
what) and *status* (what is actually done versus merged-but-not-deployed).
Each of those documents was internally coherent, but the set of them was not:
an agent or a human reading only one could reach a different, defensible
conclusion about program state than someone reading another.

This is a governance failure, not a runtime failure. No unsafe action has
resulted from it, but the risk grows with every additional ADR, roadmap edit,
report, or chat-derived instruction that is authored without a declared
ranking of authority. A system that lets "the most recent conversation" or
"the most recently edited file" silently become the operative source of truth
is not safe to build A2/A3-class automation on top of.

This ADR is the response: it defines a single authority hierarchy, a single
machine-readable source of program direction, a controlled promotion path
from proposal to binding decision, and — because this document is itself an
instance of the problem it is trying to solve — an explicit bootstrap rule
that prevents it from ratifying itself.

## 2. Decision

### 2.1 Authority classes

Every document, config file, or signal in this repository (and every
GitHub artifact referenced from it) belongs to exactly one of the following
authority classes. When two sources disagree, the class listed first wins.

1. **Normative.** `AGENTS.md`, `SOUL.md`, and Accepted ADRs under
   `docs/decisions/`. These define the safety rules and architectural
   decisions that everything else must operate within. Only a new Accepted
   ADR (or a change ratified the same way) can change a Normative source.
2. **Machine-readable (authoritative).** `config/governance/` — currently
   `config/governance/program-contract.yaml` (validated against
   `config/governance/program-contract.schema.json`) and
   `config/governance/canonical-roadmap.yaml` (validated against
   `config/governance/canonical-roadmap.schema.json`). This is the
   authoritative encoding of program direction, execution rules, and
   authority rules. It is the only class a script or CI check may treat as
   ground truth for "what phase are we in" or "what actions are permitted."
3. **Derived view.** `docs/roadmap/canonical-program-roadmap.md`, generated
   by `orchestrator/scripts/render_canonical_roadmap.py` from
   `config/governance/canonical-roadmap.yaml`. It has **no independent
   authority**. It exists for human readability only. If it and the YAML
   ever disagree, the YAML is correct and the Markdown is stale and must be
   regenerated, never hand-edited.
4. **Operational.** `docs/state/current-operational-state.md` — the
   canonical snapshot of what is actually true about the running system
   right now (deployed vs. merged-but-not-deployed, health, evidence gates).
   This class answers "what is currently the case," not "what should happen
   next" — that question belongs to the Machine-readable class.
5. **Execution.** The GitHub tracker, specifically issue #605, which at any
   time names exactly one active task via the `roadmap-selected-task`
   marker referenced from `config/governance/program-contract.yaml`
   (`canonical_sources.active_task`). This is the only place "what is
   currently being worked on" is declared.
6. **Evidence.** `docs/reports/` — dated, factual records of what was run,
   measured, or observed. Evidence supports or contradicts claims made in
   Operational or Execution documents; it does not itself set direction.
7. **Proposal.** `docs/proposals/` — advisory only. A proposal describes a
   possible design or direction change; by itself it changes nothing.
8. **Historical.** `docs/context/`, `docs/archive/`, and superseded roadmap
   documents. These are retained for audit and archaeology and carry no
   authority over current decisions.

A chat conversation, an externally produced analysis, a code comment, or a
verbal instruction is not itself in this hierarchy at all. It can only become
binding by being carried through the promotion flow in §2.3 into one of
classes 1–5 above.

**Relationship to `AGENTS.md`'s existing "Source-of-truth order."**
`AGENTS.md` already contains a "Source-of-truth order" list used "when
resolving conflicts or stale claims." That list and this section answer
different questions and must not be read as competing rankings of the same
thing:

- **This section (§2.1)** governs **program direction**: which document type
  is authoritative for "what phase are we in," "what is permitted," and "what
  changes require what governance." It is scoped to the machine-readable
  contract/roadmap and the promotion flow that changes them.
- **`AGENTS.md`'s Source-of-truth order** governs **resolving stale or
  conflicting factual claims**, mostly Operational-class (§2.1 item 4)
  questions such as "is SEC-1 actually deployed right now." Its ranking of
  fresh evidence above `AGENTS.md`/`SOUL.md`/Active ADRs is correct for that
  purpose: a merged ADR cannot override what CI or a live system actually
  shows to be true today. Two of its six items reach further than pure
  operational fact-checking — item 2 ("active roadmap PR") and item 4's
  long-term-live-target component are direction-adjacent — and are flagged
  here, not resolved, pending reconciliation with the Machine-readable class
  in a later task.

If a future situation appears to pit these two lists against each other,
that is itself a direction-vs-operational-fact confusion, not a genuine
conflict — escalate rather than silently picking one list. Task 8 of the
implementing plan ("AGENTS.md canonical-source reference, minimal-touch")
adds a reference from `AGENTS.md` to this contract; it does
not resolve or restructure this pre-existing list, which is out of scope for
G0.

### 2.2 The program contract as the authoritative machine-readable source

`config/governance/program-contract.yaml` is the single authoritative
statement of:

- **Canonical sources** — which file or tracker artifact is authoritative
  for each concern (safety policy, architecture, roadmap, roadmap derived
  view, runtime truth, active task, evidence, advisory-only sources). This
  is the machine-checkable expression of the hierarchy in §2.1.
- **Execution rules** — `one_active_task`, `one_issue_one_branch_one_pr_one_report`,
  `require_exact_main_sha`, `require_writer_lock`, `require_isolated_worktree`,
  and the required CI checks (currently `Main Gate` and `SI v2 Offline Smoke`
  active, `governance-consistency` pending until phase G0.2).
- **Authority rules** — what a *direction change* requires
  (`accepted_adr`, `program_contract_update`, `canonical_roadmap_update`,
  `owner_approval`), what a *status reconciliation* requires
  (`evidence_or_state_link`, `change_class_declared`), and the additional
  requirements for A2 actions (`scoped_approval`, `time_window`, `snapshot`,
  `rollback`, `action_allowlist`) and A3 actions (`external_signed_mandate`).
- **The `forbidden_without_a3` safety list**: `dry_run_false`, `live_orders`,
  `live_credentials`, `risk_limit_increase`, `kill_switch_bypass`. The
  contract's `north_star.live_is_currently_authorized` field is hard-pinned
  to `false` by its own JSON Schema (`program-contract.schema.json` declares
  it a `const: false`), so no future contract revision can silently flip
  live trading on without also changing the schema — itself a Direction
  change under §2.4, requiring an Accepted ADR.

`config/governance/canonical-roadmap.yaml` is the sole authoritative
roadmap. It is a directed acyclic graph of phases `G0` through `H`
(`G0` → `A` → `{B, C}` → `D` → `E` → `F` → `G` → `H`), each with an explicit
`status`, `dependencies`, and `exit_gate`, and, where applicable, linked
GitHub issues and an `execution_class` (`A1`/`A2`) or
`requires_external_mandate` flag. `docs/roadmap/canonical-program-roadmap.md`
is a Derived View rendered deterministically from that YAML by
`orchestrator/scripts/render_canonical_roadmap.py` and carries **no
authority of its own** — see §2.1 class 3. Both the contract and the roadmap
are individually schema-validated so that a malformed edit is a mechanical
CI failure rather than a silent drift.

### 2.3 Proposal → ADR → config promotion flow

New design work, whether it originates from a human, an agent, an external
analysis, or a chat, is written to `docs/proposals/<id>-<name>.md` with
`authority: advisory` in its frontmatter. A proposal is inert by
construction: writing one changes nothing about program direction. Every
proposal resolves to exactly one outcome:

- `REJECTED` — not pursued.
- `DEFERRED` — plausible, not scheduled.
- `ACCEPTED_WITH_CHANGES` — the idea is adopted but modified during review;
  the modified version still has to go through the same promotion path.
- `PROMOTED_TO_ADR` — a new ADR is drafted from the proposal.

Only the combination of (a) `PROMOTED_TO_ADR`, (b) a merged Accepted ADR,
and (c) a corresponding update to `config/governance/program-contract.yaml`
and/or `config/governance/canonical-roadmap.yaml` actually changes program
direction. Any one of the three without the others is not sufficient. In
particular: a chat message, a standalone report in `docs/reports/`, or an
external analysis is never automatically binding, no matter how detailed or
persuasive — it can motivate a proposal, but it cannot skip the flow.

### 2.4 Direction change vs. status reconciliation

Two change classes are distinguished because they carry very different risk,
and conflating them is part of what caused the drift described in §1.

**Direction change** — requires a new Accepted ADR (plus the config updates
in §2.3). Includes: adding or removing a roadmap phase; changing phase
dependencies; changing the north star (`current_target` /
`future_target` / `live_is_currently_authorized`); weakening an exit gate;
changing the `authority` rules themselves (including what counts as A2 or
A3); or changing the boundaries of safety-relevant files or controllers
(e.g. what the merge controller or runtime executor is permitted to touch).

**Status reconciliation** — does not require a new ADR. Includes: moving a
phase's `status` from `pending` to `active`, or `active` to `complete`;
attaching an issue or evidence link to an existing phase; or updating an
already-defined blocker with new evidence. Status reconciliation still
requires `evidence_or_state_link` and an explicit `change_class_declared`
tag per `program-contract.yaml`'s `authority.status_reconciliation_requires`,
so that it remains auditable — it is a lighter process, not an unaudited one.

If it is unclear which class an edit belongs to, it is treated as a
direction change until an Accepted ADR says otherwise.

### 2.5 Roles

- **Luke (owner)** sets direction, gates, and limits; issues mandates for
  A2/A3-class actions; and ratifies ADRs. Only Luke's explicit confirmation
  can move an ADR from `Proposed` to `Accepted`.
- **Agents and colleagues** analyze problems and author proposals and specs.
  They may draft ADR text, but drafting is not ratification.
- **The Hermes Writer** implements exactly the single task currently marked
  active per `canonical_sources.active_task` in the program contract
  (issue #605), respecting `one_active_task` and
  `one_issue_one_branch_one_pr_one_report`.
- **The merge controller** merges only permitted A1-class PRs, and only
  after all required checks pass. It is described here because it exists in
  code (see `orchestrator/scripts/roadmap_merge_controller.py` and
  `ADR-2026-07-19-roadmap-autonomous-merge-controller.md`), but this ADR
  does not activate it, change its scope, or grant it any new authority.
- **The runtime executor** executes only actions that are explicitly
  permitted under an A2 mandate meeting `authority.a2_requires`
  (`scoped_approval`, `time_window`, `snapshot`, `rollback`,
  `action_allowlist`), or an A3 mandate meeting `authority.a3_requires`
  (`external_signed_mandate`).
- **No agent** — Hermes Writer, merge controller, runtime executor, or any
  other automated actor — may self-approve an A2 or A3 action, or silently
  change `config/governance/program-contract.yaml` or
  `config/governance/canonical-roadmap.yaml` outside the promotion flow in
  §2.3.

### 2.6 The no-self-ratification bootstrap rule

This ADR is itself a direction change under §2.4: it introduces the
authority hierarchy, the promotion flow, and the direction/status
distinction that govern all future direction changes. That means it needs
the very instrument it creates — an Accepted ADR — in order to become
binding. This is a bootstrap paradox, and it is resolved explicitly rather
than silently, because silently resolving it would itself be the failure
mode this document exists to prevent.

**There is no self-ratification.** An agent — Hermes Writer or any other —
must never grant itself governance authority. Authoring this document,
however thoroughly, does not make it Accepted. Merging the PR that contains
it does not make it Accepted either, unless the specific sequence below is
followed.

The bootstrap sequence is:

1. This ADR is authored and lands in the PR with front-matter
   `Status: Proposed`. In this state it is a well-formed proposal for a
   governance system, nothing more — equivalent in binding force to a
   document in `docs/proposals/`.
2. Luke explicitly confirms it: a textual comment, on the G0.1 tracker issue
   or directly on the PR, that (a) references this ADR by title or file
   path, and (b) names the exact commit SHA of the PR head being confirmed.
   A GitHub "Approve" review click alone does **not** count as confirmation
   — it signals code-review sign-off, not a program-direction ratification,
   and does not name a SHA. Silence, an unrelated approval, or an automated
   check passing is not confirmation either.
3. Only after that confirmation, a commit **on top of the exact SHA named in
   step 2** flips the front-matter to `Status: Accepted`, and that commit's
   diff is limited to the `Status:` line — no substantive text may change in
   the same commit. If the confirmed content needs to change, that requires
   a new round: an updated PR head, a new confirmation naming the new SHA,
   then the isolated flip commit. CI and the governance guard are re-run on
   the flip commit (not the confirmed commit, not a prior commit, not a
   rebase), and only then is the PR eligible to merge.

A merged ADR whose front-matter still reads `Proposed` is a contradiction
that must never happen: it would mean a direction-setting document became
binding by merge alone, exactly the failure this ADR exists to close off.
Equally forbidden: flipping to `Accepted` on a commit whose ADR text differs
from what was named in Luke's confirmation, or bundling the flip with other
substantive changes.
If that state is ever observed, it must be treated as a governance
violation and reverted, not treated as an accepted decision.

This bootstrap is a one-time, human-ratified migration into the governance
system this ADR defines. It is not an exception to the no-self-ratification
rule — it is an application of it: the only actor capable of ratifying the
first ADR of a new governance system is the human owner, precisely because
no agent can ratify itself into authority.

## 3. Consequences

Once this ADR carries `Status: Accepted` on a merged PR head (per §2.6):

- `config/governance/program-contract.yaml` and
  `config/governance/canonical-roadmap.yaml` become the single source of
  truth for program direction. Any script, agent, or CI check asking "what
  phase are we in" or "what is currently permitted" reads these files, not
  a roadmap document, a chat, or a report.
- Chats, reports, and proposals remain permanently advisory. They can
  inform decisions; they cannot themselves constitute one.
- Any future direction change (§2.4) must go through Proposal → ADR →
  contract/roadmap update (§2.3). There is no shortcut, including for
  changes proposed by Luke — a direction change still needs a merged
  Accepted ADR and the matching config update, though Luke's ratification
  step is the same one used to bootstrap this ADR.
- Status reconciliation (§2.4) — phase status transitions, issue/evidence
  links, blocker updates — does not require a new ADR, only evidence and a
  declared change class, keeping routine operational updates lightweight.
- `docs/roadmap/canonical-program-roadmap.md` must never be hand-edited. It
  is regenerated from `config/governance/canonical-roadmap.yaml` via
  `orchestrator/scripts/render_canonical_roadmap.py`; a hand-edit that
  diverges from the YAML is itself a governance violation under §2.1 class 3.

**This ADR explicitly does not:**

- Activate the merge broker/controller described in
  `ADR-2026-07-19-roadmap-autonomous-merge-controller.md`. That system
  remains shipped disabled; its activation is a separate, operator-only step.
- Deploy anything, or change what is currently running on HermesTrader.
- Change any substantive safety rule in `AGENTS.md` or `SOUL.md`. It
  organizes how Normative sources relate to everything else; it does not
  rewrite their content.
- Authorize any runtime mutation, Docker/container operation, trading
  action, kill-switch change, or credential handling. All such actions
  remain gated exactly as `AGENTS.md`, `SOUL.md`, and
  `program-contract.yaml`'s `forbidden_without_a3` list already require,
  independent of this ADR.
- Mark the pre-existing competing roadmap documents under `docs/roadmap/`
  and `docs/roadmaps/` as superseded. §1 names them as part of the problem;
  stamping them with `superseded_by` frontmatter is a separate, later step
  in the implementing plan (not part of this ADR's own diff).

## 4. References

- `config/governance/program-contract.yaml`
- `config/governance/program-contract.schema.json`
- `config/governance/canonical-roadmap.yaml`
- `config/governance/canonical-roadmap.schema.json`
- `orchestrator/scripts/render_canonical_roadmap.py`
- `docs/roadmap/canonical-program-roadmap.md`
- `docs/state/current-operational-state.md`
- GitHub issue #605 (active-task marker)
- `ADR-2026-07-19-roadmap-autonomous-merge-controller.md` (related but
  independent decision; not activated by this ADR)
