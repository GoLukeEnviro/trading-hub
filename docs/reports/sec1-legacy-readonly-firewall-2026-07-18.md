# SEC-1 — Legacy Read-only Compatibility Firewall

**Date:** 2026-07-18
**Issue:** #631
**Execution class:** A1 repository-only
**Runtime mutation:** NONE

## Goal

Contain the actively used legacy `hermes-root-executor` protocol without
blindly removing compatibility. The legacy protocol must no longer transport
generic Docker, systemd, or filesystem commands as root.

## Evidence and risk

The P0 reconciliation merged in PR #630 found 85 legacy requests since
2026-07-13, including Docker and systemd categories. Historical audit records
do not contain enough safe argument classification to determine whether those
requests were read-only. Before SEC-1, the daemon appended client-controlled
legacy argv directly to root-owned binaries.

## Implementation

`hermes_root.legacy` now builds the complete subprocess argv for a bounded
read-only compatibility subset:

- Docker: `ps` only, with a small allowlist of inspection flags.
- systemd: `status`, `is-active`, or `is-enabled` for Docker and the root
  executor units only.
- filesystem: `stat` and non-recursive `ls -la` under documented roots only.

All mutations, unknown subcommands, arbitrary units, option injection,
control characters, path traversal, and paths outside the allowlist fail
closed before lock acquisition or subprocess execution.

Audit records include a fixed `legacy_classification` value. Raw legacy argv
is not added to audit, so the containment telemetry does not create a new
secret exposure path.

## Preserved boundaries

- V1 action behavior is unchanged.
- No executor capability was added.
- No host installation or service restart occurred.
- No Docker, bot, strategy, configuration, credential, kill-switch, or
  trading state was changed.
- A3 and live trading remain prohibited.

## Validation

Completed validation:

- Targeted firewall + daemon suite: **108 passed**.
- Root-executor/client/R5A regression selection: **286 passed, 1 skipped**.
- Complete root `tests/` suite: **1007 passed, 52 skipped**.
- Ruff on the new firewall, audit change, and firewall tests: **PASS**.
- Tracked-file secret scan: **PASS**.
- Python compile and `git diff --check`: **PASS**.

## Deployment status

Repository implementation only. Production deployment is a separate A2 task
requiring its own bounded approval, snapshot, rollback, and runtime proof.
