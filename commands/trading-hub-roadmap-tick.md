# Command: trading-hub-roadmap-tick

> Execute exactly **one bounded** Trading Hub roadmap iteration.
> A0 read-only and A1 repository-only work are authorized.
> Stop without mutation at every missing A2 or A3 approval.

## Purpose

Drive the autonomous issue-driven roadmap loop from the canonical task
sequence (H1 → H2 → H3A → H3B → R5A). Each tick selects the first
truly unblocked task and executes at most one task, one branch, one PR
and one report.

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
6. After merge: reconcile issue, update state, close issue.

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
- `BLOCKED_BY_MISSING_A2_APPROVAL`
- `BLOCKED_BY_MISSING_A3_APPROVAL`
- `BLOCKED_BY_RUNTIME_CLIENT_NOT_LOAD_BEARING`
- `READY_FOR_REVIEW`
- `READY_FOR_MERGE`
- `MERGED_AND_RECONCILED`

## Stop conditions

- Another active roadmap PR overlaps the selected scope
- Dirty or ambiguous working tree
- Contradictory runtime evidence cannot be resolved read-only
- Scope would require A2 or A3 without approval
- CI or relevant tests remain red
- A secret or credential would be exposed
- `dry_run=false` or live order would be placed

## Execution class authorization

- **A0:** Always authorized.
- **A1:** Authorized within task scope. Must not mutate host, Docker, bots,
  strategies, configs, credentials or live state.
- **A2:** Only with explicit issue scope, approval marker, snapshot, canary,
  allowlist, rollback, audit and bounded measurement.
- **A3:** Never authorized from this command. Requires external signed,
  time-limited, scope-specific approval.

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
