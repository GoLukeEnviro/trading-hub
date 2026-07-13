# H3B Protocol Rollout — Incident Reconciliation Report

**Date:** 2026-07-12 23:13 UTC (initial observation) / 2026-07-12 23:33 UTC (reconciliation 1, container-only) / 2026-07-12 23:58 UTC (reconciliation 2, host-verified)
**Gate:** `H3B_RUNTIME_CONTROL_DEGRADED`
**Classification:** A0 — Read-only reconciliation (no host or runtime mutation performed)

## Timeline

| Time (UTC) | Event |
|---|---|
| ~22:20 | H3B rollout executed via `nsenter` on host (PR #555 installer) |
| ~22:20 | `hermes-root-executor.service` restarted with new dual-protocol daemon |
| 21:00:07 | Old daemon: a single client sent malformed JSON; the resulting error response hit a `BrokenPipeError` in one connection thread. Non-fatal — the service kept running for 2+ hours afterward. |
| 23:08:19 | `hermes-root-executor.service` stopped and restarted (matches backup timestamp `h3b-protocol-rollout-20260712/`) — the actual rollout activation |
| 23:13 | Initial container observation: socket missing, `ROLLBACK_REQUIRED` declared |
| 23:33 | Reconciliation 1 (container-only): socket still missing, claimed "daemon crashed" / "tmpfs deleted" / service state "cannot verify" |
| 23:57–23:58 | Reconciliation 2 (host-verified, this update): **directly verified from the host as root** — service healthy, daemon never crashed; root cause identified as a stale Docker bind mount, not a daemon failure |

## Correction of Reconciliation 1

Reconciliation 1 was written entirely from container-side inference, without host access, and reached two conclusions that direct host verification now disproves:

| Reconciliation 1 claim | Host-verified reality |
|---|---|
| "New daemon crashed — socket dead" | **False.** No crash in the journal. `hermes-root-executor.service` is `active`/`running`, `MainPID=468055`, stable since `2026-07-12 23:08:19 UTC`, `NRestarts=0`, `ExecMainStatus=0`. |
| "Mount source `tmpfs[.../deleted]` — host-side tmpfs unmounted or directory removed" | **False.** The host-side directory `/run/hermes-root-executor` is live: inode `99150`, `Links: 2`, contains `executor.sock` (`srw-rw---- root:root`), last modified `23:08:19` (the restart, not a deletion). |
| "`hermes-root-executor.service` — Cannot verify, no host access path" | Verified directly via `ssh hermestrader-root` (a host access path that exists independently of the container). |
| Root executor "DOWN" (`AGENTS.md`, `current-operational-state.md`) | **False.** The daemon is up, healthy, and enforces `SO_PEERCRED` correctly (see host-side probe below). What is actually broken is the **container's view of the socket**, not the daemon. |

This is a repeat of a known failure mode: an advisory agent without host access inferred a host-side cause (daemon crash, tmpfs cleanup) from a container-side symptom (missing socket) that in fact has an entirely different, verifiable explanation. See "Root cause analysis" below.

## Host-verified state (2026-07-12 23:57 UTC, via `ssh hermestrader-root`, read-only)

| Check | Result |
|---|---|
| `systemctl is-active` | `active` |
| `ActiveState` / `SubState` | `active` / `running` |
| `MainPID` | `468055`, stable since `Sun 2026-07-12 23:08:19 UTC` |
| `NRestarts` | `0` |
| `ExecMainStatus` | `0` |
| Binary | `/usr/local/sbin/hermes-root-executor`, 14942 bytes, mode `0750`, owner `root:root`, mtime `23:08:18` |
| Binary SHA-256 | `c89768b62fd12f38f4b02e933ea39cad98de2f4faf05143b947c9da6cc8812bf` (differs from the backed-up old daemon `ff228215…` — confirms the **new** daemon is the one running) |
| `hermes_root/` package files | 9 files present (`__init__.py`, `policy.py`, `actions.py`, `audit.py`, `redact.py`, `schema.py`, `client.py`, `validate.py`, `protocol.py`), all `root:root` |
| Journal | One non-fatal `BrokenPipeError` at `21:00:07` on the pre-rollout (old) daemon from a single malformed-JSON client request; no crash traceback at or after `23:08:19` |
| Root-side functional probe (`executor_health`, raw socket, as `root`) | `{"decision": "BLOCKED", "reason": "peer_uid_not_allowed"}` — proves the socket is reachable, the daemon accepts connections, and `SO_PEERCRED` correctly rejects a non-allowlisted peer UID |

**Correction:** the root-side probe does **not** prove v1 request parsing. `handle_payload()`
checks `peer_uid` first and returns `peer_uid_not_allowed` **before** `json.loads()` and
`protocol.normalize_request()` ever run (verified by reading
`/usr/local/sbin/hermes-root-executor` directly). The probe only proves socket
reachability and `SO_PEERCRED` enforcement. Positive v1 parsing from an allowlisted
caller (Hermes, UID 10000) remains unproven and stays
`BLOCKED_FROM_HERMES_UID_10000_BY_STALE_BIND_MOUNT`.

**Conclusion: the daemon rollout succeeded (service healthy, correct binary, no crash) and the new dual-protocol daemon is up — but positive v1 protocol parsing from an allowlisted caller is still unproven.**

## Root cause analysis — why the container still cannot reach a healthy daemon

`/opt/stacks/hermes/compose.override.yaml` mounts the socket directory into the Hermes container as a **directory bind mount**:

```yaml
- /run/hermes-root-executor:/run/hermes-root-executor:ro
```

The systemd unit uses `RuntimeDirectory=hermes-root-executor` (tmpfs-backed `/run`), which means systemd **deletes and recreates** `/run/hermes-root-executor` as a fresh directory (new inode) on every service start/restart — it does not reuse the old directory in place.

Verified inode mismatch:

| | Host (current) | Container (Hermes, uid 10000) |
|---|---|---|
| Inode | `99150` | `2475` |
| Links | `2` (live) | `0` (orphaned — deleted-but-open reference) |
| Birth | `23:08:19` (this restart) | `2026-07-11 15:13:28` (container's original mount setup) |

Docker's bind mount was established against the directory instance that existed when the Hermes container's mount was last set up. The `23:08:19` host-side service restart recreated the directory with a new inode; the container's mount still points at the old, now-orphaned instance and never picks up the new one without a container recreate.

**This is the same class of bug previously documented for the D3 bridge socket mount** (`compose.override.yaml` directory bind + daemon restart → stale container-side view, requiring `hermes` container recreate to refresh).

**Fix (not applied in this session — out of scope, would be a runtime mutation):** recreate the Hermes container so its bind mount re-resolves to the current `/run/hermes-root-executor` directory.

## v1 Protocol Proof — **BLOCKED**

Executed from inside the Hermes container as UID 10000, using the canonical client (`python3 -m hermes_root`, not a manual protocol reconstruction):

```text
$ id
uid=10000(hermes) gid=10000(hermes) groups=10000(hermes)

$ test -S /run/hermes-root-executor/executor.sock
→ SOCKET_NOT_VISIBLE

$ python3 -m hermes_root executor_health --correlation-id h3b-reconcile-20260712T235758Z-5c2680c1 --class A0 --json
Executor error: Executor socket not found at /run/hermes-root-executor/executor.sock
(exit code 3)
```

Stop condition hit: **connection error** (`ExecutorConnectionError` / socket not found), exactly as specified — proof aborted, no retry, no workaround attempted.

## Legacy / A0 Compatibility Check — **BLOCKED** (same transport failure)

```text
$ python3 -m hermes_root docker_ps --correlation-id h3b-reconcile-20260712T235849Z-488d8c2b --class A0 --json
Executor error: Executor socket not found at /run/hermes-root-executor/executor.sock
(exit code 3)
```

Same failure mode as the v1 proof, confirming the block is at the **transport/mount layer**, not daemon-side protocol handling or action allowlisting.

(Note: `fs_stat` from the original probe template is not a defined action in this daemon's schema — `Unknown action` on the CLI's own validation, before any socket attempt. `docker_ps` was used instead as a real, documented A0 action.)

## Audit Correlation — no entry (expected)

`/opt/data/hermes/audit/runtime-actions.jsonl` exists (60 lines). Zero matches for either correlation ID (`h3b-reconcile-20260712T235758Z-5c2680c1`, `h3b-reconcile-20260712T235849Z-488d8c2b`) — consistent with both requests failing at the transport layer before ever reaching the daemon. No secrets or other audit content disclosed.

## Stability Window — unaffected

Rechecked after the failed proof attempts: `ActiveState=active`, `SubState=running`, `MainPID=468055` (unchanged), `NRestarts=0` (unchanged). The daemon was never touched by these read-only proof attempts.

## Installer weaknesses (retained from Reconciliation 1, still valid, from code review of `main`)

The installer at `scripts/install-hermes-root-executor.sh` has these gaps, independent of the current incident:

1. **Fake import test** — adds a path and prints "import check passed" without actually importing any `hermes_root` module
2. **Non-atomic package switch** — `rm -rf` before `mv`, leaving a window with no valid installation
3. **Incomplete healthcheck** — only checks `systemctl is-active`, not socket presence, protocol response, or restart-loop detection
4. **Unvalidated rollback** — `systemctl restart ... || true` reports success even when the service fails to start

These remain real gaps worth fixing, but **did not cause this incident** — the daemon is healthy. The incident is a container-mount staleness issue.

## Recovery path

**No host or daemon recovery is required or should be attempted.** The daemon is healthy. The only outstanding fix is refreshing the Hermes container's stale bind mount (a container recreate), which is a runtime mutation and out of scope for this read-only reconciliation. `ROLLBACK_RECOVERY_GREEN` from the original incident report was never executed and should **not** be executed — it would replace a healthy, tested v1 daemon with the old legacy-only backup for no reason.

## Gate status

```
H3B_RUNTIME_CONTROL_DEGRADED
```

**Rationale:** The root executor daemon on the host is healthy, running the new dual-protocol code, and verified functional via a host-side probe. However, Hermes (the only intended caller, from the container as UID 10000) still cannot reach it — v1 and A0/legacy-equivalent proof both fail with a connection error caused by a stale Docker bind mount. Runtime control from Hermes is therefore still **not** established, even though the underlying daemon is fine. Issue #531 remains open — none of its acceptance criteria (locking, timeout, kill-switch, approval gates, isolated mutating test) are proven from this session, and a **container recreate** (not attempted here) is required before a positive v1 proof is possible.

`H3B_RUNTIME_CONTROL_GREEN` requires: container recreate to refresh the bind mount, followed by a successful positive v1 proof, legacy/A0 proof, audit correlation, and stability verification from the Hermes container — none of which this session was authorized to perform (no runtime mutation permitted).

## References

- Issue #531 — H3B Root-Executor Client Activation
- Issue #423 — SI-v2-to-Live Roadmap (D1/D2 remain blocked)
- PR #553 — daemon source (merged `34b39f0`)
- PR #554 — state reconciliation (merged `f6be78f`)
- PR #555 — installer package-deploy fix (merged `47dfa56`)
- `scripts/install-hermes-root-executor.sh` — installer with identified weaknesses (unrelated to this incident)
- `hermes_root/daemon.py` — dual-protocol daemon (on `main`, and confirmed **running** on the host)
- `hermestrader-d3-bridge-wiring` incident (prior art) — same stale-bind-mount-after-restart failure mode on the D3 bridge socket mount
