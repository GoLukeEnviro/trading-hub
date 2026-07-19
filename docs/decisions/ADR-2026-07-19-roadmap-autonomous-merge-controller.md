# ADR-2026-07-19: Roadmap Autonomous Merge Controller

**Status:** Accepted (controller shipped; activation deferred — see §6)
**Date:** 2026-07-19
**Author:** Governance transition PR (Luke-initiated, VS Code agent prepared)
**Supersedes:** None
**Amends:**

- `AGENTS.md` — "Repository writer contract" → "Human-only merge boundary"
- `commands/trading-hub-roadmap-tick.md` — step 8 ("Agents never invoke merge")
- ADR-2026-07-12 §2.4 "Audit closure" (now layered on top of the controller)
- ADR-2026-07-11 (root-runtime-authority) — orthogonal, unchanged

**Related:**

- PR #637 — last human-only merge under the current contract (Luke)
- This PR — last human-only merge of the transition controller itself (Luke)
- Future activation PR — flips the disable switch (separate, audited)

---

## 1. Context

Since ADR-2026-07-12 the human-only merge boundary has been binding:

> Roadmap ticks and autonomous merge invocations remain disabled. Agents may
> commit, push, open a PR and run the executable merge guard, but MUST stop
> at `READY_FOR_HUMAN_MERGE`. Only Luke merges.

The existing `orchestrator/scripts/roadmap_merge_guard.py` is read-only and
returns either `READY_FOR_HUMAN_MERGE` or `BLOCKED_BY_GOVERNANCE`. It is a
correct, complete readiness evaluator but it intentionally does not perform
the merge — that has always been a human step.

Two drivers now justify introducing a narrow, contract-bound autonomous merge
controller:

1. **Volume of A1 docs/reconciliation PRs.** The roadmap produces a steady
   stream of small, A1-scoped, CI-verified PRs whose merge adds no judgement
   beyond what the read-only guard already evaluates. The cost of human
   merge for each is non-zero and the safety gain over a fully bounded
   controller is marginal.
2. **Audit rigour.** A controller that performs the merge can also emit a
   machine-auditable JSONL record tying the merge SHA, expected head SHA,
   controller identity, writer-lock holder and CI conclusions together at
   the exact moment of merge — stronger evidence than a human click.

The non-negotiable constraint is that **the controller must never weaken the
existing safety properties**. In particular:

- the read-only guard stays read-only and is not mutated;
- the writer contract stays single-writer and is not bypassed;
- the human-only merge boundary is replaced only for a narrow class of A1
  PRs that satisfy every existing invariant plus additional TOCTOU and
  identity invariants;
- activation is a separate, audited step — shipping the controller does
  not by itself enable autonomous merges.

## 2. Decision

Introduce a new, narrowly-scoped merge controller that uses the read-only
guard's result as a *lower bound* on readiness and adds stricter
invariants on top.

### 2.1 Component: `orchestrator/scripts/roadmap_merge_controller.py`

Single new module. Public surface:

- `run_controller(...)` — entry point; one PR per invocation
- `ControllerDecision` — JSON-serialisable result
- `is_controller_enabled(switch_path)` — disable-switch reader
- `detect_a2a3_triggers(issue_body, pr_body, pr_comments)` — A1-only filter
- `snapshot_drift_blockers(initial, pre_merge, *, expected_head_sha)` — TOCTOU
- `perform_squash_merge(...)` — `gh pr merge --squash --match-head-commit`
- `append_audit(audit_log_path, decision)` — JSONL writer with `fsync`
- `main(argv)` — CLI

### 2.2 Invariants layered on top of the read-only guard

For an A1 PR to be autonomously merged, **all** of the following must hold
in addition to `evaluate_merge_readiness(...).ready is True`:

1. **Controller enabled.** `/opt/data/state/roadmap-merge-controller/enabled`
   exists, is a regular file, and contains exactly `true\n`. Any other
   content, including `yes`, `1`, `True`, missing file, or non-regular
   file, blocks the merge (fail-closed).
2. **Writer lock held.** The global `RepoWriterLock` under
   `/opt/data/state/repo-writer/hermes-repo-writer.lock` is acquired
   non-blocking for the entire decision. Contention → block.
3. **A1-only enforcement.** None of the A2/A3/live-trading trigger tokens
   (`A2-APPROVED`, `A3-APPROVED`, `dry_run=false`, `live-trading`,
   `APPROVED_HERMES_ROOT_EXECUTOR_CLIENT_INTEGRATION`,
   `APPROVED_HERMESTRADER_DRY_RUN_DEPLOYMENT`, …) appears in the linked
   issue body, PR body, or PR comments.
4. **Two-snapshot TOCTOU protection.** A pre-merge re-snapshot must confirm:
   - the head SHA still equals the supplied `expected_head_sha`,
   - the head SHA did not change between the two snapshots,
   - both required checks (`main-gate`, `offline-smoke`) are still
     `COMPLETED`/`SUCCESS`,
   - the check conclusions did not drift between snapshots,
   - the full read-only guard still returns `READY_FOR_HUMAN_MERGE`
     against the pre-merge snapshot.
5. **Exact head binding at merge time.** The merge is invoked as
   `gh pr merge <pr> --repo <repo> --squash --match-head-commit <sha>`.
   GitHub rejects the merge server-side if the PR head has drifted; this
   is the authoritative last-line defence layered on top of #4.
6. **Squash-only.** No `--rebase`, `--merge`, `--auto`, `--admin`,
   `--force`, or any merge-method override is supported. The parser
   does not declare these options.
7. **Audit on every decision.** Every invocation — merge or block —
   appends one JSONL record to
   `/opt/data/state/roadmap-merge-controller/audit.jsonl` with timestamp,
   controller identity, PR number, expected issue, expected head SHA,
   decision code, blockers, merge SHA (if any), and duration.

### 2.3 Identity

The controller runs under a dedicated, named identity supplied via
`--controller-identity`. The identity is recorded in the audit log and in
the writer-lock holder metadata (as `session_id`). It MUST NOT be one of
the existing cron-tick, Hermes, Codex Cloud, or root identities — a
distinct token (e.g. `roadmap-merge-controller-bot`) is required so audit
records are unambiguous.

The controller does not introduce a new system user or new SSH key; it
reuses the existing authenticated `gh` CLI principal of the host that
invokes it. Branch protection and GitHub role permissions bound what the
controller can do at the GitHub layer (see §2.5).

### 2.4 Disable switch — default OFF

The controller is shipped **disabled**. The file
`/opt/data/state/roadmap-merge-controller/enabled` is NOT created by this
PR. Creating it with the canonical content `true\n` is a separate,
audited, host-side step that requires operator access to the
root-owned parent directory.

Rollback is correspondingly simple: delete (or overwrite) the switch
file. The next controller invocation after rollback fails closed with
`CONTROLLER_DISABLED`.

### 2.5 GitHub branch protection and permissions

Activation presupposes that the GitHub repository configuration bounds the
controller to safe behaviour independently of this code:

- `main` branch protection requires `main-gate` and `offline-smoke` to
  pass before any merge.
- `Require linear history` or `Require squash merge` is enabled.
- `Require approvals` is configured as the project requires (the controller
  does not bypass this; it requires `reviewDecision !=
  CHANGES_REQUESTED` and zero unresolved review threads, mirroring the
  read-only guard).
- The GitHub principal used by the controller has the minimum merge
  permission (typically `write` on `trading-hub`) and no admin/force-push
  rights on `main`.
- `Allow force pushes` is disabled for `main`.
- `Allow deletions` is disabled for `main`.

These settings are out of scope for this PR (no GitHub settings mutation)
but are listed as activation prerequisites in §6.

### 2.6 What the controller never does

- Never mutates Docker, cron, systemd, Freqtrade, strategies, configs,
  credentials, runtime state, the kill switch, or RiskGuard.
- Never enables live trading, deploys exchange keys, increases risk or
  capital limits, or places orders.
- Never creates A2/A3 approval markers.
- Never performs repository cleanup, history rewrite, force-push, broad
  prune, or volume removal.
- Never merges more than one PR per invocation.
- Never merges a PR whose linked issue contains A2/A3 or live-trading
  markers, even if the read-only guard says `READY_FOR_HUMAN_MERGE`.
- Never bypasses the writer lock.
- Never bypasses the read-only guard. The guard is called twice (initial
  snapshot and pre-merge snapshot); both must say `READY_FOR_HUMAN_MERGE`.

## 3. Repository contract delta

| Item | Before | After |
|------|--------|-------|
| Read-only guard (`roadmap_merge_guard.py`) | Read-only, no merge | **Unchanged** |
| Writer contract (`repo_writer.py`) | Single-writer lock + worktree | **Unchanged** |
| Merge authority | Luke only | Luke only **until activation**; then controller for narrow A1 class |
| Disable switch | N/A | `/opt/data/state/roadmap-merge-controller/enabled`, default absent |
| Audit log | Per-PR report only | + JSONL at `/opt/data/state/roadmap-merge-controller/audit.jsonl` |
| CLI merge flags | N/A | `--squash --match-head-commit <sha>` only |

## 4. Consequences

- **Positive:** Bounded autonomous merges become possible for A1 PRs that
  fully satisfy the existing read-only guard plus TOCTOU, identity, and
  A1-only invariants. Audit evidence at merge time is stronger than a
  human click.
- **Positive:** The read-only guard, the writer contract, and the
  human-only merge boundary for A2/A3/live PRs are unchanged. The blast
  radius of a controller bug is limited to A1 PRs that pass every gate.
- **Negative:** The controller adds operational surface (switch file,
  audit log, deployment runbook). Activation and rollback require operator
  access to the root-owned `/opt/data/state/roadmap-merge-controller/`
  parent.
- **Risk:** A bug in the controller could merge an A1 PR that should have
  been blocked. Mitigations: fail-closed default, two-snapshot TOCTOU,
  GitHub-side `--match-head-commit` and branch protection, separate
  activation step, easy rollback via switch deletion, and the hermetic
  test suite covering TOCTOU, head drift, CI drift, parallel merge,
  A2/A3 trigger detection, disable switch strictness, and CLI contract.
- **Risk:** A compromised controller host could perform malicious merges.
  Mitigation: GitHub branch protection, minimum-privilege principal,
  separate identity in audit, writer-lock holder metadata, and
  append-only audit log.

## 5. Test coverage

`tests/test_roadmap_merge_controller.py` (36 tests, hermetic):

- Disable-switch strictness (default OFF, fail-closed on any non-canonical
  content, directory rejection, missing-file block, audit on block).
- Writer-lock binding (contended lock blocks, parallel calls serialised
  by the shared lock, fail-closed on lock-acquire failure).
- Initial readiness via the read-only guard (PR not open, required check
  failure, audit on block).
- A1-only enforcement (parametrised trigger detection across issue body,
  PR body, and PR comments; clean A1 PR produces no triggers; A2/A3/dry_run
  markers block the merge and prevent any `perform_squash_merge` call).
- Two-snapshot TOCTOU protection (head drift, CI drift, CI conclusion
  drift, head-change-between-snapshots; merge command never called when
  drift is detected).
- Happy path (clean A1 PR merges with `expected_head_sha` passed through
  to the merge command).
- Audit log (one JSONL record per invocation, on merge and on block, with
  required fields).
- Merge-command contract (`gh pr merge --squash --match-head-commit <sha>`,
  no `--admin`/`--force`/`--auto`/`--rebase`/`--merge`/`--no-edit`).
- CLI contract (no admin/force/auto/merge-method switches declared;
  `--controller-identity` required; default `--tracker-issue 605`).

The existing `tests/test_roadmap_merge_guard.py` (21 tests) is unchanged
and continues to pass, proving the read-only guard is not weakened.

Cross-platform note: `repo_writer.py` imports POSIX-only modules
(`fcntl`, `pwd`). The controller imports `repo_writer` lazily inside
`run_controller` so that importing the controller module does not fail on
non-POSIX hosts. The test suite falls back to an in-process stub lock on
non-POSIX hosts; on POSIX it uses the real `RepoWriterLock`. CI runs on
POSIX and exercises the real lock path.

## 6. Activation prerequisites (out of scope for this PR)

Shipping this code does **not** enable autonomous merges. Activation
requires, in order:

1. This PR is merged by Luke (last human-only merge of the transition).
2. The controller module is deployed to the host(s) that will invoke it.
3. GitHub branch protection on `main` is verified to enforce
   `main-gate`/`offline-smoke`, squash-only merges, no force-push, no
   deletions.
4. The GitHub principal that will invoke the controller is confirmed to
   have minimum merge permissions and no admin/force-push rights.
5. A separate activation PR (or operator runbook step) creates
   `/opt/data/state/roadmap-merge-controller/enabled` with the exact
   content `true\n` and records the activation in
   `docs/context/roadmap-merge-controller-activation-<date>.md`.
6. The first one or two controller merges are observed closely; if any
   invariant misbehaves, the switch is deleted and the controller is
   considered blocked pending investigation.

Until all six steps are complete, the binding rule remains: **agents must
not merge PRs**.

## 7. Rollback

Rollback is a single operator step:

1. Delete or overwrite
   `/opt/data/state/roadmap-merge-controller/enabled`.
2. Optionally revert this PR (the controller becomes inert even if the
   switch file somehow survives, because the activation PR is reversed).
3. The next controller invocation fails closed with `CONTROLLER_DISABLED`.
4. The audit log is preserved as forensic evidence.

Rollback does not require touching the read-only guard, the writer
contract, branch protection, or any runtime component.

## 8. References

- `orchestrator/scripts/roadmap_merge_controller.py` — implementation
- `tests/test_roadmap_merge_controller.py` — 36 hermetic tests
- `orchestrator/scripts/roadmap_merge_guard.py` — read-only guard (unchanged)
- `orchestrator/scripts/repo_writer.py` — writer contract (unchanged)
- `commands/trading-hub-roadmap-tick.md` — per-tick algorithm (updated)
- `AGENTS.md` — repository writer contract (updated)
- PR #637 — last human-only merge under the pre-controller contract
- ADR-2026-07-12 — autonomous repository loop contract (amended)
