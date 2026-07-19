# SEC-3 — Durable pre-execution intent audit

**Date:** 2026-07-19
**Issue:** [#634](https://github.com/GoLukeEnviro/trading-hub/issues/634)
**Execution class:** A1 (repository-only)
**Runtime/deployment mutation:** None
**Deployment status:** **NOT DEPLOYED**

## Outcome

The root executor now writes a durable, redacted `intent` audit event before
every approved legacy or v1 subprocess execution. The event is flushed and
`fsync`-ed before `subprocess.run()` can be reached. A failure at open,
write, flush, file `fsync`, or new-file directory `fsync` blocks execution.

Every attempted subprocess receives one stable `audit_id`. Its durable intent
is followed by exactly one terminal event:

- `completion` for exit code 0;
- `execution_error` for a non-zero exit code or spawn/runtime error;
- `timeout` when the command exceeds its timeout.

Policy, allowlist, validation, and resource-lock rejections emit only
`rejected`; they never emit `intent`. `executor_health` remains an
in-process action and emits a single `completion` event.

## Root cause closed

The previous v2 writer appended only after execution and did not call
`flush()` or `fsync()`. A privileged action could therefore start without a
durable audit record, and a crash could leave no durable evidence of the
attempt.

The v3 writer preserves append-only JSONL, adds event correlation, serializes
in-process writers, flushes userspace buffers, syncs the audit file, and syncs
the parent directory when the audit file is first created.

## Ordering guarantee

For approved subprocess actions the enforced order is:

1. policy/allowlist validation;
2. resource lock acquisition;
3. append redacted `intent` with stable `audit_id`;
4. `flush()` and file `fsync()` (plus directory `fsync` for a new file);
5. invoke `subprocess.run()`;
6. append and durably sync one correlated terminal event;
7. release the resource lock;
8. return the client response.

If intent durability fails, step 5 is unreachable and the response is
`BLOCKED / audit_intent_durability_failure`. If terminal durability fails
after the subprocess has returned, success and subprocess output are withheld
and the response is `BLOCKED / audit_terminal_durability_failure`.

## Audit and redaction contract

Schema `hermes-root-executor-audit.v3` adds:

- `event`;
- stable pair-level `audit_id`;
- unique per-record `audit_event_id`;
- `durability_required=flush+fsync`.

The audit API does not accept raw command arguments or subprocess output.
It records action/category/resource identity, policy context, return code,
duration, and output lengths. Approval references remain reduced to
`[PRESENT]`. Regression tests use a synthetic secret canary and prove that it
does not enter the JSONL audit.

## Compatibility

- Existing client-facing v1 response keys and redaction behavior are preserved.
- The SEC-1 legacy read-only compatibility firewall remains authoritative.
- Non-zero subprocess exits remain authorization decision `ALLOWED` with the
  original return code, while the audit terminal event is
  `execution_error`.
- Existing v1 and legacy audit lines remain valid historical JSONL; new records
  use schema v3.

## Verification

Local validation from the isolated SEC-3 worktree:

- Focused durable-audit, daemon, and SEC-1 firewall tests: **125 passed**.
- Existing root-executor client tests: **72 passed**.
- R5A/executor compatibility tests: **128 passed, 1 skipped**.
- Full repository test suite: **1,024 passed, 52 skipped**.
- Ruff on every changed Python file: **PASS**.
- Python compile check: **PASS**.
- Tracked-file secret scan: **PASS**.
- GitHub CI and executable merge-guard results will be recorded in the PR
  delivery summary.

Coverage includes intent-before-subprocess ordering; write, flush, file-fsync,
and directory-fsync failure; successful and non-zero completion; spawn error;
timeout; blocked requests without intent; legacy allowlist classifications;
secret-canary absence; terminal-audit failure; concurrent JSONL validity; and
v1 response-shape compatibility.

## Limitations and follow-up

This A1 change does not deploy or restart the executor. The currently deployed
service retains its existing behavior until a separately approved A2
deployment after human merge.

Durability is local-filesystem durability as reported by `fsync`; it does not
provide remote replication or protection against storage hardware that falsely
acknowledges flushes. A terminal-audit failure can occur only after the
subprocess has run, so the executor fails the response closed but cannot undo
that already completed read-only action.

No Docker, systemd, container, strategy, trading, kill-switch, executor,
scheduler, credential, or live-capital state was changed.
