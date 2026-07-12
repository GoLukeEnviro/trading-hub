# hermes-root — Hermes Root Executor Client

Bounded, validated AF_UNIX client for the `hermes-root-executor.service`
(ADR-2026-07-11-hermes-root-runtime-authority, R0).

## Usage

```bash
# Read-only actions (A0/A1, no approval required)
hermes-root executor_health
hermes-root docker_ps
hermes-root docker_inspect --container <name>
hermes-root systemctl_status --unit <name>
hermes-root docker_compose_config --file <path>

# Mutating actions (A2, requires approval_reference)
hermes-root docker_create --image <img> --name <name> \
    --approval APPROVED_HERMES_ROOT_EXECUTOR_CLIENT_INTEGRATION
hermes-root docker_stop --container <name> \
    --approval APPROVED_HERMES_ROOT_EXECUTOR_CLIENT_INTEGRATION
hermes-root docker_remove --container <name> \
    --approval APPROVED_HERMES_ROOT_EXECUTOR_CLIENT_INTEGRATION
```

## Protocol

The client communicates with the executor daemon via a local Unix domain
socket (`/run/hermes-root-executor/executor.sock`) using a JSON-line protocol.

### Request schema

```json
{
  "schema_version": "hermes-root-executor.v1",
  "request_id": "<uuid>",
  "correlation_id": "<uuid>",
  "issue_number": 531,
  "task_name": "H3A",
  "execution_class": "A1",
  "resource_key": "docker_ps",
  "action": "docker_ps",
  "argv": ["docker", "ps"],
  "cwd": "/",
  "timeout": 30,
  "approval_reference": null
}
```

### Response schema

```json
{
  "request_id": "<echo>",
  "correlation_id": "<echo>",
  "decision": "ALLOWED | BLOCKED",
  "reason": "ok | resource_locked | peer_uid_not_allowed | ...",
  "result": {},
  "audit_seq": 1
}
```

## Security contract

- **No shell=True** — commands are transmitted as structured argv lists.
- **Unknown fields fail-closed** — the executor rejects unknown keys.
- **Unknown actions fail-closed** — only allowlisted actions are accepted.
- **Secret redaction** — credential-like values are masked before local output.
- **A2 gate** — mutating actions require an `approval_reference`.
- **A3 gate** — live-capital actions are always blocked without an externally
  signed, time-limited approval (private key never on HermesTrader).

## Execution classes

| Class | Scope | Approval required |
|-------|-------|-------------------|
| A0 | Read-only inspection | None |
| A1 | Repository-only (branch, code, docs, PR) | None |
| A2 | Dry-run runtime | `approval_reference` |
| A3 | Live capital | Externally signed approval |

## Actions

### Read-only (A0/A1)

| Action | Description | argv |
|--------|-------------|------|
| `executor_health` | Check executor daemon health | `[]` |
| `docker_ps` | List running containers | `["docker", "ps"]` |
| `docker_inspect` | Inspect a container | `["docker", "inspect", "<name>"]` |
| `systemctl_status` | Check a systemd unit | `["systemctl", "status", "<unit>"]` |
| `docker_compose_config` | Validate compose file | `["docker", "compose", "-f", "<path>", "config"]` |

### Mutating (A2)

| Action | Description | argv |
|--------|-------------|------|
| `docker_create` | Create a container | `["docker", "run", "-d", "--name", "<name>", "<image>"]` |
| `docker_stop` | Stop a container | `["docker", "stop", "<name>"]` |
| `docker_remove` | Remove a container | `["docker", "rm", "<name>"]` |

## Testing

```bash
uv run python -m pytest tests/test_hermes_root_client.py tests/test_hermes_root_daemon.py -v
```

Client tests use a fake AF_UNIX socket server — no real executor required.
Daemon tests run the repository daemon (`hermes_root/daemon.py`) itself
against a temporary socket/lock-dir/audit-path — also no real executor
required, and they never touch the production socket, kill-switch, or
audit file.

## Repository daemon (source of truth)

The daemon that used to exist only as an unversioned host artifact
(`/usr/local/sbin/hermes-root-executor`) is now versioned in this repository
as `hermes_root/daemon.py`, composed from:

| Module | Responsibility |
|--------|-----------------|
| `hermes_root/protocol.py` | Normalizes both the legacy protocol (`{category, args, resource_key}`) and this `hermes-root-executor.v1` protocol into one internal request model. Fail-closed on unknown fields, types, or schema_version. |
| `hermes_root/policy.py` | Execution-class gates (A0-A3). Server-side and authoritative — the client-side validation above is defense-in-depth only. |
| `hermes_root/actions.py` | Explicit argv builders for every v1 action (the same `READONLY_ACTIONS`/`MUTATING_ACTIONS` from `hermes_root/schema.py`). No generic shell execution. |
| `hermes_root/audit.py` | Appends structured v2 audit entries to the same append-only `runtime-actions.jsonl` the legacy daemon has always written to. |

The daemon serves **both** protocols on the same socket: legacy requests get
byte-for-byte identical behaviour to the production host daemon (same
categories, same locking, same 30s timeout, same kill-switch), while v1
requests get the full gate/action/audit pipeline above. Legacy requests never
gain new capabilities through this change.

**This repository daemon is not yet deployed.** The production host still
runs the original unversioned script. `scripts/install-hermes-root-executor.sh`
documents the deployment contract (backup, syntax-check, atomic move,
restart-with-rollback) but is intentionally not executed as part of adding
it — deployment is a separate, explicitly-gated rollout decision.

## References

- ADR-2026-07-11-hermes-root-runtime-authority (R0)
- docs/reports/r1-hermes-root-executor-implementation-2026-07-11.md
- docs/reports/r2-audit-locking-mutation-evidence-2026-07-11.md
- docs/reports/h3b-root-executor-source-migration-2026-07-12.md
