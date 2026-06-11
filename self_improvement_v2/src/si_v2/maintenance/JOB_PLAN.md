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
| **Mechanism** | SQLite `BEGIN EXCLUSIVE TRANSACTION` |
| **Timeout** | 5 seconds (configurable via timeout param) |
| **Contention** | If another process holds the lock, the job fails with `RED_LOCK_CONFLICT` |
| **Release** | `ROLLBACK` or `COMMIT` + `close()` — always released in `finally`/cleanup |
| **Safety** | Exclusive lock prevents concurrent reads during mutation (VACUUM) |

---

## Timeout Behavior

| Layer | Timeout | Action |
|-------|---------|--------|
| **MaintenanceRunner lock** | 5 seconds | Raises `RuntimeError` → `RED_LOCK_CONFLICT` verdict |
| **MaintenanceRunner overall** | Synchronous | N/A |
| **Scheduler-level** | 300 seconds | Scheduler kills the process (if configured) |

---

## Logging Behavior

- **Output**: Machine-readable JSON verdict to stdout, human-readable
  summary to stderr.
- **Verdict levels**:
  - `GREEN_*` — success or no action needed.
  - `YELLOW_*` — warning (e.g., VACUUM recommended but skipped).
  - `RED_*` — failure (integrity, schema, lock, or path).
- **Exit codes**:
  - `0` — success (GREEN or YELLOW verdict).
  - `2` — failure (RED verdict).

---

## Failure Behavior

| Failure Mode | Effect | Recovery |
|--------------|--------|----------|
| **Lock contention** | Job fails with `RED_LOCK_CONFLICT` | Retry next cycle; manual intervention if persistent |
| **Integrity failure** | Job fails with `RED_INTEGRITY_FAILURE` | Backup still exists; manual rebuild required |
| **Unsafe path** | Job fails immediately | Fix DB path configuration |
| **Unsupported schema** | Job fails with `RED_UNSUPPORTED_SCHEMA` | Rebuild DB with current schema version |
| **Disk full** | VACUUM skipped, `RED_INSUFFICIENT_DISK` verdict | Free disk space; VACUUM runs next cycle |
| **Backup failure** | Mutation skipped, `RED_INTEGRITY_FAILURE` verdict | Manual backup required |

---

## Rollback Behavior

| Scenario | Rollback Action |
|----------|-----------------|
| **Post-maintenance integrity failure** | Backup is automatically restored (copy back via `shutil.copy2`) |
| **VACUUM fails mid-way** | Original DB remains intact (VACUUM INTO creates new file, atomic replace on success) |
| **Manual rollback needed** | Use the timestamped `.bak` file: `cp <backup> <db_path>` |
| **Backup file naming** | `<stem>.<YYYYMMDD>THHMMSSZ>.bak` alongside the original DB |

---

## Disk Space Requirements

| Operation | Free Space Required |
|-----------|---------------------|
| ANALYZE | None |
| PRAGMA optimize | None |
| VACUUM | 2× current DB size |
| Backup | DB size (one-time, in same filesystem) |

The runner checks `os.statvfs()` before VACUUM and fails with
`RED_INSUFFICIENT_DISK` if less than 2× the DB size is available.

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
- Always create timestamped backup before mutation.
- Never overwrite an existing backup file.
- Run post-operation integrity and foreign-key checks.
- Restore from backup on failed post-validation.
- Leave original DB unchanged on precondition failure.

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
