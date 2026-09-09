# Hermes A2 cutover contract hardening — Issue #728

Date: 2026-09-09

Execution class: A1, repository-only

Parent: #699

Production cutover: **not executed**

## Outcome

Issue #728 closes the repository-side gaps between the proven 0.21 staging /
probe work and a future production transaction. The implementation is ready
for PR/CI/merge and, after merge, for a fresh maintenance-window revalidation.

```text
PRODUCTION_HERMES=0.19.0
CUTOVER_EXECUTED=NO
EXPECTED_POST_MERGE_STATE=READY_FOR_A2_CUTOVER_REVALIDATION
```

No Hermes production state, systemd unit, Root Executor, trading container,
image, volume, strategy, config or credential was mutated by this A1 task.

## Root causes closed

1. The old pre-cutover manifest omitted `pre_upgrade_state_path`, while
   rollback required it.
2. The old pre-cutover gate accepted a stopped fleet and captured only names
   and display-status strings.
3. Readiness did not bind the runtime image IDs/tags and Rainbow provenance to
   the canonical R5A image lock.
4. Probe migration logic was embedded in a one-off heredoc and could diverge
   from the future production migration.
5. Post-mutation failures only recommended rollback; they did not enter the
   explicit state+release restoration transaction.

## Implementation

### Shared state primitives

`ops/hermes/hermes_native_change_c.py` now owns reusable inspection and
migration logic for both isolated probe and production A2:

- source/target config schemas `33 -> 39`;
- source/target DB schemas `22 -> 26`;
- root/profile session counts measured at runtime (`post == pre`);
- `PRAGMA integrity_check == ok` and zero foreign-key rows;
- preservation of the three explicitly required structured operational
  settings without restoring the superseded duplicated system prompt.

### Final stopped-state snapshot

`pre-cutover` now requires the exact separate marker
`APPROVED_A2_HERMES_021_CUTOVER`. It validates every prerequisite and the
canonical R5A gate, stops desktop/dashboard/gateway, and only then creates the
final rollback state below:

```text
/var/lib/hermes-native-change-c/pre-upgrade-state/<UTC-stamp>/
```

Every SQLite database detected in `/opt/data/hermes` is materialized through
the hardened SQLite snapshot helper. WAL/SHM sidecars are never copied beside
the materialized database. The snapshot contains a complete file/hash/mode
inventory, root/profile schema and session evidence, release identity, backup
reference, fleet/provenance reference and an integrity-bound manifest plus
SHA-256 sidecar. Copied state files are write-disabled.

The atomic mode-0600 pre-cutover manifest records the exact previous release,
target, state snapshot path/hash, runtime session baselines, backup proof,
fleet proof, image lock, timestamp, operator and `gates_passed=true`.

### One canonical R5A gate

`hermes_root/r5a_recovery.py verify-only` is the common read-only gate used by
readiness, pre-cutover, cutover revalidation and post-cutover validation. It
requires:

- exactly the five canonical Compose services and no Rebel;
- 5/5 running and healthy, zero restarts, `OOMKilled=false`;
- 4/4 read-only-mounted Freqtrade configs with `dry_run=true`;
- exact immutable container tags and image IDs;
- exact image manifests, users, provenance labels, Dockerfile/entrypoint/base
  hashes, Rainbow source-lock hash and rendered Compose contract.

Any mismatch exits non-zero before `CUTOVER_READY=YES` or a valid pre-cutover
manifest can be emitted.

### Transaction and automatic rollback

The future `cutover` command requires the same explicit A2 marker and a valid,
integrity-bound pre-cutover manifest. It rechecks backup, migration, rollback,
release and R5A proofs; requires the three Hermes writers to remain stopped;
migrates the real state offline with pinned 0.21 Python; atomically swaps the
release pointer; starts gateway/dashboard/desktop; and validates version,
health/status, root/profile state, listeners, Root Executor and R5A.

After the first production mutation, failure enters automatic rollback. The
failed candidate state is retained under quarantine, the exact snapshot is
restored and hash-checked, the exact previous pointer is restored, services
are restarted in order, and 0.19/SQLite/session/Root-Executor/R5A gates are
reproved. The Root Executor is never stopped, restarted, reloaded or deployed.

## Regression matrix

The tests cover missing/nonexistent snapshot paths, missing/wrong manifest
hashes, snapshot corruption, source schema/pointer mismatch, runtime session
drift, invalid backup/migration/rollback proofs, incomplete manifests, 0600
atomic writes, stopped/unhealthy/restarted/OOM fleet, wrong image ID/tag/lock,
Rainbow provenance mismatch, Rebel presence and `dry_run=false`.

The transaction suite includes a complete orchestration happy fixture and an
exact rollback fixture. It also injects every post-mutation failure class and
proves routing to automatic rollback: service stop/snapshot/config/DB/schema/
session/SQLite/FK/symlink/startup/backend/listener/Root-Executor/R5A failures.

## Local validation

```text
Targeted Change-C + R5A: 71 passed, 2 skipped (UV staging fixtures)
Targeted Change-C + R5A + backup + secret/governance: 135 passed, 2 skipped
Full repository suite as hermes: 1367 passed, 54 skipped, 1 failed
Pristine main comparison: same single failure
  tests/test_repo_writer.py::...::test_host_repo_path_is_rejected
Reason: known host bind-path alias makes /workspace and /opt/data resolve to
the same checkout; already documented after PR #721.

bash -n: PASS
ShellCheck: PASS
Ruff (changed Python/tests): PASS
py_compile: PASS
git diff --check: PASS
Live read-only R5A verify-only: PASS
Offline-smoke SI-v2 Ruff/planning checks: PASS
Offline-smoke pytest: 8 environment-specific failures; all 8 reproduced by
the exact failing selectors on pristine main (pre-existing sandbox/path
ownership artifacts, unrelated to Change-C)
```

CI, secret scan, governance consistency and offline smoke are required again
on the exact PR head before merge.

## Future maintenance-window operator sequence

This sequence is intentionally **not executed by #728**. `<snapshot-id>` and
`<backup-report>` must come from the new backup run, never from the historical
proof.

```bash
# 1. Fresh disaster-recovery proof while 0.19 remains online.
sudo systemctl start --no-block hermestrader-backup.service
sudo systemctl show hermestrader-backup.service -p ActiveState -p Result -p ExecMainStatus
sudo jq . /var/lib/hermestrader-backup/latest-report.json
sudo /usr/local/sbin/hermestrader-backup-restore-proof \
  --snapshot-id <snapshot-id> --backup-report <backup-report>
sudo jq . /var/lib/hermes-native-change-c/backup-proof.json

# 2. Fresh immutable fleet proof and aggregate readiness.
sudo python3 /opt/data/projects/trading-hub/hermes_root/r5a_recovery.py verify-only
sudo bash /opt/data/projects/trading-hub/scripts/hermes-native-change-c.sh readiness

# 3. Explicitly authorized stopped-state preparation.
sudo bash /opt/data/projects/trading-hub/scripts/hermes-native-change-c.sh \
  pre-cutover --approval APPROVED_A2_HERMES_021_CUTOVER
sudo python3 /opt/data/projects/trading-hub/ops/hermes/hermes_native_change_c.py \
  verify-manifest \
  --manifest /var/lib/hermes-native-change-c/pre-cutover-manifest.json \
  --profile trading-hub-orchestrator
sudo jq . /var/lib/hermes-native-change-c/pre-cutover-manifest.json

# 4. Only after explicit operator review/decision: execute the A2 transaction.
sudo bash /opt/data/projects/trading-hub/scripts/hermes-native-change-c.sh \
  cutover --approval APPROVED_A2_HERMES_021_CUTOVER

# 5. Immediate evidence, then a fresh post-upgrade backup and 15-30 min watch.
sudo bash /opt/data/projects/trading-hub/scripts/hermes-native-change-c.sh validate
sudo bash /opt/data/projects/trading-hub/scripts/hermes-native-change-c.sh report
sudo systemctl start --no-block hermestrader-backup.service
```

If the operator aborts after `pre-cutover` while the services are deliberately
stopped, run the manifest-bound recovery command:

```bash
sudo bash /opt/data/projects/trading-hub/scripts/hermes-native-change-c.sh rollback
```

## Risks and rollback

- `pre-cutover` is itself an A2 production mutation because it stops writers;
  the marker is therefore mandatory even though it does not migrate state.
- Snapshot size and duration scale with required non-cache Hermes state.
- A permanently failing systemd service can prevent full availability even
  after exact state/release restoration; the failed candidate remains
  quarantined and the audit log identifies the stopping point.
- No command may set `dry_run=false`; trading authority remains unchanged.
