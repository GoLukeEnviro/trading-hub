# H3B Protocol Rollout — FAILURE Report

**Date:** 2026-07-12 23:13 UTC
**Gate:** `H3B_PROTOCOL_ROLLOUT_ROLLBACK_REQUIRED`
**Classification:** A2 — Approved dry-run runtime (failed, requires manual host recovery)

## What happened

1. PR #553 (daemon source) merged at `34b39f0` ✅
2. PR #554 (state reconciliation) merged at `f6be78f` ✅
3. PR #555 (installer package-deploy fix) merged at `47dfa56` ✅
4. Cron job `cfe85ed7f7ee` (trading-hub-roadmap-tick) paused ✅
5. Backup created at `/root/backups/h3b-protocol-rollout-20260712/` ✅
6. Install script executed via `nsenter` on host ✅
7. `hermes-root-executor.service` restarted ✅
8. **New daemon crashed — socket dead** 🔴

## Current state

| Component | Status |
|-----------|--------|
| `/run/hermes-root-executor/executor.sock` | **MISSING** — daemon not running |
| `/run/hermes-root-executor/locks/` | **MISSING** |
| `hermes-root-executor.service` | **FAILED** (presumed, cannot verify from container) |
| Hermes container | Running, healthy |
| Docker proxy | Running |
| Bridge | Running (read-only only) |
| Cron job | Recreated as `f18cbcdb56b7` (old job lost in session state reset) |
| Backup | Intact at `/root/backups/h3b-protocol-rollout-20260712/` |

## Why recovery from container is impossible

- The executor socket is the **only** path for privileged host commands from the container
- The Docker proxy blocks container creation (`403 Forbidden`)
- The Bridge only supports read-only operations
- The Hermes container has no `nsenter`/`systemctl`/`sudo` access
- The container runs as UID 10000, unprivileged

## Daemon works in isolation

The repository daemon was tested in the container and works correctly:

```
Legacy: {"decision": "ALLOWED", "returncode": 0, ...}  ✅
V1:     {"decision": "ALLOWED", "reason": "ok", ...}    ✅
```

The crash on the host is likely due to one of:
- Python version mismatch (host may have older Python without `from __future__ import annotations` support)
- `nsenter`-based `systemctl restart` not working correctly in the install context
- Package deployment path issue (the `hermes_root/` package may not have been placed correctly via `nsenter`)
- The `systemd` unit's `RuntimeDirectory=` directive may have reset the socket directory permissions

## Manual recovery required

The user must SSH into HermesTrader as root and execute:

```bash
# 1. Restore old daemon
cp -p /root/backups/h3b-protocol-rollout-20260712/hermes-root-executor /usr/local/sbin/

# 2. Remove new package (if present)
rm -rf /usr/local/sbin/hermes_root

# 3. Restart service
systemctl restart hermes-root-executor.service

# 4. Verify
systemctl status hermes-root-executor.service
ls -la /run/hermes-root-executor/executor.sock
```

## Investigation needed before retry

1. Check `journalctl -u hermes-root-executor.service` for the crash reason
2. Verify host Python version supports all daemon imports
3. Test the install script in a dry-run mode (DESTDIR) before retrying
4. Consider adding a `--check` mode to the install script that validates without restarting

## Backup contents

```
/root/backups/h3b-protocol-rollout-20260712/
├── hermes-root-executor          (old daemon, 8521 bytes)
├── old-daemon.sha256             (ff228215b5e28c2e...)
└── hermes-root-executor.service  (systemd unit)
```

## Cron job

The original cron job `cfe85ed7f7ee` was lost when the Hermes session state reset.
Recreated as `f18cbcdb56b7` with identical configuration:
- Name: `trading-hub-roadmap-tick`
- Schedule: `*/30 * * * *`
- Workdir: `/workspace/projects/trading-hub`
- ⚠️ Gateway not running — jobs won't fire automatically

## Verdict

```
H3B_PROTOCOL_ROLLOUT_ROLLBACK_REQUIRED
```

The rollout failed. The production daemon is down. Manual host recovery is required.
The repository code (PRs #553, #554, #555) is correct and tested — the failure is
in the deployment mechanism, not the daemon itself.
