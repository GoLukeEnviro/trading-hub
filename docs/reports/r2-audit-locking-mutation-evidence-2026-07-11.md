# R2 — Audit, Locking and Mutation Evidence (2026-07-11)

R2 builds on the audit and locking foundation already delivered as part of
R1's implementation (`hermes-root-executor`), since audit/locking were
tightly coupled to the executor's core request-handling loop and were built
directly into it rather than as a bolt-on afterward. This report closes out
R2 by verifying that foundation against the ADR's R2 bar and adding the one
missing piece: log rotation for long-term operation.

## Already Delivered in R1 (verified, not re-implemented)

| R2 requirement | Status |
|---|---|
| JSONL audit trail, root-owned, append-only | Delivered — `/opt/data/hermes/audit/runtime-actions.jsonl`, `600 root:root`, opened in append (`"a"`) mode |
| No secrets in audit log | Delivered — argument redaction for `KEY`/`SECRET`/`TOKEN`/`PASSWORD` fields before every write; command output logged as length only (`stdout_len`/`stderr_len`), never raw content — stricter than the D3 result-hash pattern this was modeled on, since lengths alone cannot leak content even under hash-collision analysis |
| Failed mutations logged | Delivered — every `BLOCKED` decision (`peer_uid_not_allowed`, `resource_locked`, `command_timeout`, `emergency_disable_switch_active`, `unknown_category`, `invalid_args`) is audited identically to successes |
| Per-resource exclusive locking | Delivered — `fcntl.flock` non-blocking per `resource_key`, verified live under concurrent load in R1 (see R1 report, test 4) |

## Added in R2

| Item | Detail |
|---|---|
| Log rotation | `/etc/logrotate.d/hermes-root-executor`: weekly rotation, 12 generations kept (~3 months), compressed, `create 0600 root root` to preserve permissions across rotation. Validated via `logrotate -d` (dry run, exit 0, no syntax errors). Prevents unbounded audit log growth over long-term operation. |

## Verification

- `logrotate -d /etc/hermes-root-executor` dry run: no errors, correct file targeted.
- Audit log permissions preserved across the config (`create 0600 root root` matches the executor's own `os.chmod(AUDIT_PATH, 0o600)`).
- No changes to `hermes-root-executor` itself in this phase — R1's implementation already met the audit/locking bar; R2 is additive (rotation) and confirmatory (this report), not a rewrite.

## Note on Scope

D2 (`hermes-runtime-runner`) does not currently have log rotation configured
either (`/var/log/hermes-runtime-runner/audit.jsonl`) — out of scope for
this report, since D2 is superseded infrastructure per the R0 ADR and is
expected to be retired once the root executor is load-bearing, not worth
additional investment now.

## Verdict

`R2_AUDIT_LOCKING_MUTATION_EVIDENCE_CLOSED`
