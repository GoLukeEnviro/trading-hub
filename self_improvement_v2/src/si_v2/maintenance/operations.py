"""Maintenance operations — ANALYZE, PRAGMA optimize, and VACUUM for derived caches.

All operations default to dry-run (no mutation). Execute mode requires
an explicit ``--execute`` flag and performs safety checks before mutating.

Safety guarantees:
- Create timestamped backup before any mutation
- Never overwrite existing backup
- Run post-operation integrity and foreign-key checks
- Restore or quarantine on failed post-validation
- Leave original DB unchanged on precondition failure
"""

from __future__ import annotations

import contextlib
import shutil
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from .inspector import inspect_cache, is_safe_cache_path
from .models import (
    MaintenanceEvidence,
    MaintenanceOperation,
    MaintenanceRequest,
    MaintenanceResult,
    MaintenanceVerdict,
)

# Minimum free disk space multiplier for VACUUM (2x DB size)
VACUUM_DISK_MULTIPLIER: float = 2.0


def execute_analyze(
    request: MaintenanceRequest,
    evidence: MaintenanceEvidence,
) -> MaintenanceResult:
    """Run ANALYZE on a cache database.

    ANALYZE is always safe — it updates SQLite query planner statistics
    without modifying the schema or row data.

    Args:
        request: The maintenance request.
        evidence: Pre-collected inspection evidence.

    Returns:
        MaintenanceResult with verdict and outcome.
    """
    return _execute_operation(
        request=request,
        evidence=evidence,
        operation=MaintenanceOperation.ANALYZE,
        operation_fn=lambda conn: conn.execute("ANALYZE"),
    )


def execute_optimize(
    request: MaintenanceRequest,
    evidence: MaintenanceEvidence,
) -> MaintenanceResult:
    """Run PRAGMA optimize on a cache database.

    PRAGMA optimize is always safe — it defragments indexes and updates
    statistics without modifying the schema or row data.

    Args:
        request: The maintenance request.
        evidence: Pre-collected inspection evidence.

    Returns:
        MaintenanceResult with verdict and outcome.
    """
    return _execute_operation(
        request=request,
        evidence=evidence,
        operation=MaintenanceOperation.OPTIMIZE,
        operation_fn=lambda conn: conn.execute("PRAGMA optimize"),
    )


def execute_vacuum(
    request: MaintenanceRequest,
    evidence: MaintenanceEvidence,
) -> MaintenanceResult:
    """Run VACUUM on a cache database.

    VACUUM requires:
    - Free disk space >= 2x DB size
    - Backup created before operation
    - Exclusive lock
    - Post-operation integrity validation

    Args:
        request: The maintenance request.
        evidence: Pre-collected inspection evidence.

    Returns:
        MaintenanceResult with verdict and outcome.
    """
    messages: list[str] = []
    executed_at = datetime.now(UTC)

    # --- Check disk space ---
    needed_mb = evidence.db_size_mb * VACUUM_DISK_MULTIPLIER
    if evidence.free_mb < needed_mb:
        messages.append(
            f"Insufficient disk for VACUUM: {evidence.free_mb:.1f} MB free, "
            f"need at least {needed_mb:.1f} MB"
        )
        return MaintenanceResult(
            request=request,
            verdict=MaintenanceVerdict.RED_INSUFFICIENT_DISK,
            evidence=evidence,
            operation=MaintenanceOperation.VACUUM,
            executed_at=executed_at,
            operation_ok=False,
            backup_path=None,
            messages=messages,
        )

    return _execute_operation(
        request=request,
        evidence=evidence,
        operation=MaintenanceOperation.VACUUM,
        operation_fn=lambda conn: _vacuum_safe(conn, messages),
        pre_checks=None,
        messages=messages,
    )


def _execute_operation(
    request: MaintenanceRequest,
    evidence: MaintenanceEvidence,
    operation: MaintenanceOperation,
    operation_fn: Callable[[sqlite3.Connection], object],
    pre_checks: object | None = None,
    messages: list[str] | None = None,
) -> MaintenanceResult:
    """Execute a maintenance operation with full safety guards.

    Steps:
    1. Verify path safety
    2. Verify file exists
    3. Verify schema version support
    4. Verify integrity pre-check passes
    5. Acquire exclusive lock
    6. Create timestamped backup (never overwrite existing)
    7. Execute the operation
    8. Release lock
    9. Run post-validation integrity checks
    10. On failure: restore from backup
    """
    if messages is None:
        messages = []

    executed_at = datetime.now(UTC)
    resolved = request.db_path.resolve()

    # --- 1. Path safety ---
    if not is_safe_cache_path(resolved):
        messages.append(f"Unsafe cache path: {resolved}")
        return MaintenanceResult(
            request=request,
            verdict=MaintenanceVerdict.RED_UNSAFE_PATH,
            evidence=evidence,
            operation=operation,
            executed_at=executed_at,
            operation_ok=False,
            backup_path=None,
            messages=messages,
        )

    # --- 2. File existence ---
    if not resolved.exists():
        messages.append(f"Database not found: {resolved}")
        return MaintenanceResult(
            request=request,
            verdict=MaintenanceVerdict.RED_INTEGRITY_FAILURE,
            evidence=evidence,
            operation=operation,
            executed_at=executed_at,
            operation_ok=False,
            backup_path=None,
            messages=messages,
        )

    # --- 3. Schema version ---
    if evidence.schema_version is None or evidence.schema_version < 1:
        messages.append(
            f"Unsupported or missing schema version: {evidence.schema_version}"
        )
        return MaintenanceResult(
            request=request,
            verdict=MaintenanceVerdict.RED_UNSUPPORTED_SCHEMA,
            evidence=evidence,
            operation=operation,
            executed_at=executed_at,
            operation_ok=False,
            backup_path=None,
            messages=messages,
        )

    # --- 4. Integrity pre-check ---
    if evidence.integrity_ok is False:
        messages.append("Pre-operation integrity check failed")
        return MaintenanceResult(
            request=request,
            verdict=MaintenanceVerdict.RED_INTEGRITY_FAILURE,
            evidence=evidence,
            operation=operation,
            executed_at=executed_at,
            operation_ok=False,
            backup_path=None,
            messages=messages,
        )

    # --- 5. Acquire exclusive lock ---
    lock_conn: sqlite3.Connection | None = None
    try:
        lock_conn = _acquire_exclusive_lock(resolved)
    except RuntimeError as exc:
        messages.append(f"Lock acquisition failed: {exc}")
        return MaintenanceResult(
            request=request,
            verdict=MaintenanceVerdict.RED_LOCK_CONFLICT,
            evidence=evidence,
            operation=operation,
            executed_at=executed_at,
            operation_ok=False,
            backup_path=None,
            messages=messages,
        )

    try:
        # --- 6. Create backup ---
        if request.backup_dir is not None:
            backup_parent = request.backup_dir.resolve()
            backup_parent.mkdir(parents=True, exist_ok=True)
        else:
            backup_parent = resolved.parent

        backup_path = _create_timestamped_backup(
            resolved,
            backup_parent,
            lock_conn,
            messages,
        )
        if backup_path is None:
            messages.append("Failed to create backup before operation")
            return MaintenanceResult(
                request=request,
                verdict=MaintenanceVerdict.RED_INTEGRITY_FAILURE,
                evidence=evidence,
                operation=operation,
                executed_at=executed_at,
                operation_ok=False,
                backup_path=None,
                messages=messages,
            )

        # --- 7. Execute the operation ---
        # The operation_fn receives the lock connection
        try:
            operation_fn(lock_conn)  # type: ignore[call-arg]
            lock_conn.commit()
        except Exception as exc:
            messages.append(f"Operation failed: {exc}")
            _restore_from_backup(resolved, backup_path, messages)
            return MaintenanceResult(
                request=request,
                verdict=MaintenanceVerdict.RED_INTEGRITY_FAILURE,
                evidence=evidence,
                operation=operation,
                executed_at=executed_at,
                operation_ok=False,
                backup_path=backup_path,
                messages=messages,
            )

    finally:
        # Release exclusive lock
        if lock_conn is not None:
            with contextlib.suppress(Exception):
                lock_conn.close()
            lock_conn = None

    # --- 9. Post-validation (on a fresh connection) ---
    post_ok, post_msgs = _run_post_validation(resolved)
    if not post_ok:
        messages.extend(post_msgs)
        _restore_from_backup(resolved, backup_path, messages)
        return MaintenanceResult(
            request=request,
            verdict=MaintenanceVerdict.RED_INTEGRITY_FAILURE,
            evidence=evidence,
            operation=operation,
            executed_at=executed_at,
            operation_ok=False,
            backup_path=backup_path,
            messages=messages,
        )

    messages.append(f"{operation.name} completed successfully")
    return MaintenanceResult(
        request=request,
        verdict=MaintenanceVerdict.GREEN_NO_ACTION,
        evidence=evidence,
        operation=operation,
        executed_at=executed_at,
        operation_ok=True,
        backup_path=backup_path,
        messages=messages,
    )


def _acquire_exclusive_lock(db_path: Path, timeout: float = 5.0) -> sqlite3.Connection:
    """Acquire an exclusive SQLite lock.

    Opens a connection with the given timeout and starts a
    BEGIN EXCLUSIVE TRANSACTION.

    Args:
        db_path: Path to the database file.
        timeout: Busy timeout in seconds.

    Returns:
        The locked connection (caller must close it).

    Raises:
        RuntimeError: If the lock cannot be acquired.
    """
    try:
        conn = sqlite3.connect(str(db_path), timeout=timeout)
        conn.execute("BEGIN EXCLUSIVE TRANSACTION")
    except sqlite3.OperationalError as exc:
        msg = f"Could not acquire exclusive lock on {db_path}: {exc}"
        raise RuntimeError(msg) from exc
    return conn


def _create_timestamped_backup(
    db_path: Path,
    backup_dir: Path,
    lock_conn: sqlite3.Connection | None,
    messages: list[str],
) -> Path | None:
    """Create a timestamped backup of the database.

    Uses SQLite backup API for consistent snapshots. Never overwrites
    an existing backup file.

    Args:
        db_path: Path to the original database.
        backup_dir: Directory to place the backup.
        lock_conn: Optional connection with exclusive lock for consistent backup.
        messages: Message list to append warnings to.

    Returns:
        Path to the backup, or None on failure.
    """
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup_path = backup_dir / f"{db_path.stem}.{timestamp}.bak"

    # Never overwrite existing backup
    if backup_path.exists():
        messages.append(f"Backup already exists: {backup_path}")
        return None

    try:
        src_conn: sqlite3.Connection | None = None
        try:
            if lock_conn is not None:
                lock_conn.commit()
                src_conn = lock_conn
            else:
                src_conn = sqlite3.connect(str(db_path))

            dst_conn = sqlite3.connect(str(backup_path))
            try:
                src_conn.backup(dst_conn)
                dst_conn.commit()
            finally:
                dst_conn.close()
        finally:
            if src_conn is not None and lock_conn is None:
                src_conn.close()
    except Exception as exc:
        messages.append(f"Backup failed: {exc}")
        return None

    return backup_path


def _vacuum_safe(
    conn: sqlite3.Connection,
    messages: list[str],
) -> None:
    """Perform VACUUM in-place using the exclusive lock already held.

    VACUUM requires exclusive access, which we already hold. After VACUUM
    the database is compacted and rebuilt.

    Args:
        conn: Connection with exclusive lock.
        messages: Message list to append info to.
    """
    try:
        conn.execute("VACUUM")
        conn.commit()
        messages.append("VACUUM completed successfully")
    except Exception as exc:
        messages.append(f"VACUUM failed: {exc}")
        raise


def _run_post_validation(db_path: Path) -> tuple[bool, list[str]]:
    """Run integrity checks after a maintenance operation.

    Args:
        db_path: Path to the database to validate.

    Returns:
        Tuple of (ok: bool, messages: list[str]).
    """
    messages: list[str] = []
    uri = db_path.as_uri()
    conn = sqlite3.connect(uri, uri=True)
    try:
        conn.execute("PRAGMA query_only = ON;")

        # integrity_check
        rows = conn.execute("PRAGMA integrity_check;").fetchall()
        if not all(r[0] == "ok" for r in rows):
            bad = [r[0] for r in rows if r[0] != "ok"]
            messages.append(f"Post-operation integrity check failed: {bad}")
            return False, messages

        # quick_check
        qc_row = conn.execute("PRAGMA quick_check;").fetchone()
        if qc_row is not None and qc_row[0] != "ok":
            messages.append(f"Post-operation quick_check failed: {qc_row[0]}")
            return False, messages

        # foreign_key_check
        fk_rows = conn.execute("PRAGMA foreign_key_check;").fetchall()
        if len(fk_rows) > 0:
            messages.append(f"Post-operation foreign_key_check: {len(fk_rows)} violations")
            return False, messages

        messages.append("Post-operation validation passed")
        return True, messages
    finally:
        conn.close()


def _restore_from_backup(
    db_path: Path,
    backup_path: Path,
    messages: list[str],
) -> None:
    """Restore the original database from a backup file.

    Args:
        db_path: Target path to restore to.
        backup_path: Path to the backup file.
        messages: Message list to append info to.
    """
    if not backup_path.exists():
        messages.append(f"Cannot restore: backup not found {backup_path}")
        return

    try:
        shutil.copy2(str(backup_path), str(db_path))
        messages.append(f"Restored from backup: {backup_path}")
    except Exception as exc:
        messages.append(f"Restore from backup failed: {exc}")


class MaintenanceRunner:
    """High-level runner that orchestrates the full maintenance workflow.

    Combines inspection, verdict, and operation execution into a single
    callable interface.
    """

    @staticmethod
    def run(request: MaintenanceRequest) -> MaintenanceResult:
        """Run maintenance according to the request mode.

        Args:
            request: Complete maintenance request.

        Returns:
            MaintenanceResult with verdict, evidence, and outcome.
        """
        db_path = request.db_path.resolve()
        mode = request.mode

        # Always start with path safety check — reject unsafe paths even
        # if the file doesn't exist yet
        if not is_safe_cache_path(db_path):
            return MaintenanceResult(
                request=request,
                verdict=MaintenanceVerdict.RED_UNSAFE_PATH,
                evidence=inspect_cache(db_path),
                operation=None,
                executed_at=datetime.now(UTC),
                operation_ok=None,
                backup_path=None,
                messages=[f"Unsafe cache path: {db_path}"],
            )

        # Always start with inspection
        evidence = inspect_cache(db_path)

        if mode == "inspect":
            return MaintenanceResult(
                request=request,
                verdict=_verdict_from_evidence(evidence),
                evidence=evidence,
                operation=None,
                executed_at=datetime.now(UTC),
                operation_ok=None,
                backup_path=None,
                messages=["Inspection completed"],
            )

        if mode == "dry-run":
            verdict = _verdict_from_evidence(evidence)
            return MaintenanceResult(
                request=request,
                verdict=verdict,
                evidence=evidence,
                operation=None,
                executed_at=datetime.now(UTC),
                operation_ok=None,
                backup_path=None,
                messages=["Dry-run completed — no mutations performed"],
            )

        if mode == "execute-analyze":
            return execute_analyze(request, evidence)

        if mode == "execute-optimize":
            return execute_optimize(request, evidence)

        if mode == "execute-vacuum":
            return execute_vacuum(request, evidence)

        msg = f"Unknown mode: {mode}"
        raise ValueError(msg)


def _verdict_from_evidence(evidence: MaintenanceEvidence) -> MaintenanceVerdict:
    """Derive a verdict from inspection evidence."""
    if evidence.schema_version is None and evidence.db_size_mb > 0:
        return MaintenanceVerdict.RED_UNSUPPORTED_SCHEMA
    if evidence.integrity_ok is False:
        return MaintenanceVerdict.RED_INTEGRITY_FAILURE
    if evidence.foreign_keys_ok is False:
        return MaintenanceVerdict.RED_INTEGRITY_FAILURE
    if evidence.quick_check_ok is False:
        return MaintenanceVerdict.RED_INTEGRITY_FAILURE
    if not evidence.rebuildable and evidence.db_size_mb > 0:
        return MaintenanceVerdict.YELLOW_REBUILD_RECOMMENDED
    if evidence.free_mb < evidence.db_size_mb * VACUUM_DISK_MULTIPLIER and evidence.db_size_mb > 0:
        return MaintenanceVerdict.YELLOW_VACUUM_RECOMMENDED
    return MaintenanceVerdict.GREEN_NO_ACTION
