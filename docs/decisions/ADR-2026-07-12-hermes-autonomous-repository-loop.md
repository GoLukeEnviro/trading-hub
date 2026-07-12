# ADR-2026-07-12: Hermes Autonomous Repository Loop Contract

**Status:** Accepted
**Date:** 2026-07-12
**Author:** H1 Governance Reconciliation (Issue #525)
**Related roadmap:** Autonomous roadmap H1 → H2 → H3A → H3B → R5A

---

## 1. Context

Hermes operates from the `trading-hub-orchestrator` profile with read/write
access to the primary repository (`trading-hub`) and read/write access to the
secondary repository (`ai4trade-bot`) under explicit cross-repo scope only.
The `hermes-root-executor.service` is shipped and active (PR #508, R1),
providing UID-separated root runtime authority over HermesTrader.

To move from ad-hoc sessions to a structured, audit-safe, issue-driven
autonomous loop, Hermes needs a permanent repository-resident contract that
governs every agent session acting on the roadmap.

This ADR records the completion of the H1 governance reconciliation (#525)
and defines the durable contract for all future autonomous roadmap sessions.

## 2. Decision

### 2.1 Source-of-truth order

When resolving conflicts or stale claims, agents MUST use this hierarchy:

1. Freshly verified Git, GitHub, CI and runtime evidence
2. Existing active roadmap PR and its linked issue
3. Latest explicitly superseding section in `docs/state/current-operational-state.md`
4. Issue #423 for live gates and the long-term live target
5. Active ADRs, `AGENTS.md`, and `SOUL.md`
6. `IDEA.md` exclusively as non-authoritative workspace orientation; its absence is not an error

### 2.2 Execution classes

- **A0 — Read-only:** inspection, evidence collection, analysis and reports. No mutation.
- **A1 — Repository-only:** branch, code/docs/tests, commit, push, PR, CI repair, issue/state reconciliation after merge. Exactly one active roadmap PR.
- **A2 — Approved dry-run runtime:** only with explicit issue scope, approval marker, snapshot, canary, allowlist, rollback, audit and bounded measurement.
- **A3 — Live capital:** never inferred from root access or A0–A2. Requires externally signed, time-limited, scope-specific approval.

**Always prohibited without explicit A3 approval:**
- `dry_run=false`
- Live orders
- Live exchange credentials
- Capital or risk limit increases
- RiskGuard weakening
- Kill-switch bypass or deactivation

### 2.3 Autonomous roadmap session algorithm

1. Read `AGENTS.md`, `SOUL.md`, `docs/state/current-operational-state.md`, and issue #423.
2. Inspect open PRs and linked active issues.
3. Finish or formally block the existing roadmap PR before selecting another task.
4. Select the first truly unblocked task.
5. Execute one GOAL, one branch, one PR and one report.
6. Reconcile issue and state after merge.
7. Stop at every missing A2 or A3 approval.

### 2.4 Audit closure

Before recommending or performing a merge:
1. Re-fetch the PR from GitHub.
2. Capture the final head SHA.
3. Verify CI against exactly that SHA.
4. Check open reviews and threads.
5. Reconcile PR body with actual final state.
6. Reconcile checked-in report with actual final state.
7. Correct test counts, SHAs, runtime actions, snapshots and rollback.
8. No stale stage reports as final evidence.
9. Merge only with `expected_head_sha`.
10. Stop on branch or CI drift.

### 2.5 Canonical roadmap

The canonical task sequence is:

```
H1 → H2 → H3A → H3B → R5A
```

Each task is one issue, one branch, one PR, one report. No task may start
before its predecessor is merged and reconciled.

## 3. Repository contract

| Item | Value |
|------|-------|
| Active profile | `trading-hub-orchestrator` |
| Primary repo (read/write) | `/workspace/projects/trading-hub` |
| Host path | `/opt/data/projects/trading-hub` |
| Secondary repo (read/write, cross-repo scope only) | `/workspace/projects/ai4trade-bot` |
| Root Executor | `hermes-root-executor.service` shipped and active (PR #508) |
| Roadmap command | `commands/trading-hub-roadmap-tick.md` |
| Live-gate anchor | Issue #423 |
| A2 approval | `APPROVED_HERMES_ROOT_EXECUTOR_CLIENT_INTEGRATION` / `APPROVED_HERMESTRADER_DRY_RUN_DEPLOYMENT` |
| A3 approval | Externally signed, time-limited, scope-specific |

## 4. Consequences

- **Positive:** Every autonomous session follows a verifiable, audit-safe
  pattern. Stale claims are resolved by a defined hierarchy. Execution class
  boundaries prevent unauthorized scope escalation.
- **Negative:** The algorithm adds overhead (read six files, check PRs, check
  CI). This is intentional — autonomous execution must be slower and more
  careful than human-driven work.
- **Risk:** If `docs/state/current-operational-state.md` falls stale, the
  source-of-truth hierarchy degrades to GitHub-only. The reconciliation
  report convention mitigates this by requiring state updates after every
  merge.

## 5. References

- Issue #423 — Hermes Agent Operating Backlog (live gates)
- Issue #525 — H1 Governance Reconciliation (this ADR's parent)
- PR #524 — R7A Greenfield Compose + Rainbow Runtime (`ee767a10`)
- PR #508 — Root Executor Service (R1)
- ADR-2026-07-11-hermes-root-runtime-authority (R0)
- ADR-2026-07-01-si-v2-autonomous-dry-run-loop-live-target
- `AGENTS.md` — primary operational instruction file
- `SOUL.md` — project identity and safety principles
- `docs/state/current-operational-state.md` — canonical state snapshot
- `commands/trading-hub-roadmap-tick.md` — bounded autonomous iteration command
