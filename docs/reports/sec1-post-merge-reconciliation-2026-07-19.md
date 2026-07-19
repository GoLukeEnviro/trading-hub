# SEC-1 Post-Merge Reconciliation — 2026-07-19

**Issue:** #631

**Tracker:** #605

**Execution class:** A1 repository-only

**Runtime mutation:** NONE

## Goal

Reconcile the canonical repository state after Luke squash-merged SEC-1 PR
#632. This reconciliation records repository and governance facts only; it
does not claim that the merged executor code is deployed.

## Verified merge facts

- PR #632 state: `MERGED`.
- Merge commit: `450c58d15d2af89f8731cc8219c19da3dedae1b8`.
- Merge time: `2026-07-19T00:07:04Z`.
- PR head: `9b03f954d95e2846cb661558c6c32c8211311dab`.
- `main-gate`: completed successfully.
- `offline-smoke`: completed successfully.
- Open PRs before this reconciliation: none.

## Reconciled state

- SEC-1 containment is present on `main`.
- The legacy compatibility path now uses server-built command arguments and a
  bounded read-only allowlist.
- Mutation, unknown commands, option injection, path traversal, and
  out-of-scope filesystem access fail closed before subprocess execution.
- Audit records use fixed non-secret legacy classifications rather than raw
  caller-controlled arguments.
- The merged implementation report remains
  `docs/reports/sec1-legacy-readonly-firewall-2026-07-18.md`.

## Governance reconciliation

Issue #631 was automatically closed by the implementation merge. It was
reopened only for this bounded post-merge reconciliation so the required
single-issue merge guard can bind this state PR to the same SEC-1 scope. The
PR closes #631 again after Luke's human merge.

Tracker #605 remains selected on #631 while this reconciliation PR is active.
The next roadmap task must not be selected before this PR is merged or
formally blocked.

## Preserved boundaries

- No executor binary or service deployment.
- No service restart or Docker mutation.
- No bot, strategy, configuration, credential, order, or kill-switch change.
- No live-capital action and no `dry_run=false`.
- The P0 runtime evidence remains authoritative for deployed behavior.
- SEC-3 durable intent-audit work remains separate.

## Validation

- Markdown links and local references: PASS.
- `git diff --check`: PASS.
- Targeted secret scan: PASS.
- GitHub required checks: required on this PR; merge readiness is evaluated
  only after both complete successfully.

## Decision

**GO:** this docs-only state reconciliation.

**NO-GO:** deployment, restart, runtime proof, R5B continuation, kill-switch
mutation, or any A2/A3 action without a new scope-specific approval.

The session stops at `READY_FOR_HUMAN_MERGE`; only Luke merges.
