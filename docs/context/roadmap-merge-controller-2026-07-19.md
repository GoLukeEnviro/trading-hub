# Roadmap Autonomous Merge Controller — Implementation Notes

**Date:** 2026-07-19
**PR:** (this PR)
**ADR:** [ADR-2026-07-19](../decisions/ADR-2026-07-19-roadmap-autonomous-merge-controller.md)
**Scope:** A1 repository-only; governance transition

---

## Summary

This record captures the implementation details, design trade-offs, and
operational notes for the bounded roadmap autonomous merge controller
introduced by ADR-2026-07-19. It is intentionally a context document, not
an authoritative contract; the ADR and the source files are authoritative.

## What changed

### New files

- `orchestrator/scripts/roadmap_merge_controller.py` — bounded controller
- `tests/test_roadmap_merge_controller.py` — 36 hermetic tests
- `docs/decisions/ADR-2026-07-19-roadmap-autonomous-merge-controller.md`

### Modified files

- `AGENTS.md` — adds a bounded controller subsection under "Repository
  writer contract" / "Human-only merge boundary"; explicitly states that
  the controller is **shipped disabled** and the human-only boundary
  remains binding until activation.
- `commands/trading-hub-roadmap-tick.md` — step 8 references the new
  controller and restates that agents must not invoke it until activation.
- `CLAUDE.md` — thin handoff pointer.

### Unchanged files (defence in depth)

- `orchestrator/scripts/roadmap_merge_guard.py` — read-only; untouched.
- `orchestrator/scripts/repo_writer.py` — writer contract; untouched.
- `tests/test_roadmap_merge_guard.py` — read-only-guard tests; untouched.
- `tests/test_repo_writer.py` / `tests/test_repo_writer_hardening.py` —
  writer-contract tests; untouched.

## Design choices and trade-offs

### Why a separate controller instead of mutating the guard

The user prompt required that `roadmap_merge_guard.py` stays read-only.
A separate controller that calls the guard's `collect_snapshot` and
`evaluate_merge_readiness` keeps the guard as a pure function with one
job (evaluating facts) and isolates all side effects (lock acquire, gh
merge, audit write) in the new module. This also keeps the existing
21 guard tests as a regression net without modification.

### Why two snapshots instead of one

A single snapshot proves the PR was mergeable at time T₀ but says nothing
about T₁ (the moment of `gh pr merge`). GitHub's `--match-head-commit`
already protects against head drift server-side, but a second snapshot
adds three more properties:

- the head SHA did not change between T₀ and T₁,
- the required CI checks did not change conclusion between T₀ and T₁
  (e.g. a flaky re-run turned `SUCCESS` into `FAILURE`),
- the full guard still returns `READY_FOR_HUMAN_MERGE` against the
  freshest facts.

If GitHub rejected a head drift, we would still know locally that we
attempted a merge with stale facts; the second snapshot prevents the
attempt altogether and writes an audit record with the drift evidence.

### Why `--match-head-commit` instead of relying on local checks

GitHub's `--match-head-commit` is the authoritative server-side binding.
Even if every local check passed, GitHub rejects the merge if the PR's
current head differs from the supplied SHA. This is a defence-in-depth
layer on top of our own two-snapshot check. It is also the only way to
prove to an auditor that we merged exactly the SHA we evaluated.

### Why squash-only

The pre-controller convention is squash-merge (PR #635, PR #637 etc.).
Allowing `--rebase` or `--merge` would either rewrite commits (rebase)
or introduce merge commits (merge), neither of which matches the audit
shape the repository has today. The parser intentionally omits any
merge-method override; `--squash` is the only mode.

### Why fail-closed disable switch instead of opt-out

Opt-in (file must exist with exact content) is strictly safer than
opt-out (file must exist with disable content). With opt-in:

- shipping the controller does nothing until activation,
- deleting the switch file is a complete rollback,
- a missing switch, an unreadable switch, or a switch with the wrong
  content all produce `CONTROLLER_DISABLED`.

The strict equality check (exactly `true\n`, not `yes`, `1`, `True`, `on`,
`enabled`) removes ambiguity and prevents an env-variable-style mishap.

### Why A1-only trigger scanning

The read-only guard does not distinguish A1 from A2/A3 PRs — it only
checks the PR's mechanical readiness (CI, drafts, threads, head SHA,
linked issue, tracker). An A2 deployment PR can mechanically pass every
guard invariant and still be a human-only merge. The controller adds a
deny-list scan over the issue body, PR body, and PR comments for known
A2/A3/live-trading tokens. The list is intentionally short and explicit;
anything not on the list is treated as A1.

### Why lazy import of `repo_writer`

`repo_writer.py` imports `fcntl` and `pwd` at module load time. Both are
POSIX-only. Importing the controller on a non-POSIX host (Windows dev,
some CI matrices) would otherwise fail at import time, breaking the
entire test collection. The lazy import inside `run_controller` keeps the
controller importable everywhere and only fails if the controller is
actually asked to acquire the production lock on a non-POSIX host (which
is itself a misconfiguration).

### Why the test suite ships a stub lock for non-POSIX

Same reason. The 36 controller tests cover the controller logic, which
is host-independent. The POSIX-specific lock mechanics are already
covered by `tests/test_repo_writer.py` (which skips on non-POSIX or uses
the real lock on POSIX). The stub provides the same `acquire`/`release`
contract with in-process serialisation so the parallel-merge test still
exercises the contention path.

## Operational runbook (activation — separate PR/step)

> Not executed by this PR. Recorded here as the authoritative steps.

1. Confirm this PR has been merged by Luke and deployed to the host.
2. Confirm GitHub `main` branch protection enforces `main-gate` and
   `offline-smoke`, requires squash merge, disallows force-push and
   deletions.
3. Confirm the GitHub principal that will invoke the controller has
   minimum merge permission and no admin rights.
4. Preprovision the audit log path with the expected ownership
   (`/opt/data/state/roadmap-merge-controller/audit.jsonl`, writable by
   the controller principal, append-only if the filesystem supports it).
5. Create the switch file with **exactly** `true\n` as content:

   ```bash
   printf 'true\n' > /opt/data/state/roadmap-merge-controller/enabled
   ```

   The parent directory must be root-owned; only operator/root can
   create the switch.
6. Trigger one controller invocation against a small, known A1 PR.
   Inspect the resulting audit record.
7. Record activation in
   `docs/context/roadmap-merge-controller-activation-<date>.md`.

## Operational runbook (rollback)

1. Delete or overwrite the switch file:

   ```bash
   rm -f /opt/data/state/roadmap-merge-controller/enabled
   ```

2. The next controller invocation fails closed with `CONTROLLER_DISABLED`
   and writes an audit record.
3. If the controller itself is suspect, revert this PR. The read-only
   guard and the writer contract remain unaffected.
4. Preserve the audit log as forensic evidence.

## Test execution

```
pytest tests/test_roadmap_merge_controller.py -v
pytest tests/test_roadmap_merge_guard.py -v        # unchanged, regression net
```

Both pass on Windows (with stub lock) and on POSIX (with real lock).
CI (`main-gate`, `offline-smoke`) runs on POSIX and exercises the real
`RepoWriterLock`.

## Scope discipline

This PR is A1 repository-only. It does not:

- create the disable switch file,
- activate the controller,
- mutate GitHub branch protection,
- mutate Docker, cron, systemd, Freqtrade, strategies, configs,
  credentials, runtime state, the kill switch, or RiskGuard,
- create any A2/A3 approval marker,
- merge any PR.

The first merge under the new controller, when it happens, will be a
separate, audited event recorded in
`docs/context/roadmap-merge-controller-first-merge-<date>.md`.

## Open follow-ups (out of scope)

- GitHub branch protection audit (separate issue).
- GitHub principal / deploy key audit for the controller identity
  (separate issue).
- Canary merge evidence bundle template (separate issue).
- Optional Prometheus/observability hook for the audit log
  (separate issue, low priority).
