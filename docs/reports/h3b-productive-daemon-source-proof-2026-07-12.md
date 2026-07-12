# H3B — Productive Root-Executor Daemon Source-of-Truth Proof

**Date:** 2026-07-12
**Classification:** A0 — Read-only evidence collection
**Verdict:** `STOP — PRODUCTIVE_DAEMON_NOT_FROM_REPOSITORY`

## Request

> Beweise die Source of Truth des produktiven Root-Executor-Daemons. Wenn der
> laufende /usr/local/sbin/hermes-root-executor aus dem Trading-Hub-Repository
> erzeugt wird, implementiere ausschließlich dort die Protokoll-Reconciliation.
> Falls der Daemon aus einer anderen Quelle stammt, stoppe sofort, dokumentiere
> die tatsächliche Quelle mit Belegen und implementiere nichts.

## Evidence Collected

### 1. Productive daemon identity

| Property | Value |
|----------|-------|
| Path | `/usr/local/sbin/hermes-root-executor` |
| Size | 8521 bytes |
| Type | Monolithic single-file Python script (stdlib only) |
| Deployed | 2026-07-11 14:17:49 UTC |
| systemd unit | `/etc/systemd/system/hermes-root-executor.service` (379 bytes, 2026-07-11) |
| Service status | `active (running)` since 2026-07-11 15:13:28 UTC |
| Main PID | 2170 (`/usr/bin/python3 /usr/local/sbin/hermes-root-executor`) |
| Protocol | **Legacy only** — `{category, args, resource_key}` |
| Categories | `docker`, `systemd`, `fs_stat`, `fs_ls` |
| v1 support | **None** — `executor_health` returns `BLOCKED: unknown_category` |

### 2. Repository daemon identity

| Property | Value |
|----------|-------|
| Path | `hermes_root/daemon.py` |
| Size | 14822 bytes |
| Type | Modular package (9 modules: `daemon.py`, `protocol.py`, `actions.py`, `policy.py`, `audit.py`, `schema.py`, `validate.py`, `redact.py`, `client.py`) |
| Commit | `38dbaa5` (2026-07-12 22:43:36 UTC) |
| Branch | `feat/h3b-version-root-executor-daemon` |
| Protocol | **Dual** — Legacy + `hermes-root-executor.v1` |
| Deployed | **Never** — `H3B_DAEMON_SOURCE_READY`, not deployed |

### 3. Timeline proof

| Date | Event | Evidence |
|------|-------|----------|
| 2026-07-11 14:11 | R1 daemon deployed to host | `stat` shows `Birth: 2026-07-11 14:11:21` |
| 2026-07-11 14:17 | R1 daemon last modified | `stat` shows `Modify: 2026-07-11 14:17:49` |
| 2026-07-11 15:13 | Service started | `systemctl status` shows `Active since Sat 2026-07-11 15:13:28` |
| 2026-07-11 16:22 | R1 report merged (PR #508) | Commit `4471821` |
| 2026-07-12 22:43 | Repository daemon created | Commit `38dbaa5` |

**The production daemon was deployed ~31 hours before the repository daemon
even existed.** The repository daemon cannot be the source of the production
daemon.

### 4. R1 report explicit statement

From `docs/reports/r1-hermes-root-executor-implementation-2026-07-11.md` (PR #508):

> *"per the established D1/D2/D3 pattern, the privileged daemon script itself
> lives on the HermesTrader host, not in this repository, and is documented
> here."*

The R1 report explicitly confirms the daemon was authored and deployed directly
on the host, outside the repository.

### 5. Runtime protocol verification

**Legacy request (works):**
```json
{"category": "fs_stat", "args": ["/usr/local/sbin/hermes-root-executor"], "resource_key": "check:source"}
→ {"decision": "ALLOWED", "returncode": 0, "stdout": "…", "stderr": ""}
```

**v1 request (blocked):**
```json
{"schema_version": "hermes-root-executor.v1", "action": "executor_health", …}
→ {"decision": "BLOCKED", "reason": "unknown_category"}
```

The production daemon has no `schema_version` dispatch, no `protocol.normalize_request()`,
no `_handle_v1()`. It is a single `handle_command()` function that only checks
`CATEGORY_BINARIES` — a flat dict of four legacy categories.

### 6. Structural comparison

| Feature | Production daemon (8521 B) | Repository daemon (14822 B) |
|---------|---------------------------|----------------------------|
| Architecture | Single file, all functions inline | Package: 9 modules |
| Protocol dispatch | `if category not in CATEGORY_BINARIES` | `protocol.normalize_request()` → legacy/v1 branch |
| Audit | Inline `audit()` function | `hermes_root.audit.write_audit_entry()` |
| Locking | Inline `acquire_lock()`/`release_lock()` | `RootExecutorDaemon._acquire_lock()` |
| Timeout cleanup | Inline `cleanup_after_timeout()` | `RootExecutorDaemon._cleanup_after_timeout()` |
| Policy gate | None (legacy has no execution classes) | `policy.evaluate_gate()` with A0–A3 |
| Action allowlist | None (legacy has no actions) | `actions.build_argv()` with `ALL_ACTIONS` |
| Schema version | None | `SCHEMA_VERSION = "hermes-root-executor.v1"` |
| Daemon version | None | `DAEMON_VERSION = "2.0.0-repo"` |
| Request ID | None (generated per-request) | `request_id` + `correlation_id` |
| Structured response | `{decision, returncode, stdout, stderr}` | `{schema_version, request_id, correlation_id, decision, reason, returncode, stdout, stderr, started_at, finished_at, duration_ms, resource_key, action, execution_class, audit_id}` |

## Root Cause

The production daemon was authored and deployed directly on the HermesTrader
host as part of R1 (PR #508, 2026-07-11). It was never sourced from the
trading-hub repository. The repository daemon (`hermes_root/daemon.py`) was
created later (2026-07-12) as a reimplementation with dual-protocol support,
but has never been deployed.

The `scripts/install-hermes-root-executor.sh` deployment contract exists in the
repository but has never been executed. The production daemon was installed by a
different, undocumented path (likely manual `scp`/`cat` by the `deploy` user,
as indicated by the R1 report's `Co-authored-by: deploy <deploy@hermestrader.local>`).

## Decision

**STOP.** No code shall be written, tested, committed, pushed, or PR'd for
protocol reconciliation in the repository daemon, because the production daemon
does not originate from this repository. The repository daemon is a separate,
never-deployed reimplementation.

## Next Step

The protocol reconciliation must happen at the **deployment boundary**, not in
the repository daemon. Two paths exist:

1. **Deploy the repository daemon** via `scripts/install-hermes-root-executor.sh`
   (requires explicit, gated rollout approval per the operational state).
2. **Patch the production daemon in-place** on the host to add v1 protocol
   support (requires root access to the host, outside repository scope).

Neither path is authorized by the current operational state without explicit
approval. The operational state says:

> *"H3B root-executor client activation → socket bind-mount complete; blocked on
> production daemon still speaking only the legacy protocol. Repository daemon
> source now exists (H3B_DAEMON_SOURCE_READY, PR pending review) but is not
> deployed — deployment requires a separate, explicitly-gated rollout approval."*

## Validation

- [x] Production daemon content retrieved via executor socket (full source read)
- [x] Production daemon stat confirmed (size, dates, ownership)
- [x] systemd service status confirmed (active, PID, start time)
- [x] Legacy protocol confirmed working (fs_stat, docker, systemd, fs_ls)
- [x] v1 protocol confirmed blocked (`unknown_category`)
- [x] Repository daemon commit timeline confirmed (38dbaa5, 2026-07-12)
- [x] R1 report explicit statement confirmed (PR #508)
- [x] install script confirmed never executed (no deployment audit trail)
- [x] Operational state confirmed (H3B_DAEMON_SOURCE_READY, not deployed)
