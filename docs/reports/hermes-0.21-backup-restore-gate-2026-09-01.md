# Hermes 0.21 backup/restore gate — 2026-09-01

## Observation

- Parent issue: #699; atomic child issue: #716; PR: #717.
- Exact later release context: Hermes Agent `0.21.0`, tag `v2026.8.31`, commit `29112bef099274229cadff79cdff7bf7b99c4b77`.
- The upstream annotated tag is not cryptographically verified. No staging, migration, symlink switch, or cutover occurred.
- Production remained `/opt/hermes-native/current -> /opt/hermes-native/releases/0.19.0`; `hermes --version` returned `Hermes Agent v0.19.0 (2026.7.20)`.
- The 2026-09-01 scheduled backup had previously timed out in `export-host-sqlite` and incorrectly recorded `SUCCESS / 0` without a snapshot.
- Live discovery from PR head `17661fb740b51fa435d8db0d118a3d7448616726` selected exactly 9 canonical Hermes SQLite databases. The 3 canonical dry-run Freqtrade database specifications are explicit in the script.
- Initial PR-head CI passed: `main-gate`, `offline-smoke`, and `governance-consistency` all `SUCCESS`.

## Cause

The original timeout had two proven causes:

1. recursive `find /opt/data/hermes` discovery included historical databases below `state-snapshots/` and `backups/`, while rsync also captured those trees; and
2. SIGTERM from the outer systemd timeout fell through to an EXIT report with code zero.

PR head `17661fb` fixed both defects, but the first controlled runtime run exposed another load-bearing defect. The SQLite CLI `.backup` of the active root WAL database did not make progress under concurrent production writes: for `/opt/data/hermes/state.db` (271 MiB), `/proc/<sqlite3>/io` increased from about 241 GiB to 440 GiB logical reads while the destination remained 0 bytes. The run was terminated after 152 seconds to prevent continued CPU/resource consumption.

The corrected signal handler produced the required failure result:

```json
{
  "timestamp": "20260901T084411Z",
  "status": "FAILED",
  "exit_code": 143,
  "stage": "export-host-sqlite",
  "reason": "SIGNAL_TERM",
  "snapshot_id": ""
}
```

## Changes in PR #717

- `ops/hermes/hermestrader-backup.sh`
  - explicit canonical DB specification;
  - path/root/symlink and unknown-production-DB gates;
  - recursive source exclusions;
  - fail-closed timeout and signal reporting;
  - exact SQLite inventory in the backup report.
- `ops/hermes/hermestrader-backup-excludes.txt`
  - recursive backup, snapshot, recovery, restore, cache, quarantine, temp, test, probe, and previous-upgrade exclusions.
- `ops/hermes/hermestrader_backup_restore_proof.py`
  - exact run/snapshot binding;
  - isolated Restic restore;
  - complete manifest and SHA-256 verification;
  - all 12 canonical SQLite integrity checks;
  - atomic positive proof and non-destructive failure reports.
- `tests/test_hermestrader_backup_gate.py`
  - 30 discovery, exclusion, timeout, signal, snapshot-binding, restore, checksum, integrity, and proof tests.

## Validation

| Gate | Result | Evidence |
|---|---|---|
| Release context | PASS | exact `0.21.0 / v2026.8.31 / 29112bef…`; tag documented as not cryptographically verified |
| Backup discovery | PASS | live read-only discovery returned the exact 9 Hermes DBs; 3 Freqtrade specs are explicit |
| Recursive excludes | PASS | source-capture regression test and versioned exclusion file |
| Unknown DB | PASS | regression test fails with `UNKNOWN_PRODUCTION_DB` |
| Timeout semantics | PASS | watchdog test reports `FAILED / TIMEOUT / 124`; live SIGTERM reports `FAILED / SIGNAL_TERM / 143` |
| Targeted tests | PASS | 30/30 |
| Bash syntax | PASS | `bash -n` |
| ShellCheck | PASS | no findings |
| Ruff | PASS | new Python and test files |
| Root test suite | FAIL (environment-specific) | 1,288 passed, 55 skipped, 1 pre-existing host-symlink guard failure; initial GitHub `main-gate` passed hermetically |
| Initial PR CI | PASS | all 3 required checks green on `17661fb` |
| Exact-head deployment | PASS | installed hashes matched PR artifacts; prior files backed up with SHA/owner/mode |
| Backup run | FAIL | controlled run `20260901T084411Z`; no snapshot; active WAL `.backup` did not progress |
| Restore | NOT_RUN | backup failure is a hard stop |
| Checksums | NOT_RUN | no fresh snapshot |
| SQLite restore integrity | NOT_RUN | no restore |
| `backup-proof.json` | FAIL | absent; never manually authored |
| Production Hermes | PASS | still 0.19.0; gateway/dashboard/desktop/root executor active; expected listeners only |
| Production SQLite | PASS | post-abort `PRAGMA integrity_check` = `ok` for all 9 Hermes DBs |
| Fleet baseline | PASS | exactly 5/5 `hermestrader-dryrun-*` containers healthy; no `dry_run=false`, config, image, strategy, or credential mutation |
| Runtime rollback | PASS | original backup script/filter restored to SHA `deea878f…` / `693a266d…`; failed-head restore tool retained in the recoverable deployment backup directory |
| Final CI | NOT_RUN | runtime failure stops the gate before final evidence commit CI |
| Merge guard / merge | NOT_RUN | PR must not merge while the runtime gate is red |

## Runtime evidence

Key commands:

```text
/usr/local/sbin/hermestrader-backup.sh discover-host
systemctl start hermestrader-backup.service
cat /proc/<sqlite3-pid>/io
stat <isolated-export-destination>
systemctl stop hermestrader-backup.service
jq . /var/lib/hermestrader-backup/latest-report.json
readlink -f /opt/hermes-native/current
systemctl is-active hermes-gateway hermes-dashboard hermes-desktop-serve hermes-root-executor
docker ps --filter name=hermestrader-dryrun-
sqlite3 -readonly <each-canonical-db> 'PRAGMA integrity_check;'
```

Deployment rollback evidence is retained at:

```text
/var/lib/hermestrader-backup/deploy-backups/20260901T084326Z-pr717-17661fb/
```

No Restic repository location, credential, token, secret, or database content is included in this report.

## Gate

```text
BACKUP_RESTORE_BLOCKED
```

No second backup attempt, restore, staging, migration, service restart, or cutover was performed.
