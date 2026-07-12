# H3B — Root-Executor Runtime Control Report

**Date:** 2026-07-12
**Issue:** #531
**Branch:** `ops/h3b-root-executor-client-activation`
**Execution class:** A2
**Based on main:** `2d83da6`
**H3A dependency:** PR #533 / `38203a7a835bc2e8598566ac98e8f572a4ca4377`
**Approval:** `APPROVED_HERMES_ROOT_EXECUTOR_CLIENT_INTEGRATION`
**Correlation ID:** `h3b-6be0e4d739c3`

---

## 1. Start-Gates

### A. Repository

| Check | Result |
|-------|--------|
| `git status --short` | Clean (2 new files unstaged) |
| Branch | `main` → `ops/h3b-root-executor-client-activation` |
| HEAD | `2d83da6` |
| `origin/main` | `2d83da6` (in sync) |
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

Marker `APPROVED_HERMES_ROOT_EXECUTOR_CLIENT_INTEGRATION` present. ✅

### D. Root Executor — CRITICAL FINDING

| Check | Expected | Actual |
|-------|----------|--------|
| Socket path | `/run/hermes-root-executor/executor.sock` | **MISSING** |
| Socket directory | `/run/hermes-root-executor/` | **MISSING** |
| Bridge socket | `/run/hermes-bridge/bridge.sock` | ✅ Present, functional |
| Docker proxy | Read-only via port 2375 | ✅ Reachable, 403 on mutations |
| Hermes UID/GID | 10000/10000 | ✅ Confirmed |
| `hermes` CLI | Not in container | ❌ Not on PATH |

The `hermes-root-executor.service` socket directory is **not bind-mounted** into the Hermes container. The bridge socket (`/run/hermes-bridge`) is mounted and functional, proving the mount pattern works — but the executor socket mount is missing.

### E. Bootstrap Path Analysis

| Path | Status | Capability |
|------|--------|------------|
| D3 Bridge | ✅ Active | Read-only Docker visibility + `github_comment` mutation. **No compose/container mutation.** |
| D2 Host Runner | ❌ Not installed | — |
| Raw `docker.sock` | ❌ Absent (by design) | — |
| Direct executor socket | ❌ Not mounted | — |

**No auditierbarer Bootstrap-Pfad exists.** Hermes cannot mount the socket from within the container.

### F. Backup Gate

Restic not accessible from within container. No `restic` binary on PATH. Backup gate cannot be verified from within Hermes.

---

## 2. H3A Client Verification

### Client modules (all present on `main`)

| File | Status |
|------|--------|
| `hermes_root/__init__.py` | ✅ |
| `hermes_root/schema.py` | ✅ |
| `hermes_root/client.py` | ✅ |
| `hermes_root/validate.py` | ✅ |
| `hermes_root/redact.py` | ✅ |
| `tests/test_hermes_root_client.py` | ✅ 29 tests (H3A) |

### CLI entry point (added in H3B)

| File | Status |
|------|--------|
| `hermes_root/__main__.py` | ✅ NEW — stdlib-only CLI wrapper |

### CLI behavior verified

```
$ python -m hermes_root --help          → exit 0, full help output
$ python -m hermes_root executor_health → exit 3 (socket not found)
$ python -m hermes_root docker_ps       → exit 3 (socket not found)
$ python -m hermes_root docker_create --image alpine --name test
                                        → exit 2 (A2 requires approval)
$ python -m hermes_root docker_create --image alpine --name test --approval APPROVED_TEST
                                        → exit 3 (socket not found, but validation passed)
```

### Client/Server protocol compatibility

The H3A client implements the documented protocol from `commands/hermes-root-runtime.md`:
- JSON-line framing (newline-delimited)
- `schema_version: "hermes-root-executor.v1"`
- Structured `argv` lists (no shell strings)
- `correlation_id` echo in response
- `decision: ALLOWED | BLOCKED`
- `audit_seq` tracking
- Secret redaction before local output

**Cannot verify against real server** — socket not mounted. Protocol compatibility is assumed from R1/R2 documentation but not runtime-proven.

---

## 3. CLI Implementation (H3B addition)

### `hermes_root/__main__.py`

- Stdlib-only (`argparse`, `json`, `os`, `sys`, `uuid`)
- No `shell=True`, no shell string concatenation
- Structured `argv` lists
- Explicit `execution_class`, `issue_number`, `correlation_id`, `resource_key`, `cwd`, `timeout`
- Fail-closed on unknown actions
- A2 blocked without `--approval`
- A3 always blocked (client-side validation)
- `--json` flag for machine-readable output
- Sensible exit codes: 0=ALLOWED, 1=BLOCKED, 2=validation error, 3=connection error

### New CLI tests (11 tests)

| Test | What it proves |
|------|---------------|
| `test_cli_help` | `--help` exits 0 |
| `test_cli_unknown_action` | Unknown action → exit 2 |
| `test_cli_a2_without_approval` | A2 without `--approval` → exit 2 |
| `test_cli_a3_blocked` | A3 always blocked → exit 2 |
| `test_cli_missing_required_arg` | Missing `--container` → exit 2 |
| `test_cli_socket_not_found` | Missing socket → exit 3 |
| `test_cli_json_output` | `--json` produces valid JSON |
| `test_cli_readonly_action` | Read-only action → exit 0 |
| `test_cli_a2_with_approval` | A2 with approval → exit 0 |
| `test_cli_secret_redaction_in_argv` | No raw secrets in output |
| `test_cli_shell_injection_stays_single_arg` | argv stays list, not string |

---

## 4. Test Results

```
tests/test_hermes_root_client.py ........40 passed (29 H3A + 11 H3B CLI)
tests/test_hermestrader_dryrun_compose.py ...106 passed, 1 skipped
Total: 146 passed, 1 skipped
```

---

## 5. Decision

**BLOCKED_BY_BOOTSTRAP_CONTROL_PATH**

The `hermes-root-executor.service` socket (`/run/hermes-root-executor/executor.sock`) is not mounted into the Hermes container. No auditierbarer Bootstrap-Pfad exists to perform the mount from within the container.

### What H3B delivers

- ✅ Production CLI entry point (`hermes_root/__main__.py`) — `python -m hermes_root`
- ✅ 11 new CLI tests (40 total client tests, all passing)
- ✅ CLI verified: help, validation, error handling, JSON output, secret redaction
- ✅ Client/Server protocol documented and implemented
- ❌ Runtime proof — blocked by missing socket mount

### What unblocks H3B

Host-side operator must:
1. Add bind-mount to Hermes compose config:
   ```yaml
   volumes:
     - /run/hermes-root-executor:/run/hermes-root-executor:ro
   ```
2. Verify socket permissions allow UID 10000
3. Recreate Hermes container
4. Verify socket reachable: `python -m hermes_root executor_health`

### What Hermes CAN do now

- `python -m hermes_root executor_health` — will work once socket is mounted
- `python -m hermes_root docker_ps` — will work once socket is mounted
- `python -m hermes_root docker_inspect --container hermes` — will work once socket is mounted
- All read-only and A2 mutating actions are implemented and tested

---

## 6. Evidence

| Item | Value |
|-------|-------|
| Issue | #531 OPEN |
| Branch | `ops/h3b-root-executor-client-activation` |
| Base HEAD | `2d83da6` |
| H3A Merge-SHA | `38203a7` |
| Correlation ID | `h3b-6be0e4d739c3` |
| Container UID/GID | 10000/10000 |
| Bridge socket | ✅ `/run/hermes-bridge/bridge.sock` |
| Executor socket | ❌ Not mounted |
| Docker proxy | Read-only (403 on mutations) |
| H3A client tests | 29 passed |
| H3B CLI tests | 11 passed |
| HermesTrader tests | 106 passed, 1 skipped |
| Total | 146 passed, 1 skipped |

---

## 7. Gate Status

**BLOCKED_BY_BOOTSTRAP_CONTROL_PATH**

The executor daemon exists on the host (per R1 verification) but its socket is not reachable from the Hermes container. The H3B CLI is production-ready and will activate immediately once the socket mount is added.
