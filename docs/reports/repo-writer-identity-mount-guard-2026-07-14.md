# Repository Writer Identity/Mount Guard — 2026-07-14

## Result

`A1_WRITER_IDENTITY_GUARD_GREEN_READY_FOR_PR`

- Issue: #615
- Base: `origin/main` at `beef77789cca574a8beab9c2e1876983747e3bf1`
- Branch: `ops/writer-identity-guard2026-07-14`
- Scope: repository code, tests, command documentation, and this report only
- Runtime mutation: `NONE`

PR #613 / Issue #594 remains `A0_AUDIT_GREEN_KEEP_MERGE`. This guard addresses
the separate writer-identity/filesystem incident and does not reimplement or
revert #594.

## Guard contract

`RepoWriterLock` and `IsolatedWorktree` now fail before creating writer state
unless the production process and namespace match all of the following:

- effective UID `10000` and passwd user `hermes`;
- canonical repo `/workspace/projects/trading-hub`;
- lock `/opt/data/state/hermes-repo-writer.lock`;
- worktree parent `/opt/data/projects/trading-hub-worktrees`;
- lock/worktree parents are directories owned by `10000:10000` and writable.

All mismatches use the stable error code `WRITER_IDENTITY_MISMATCH`.
`enforce_sandbox=False` is no longer a production bypass. Temporary test paths
require the explicit constructor injection `test_mode=True`; production
defaults keep both the environment guard and existing sandbox checks enabled.

## TDD evidence

RED before production code:

```text
9 failed, 34 deselected
```

The failures covered root identity, wrong username, wrong lock path without
state creation, host repo path, wrong worktree parent, wrong ownership,
non-writable parent, missing explicit test mode, and the new test-mode API.

GREEN after the minimal guard and hermetic-test migration:

```text
43 passed in 1.05s
```

Command:

```bash
/workspace/projects/trading-hub/.venv/bin/python -m pytest tests/test_repo_writer.py -q
```

Additional validation:

```text
POSITIVE_GUARD_OK lock=/opt/data/state/hermes-repo-writer.lock
ROOT_NEGATIVE_PROBE_OK code=WRITER_IDENTITY_MISMATCH
HOST_PATH_NEGATIVE_PROBE_OK code=WRITER_IDENTITY_MISMATCH
python3 -m py_compile orchestrator/scripts/repo_writer.py tests/test_repo_writer.py
git diff --check
```

The positive probe ran as Hermes UID 10000 in the actual container namespace.
The negative probes proved rejection of container root and the host-only repo
path while leaving the real lock and worktree state unchanged.

`ruff` was not available in the existing Hermes virtual environment, so no
package was installed; syntax compilation, the focused contract suite,
live namespace probes, and diff checks provide the bounded validation.

## Incident cleanup evidence

Before this A1 branch, the stale root worktree and fake host lock were moved
atomically under the real Hermes writer lock into:

```text
/opt/data/hermes/recovery/writer-identity-incident-20260714T183244Z/
```

The wrong source paths are absent, recovery checksums pass, the canonical
checkout is clean/synchronized, and only the canonical plus legitimate
`crypto-research` worktrees remain registered.

## Safety and rollback

No Docker lifecycle, bot, trading, strategy, Freqtrade, Cron, configuration,
credential, dry-run, or live-capital state changed. Rollback is a normal
repository revert of this focused PR; no runtime rollback is required.
