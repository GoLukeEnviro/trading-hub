# Governance writer-inode and merge-guard recovery — 2026-07-15

## Scope and authority

- Issue: #621
- Execution class: A1 repository-only, plus the explicitly requested narrow
  host preprovisioning of one lock directory and one lock file.
- Trading/runtime mutation: none.
- Merge policy: human-only; agent terminal state is
  `READY_FOR_HUMAN_MERGE`.

## Revalidated starting state

- `origin/main`: `a820c9560e354087470525cd7d8bf96e564c23ca`.
- PR #620: merged; commits `0b3061e` and final head `56911e4`, merge
  `a820c95`; both `main-gate` and `offline-smoke` succeeded. Issue #594 is
  closed. The planned formal close was no longer possible because external
  state had already advanced to merged.
- PR #618 remains on `main`; its separate revert is deliberately outside this
  atomic issue.
- No open PR existed when #621 was selected.
- No active Hermes writer or scheduled roadmap tick was found during the
  preflight.
- The canonical checkout was behind and contained two files byte-identical to
  the already merged PR #620 state. They were preserved in stash evidence,
  then canonical `main` was fast-forwarded without reset, clean or prune.

## Stable lock invariant

The approved host operation created exactly:

- host parent `/opt/data/hermes/state/repo-writer`: `root:root`, mode `0755`;
- host file
  `/opt/data/hermes/state/repo-writer/hermes-repo-writer.lock`:
  `10000:10000`, mode `0600`;
- container mapping `/opt/data/state/repo-writer/hermes-repo-writer.lock`.

Host and container observations both reported device `2049`, inode `943906`.
UID 10000 can open the file but cannot unlink or replace its directory entry.
Production code opens without `O_CREAT`, records device/inode in holder JSON,
and revalidates FD-versus-path identity with `assert_held()` before repository
mutations. It fails closed with `LOCK_FILE_MISSING`, `LOCK_PATH_REPLACED`,
`LOCK_OWNERSHIP_INVALID`, or `BLOCKED_BY_ACTIVE_REPO_WRITER`.

## Human merge guard

`orchestrator/scripts/roadmap_merge_guard.py` is read-only and accepts the PR,
expected issue, exact expected head SHA, and tracker issue (default #605). It
blocks closed/formally blocked PRs, issue/order mismatch, SHA drift, blocked
issues, missing or non-successful required checks, unresolved review threads,
requested changes, and formal governance-block comments. It has no merge or
execute switch and can return only `READY_FOR_HUMAN_MERGE` or
`BLOCKED_BY_GOVERNANCE`.

## Verification evidence

- RED: the new test suite initially failed because the merge-guard module did
  not exist.
- GREEN: `77 passed` for repository writer, inode hardening, and merge-guard
  suites after implementation.
- Root safe suite: `948 passed`, `52 skipped`; Control Plane: `144 passed`;
  live-trading invariants and tracked-secret scan: GREEN.
- Ruff and format checks are GREEN; compile check completed with one existing
  unrelated escape-sequence warning.
- Real two-process rehearsal: Writer A acquired device/inode `2049:943906`;
  Writer B exited through `BLOCKED_BY_ACTIVE_REPO_WRITER`.
- Real unlink rehearsal as UID 10000: `PermissionError`; the file remained
  device/inode `2049:943906`, owner `10000:10000`, mode `0600`.
- Fresh host/container stat observations remained identical after rehearsal.
- The #605 machine marker selects #621, and the active main ruleset requires
  both `main-gate` and `offline-smoke`.
- The exact guard blocked merged PR #620 in the authenticated operator context
  with `PR_NOT_OPEN`, `ISSUE_NOT_OPEN`, and `TRACKER_TASK_MISMATCH` (exit 2).
- The first Hermes guard call returned HTTP 401 and failed closed as
  `GITHUB_FACT_COLLECTION_FAILED` (exit 3). Follow-up proved the cause without
  exposing a token: an invalid ambient `GH_TOKEN` overrode the valid persistent
  login in `/opt/data/.config/gh/hosts.yml`. After `unset GH_TOKEN`,
  `gh auth status` was GREEN for `GoLukeEnviro`. No credential was changed.
  Until a distinct controller identity is proven, the persistent Hermes login
  may collect readiness facts, but Luke remains the only merge authority.
- A strict worktree-only SI-v2 import check still reproduces the pre-existing
  `backtests.cost_model` installability defect. That is the deliberately
  sequenced Phase-0A correction after the #618 revert, not part of #621. The
  required GitHub `offline-smoke` result for this exact PR remains the merge
  authority for this stage.
- Required final checks and GitHub CI are recorded on the PR before handoff.

## Deferred follow-up

After Luke merges this PR, the next bounded issue is the separate PR #618
revert. Phase 0A publication, #604/Gate 0, and all later safety/allocator work
remain sequenced behind that human merge and are not bundled here.
