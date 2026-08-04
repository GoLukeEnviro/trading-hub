# Command: trading-hub-roadmap-tick

> Execute exactly **one bounded** Trading Hub roadmap iteration.
> A0 read-only and A1 repository-only work are authorized.
> The Standing Owner Authorization (ADR-2026-08-04) is active: missing
> per-task human markers are not blockers. Technical gates remain binding.

## Purpose

Drive one issue selected by the canonical roadmap tracker (#605). Each run
executes at most one task, one branch, one PR and one report, then reconciles
after merge (autonomous merge under the Standing Owner Authorization once CI
and the merge guard are green).

## Inputs (read-only)

1. `AGENTS.md` and `SOUL.md` — operator identity and rules
2. `docs/state/current-operational-state.md` — current repo/phase state
3. Issue #423 — live gates anchor
4. Open PRs: `gh pr list --repo GoLukeEnviro/trading-hub --state open`
5. Open roadmap issues: `gh issue list --repo GoLukeEnviro/trading-hub --state open --label roadmap`
6. Active ADRs under `docs/decisions/`

If `IDEA.md` exists on the checked-out main revision, it may be read as
non-authoritative workspace orientation. Its absence is not an error.

## Algorithm

1. Read all required inputs.
2. If an active roadmap PR exists: finish it, validate it, or formally block
   it. Do not start a new task.
3. Identify the first unblocked task in the canonical sequence.
4. Verify all dependency gates are GREEN.
5. Execute one GOAL, one branch, one PR and one report.
6. Run the read-only merge guard against the expected issue, head SHA and
   tracker selection. Under the Standing Owner Authorization
   (ADR-2026-08-04, active until revoked/superseded), merge autonomously
   after green CI and a green guard; then reconcile issue and state in the
   same run or the immediate next run.
7. If the standing authorization is revoked/superseded, stop at
   `READY_FOR_HUMAN_MERGE` for a human merge.

## Output

Return a structured summary:

- **Selected task:** issue number and title
- **Execution class:** A0 / A1 / A2 / A3
- **Branch:** name
- **PR:** number and SHA
- **Tests:** count and result
- **CI:** status
- **Merge state:** merged / ready / blocked
- **Evidence:** test output, diff check, CI link
- **Blocker:** exactly one if blocked, otherwise `NONE`
- **Next automatic action:** next tick task or `STOP`

## Gate status

Exactly one of:

- `TASK_SELECTED`
- `BLOCKED_BY_OPEN_PR`
- `BLOCKED_BY_DIRTY_WORKTREE`
- `BLOCKED_BY_CI`
- `BLOCKED_BY_MERGE_GUARD`
- `BLOCKED_BY_HEAD_DRIFT`
- `BLOCKED_BY_BRANCH_PROTECTION`
- `BLOCKED_BY_MISSING_A2_TECHNICAL_PREREQUISITE`
- `BLOCKED_BY_MISSING_A3_TECHNICAL_PREREQUISITE`
- `BLOCKED_BY_RUNTIME_CLIENT_NOT_LOAD_BEARING`
- `READY_FOR_REVIEW`
- `MERGE_ELIGIBLE` (standing authorization active, all gates green)
- `HUMAN_MERGE_RECONCILED`

(`BLOCKED_BY_MISSING_A2_APPROVAL`, `BLOCKED_BY_MISSING_A3_APPROVAL` and
`READY_FOR_HUMAN_MERGE` are only valid while the Standing Owner Authorization
has been explicitly revoked or superseded.)

## Stop conditions

- `BLOCKED_BY_ACTIVE_REPO_WRITER` — another Hermes session holds the
  global repository writer lock (see §Repository writer contract below).
  Do not override without explicit operator approval.
- `WRITER_IDENTITY_MISMATCH` — the process identity or canonical
  repo/lock/worktree namespace is not the Hermes production writer
  contract. Stop before creating lock or worktree state.
- `LOCK_FILE_MISSING` — the root-protected, preprovisioned lock is absent.
- `LOCK_OWNERSHIP_INVALID` — lock type, ownership, mode or access is invalid.
- `LOCK_PATH_REPLACED` — the held FD and canonical path no longer identify
  the same device/inode. Stop every repository mutation.
- Another active roadmap PR overlaps the selected scope
- Dirty or ambiguous working tree
- Contradictory runtime evidence cannot be resolved read-only
- Scope would require A2 or A3 without approval
- CI or relevant tests remain red
- A secret or credential would be exposed
- `dry_run=false` or live order would be placed

## Repository writer contract (mandatory for every tick)

This command runs under the enforced single-writer contract
(`orchestrator/scripts/repo_writer.py`). Every tick MUST:

Before step 1, the production preflight requires effective UID `10000`,
passwd user `hermes`, canonical repo `/workspace/projects/trading-hub`,
lock `/opt/data/state/repo-writer/hermes-repo-writer.lock`, and worktree
parent `/opt/data/projects/trading-hub-worktrees`. The lock parent must be
`root:root` and not writable by UID 10000; the preprovisioned file must be a
regular `10000:10000` mode-`0600` file. Production never uses `O_CREAT`. The
worktree parent remains `10000:10000` and writable. A mismatch fails closed
before writer state is created. Host paths such as
`/opt/data/projects/trading-hub` are invalid. `test_mode=True` is exclusively
for hermetic tests and is never valid for a roadmap tick.

1. Acquire the global `RepoWriterLock`
   (`orchestrator/scripts/repo_writer.RepoWriterLock`) at
   `/opt/data/state/repo-writer/hermes-repo-writer.lock`.
   - Non-blocking: fails immediately with
     `BLOCKED_BY_ACTIVE_REPO_WRITER` when another session holds the lock.
   - Do not override this failure — STOP and report the holder.

2. Inspect open PRs (read-only, pre-lock).

3. Create an isolated git worktree:
   - Fork from `origin/main` (pinned SHA, not a moving branch).
   - Worktree parent: `/opt/data/projects/trading-hub-worktrees/`
     (hermes-writable, never inside the shared checkout).
   - Branch name must match
     `(feat|fix|docs|ops|chore|test|refactor|ci|codex)/[a-z0-9][a-z0-9_./-]*`.
     Codex Cloud A1 sessions use the `codex/{feature}{date}` prefix required
     by the repository operating instructions.
     `main` itself is rejected.

4. Verify the shared canonical checkout (`/workspace/projects/trading-hub`)
   is on branch `main` and has no uncommitted changes.

5. Verify the newly created worktree is clean
   (`git status --porcelain` empty, HEAD on the requested branch).

6. Execute the task entirely inside the worktree.

7. Call `assert_held()` immediately before worktree, commit, push and PR
   mutations. Commit, push and open exactly one PR.

8. Run `orchestrator/scripts/roadmap_merge_guard.py` with the PR number,
   expected issue, exact head SHA and #605 selection. Red or missing
   `main-gate`/`offline-smoke`, head drift, blocked state, unresolved threads,
   changed order or a formal governance block must stop. Under the Standing
   Owner Authorization (ADR-2026-08-04), a green guard permits autonomous
   merge via the normal protected GitHub merge path (no branch-protection
   bypass, no force-merge). Verify the merge independently via GitHub and
   `origin/main`.
   - In the Hermes container, first run `unset GH_TOKEN` and then
     `gh auth status`. A stale environment override must never shadow the
     persistent `/opt/data/.config/gh/hosts.yml` login.
   - Never print, copy or persist token values. Missing authentication is
     `GITHUB_FACT_COLLECTION_FAILED` and a hard stop.

   **Bounded autonomous merge controller (ADR-2026-07-19, shipped disabled).**
   A separate controller at `orchestrator/scripts/roadmap_merge_controller.py`
   delegates merge execution to a root broker at
   `orchestrator/scripts/roadmap_merge_controller_broker.py` for future
   bounded autonomous merges of A1 PRs. The controller uses the read-only
   guard result as a lower bound and adds credential isolation, independent
   broker re-verification, self-protecting denylist, Phase-0 path allowlist,
   full-field TOCTOU, and Intent+Completion audit. Until the disable switch
   at `/opt/data/state/roadmap-merge-controller/enabled` exists with the exact
   content `true\n` (operator-created, root-owned), agents MUST NOT invoke the
   controller. Roadmap ticks merge autonomously only under the Standing Owner
   Authorization (ADR-2026-08-04) via the normal protected GitHub merge path
   after a green guard; without it, ticks stop at `READY_FOR_HUMAN_MERGE`. See
   ADR-2026-07-19 for the full contract, activation prerequisites and rollback.

9. After human merge or formal abort, remove only the explicitly named
   worktree with `git worktree remove`. Never run a broad prune.

10. Release the global writer lock.

**Never:** switch branches in the shared canonical checkout, commit
directly in the shared checkout, use `git add .`, `git reset --hard`,
`git clean`, `git push -f`, or rewrite history.

**Never:** merge a PR while the Standing Owner Authorization is revoked or
superseded, bypass branch protection, force-merge, merge with red/pending CI,
merge with a blocked merge guard, merge with head drift, or merge with
unresolved review threads. The shipped-disabled controller at
`orchestrator/scripts/roadmap_merge_controller.py` remains inert until a
separate operator activation creates the enable switch; its non-activation is
not a missing human approval while the standing authorization is active.

See `orchestrator/scripts/repo_writer.py` for the full API
(`RepoWriterLock`, `IsolatedWorktree`, `RepoWriterError`).

## Execution class authorization

- **A0:** Always authorized.
- **A1:** Authorized within task scope. Must not mutate host, Docker, bots,
  strategies, configs, credentials or live state. A1 merge is
  standing-approved (ADR-2026-08-04) after green CI and green merge guard.
- **A2:** Within explicit issue scope once all technical guardrails exist
  (snapshot, canary, allowlist, rollback, audit, bounded measurement). The
  human gate is standing-approved; technical prerequisites remain binding.
- **A3:** Standing-approved when the technical live contract is fully green
  (C4 KEEP, live candidate report PASS, runtime baseline GREEN, breakglass
  operational, revocation proven, isolated canary, bounded capital, rollback,
  audit). Not authorized from this command until those prerequisites are
  proven.

## Scope

- Repository-only (A0/A1) by default.
- No Docker, host, bot, strategy, config or credential mutation in A0/A1.
- No live trading, no `dry_run=false`, no exchange key deployment.
- No unrelated repository hygiene.

## Suggested PR title template

`<type>(<scope>): <imperative summary>`

Examples:
- `docs(governance): align Hermes orchestrator and autonomous repository loop`
- `ops(hermes): activate bounded autonomous roadmap tick`
- `feat(hermes): add production root-executor client contract`
