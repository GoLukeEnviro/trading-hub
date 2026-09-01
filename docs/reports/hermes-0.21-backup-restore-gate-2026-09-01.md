# Hermes 0.21 backup/restore gate — 2026-09-01

## Observation

- Parent issue: #699; atomic child issue: #716; PR: #717.
- The later release contract is exactly Hermes Agent `0.21.0`, tag
  `v2026.8.31`, commit `29112bef099274229cadff79cdff7bf7b99c4b77`.
  The upstream annotated tag is not cryptographically verified.
- Production remained `/opt/hermes-native/current ->
  /opt/hermes-native/releases/0.19.0`; the installed binary reported Hermes
  Agent `v0.19.0`, Python `3.13.5`.
- No Hermes service restart, 0.21 staging, state migration, symlink switch,
  cutover, or trading-fleet mutation occurred.
- Runtime discovery selected exactly nine canonical Hermes databases. Three
  canonical dry-run Freqtrade databases are specified explicitly, for twelve
  verified databases in each backup.
- The fresh qualifying run `20260901T092907Z` completed successfully in 856
  seconds and created snapshot
  `781d93e19f7ee4467417e60098305c10a07651c7cd07b87b7939d32a4c2c36af`.
- The isolated restore completed at
  `/var/lib/hermes-native-change-c/restore-proof/20260901T094412.411335Z`.
  Its manifest has 50,758 entries, all checksums match, and all twelve SQLite
  databases return exactly `ok` from `PRAGMA integrity_check`.
- `/var/lib/hermes-native-change-c/backup-proof.json` was written atomically
  by the verifier with mode `0600`, exact snapshot binding, and
  `verified=true`.

## Cause

The original scheduled timeout had two proven defects:

1. recursive SQLite discovery and rsync source capture included historical
   backup/snapshot namespaces; and
2. SIGTERM from the outer systemd timeout could fall through to an EXIT report
   with code zero.

The first controlled corrective run (`20260901T084411Z`) then proved that the
SQLite CLI's incremental `.backup` could repeatedly restart under concurrent
writes to the active root WAL database. The destination remained empty while
logical reads grew to about 440 GiB. The run was terminated after 152 seconds
and correctly recorded `FAILED / SIGNAL_TERM / 143` without a snapshot.

The next corrective used one full backup-API step to hold a continuous source
read transaction. That solved restart starvation, but run
`20260901T090933Z` exposed the systemd sandbox edge case: `kanban.db` retained
a WAL-mode database header without `-wal`/`-shm` files. Opening it through the
SQLite API attempted `O_RDWR|O_CREAT` on `kanban.db-wal`; `ProtectSystem=strict`
correctly returned `EROFS`. The run failed closed as
`SQLITE_EXPORT_FAILED`, produced no snapshot, and never wrote a proof.

The final helper therefore uses two allowlisted, bounded methods:

- active WAL/rollback state: one full SQLite backup-API step; and
- no transaction sidecars: exclusive raw copy with source identity/size/
  mtime/ctime stability checks, sidecar checks before/during/after, two
  SHA-256 reads, destination `fsync`, and immutable integrity validation.

An incomplete WAL sidecar set, source change, hash mismatch, timeout, or
integrity failure remains a hard failure.

## Changes

- `ops/hermes/hermestrader-backup.sh`
  - exact canonical database inventory and unknown-DB gate;
  - historical/temporary namespace exclusions and no recursive self-capture;
  - fail-closed timeout/signal reporting;
  - bounded SQLite snapshot helper with the actual method recorded per DB;
  - fresh snapshot, repository check, retention, and atomic report binding.
- `ops/hermes/hermestrader-backup-excludes.txt`
  - backup, snapshot, recovery, restore, cache, quarantine, temp, test, probe,
    and previous-upgrade exclusions.
- `ops/hermes/hermestrader_sqlite_snapshot.py`
  - full-step backup API for active transaction sidecars;
  - stable, hash-bound read-only copy for inactive WAL-header databases under
    the production systemd sandbox.
- `ops/hermes/hermestrader_backup_restore_proof.py`
  - exact report/snapshot binding, isolated restore, complete manifest and
    checksum verification, twelve canonical integrity checks, atomic proof.
- `tests/test_hermestrader_backup_gate.py`
  - discovery/exclusion, timeout/signal, active WAL, read-only inactive WAL,
    method allowlist, restore, checksum, integrity, and atomic-proof coverage.
- `docs/state/current-operational-state.md`
  - superseding runtime truth and the next permitted gate.

## Validation

| Gate | Result | Evidence |
|---|---|---|
| Release pin | PASS | exact later contract `0.21.0 / v2026.8.31 / 29112bef…`; tag explicitly not cryptographically verified |
| Backup discovery | PASS | installed `discover-host`: exactly 9 Hermes DBs; 3 Freqtrade specs; historical namespaces excluded |
| Backup run | PASS | `20260901T092907Z`, exit 0, 50,759 files, 2,840,260,340 bytes, Restic check `ok`, retention `ok` |
| Restore | PASS | isolated root `/var/lib/hermes-native-change-c/restore-proof/20260901T094412.411335Z` |
| Checksums | PASS | 50,758 manifest entries equal 50,758 restored non-manifest files; independent `sha256sum --quiet -c` exit 0 |
| SQLite integrity | PASS | 12/12 canonical exports return exactly `ok` |
| `backup-proof.json` | PASS | exact fresh snapshot ID; all verification booleans true; `verified=true`; mode `0600` |
| Timeout semantics | PASS | unit tests `FAILED/TIMEOUT/124`; live aborted run `FAILED/SIGNAL_TERM/143` |
| Sandbox probes | PASS | `kanban.db`: stable-copy SHA match + integrity `ok`; active `state.db`: full-step + integrity `ok` under `ProtectSystem=strict` |
| Targeted tests | PASS | 51 passed, 3 skipped (backup gate plus Change-C contract tests) |
| Bash/ShellCheck/Ruff | PASS | `bash -n`, ShellCheck, Ruff, `py_compile`, diff check, and secret scan |
| Root test suite | FAIL (host-specific) | 1,294 passed, 55 skipped; only `test_host_repo_path_is_rejected` fails because this host resolves `/workspace` to the host path; GitHub CI passes hermetically |
| PR-head CI | PASS | `main-gate`, `governance-consistency`, and `offline-smoke` green on `935b4dbcc36d7ecd966a988915e4bb91eade0da2` |
| Exact-head deployment | PASS | all four installed SHA-256 values exactly match PR head; prior files retained at `/var/lib/hermestrader-backup/deploy-backups/20260901T-pr717-935b4db-WGSmeI17` |
| Production baseline | PASS | Hermes 0.19.0; gateway/dashboard/desktop/root executor active; root executor socket listening; expected 9119/19119 listeners; no 8642 listener |
| Fleet baseline | PASS | exactly 5/5 `hermestrader-dryrun-*` containers healthy; no fleet mutation |
| 0.21 staging | NOT_RUN | separate next gate |
| Migration probe | NOT_RUN | separate next gate |
| Rollback readiness | NOT_RUN | separate next gate |

## PR / CI

```text
Branch: fix/hermes-backup-restore-gate-20260901
Runtime-validated commit: 935b4dbcc36d7ecd966a988915e4bb91eade0da2
PR: #717
CI on runtime-validated commit: PASS (3/3)
Final evidence commit CI: pending before merge
Merge SHA: recorded by post-merge reconciliation on #716
```

## Runtime evidence

Key commands executed:

```text
/usr/local/sbin/hermestrader-backup.sh discover-host
systemd-run ... ProtectSystem=strict ... hermestrader-sqlite-snapshot <source> <isolated-destination>
systemctl start --no-block hermestrader-backup.service
systemctl show hermestrader-backup.service -p ActiveState -p Result -p ExecMainStatus
jq . /var/lib/hermestrader-backup/latest-report.json
/usr/local/sbin/hermestrader-backup-restore-proof --snapshot-id <exact-id> --backup-report <exact-report>
jq . /var/lib/hermes-native-change-c/backup-proof.json
sha256sum --quiet -c SHA256SUMS
readlink -f /opt/hermes-native/current
/opt/hermes-native/current/bin/hermes --version
systemctl is-active hermes-gateway hermes-dashboard hermes-desktop-serve hermes-root-executor
docker ps --filter name=hermestrader-dryrun-
ss -lntp
ss -lxnp
```

Installed artifact SHA-256 values:

```text
f5519c62f1bbd31df8afef75e2e72efbaef3af232d2beb009a0b0bf8c9614143  hermestrader-backup.sh
0d09aa1a291035634848e056d8dd5d293998f27a305a7c942abbaf95897c9b1b  hermestrader-backup-excludes.txt
637fc249b9340b43b437deab009406682a0dae76ea615b99bf162b055eb5b722  hermestrader_sqlite_snapshot.py
2356b41e9a8df164658d962d11e7a8c26aa8064bd705422b568d4a8cb6573ab4  hermestrader_backup_restore_proof.py
```

No repository location, credential, token, secret, database content, or
redacted configuration value is included in this report.

## Gate

```text
BACKUP_RESTORE_PROOF_PASS
```

## Next roadmap task

A1: harden Change-C for exact Hermes 0.21.0 locked side-by-side staging,
isolated migration probe, and complete state-plus-release rollback. No
production cutover is authorized by this result.
