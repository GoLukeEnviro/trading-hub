# Codex Cloud A1 Writer Contract — Issue #592

**Timestamp:** 2026-07-14T14:12:04Z  
**Execution class:** A1 repository-only  
**Branch:** `codex/a1-writer-contract2026-07-14`  
**Status:** READY_FOR_REVIEW

## Goal

Resolve the next Codex Cloud backlog item after PR #591 by aligning the
repository writer contract with Codex Cloud A1 branch governance while keeping
single-writer, isolated-worktree, dry-run, and no-runtime-mutation safeguards
intact.

## Evidence reviewed

- `AGENTS.md` and `SOUL.md` were read before mutation.
- `docs/state/current-operational-state.md` confirms PR #591 is merged and the
  Codex Cloud backlog remains non-authoritative until the later ADR gate.
- `docs/testing/validation-policy.md` was checked for required validation.
- `orchestrator/scripts/repo_writer.py`, `tests/test_repo_writer.py`, and
  `commands/trading-hub-roadmap-tick.md` were inspected as the active writer
  contract implementation and command documentation.

## Change summary

- Extended the enforced branch-name allowlist to include the `codex/` prefix
  required for Codex Cloud A1 sessions.
- Added regression tests proving both `RepoWriterLock.acquire()` and
  `IsolatedWorktree` accept a `codex/{feature}{date}` branch name.
- Updated the roadmap tick command documentation so the documented branch
  contract matches the executable contract.

## Safety assessment

- No Docker, VPS, container, scheduler, exchange, secret, or runtime mutation was
  performed.
- No trading strategy/config behavior was changed.
- No `dry_run=false`, live order, risk increase, RiskGuard weakening, or
  kill-switch bypass was introduced.
- The change is repository-only and fail-closed: non-allowlisted branch prefixes
  remain rejected by the same validation path.

## Validation

Commands executed from `/workspace/trading-hub`:

1. `python3 -m pytest tests/test_repo_writer.py -q` — PASS (`34 passed`).
2. `python3 scripts/secret_scan.py --tracked` — PASS.
3. `python3 -m compileall orchestrator tests scripts` — PASS.
4. `git diff --check` — PASS.

## Rollback

Revert this PR. That removes the `codex/` branch-prefix allowance and the
matching regression/documentation updates, restoring the previous writer
contract behavior.

## Next task after merge

After Issue #592 is merged, the next Codex Cloud backlog task is Issue #606
(reproducible Codex Cloud environment), subject to the same single active PR and
writer-contract governance.
