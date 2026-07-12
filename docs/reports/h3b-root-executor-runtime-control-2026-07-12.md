# H3B — Root-Executor Runtime Control Report

**Date:** 2026-07-12
**Issue:** #531
**Branch:** `ops/h3b-root-executor-client-activation`
**Execution class:** A2
**Based on main:** `f471f4a661f432939530ba6128d70d0e843a1975`
**H3A dependency:** PR #533 / `38203a7a835bc2e8598566ac98e8f572a4ca4377`
**Approval:** `APPROVED_HERMES_ROOT_EXECUTOR_CLIENT_INTEGRATION`
**Correlation ID:** `h3b-995ca15eae70`

---

## 1. Start-Gates

### A. Repository

| Check | Result |
|-------|--------|
| `git status --short` | Clean |
| Branch | `main` |
| HEAD | `f471f4a` |
| `origin/main` | `f471f4a` (in sync) |
| H3A in origin/main | ✅ `38203a7` is ancestor |
| Open PRs | None (no overlapping roadmap PR) |

### B. Issues

| Issue | State |
|-------|-------|
| #525 (H1) | CLOSED |
| #526 (H2) | CLOSED |
| #530 (H3A) | CLOSED |
| #531 (H3B) | OPEN |
| #527 (R5A) | OPEN |

### C. Approval

Marker `APPROVED_HERMES_ROOT_EXECUTOR_CLIENT_INTEGRATION` present in session context. ✅

### D. Root Executor — CRITICAL FINDING

| Check | Expected | Actual |
|-------|----------|--------|
| Socket path | `/run/hermes-root-executor/executor.sock` | **MISSING** — directory does not exist in container |
| Socket directory | `/run/hermes-root-executor/` | **MISSING** |
| Daemon binary | `/usr/local/sbin/hermes-root-executor` | **MISSING** (not accessible from container) |
| systemd unit | `/etc/systemd/system/hermes-root-executor.service` | **MISSING** (not accessible from container) |
| Audit log | `/opt/data/hermes/audit/runtime-actions.jsonl` | **MISSING** |

The `hermes-root-executor.service` is documented as "shipped and active" (R1 report, PR #508), but it is **not accessible from within the Hermes container**. The socket directory `/run/hermes-root-executor/` is not bind-mounted into the container, unlike `/run/hermes-bridge/` which is mounted and functional.

### E. Bootstrap Path Analysis

| Path | Status | Capability |
|------|--------|------------|
| D3 Bridge (`hermes-bridge-client`) | ✅ Active | Read-only: `read_report`, `git_status`, `runtime_status_read`, `old_vps_probe`. Mutation: `github_comment` (approval-gated). **No Docker/systemd mutation.** |
| D2 Host Runner | ❌ Not installed | Documented as PLAN-ONLY package. Files at `/usr/local/sbin/hermes-runtime-runner` etc. do not exist. |
| Raw `docker.sock` | ❌ Absent (by design) | Not mounted in Hermes container. |
| `hermes` CLI | ❌ Not on PATH | No profile/config management available from within container. |
| Direct socket access | ❌ | `/run/hermes-root-executor/` not mounted. |

### F. Backup Gate

Restic configuration not accessible from within the container. No `restic` binary on PATH. Cannot verify snapshot status or create pre-H3B snapshot from within Hermes.

---

## 2. Blocker Analysis

**Root cause:** The `hermes-root-executor.service` socket directory is not bind-mounted into the Hermes container. The container currently has these mounts:

- `/opt/data/hermes` → `/opt/data` (rw)
- `/run/hermes-bridge` → `/run/hermes-bridge` (rw)
- `/opt/data/hermes/bin/gh` → `/usr/local/bin/gh` (ro)
- `/opt/data/projects` → `/workspace/projects` (rw)

Missing: `/run/hermes-root-executor` → `/run/hermes-root-executor`

Without this mount, the H3A client cannot reach the executor socket, and no read-only or mutating proof can be performed.

**Required host-side action:** Add a bind-mount of `/run/hermes-root-executor` (or the parent directory) into the Hermes container, matching the existing pattern used for `/run/hermes-bridge`. The Hermes container must then be recreated.

**Who can perform this:** A human operator with host access (via SSH, the `operator` user, or the `deploy` user). Hermes cannot perform this from within the container with currently available tools — the D3 bridge has no compose/container-mutation capability, and the D2 host runner is not installed.

---

## 3. Decision

**H3B is BLOCKED.** The executor exists on the host (per R1 verification) but is not reachable from the Hermes container. No auditierbarer Bootstrap-Pfad exists to mount the socket from within the container.

### What would be needed to unblock

1. Host-side operator adds bind-mount to Hermes compose configuration:
   ```yaml
   volumes:
     - /run/hermes-root-executor:/run/hermes-root-executor:ro
   ```
2. Verify socket permissions: `srw-rw---- root:hermes` (UID 10000 must be in `hermes` group)
3. Recreate Hermes container: `docker compose up -d hermes`
4. Verify socket reachable from within container
5. Resume H3B from checkpoint

### What Hermes CAN do now

- Write the checkpoint report (this file)
- Create the branch and commit the report
- Push and create a PR documenting the blocker
- The PR serves as evidence that H3B was attempted and blocked at the bootstrap gate

---

## 4. Gate Status

**BLOCKED_BY_BOOTSTRAP_CONTROL_PATH**

The `hermes-root-executor.service` socket is not mounted into the Hermes container. No auditierbarer Bootstrap-Pfad exists to perform the mount from within the container. D3 bridge has no compose/container-mutation capability. D2 host runner is not installed.

### Evidence

| Item | Value |
|-------|-------|
| Container UID | 10000 (hermes) |
| Container GID | 10000 (hermes) |
| Bridge socket | `/run/hermes-bridge/bridge.sock` — mounted, functional |
| Executor socket | `/run/hermes-root-executor/executor.sock` — NOT mounted |
| Docker access | Read-only proxy only (port 2375), no raw socket |
| D3 bridge actions | read_report, git_status, runtime_status_read, old_vps_probe, github_comment |
| D2 host runner | Not installed |
| `hermes` CLI | Not on PATH |

---

## 5. Next Step

Human operator must mount `/run/hermes-root-executor` into the Hermes container. After container recreation, H3B can resume from this checkpoint with correlation ID `h3b-995ca15eae70`.
