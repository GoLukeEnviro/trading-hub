# Hermes H3A — Root-Executor Client Contract Report

**Date:** 2026-07-12
**Issue:** #530
**Branch:** `feat/h3a-root-executor-client-contract`
**Execution class:** A1 — Repository-only
**Based on main:** `ac72c4a2f3e2d49aa74f5210d82aa949e634bf90`

---

## 1. Goal

Implement a production-ready, tested client and tool contract for the existing
`hermes-root-executor.service` (R0/R1) without modifying the host or container
runtime.

## 2. Protocol reconstruction

The executor wire protocol was reconstructed from:

- R1 report (`docs/reports/r1-hermes-root-executor-implementation-2026-07-11.md`)
- R2 report (`docs/reports/r2-audit-locking-mutation-evidence-2026-07-11.md`)
- D3 bridge reference implementation (`/opt/data/bridge/bridge_protocol.json`,
  `/opt/data/bin/hermes-bridge-client`)
- R0 ADR (`docs/decisions/ADR-2026-07-11-hermes-root-runtime-authority.md`)

Key protocol facts:

| Property | Value |
|----------|-------|
| Transport | AF_UNIX, SOCK_STREAM |
| Socket path | `/run/hermes-root-executor/executor.sock` |
| Auth | SO_PEERCRED (UID 10000) |
| Format | JSON-line (one JSON object per line, newline-terminated) |
| Timeout | 30s hard limit |
| Decision types | ALLOWED, command_timeout, peer_uid_not_allowed, resource_locked, emergency_disable_switch_active, unknown_category, invalid_args |

## 3. Implementation

### Module structure

```
hermes_root/
├── __init__.py      # Public API exports
├── schema.py        # ExecutorRequest, ExecutorResponse dataclasses
├── client.py        # AF_UNIX transport (send_request)
├── validate.py      # Request validation (fail-closed)
└── redact.py        # Secret redaction for local output
```

### Security contract

| Requirement | Implementation |
|-------------|---------------|
| No shell=True | argv transmitted as structured list, never concatenated |
| Unknown fields fail-closed | Schema validation rejects unknown keys |
| Unknown actions fail-closed | Only actions in ALL_ACTIONS accepted |
| Secret redaction | KEY/SECRET/TOKEN/PASSWORD patterns + long base64/hex strings redacted |
| A2 gate | `execution_class=A2` requires `approval_reference` |
| A3 gate | `execution_class=A3` always blocked (requires external signature) |
| Max payload size | 1 MiB response cap |
| Timeout | Configurable connect + read timeouts |

### Supported actions

**Read-only (A0/A1):**
`executor_health`, `docker_ps`, `docker_inspect`, `systemctl_status`,
`docker_compose_config`

**Mutating (A2, requires approval):**
`docker_create`, `docker_stop`, `docker_remove`

## 4. Tests

29 tests with fake AF_UNIX socket server:

| Category | Tests | Status |
|----------|-------|--------|
| Positive — valid request | 4 | ✅ |
| Schema validation | 11 | ✅ |
| A2/A3 approval gates | 3 | ✅ |
| Transport errors | 4 | ✅ |
| Shell injection | 1 | ✅ |
| Secret redaction | 4 | ✅ |
| Server error response | 1 | ✅ |
| Timeout | 1 | ✅ |
| **Total** | **29** | **ALL GREEN** |

### Test coverage

- Valid request succeeds
- Correlation ID preserved end-to-end
- All 5 read-only actions accepted
- argv preserved as list (not string)
- Bad schema version blocked
- Unknown action blocked
- Invalid execution class blocked
- Empty request_id blocked
- Empty correlation_id blocked
- Negative issue_number blocked
- argv not a list blocked
- argv too long blocked
- argv element too long blocked
- cwd not absolute blocked
- Timeout out of range blocked
- A2 without approval blocked
- A2 with approval passes
- A3 always blocked
- Socket not found → ExecutorConnectionError
- Invalid JSON response → ExecutorProtocolError
- Empty response → ExecutorProtocolError
- Too large response → ExecutorProtocolError
- Shell injection stays single argv element
- Secret keys redacted
- Long token strings redacted
- argv secrets redacted
- argv token values redacted
- Server BLOCKED response handled
- Client timeout → ExecutorTimeoutError

## 5. Deliverables

| Deliverable | Path |
|-------------|------|
| Client code | `hermes_root/` (4 modules) |
| Tests | `tests/test_hermes_root_client.py` (29 tests) |
| Protocol docs | `commands/hermes-root-runtime.md` |
| This report | `docs/reports/hermes-root-client-contract-2026-07-12.md` |

## 6. Validation

- `git diff --check` ✅
- `uv run python -m pytest tests/test_hermes_root_client.py -v` ✅ **29 passed**
- `uv run python -m pytest tests/test_hermestrader_dryrun_compose.py -q` ✅ **106 passed, 1 skipped**
- No host/Docker/runtime mutation (A1 only)
- No secrets exposed
- No new dependencies (stdlib only)

## 7. Stop condition check

| Stop condition | Status |
|----------------|--------|
| Executor protocol not reconstructable | NO — reconstructed from R1/R2 + D3 bridge |
| Host change would be necessary | NO — A1 only |
| Raw docker.sock would be necessary | NO |
| Client would need sudo | NO |
| A2/A3 approval would need to be simulated | NO — tested with fake server |
| Tests or CI red | NO — 135 passed, 1 skipped |
| Secret leak | NONE |

## 8. Merge prerequisites

- [x] Client code implemented and tested
- [x] Protocol documentation written
- [x] Report written and committed
- [x] No host/Docker/bot/strategy/config mutation
- [x] No secret exposure
- [x] No CI/state drift

---

## Gate status

`READY_FOR_REVIEW`

## Next step

After merge: close #530 with merge SHA, unblock #531 (H3B).
Do NOT start H3B in the same run — requires APPROVED_HERMES_ROOT_EXECUTOR_CLIENT_INTEGRATION.
