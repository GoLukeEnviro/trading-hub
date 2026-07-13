# H3B Runtime-Control Proof — 2026-07-13 (Container Recreate + Blocker Discovery)

**Date:** 2026-07-13 00:20–00:35 UTC
**Gate:** `H3B_RUNTIME_CONTROL_DEGRADED`
**Classification:** A2 — approved dry-run runtime (`APPROVED_HERMES_ROOT_EXECUTOR_CLIENT_INTEGRATION`), single scoped mutation performed

## Goal

Close H3B (Issue #531) by refreshing the stale Hermes bind mount identified in PR #557
and completing the full bounded runtime-control proof matrix.

## Preconditions (verified before mutation)

| Check | Result |
|---|---|
| `main` contains `a5a8cbe` | ✅ verified, local checkout fast-forwarded |
| Working tree clean | ✅ |
| Other open roadmap PRs | ✅ none |
| `hermes-root-executor.service` | ✅ active/running, `MainPID=468055`, `NRestarts=0` |
| Host socket + inode | ✅ exists, inode `99150`, links `2` |
| Container socket + inode (pre-recreate) | orphaned, inode `2475`, links `0` (confirms the stale-mount diagnosis from PR #557) |
| Hermes UID/GID | ✅ `10000:10000` |
| Raw `/var/run/docker.sock` in Hermes | ✅ absent |
| Container/network/volume inventory | ✅ captured (`hermes`, `rainbow-live-dashboard-1`, `rainbow-live-rainbow-1`, `hermes-docker-socket-proxy-1`; networks `bridge`, `hermes_default`, `host`, `none`, `rainbow-live_default`; no hermes-named volumes) |
| Compose paths | `/opt/stacks/hermes/compose.yaml` + `/opt/stacks/hermes/compose.override.yaml`, service name `hermes` |
| `BACKUP_GATE_GREEN` | ✅ restic functional, fresh snapshot `49b76bb0` taken (tag `h3b-container-recreate-<ts>`) before mutation |
| Root-only Compose backup | ✅ `/root/backups/h3b-container-recreate-20260713/` with `compose-files.sha256` |
| Cron/roadmap writer | No `trading-hub-roadmap-tick` job exists on Hermes currently (only `heartbeat-monitor`, `daily-health`) — nothing to pause |

All preconditions green. Proceeded to the single authorized mutation.

## Mutation performed

```bash
cd /opt/stacks/hermes
docker compose -f compose.yaml -f compose.override.yaml up -d --no-deps --force-recreate hermes
```

Pre-recreate container ID: `2905506b8e32`. Post-recreate: `c9c4ffb2fe3a`.

## Containment proof — PASSED

| Check | Result |
|---|---|
| Only Hermes container ID changed | ✅ (`rainbow-live-dashboard-1`, `rainbow-live-rainbow-1`, `hermes-docker-socket-proxy-1` unchanged) |
| Networks unchanged | ✅ same 5 networks |
| Hermes UID/GID after recreate | ✅ `10000:10000` |
| Raw `docker.sock` in Hermes | ✅ absent |
| Repo mount read/write | ✅ `/workspace/projects/trading-hub` writable as documented |
| Executor directory inode (container) vs host | ✅ **now matches**: `99150`/links `2` on both — the stale-mount bug from PR #557 is fixed |
| `hermes-root-executor.service` | ✅ untouched: `active`/`running`, `MainPID=468055` (unchanged), `NRestarts=0` (unchanged) |
| Compose files | ✅ unchanged, same SHA-256 as pre-mutation backup |

**The container recreate fully resolved the stale bind mount** documented in PR #557 — this is a real, verified fix, not a regression.

## New blocker discovered — socket still unreachable for a different reason

With the inode now matching, the socket **should** have been visible. It was not:

```text
$ docker exec -u 10000 hermes ls -la /run/hermes-root-executor/
ls: cannot open directory '/run/hermes-root-executor/': Permission denied

$ docker exec -u 10000 hermes python3 -c "...connect('/run/hermes-root-executor/executor.sock')..."
CONNECT_FAILED: PermissionError [Errno 13] Permission denied
```

Root cause, fully isolated (read-only inspection, no further mutation):

* Host directory: `drwxr-x--- root root` (`0750`), no ACL entries (`getfacl` confirms plain Unix bits only).
* Socket file: `srw-rw---- root root`, no ACL entries.
* Both come from the systemd unit: `RuntimeDirectory=hermes-root-executor`, `RuntimeDirectoryMode=0750`, `User=root`, `Group=root`.
* Hermes runs as `uid=10000 gid=10000` — neither the owner nor a member of group `root` (gid `0`). It structurally has **zero** traversal permission into the directory, at the OS level, regardless of the bind mount.
* This is **not** an application-level allowlist gap: `hermes-root-executor`'s `DEFAULT_ALLOWED_UIDS = frozenset({10000})` already correctly allowlists Hermes. The daemon would accept a request from UID 10000 if one could reach it — but the OS never lets the connection attempt reach the daemon's accept() loop, because `connect()` itself requires directory-traversal permission on every path component.

**This is a distinct root cause from the stale bind mount and was not part of the authorized mutation scope for this run** (`docker compose ... --force-recreate hermes` only). Fixing it requires either:

1. An ACL grant on the live runtime directory (`setfacl -m u:10000:rx /run/hermes-root-executor`, `setfacl -m u:10000:rw /run/hermes-root-executor/executor.sock`) — additive, reversible, but is itself a host mutation not covered by this run's approval, which scoped the mutation to "recreate only the existing Hermes service."
2. A systemd unit change (e.g. `RuntimeDirectoryMode=0770` + a shared group, or an `ExecStartPost=` ACL hook) — requires a service restart, which this run's authorization explicitly forbids ("Do not: restart hermes-root-executor.service").

Neither was attempted. No workaround was improvised.

## Proof matrix status

| Step | Status |
|---|---|
| Positive v1 proof (UID 10000, canonical client) | **BLOCKED** — `PermissionError`, socket unreachable |
| Read-only action-proof matrix | **BLOCKED** — same transport-level cause |
| Security proof matrix (wrong UID, missing approval, A3, kill-switch, locking, timeout, isolated mutation lifecycle) | **NOT ATTEMPTED** — all require a working connection first |
| Audit correlation | **BLOCKED** — no request reached the daemon |

No temporary test state (locks, kill-switch toggles, disposable containers) was created, since every test in the matrix depends on a successful connection that never became available. Nothing to restore.

## Stability proof

* `hermes-root-executor.service`: unchanged (`active`/`running`, `MainPID=468055`, `NRestarts=0`)
* Hermes container: `running`, healthy container state, UID/GID `10000:10000`
* No disposable containers created
* No network/volume changes
* Compose files unchanged
* Working tree: only this branch's doc changes

## Gate status

```
H3B_RUNTIME_CONTROL_DEGRADED
```

**Blocker:**

```
BLOCKED_BY_EXECUTOR_RUNTIME_DIRECTORY_PERMISSIONS
```

The stale-bind-mount blocker from PR #557 is **resolved** (verified: inode match, containment clean). The new blocker is a systemd `RuntimeDirectoryMode=0750`/`Group=root` configuration that denies UID 10000 (Hermes, the daemon's own correctly-configured allowlisted caller) OS-level traversal into the runtime directory. Issue #531's acceptance matrix (locking, timeout, kill-switch, approval gates, isolated mutating test, positive v1 proof) remains entirely unproven — none of it could be attempted.

`H3B_RUNTIME_CONTROL_GREEN` requires, in a separate explicitly-approved run: either an ACL grant on the runtime directory or a systemd unit fix (with the required service restart), followed by the full Issue #531 proof matrix this run could not reach.

## References

- Issue #531 — H3B Root-Executor Client Activation
- PR #557 (merged `a5a8cbe`) — stale bind mount, now resolved by this run's container recreate
- `/usr/local/sbin/hermes-root-executor` — `DEFAULT_ALLOWED_UIDS = frozenset({10000})` (correct), `RuntimeDirectoryMode=0750`/`Group=root` in the paired systemd unit (the actual blocker)
- Restic snapshot `49b76bb0` (pre-mutation, tag `h3b-container-recreate-<ts>`)
- `/root/backups/h3b-container-recreate-20260713/` — Compose file backup + SHA-256
