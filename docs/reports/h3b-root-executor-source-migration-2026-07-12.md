# H3B — Root-Executor Daemon Source Migration

**Date:** 2026-07-12
**Issue:** #531
**Branch:** `feat/h3b-version-root-executor-daemon`
**Execution class:** A1 (repository-only work: branch, code, tests, docs, PR)

## Summary

The Hermes root-executor daemon has, since R1 (2026-07-11), existed only as
an unversioned host artifact at `/usr/local/sbin/hermes-root-executor`. This
change adds a versioned, tested, dual-protocol implementation to the
repository as `hermes_root/daemon.py` (plus four supporting modules), so the
daemon can be reviewed, tested, and deployed like any other piece of the
codebase instead of being hand-edited on the host.

**This change does not deploy anything.** The production daemon on
HermesTrader is untouched and continues running unmodified.

## Corrections to the original task premise

Fresh verification against the live repository and GitHub, done immediately
before implementation, found three factual corrections to the assumptions
this task started from:

1. **"PR #530" does not exist.** GitHub returns 404 for pull request #530 in
   `GoLukeEnviro/trading-hub`. The intended reference is **PR #533**
   ("feat(hermes): add production root-executor client contract", merged
   2026-07-12T12:14:54Z, commit `38203a7`) — the same commit
   `docs/state/current-operational-state.md` had also mislabeled as `#530`
   in its H3A row; that line is corrected as part of this change.
2. **No pre-existing `hermes_root/adapter.py`.** The task premise assumed an
   existing client-side adapter bridging the legacy and v1 protocols. No such
   file exists in the repository, committed or otherwise. The dual-protocol
   bridge is implemented entirely inside the new `hermes_root/daemon.py` /
   `hermes_root/protocol.py`.
3. **Issue #531 was already CLOSED** (not open with a
   `H3B_BOOTSTRAP_DEGRADED` label) with resolution
   `BLOCKED_BY_BOOTSTRAP_CONTROL_PATH`. Between that closure and this task
   starting, the socket bind-mount blocker was independently resolved
   host-side (`/opt/stacks/hermes/compose.override.yaml` now mounts
   `/run/hermes-root-executor:/run/hermes-root-executor:ro` into the Hermes
   container). A live `executor_health` v1 request from inside the container
   now reaches the daemon and is rejected with `{"decision":"BLOCKED",
   "reason":"unknown_category"}` — empirical, current proof that the real
   remaining blocker is exactly the protocol mismatch this change addresses,
   not the socket mount.

## Previously unversioned host source (frozen, read-only)

| Field | Value |
|---|---|
| Path | `/usr/local/sbin/hermes-root-executor` |
| SHA-256 | `ff228215b5e28c2e1619148f9e06229c5cc24844d9f8a58a85256b32f4949d14` |
| Owner:mode | `root:root 0750` |
| Service | `hermes-root-executor.service` (systemd, `User=root`, `Restart=on-failure`) |
| Socket | `/run/hermes-root-executor/executor.sock`, `0660 root:hermes` |

## Legacy protocol contract (replicated exactly in `hermes_root/daemon.py`)

- Request: `{"category": "docker|systemd|fs_stat|fs_ls", "args": [...], "resource_key": "..."}`
- Response: `{"decision": "ALLOWED|BLOCKED", "reason"?, "returncode"?, "stdout"?, "stderr"?}`
- Category → binary: `docker→["docker"]`, `systemd→["systemctl"]`, `fs_stat→["stat"]`, `fs_ls→["ls","-la"]`; argv = binary + args, never through a shell.
- Peer auth: `SO_PEERCRED`, allowed UID `{10000}`.
- Kill-switch: `/etc/hermes-root-executor/DISABLED` (existence blocks everything).
- Locking: `fcntl.flock(LOCK_EX|LOCK_NB)` per safe-encoded `resource_key`.
- Timeout: 30s hard, with best-effort `docker rm -f` cleanup for un-detached `docker run`.
- Audit: append-only JSONL, `args_redacted` masks `KEY=`/`SECRET=`/`TOKEN=`/`PASSWORD=` values.

## New repository source of truth

| Module | Responsibility |
|---|---|
| `hermes_root/protocol.py` | Dual-protocol normalization (legacy + `hermes-root-executor.v1`), fail-closed on unknown fields/types/schema_version. |
| `hermes_root/policy.py` | Server-side execution-class gates A0-A3. |
| `hermes_root/actions.py` | Explicit argv builders for the 9 actions already defined in `hermes_root/schema.py` (`READONLY_ACTIONS` ∪ `MUTATING_ACTIONS` — reused as-is, not redefined, to stay consistent with the already-shipped CLI). |
| `hermes_root/audit.py` | Audit v2 writer, appends to the same append-only file the legacy daemon uses; existing lines never rewritten. |
| `hermes_root/daemon.py` | AF_UNIX server tying the above together; legacy requests get byte-for-byte legacy behaviour, v1 requests go through policy → actions → audit. |

Note: the task brief's action list (`docker_start` instead of
`systemctl_restart`, plus `fs_stat`/`fs_ls` as v1 actions) did not match the
already-merged `hermes_root/schema.py` constants that the shipped CLI
(`__main__.py`) already depends on. `schema.py` was treated as authoritative
per its own "source of truth" instruction; `actions.py` implements exactly
its 9 actions. `fs_stat`/`fs_ls` remain legacy-only categories, not v1
actions — this is a pre-existing, already-shipped design choice, not
something introduced here.

## Dual-protocol dispatch

Legacy detection: `category` present, no `schema_version`. v1 detection:
`schema_version == "hermes-root-executor.v1"`. Anything else is rejected as
`invalid_protocol`. Legacy requests are tagged `legacy_protocol=true`,
receive server-generated `request_id`/`correlation_id`, and gain no new
capability. v1 is the canonical path going forward.

## Gates (A0-A3)

Identical semantics to the client-side contract in `hermes_root/validate.py`,
enforced server-side: A0/A1 read-only only; A2 mutation requires the action
to be in `MUTATING_ACTIONS`, `approval_reference` to exactly equal
`APPROVED_HERMES_ROOT_EXECUTOR_CLIENT_INTEGRATION`, and issue/task context to
be present; A3 is always blocked, no exception, even with a correct
approval_reference.

## Audit v2

New fields appended per entry: `audit_schema_version`, `audit_id`,
`timestamp`, `request_id`, `correlation_id`, `issue_number`, `task_name`,
`execution_class`, `action`, `category`, `resource_key`, `peer_pid`,
`peer_uid`, `legacy_protocol`, `approval_reference_redacted` (`"[PRESENT]"`
or `null`, never the raw value), `decision`, `reason`, `returncode`,
`duration_ms`, `stdout_len`, `stderr_len`, `timeout`, `daemon_version`,
`repository_commit`. Written through `hermes_root.redact.redact_dict()` as a
second layer of defense. Existing legacy audit lines are untouched.

## Tests

New: `tests/test_hermes_root_daemon.py` — 33 tests, all passing on first
implementation pass:

- **Category A (legacy parity, 13 tests):** valid docker/systemd/fs_stat/fs_ls
  reads, unknown category, invalid args type, wrong UID, kill-switch,
  resource locking, timeout, response schema shape, invalid JSON, audit entry.
- **Category B (v1 protocol, 9 tests):** valid read, wrong schema_version,
  missing required field, unknown field, wrong field type, argv too long,
  unknown action, payload too large, timeout out of range.
- **Category C (gates, 6 tests):** A0/A1 mutation blocked, A2 without/with
  wrong/with correct approval, A3 always blocked.
- **Category D (audit, 4 tests):** correlation/request id present, approval
  reference redacted, legacy_protocol flag correctness, no secret leakage.
- Plus one true end-to-end test over a real `AF_UNIX` socket
  (`test_real_socket_end_to_end`) proving the socket-server wiring itself,
  not just the internal handler function.

Regression (Category E): `tests/test_hermes_root_client.py` (40) and
`tests/test_hermestrader_dryrun_compose.py` (106 passed, 1 skipped) both
still fully pass, unmodified.

**Combined: 179 passed, 1 skipped** (was 146 passed, 1 skipped before this
change).

Test execution path used: `docker exec -u hermes hermes bash -lc "cd
/workspace/projects/trading-hub && PYTHONPATH=. .venv/bin/pytest ..."` — the
host `deploy` user has no working `uv`/`pytest`; the repository's own
`.venv` (present in the read-write container mount) is the actual working
test environment.

## Install contract (documented, not executed)

`scripts/install-hermes-root-executor.sh`: resolves and prints the repo
commit, `py_compile`-checks the source, backs up the currently installed
daemon with a timestamp, writes to a temp file on the same filesystem,
`chown root:root` + `chmod 0750`, atomically renames into place, restarts
`hermes-root-executor.service` only after a successful post-write syntax
check, and automatically rolls back to the backup if the service fails to
become active. Never touches the audit file, compose files, or the Hermes
container. **Not run in this change.**

## Rollback

This change is additive-only at the repository level (5 new modules, 1 new
test file, 3 doc updates, 1 new script) — nothing on `main` is removed or
behaviourally changed for any existing caller. Reverting is a plain `git
revert` of the merge commit; there is no host state to roll back because
nothing was deployed.

## Explicitly not claimed

- **No host rollout.** `/usr/local/sbin/hermes-root-executor` is unchanged.
- **No `H3B_RUNTIME_CONTROL_GREEN` claim.** That requires an actual deployed,
  running repository daemon proven against real Hermes traffic — separate,
  future, explicitly-gated work.
- **No R5A.** HermesTrader deployment remains blocked pending
  `H3B_RUNTIME_CONTROL_GREEN` + `APPROVED_HERMESTRADER_DRY_RUN_DEPLOYMENT`.

## Gate

**`H3B_DAEMON_SOURCE_READY`**
