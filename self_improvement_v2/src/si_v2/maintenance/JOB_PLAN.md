# Derived Cache Maintenance — Daily Job Plan

> **Status: 🟡 INACTIVE — requires separate approval before activation.**
>
> This document defines the approval-gated daily maintenance plan for derived
> SQLite caches in the SI v2 system.
> **Do NOT install or activate any scheduler.** This is a design document only.

---

## Overview

| Attribute | Value |
|-----------|-------|
| **Target** | Derived SQLite caches (`source_regime_stats`, etc.) |
| **CLI** | `python -m si_v2.maintenance.cli` |
| **Cycle** | Daily |
| **Default mode** | `inspect` (read-only, no data mutation) |
| **Execute flag** | `--execute` (requires separate human approval token) |
| **Operation modes** | `inspect`, `dry-run`, `execute-analyze`, `execute-optimize`, `execute-vacuum` |

---

## Activation Prerequisites

This job plan is **INACTIVE** by design. Before any scheduler is activated:

1. **Manual proof required**: Run the following and capture successful JSON output:
   ```bash
   python -m si_v2.maintenance.cli inspect /path/to/cache.db
   python -m si_v2.maintenance.cli dry-run /path/to/cache.db
   python -m si_v2.maintenance.cli execute-analyze /path/to/cache.db --execute
   python -m si_v2.maintenance.cli execute-optimize /path/to/cache.db --execute
   ```
2. **Separate human approval token**: An operator must explicitly approve via
   the controller approval ceremony. No automated self-approval.
3. **Verification window**: Run daily in `dry-run` mode for 7 days before
   enabling `execute` modes.

---

## Lock Behavior

| Aspect | Behavior |
|--------|----------|
| **Mechanism** | Process-level `fcntl.flock(LOCK_EX)` on a sidecar `.maintenance.lock` file |
| **Timeout** | 10 seconds (configurable via `_advisory_lock` timeout param) |
| **Contention** | If another process holds the lock, fails with `RED_LOCK_CONFLICT` |
| **Release** | Released when context manager exits — always cleaned up in `finally` |
| **Safety** | Advisory file lock, not SQLite exclusive transaction. The lock is held for the full copy-on-write + promotion cycle. |

---

## Timeout Behavior

| Layer | Timeout | Action |
|-------|---------|--------|
| **Advisory lock** | 10 seconds | Raises `RuntimeError` → `RED_LOCK_CONFLICT` verdict |
| **MaintenanceRunner overall** | Synchronous | N/A |
| **Scheduler-level** | 300 seconds | Scheduler kills the process (if configured) |

---

## Logging Behavior

- **Output**: Machine-readable JSON verdict to stdout, human-readable
  summary to stderr.
- **Verdict levels**:
  - `GREEN_*` — success or no action needed.
  - `YELLOW_*` — warning (e.g., VACUUM recommended but skipped).
  - `RED_*` — failure (integrity, schema, lock, path, identity, source-changed, promotion).
- **Exit codes**:
  - `0` — success (GREEN or YELLOW verdict).
  - `2` — failure (RED verdict).

---

## Failure Behavior

| Failure Mode | Effect | Recovery |
|--------------|--------|----------|
| **Lock contention** | Fails with `RED_LOCK_CONFLICT` | Retry next cycle; manual intervention if persistent |
| **Integrity failure (pre)** | Fails with `RED_INTEGRITY_FAILURE` | Manual rebuild required |
| **Integrity failure (post on copy)** | Copy discarded, original untouched | Original still intact |
| **Source changed during maintenance** | Fails with `RED_SOURCE_CHANGED` | Retry next cycle |
| **Promotion failure** | Fails with `RED_PROMOTION_FAILURE`; original restored from backup | Manual verification required |
| **Unsafe path** | Fails immediately | Fix DB path configuration |
| **Unsupported schema** | Fails with `RED_UNSUPPORTED_SCHEMA` | Rebuild DB with current schema version |
| **Identity failure** | Fails with `RED_IDENTITY_FAILURE` | Verify cache is a valid SI v2 derived cache |
| **Disk full** | Fails with `RED_INSUFFICIENT_DISK` | Free disk space; retry next cycle |
| **Backup failure** | Operation skipped | Manual backup required |

---

## Rollback Behavior

| Scenario | Rollback Action |
|----------|-----------------|
| **Post-maintenance integrity failure on copy** | Copy is discarded; original remains untouched (no promotion occurred) |
| **Source changed during maintenance** | Copy is discarded; retry on next cycle |
| **Promotion fails** | Automatic restore: the renamed original backup is copied back to the original path |
| **Manual rollback needed** | Use the timestamped `.original.<timestamp>.bak` file in the backup directory |

---

## Copy-on-Write Maintenance Flow

All mutating operations use a **copy-on-write** strategy to guarantee the
original database is never modified in-place:

1. Acquire exclusive advisory lock file
2. Re-inspect the source cache after lock acquisition
3. Record source identity, size, mtime, SHA-256 fingerprint, and metadata
4. Check total required disk space (original + backup + temp copy + journal + margin)
5. Create a timestamped backup of the original via SQLite backup API
6. Create a consistent temporary copy via SQLite backup API
7. Run the maintenance operation (ANALYZE, OPTIMIZE, or VACUUM) on the copy
8. Run integrity_check, quick_check, foreign_key_check, schema check, and
   metadata check on the maintained copy
9. Re-check that the source cache did not change while the copy was maintained
10. Rename the original to a unique timestamped backup
11. Atomically promote the validated temporary copy (rename)
12. Fsync the promoted file and containing directory
13. Move WAL/SHM sidecar files if present
14. Restore the original automatically if promotion fails
15. Release the advisory lock

**VACUUM is performed on the copy**, not via VACUUM INTO. The copy is
maintained in-place, then promoted atomically via filesystem rename.

---

## Disk Space Requirements

| Operation | Free Space Required |
|-----------|---------------------|
| ANALYZE | 2× DB size + 10 MB overhead |
| PRAGMA optimize | 2× DB size + 10 MB overhead |
| VACUUM | 3× DB size + 10 MB overhead |
| Backup | DB size (one-time, in same filesystem) |

The runner checks `os.statvfs()` before any operation and accounts for
simultaneous space needs: original file + backup copy + temp copy +
SQLite journal/WAL overhead + safety margin. Insufficient space produces
`RED_INSUFFICIENT_DISK`.

---

## Daily Maintenance Flow

1. **Inspect** (always first):
   ```bash
   python -m si_v2.maintenance.cli inspect <DB_PATH>
   ```
2. **Dry-run** (if inspection looks clean):
   ```bash
   python -m si_v2.maintenance.cli dry-run <DB_PATH>
   ```
3. **Execute ANALYZE + OPTIMIZE** (safe, non-destructive):
   ```bash
   python -m si_v2.maintenance.cli execute-analyze <DB_PATH> --execute
   python -m si_v2.maintenance.cli execute-optimize <DB_PATH> --execute
   ```
4. **Execute VACUUM** (only if needed, requires disk space):
   ```bash
   python -m si_v2.maintenance.cli execute-vacuum <DB_PATH> --execute
   ```

---

## Safety Rules

- Never modify JSONL or source-ledger data files.
- Never modify Shadowlock data.
- Identity validation: only approved SI v2 derived caches are accepted.
- SQLite `mode=ro` URI parameter prevents accidental database creation.
- Copy-on-write: original is never modified in-place.
- Always create timestamped backup with microsecond precision before mutation.
- Never overwrite an existing backup file — backups are unique.
- Full post-maintenance validation (integrity, FK, schema, metadata) on the copy before promotion.
- Source-change detection prevents promotion if the original changed during maintenance.
- Automatic restore from backup on promotion failure.
- WAL/SHM sidecar files are moved to the promoted database.
- Advisory file lock (not SQLite exclusive transaction) for process-level safety.

---

## Approval Gate

This job plan is **INACTIVE**. To activate:

1. **Operator reviews** this document and verifies all safety constraints.
2. **Operator provides** separate human approval token via controller gate.
3. **Dev runs** manual proof: all five CLI modes against a test cache.
4. **Dev runs** daily dry-run for 7 days in production-like environment.
5. **Dev configures** scheduler (systemd timer or Hermes cron) **only after**
   step 4 passes.
6. **Dev verifies** first scheduled run succeeds via logs.

> **Until approved, run maintenance manually with:**
>
> ```bash
> python -m si_v2.maintenance.cli inspect <DB_PATH>
> python -m si_v2.maintenance.cli dry-run <DB_PATH>
> python -m si_v2.maintenance.cli execute-analyze <DB_PATH> --execute
> python -m si_v2.maintenance.cli execute-optimize <DB_PATH> --execute
> python -m si_v2.maintenance.cli execute-vacuum <DB_PATH> --execute
> ```
