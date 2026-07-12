# H3B Protocol Rollout — Incident Reconciliation Report

**Date:** 2026-07-12 23:13 UTC (initial observation) / 2026-07-12 23:33 UTC (reconciliation)
**Gate:** `H3B_RUNTIME_CONTROL_DEGRADED`
**Classification:** A0 — Read-only reconciliation (no host mutation performed)

## Timeline

| Time (UTC) | Event |
|---|---|
| ~22:20 | H3B rollout executed via `nsenter` on host (PR #555 installer) |
| ~22:20 | `hermes-root-executor.service` restarted with new dual-protocol daemon |
| ~22:20 | New daemon crashed — socket dead |
| 23:13 | Initial container observation: socket missing, `ROLLBACK_REQUIRED` declared |
| 23:33 | Reconciliation: socket still missing, mount source deleted, no host access |

## Verified current state (2026-07-12 23:33 UTC)

All checks performed from Hermes container as UID 10000:

| Check | Result |
|---|---|
| UID | `uid=10000(hermes) gid=10000(hermes)` |
| `/run/hermes-root-executor/` | Directory exists, empty, read-only tmpfs mount |
| `/run/hermes-root-executor/executor.sock` | **MISSING** (`FileNotFoundError` on connect) |
| Mount source | `tmpfs[/hermes-root-executor//deleted]` — host-side tmpfs unmounted or directory removed |
| `hermes-root-executor.service` | **Cannot verify** — no host access path available |
| Docker proxy | Running, read-only (POST /exec → 403) |
| Bridge | Running, read-only only (`runtime_status_read`) |
| SSH to host | Not available (no keys, no hostname resolution, port 22 closed on gateway) |
| `nsenter` | `Operation not permitted` (no CAP_SYS_ADMIN) |

## Why Hermes cannot self-recover

The executor socket is the **only** privileged host path from the container. With the socket dead:

- No `systemctl` access to check or restart the service
- No `docker` exec/create access (proxy blocks mutations)
- No SSH keys or network path to the host
- No `nsenter` capability

This is a **Catch-22**: the one service that could fix the problem is the one that's broken.

## v1 Protocol Proof

**BLOCKED** — cannot perform v1 `executor_health` request. Socket does not exist.

## Legacy Protocol Proof

**BLOCKED** — cannot perform legacy `fs_stat` request. Socket does not exist.

## Audit Correlation

**BLOCKED** — no requests could be sent, therefore no audit entries to correlate.

## Stability Window

**BLOCKED** — cannot query `systemctl show` for PID or restart counter.

## Root cause analysis

### What is known

The mount source `tmpfs[/hermes-root-executor//deleted]` indicates the host-side tmpfs
at `/run/hermes-root-executor` was either unmounted or the directory was removed after
the container's bind-mount was established. This is consistent with the daemon crash:
if the daemon process died, systemd's `RuntimeDirectory=` directive may have cleaned
up the tmpfs, leaving the container with a stale, empty mount.

### What is NOT known (requires host access)

- Actual crash reason (no `journalctl` output available)
- Host Python version
- Installed daemon file permissions and hash
- Whether the new `hermes_root/` package was deployed correctly
- Whether the systemd unit's `RuntimeDirectory=` directive caused the cleanup
- Whether the daemon ever started successfully before crashing

### Installer weaknesses identified (from code review of `main`)

The installer at `scripts/install-hermes-root-executor.sh` has these gaps:

1. **Fake import test** — adds a path and prints "import check passed" without
   actually importing any `hermes_root` module (lines ~130-135)
2. **Non-atomic package switch** — `rm -rf` before `mv`, leaving a window with
   no valid installation
3. **Incomplete healthcheck** — only checks `systemctl is-active`, not socket
   presence, protocol response, or restart-loop detection
4. **Unvalidated rollback** — `systemctl restart ... || true` reports success
   even when the service fails to start

These weaknesses explain why a failed rollout could leave the system unrecovered,
but do not by themselves identify the crash cause.

## Recovery path

Manual host recovery is required. The user must SSH into HermesTrader as root
(or via `operator` breakglass) and:

1. Capture failure evidence: `journalctl -u hermes-root-executor.service -b`
2. Restore the old daemon from `/root/backups/h3b-protocol-rollout-20260712/`
3. Verify socket, service stability, and protocol response
4. Report `ROLLBACK_RECOVERY_GREEN` with evidence

## Gate status

```
H3B_RUNTIME_CONTROL_DEGRADED
```

**Rationale:** The root executor is down. No v1 or legacy protocol proof is
possible from the container. The repository daemon source (PRs #553, #554, #555)
is on `main` but the deployment failed. Issue #531 remains open — all acceptance
criteria (locking, timeout, kill-switch, approval gates, isolated mutating test)
are unproven.

`H3B_RUNTIME_CONTROL_GREEN` requires a successful host recovery followed by
positive v1 proof, legacy proof, audit correlation, and stability verification
from the Hermes container.

## What this report corrects from the initial observation

| Initial claim | Corrected |
|---|---|
| "production daemon is down" | **Retained** — verified from container |
| "socket missing" | **Retained** — verified via `FileNotFoundError` on connect |
| "manual rollback required" | **Retained** — no self-recovery path exists |
| "repository code is correct and tested" | **Removed** — host parity not proven |
| "failure is in the deployment mechanism" | **Removed** — root cause not yet proven |
| `H3B_PROTOCOL_ROLLOUT_ROLLBACK_REQUIRED` | **Replaced** with `H3B_RUNTIME_CONTROL_DEGRADED` |
| Hypothetical recovery commands | **Replaced** with verified mount-source analysis |

## References

- Issue #531 — H3B Root-Executor Client Activation
- Issue #423 — SI-v2-to-Live Roadmap (D1/D2 remain blocked)
- PR #553 — daemon source (merged `34b39f0`)
- PR #554 — state reconciliation (merged `f6be78f`)
- PR #555 — installer package-deploy fix (merged `47dfa56`)
- `scripts/install-hermes-root-executor.sh` — installer with identified weaknesses
- `hermes_root/daemon.py` — dual-protocol daemon (on `main`, not deployed)
