# R1 — Hermes Root Executor Service Implementation (2026-07-11)

Implements the architecture decided in `ADR-2026-07-11-hermes-root-runtime-authority.md`
(R0). This report documents the implementation; per the established D1/D2/D3
pattern, the privileged daemon script itself lives on the HermesTrader host,
not in this repository, and is documented here.

## Architecture Implemented

```
Hermes Agent / UI  (stays UID 10000, unprivileged)
        |
        | local authenticated Unix socket (SO_PEERCRED peer-credential check)
        v
hermes-root-executor.service  (UID 0, full host/Docker authority)
```

## Host Artifacts

| Path | Purpose | Ownership |
|---|---|---|
| `/usr/local/sbin/hermes-root-executor` | Daemon implementation (Python, stdlib only) | root:root, 750 |
| `/etc/systemd/system/hermes-root-executor.service` | systemd unit, `Restart=on-failure` | root:root |
| `/run/hermes-root-executor/executor.sock` | Local-only Unix domain socket, self-healing ownership (root:hermes, 0750 dir / 0660 socket) on every start | root:hermes |
| `/etc/hermes-root-executor/DISABLED` | Emergency disable switch (absence = normal operation) | not present by default |
| `/opt/data/hermes/audit/runtime-actions.jsonl` | Append-only JSONL audit log, secret-redacted | root:root, 600 |
| `/usr/local/sbin/hermes-root-executor-test-client` | Minimal test client for verification (not for production use by Hermes itself — Hermes's real client integration is a separate future task) | root:root, 755 |

## Security Mechanisms (ADR Section 3) — Implemented

1. **Local socket only** — no TCP listener, `AF_UNIX` exclusively.
2. **Peer-credential check** — `SO_PEERCRED` kernel-enforced UID check; only UID 10000 (Hermes) is in `ALLOWED_UIDS`. Verified: `deploy` (UID 1000, incidentally a member of the `hermes` group and therefore able to reach the socket file) is correctly rejected at the peer-credential layer, not just by file permissions.
3. **Exclusive locks** — per-resource-key `fcntl.flock` (non-blocking), one lock file per resource under `/run/hermes-root-executor/locks/`.
4. **Command timeout** — 30s hard limit via `subprocess.run(..., timeout=...)`.
5. **Full audit log** — every command logged with decision, caller PID/UID, redacted args, timestamp; failures and blocks logged identically to successes.
6. **Secret redaction** — any argument matching `KEY`/`SECRET`/`TOKEN`/`PASSWORD` with an `=` is redacted to `NAME=[REDACTED]` before logging.
7. **Emergency disable switch** — presence of `/etc/hermes-root-executor/DISABLED` blocks all commands immediately, checked first before any other logic.

## Verification (live, on HermesTrader, 2026-07-11)

| # | Test | Result |
|---|---|---|
| 1 | Daemon starts as systemd service | PASS — `systemctl status` active, enabled |
| 2 | Peer-credential rejects non-allowed UID | PASS — `deploy` (UID 1000) blocked with `peer_uid_not_allowed`, despite having filesystem access to the socket via group membership |
| 3 | Allowed UID (10000) executes real command | PASS — `docker ps` via executor returned live container list |
| 4 | Full container lifecycle via executor | PASS — created, inspected, stopped, removed a dedicated test container (`r1-verify-testcontainer`); confirmed removed afterward. No production container (`hermes`, `hermes-docker-socket-proxy-1`) was touched |
| 5 | Exclusive lock prevents concurrent conflicting mutation | PASS — two concurrent commands against the same `resource_key`: the long-running one succeeded, the concurrent one was correctly `BLOCKED: resource_locked` |
| 6 | Command timeout enforced | PASS on retest — first attempt revealed a real bug (see below), fixed, then verified: 90s sleep command times out at ~30s, `BLOCKED: command_timeout` |
| 7 | Audit log completeness and secret-safety | PASS — 12 entries covering all decision types (`ALLOWED`, `command_timeout`, `peer_uid_not_allowed`, `resource_locked`), zero secret-pattern matches found in the log |
| 8 | Emergency disable switch | PASS — creating `/etc/hermes-root-executor/DISABLED` blocks all commands immediately; removing it restores normal operation, verified with before/during/after calls |

## Bug Found and Fixed During Verification

Initial timeout handling killed the `docker run` CLI client process on
`subprocess.TimeoutExpired`, but a non-detached `docker run` container is
**not** a child process of that client — killing the client left the
container running, orphaned, on the Docker daemon. Fixed with a best-effort
compensating cleanup (`docker rm -f <resource_key>`) triggered specifically
for non-detached `docker run` timeouts, logged in the audit entry's
`cleanup` field. Retested: no orphaned containers after timeout.

## Explicitly Out of Scope for R1 (per ADR Follow-Up Phases)

- Hermes's own client-side integration (the real Hermes agent connecting to
  this socket) — not implemented, only a minimal test client for
  verification purposes.
- No trading bot or production container (`hermes`,
  `hermes-docker-socket-proxy-1`) was created, mutated, or removed during
  implementation or testing.
- R2 (audit/locking/mutation-evidence hardening) builds on this JSONL audit
  baseline but is a separate phase.
- D1/D2/D3 remain running, untouched, as the documented fallback path during
  the R1-R2 transition (ADR Section 6).

## Verdict

`R1_HERMES_ROOT_EXECUTOR_SERVICE_IMPLEMENTED_AND_VERIFIED`
