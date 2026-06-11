"""Maintenance operations — ANALYZE, PRAGMA optimize, and VACUUM for derived caches.

All operations default to dry-run (no mutation). Execute mode requires
an explicit ``--execute`` flag and performs safety checks before mutating.

Safety guarantees:
- Advisory file lock for process-level exclusive access
- Copy-on-write: maintain a temporary copy, promote only on success
- Timestamped backup with microseconds (never overwrites existing)
- Full disk space accounting (original + temp + journal + margin)
- WAL/SHM artifact handling
- Post-operation integrity checks on the copy before promotion
- Automatic restore on promotion failure
- Injectable clock for deterministic tests
"""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import os
import shutil
import sqlite3
import time
from pathlib import Path

from .inspector import SUPPORTED_SCHEMA_VERSIONS, inspect_cache, is_safe_cache_path
from .models import (
    Clock,
    MaintenanceEvidence,
    MaintenanceMode,
    MaintenanceOperation,
    MaintenanceRequest,
    MaintenanceResult,
    MaintenanceVerdict,
)

# Minimum free disk space multiplier for VACUUM (2x DB size)
VACUUM_DISK_MULTIPLIER: float = 2.0

# Safety margin for SQLite temporary/journal/WAL overhead (additive MB)
SQLITE_OVERHEAD_MARGIN_MB: float = 10.0

# Suffix for advisory lock files
ADVISORY_LOCK_SUFFIX: str = ".maintenance.lock"


# ---------------------------------------------------------------------------
# Advisory file lock
# ---------------------------------------------------------------------------


@contextlib.contextmanager
def _advisory_lock(db_path: Path, timeout: float = 10.0):
    """Acquire an exclusive process-level advisory lock via a lock file.

    Uses ``fcntl.flock`` with ``LOCK_EX`` on a sidecar lock file. The
    lock is released when the context exits.

    Args:
        db_path: Path to the database being maintained.
        timeout: Maximum seconds to wait for the lock.

    Raises:
        RuntimeError: If the lock cannot be acquired within *timeout*.
    """
    lock_path = db_path.with_name(db_path.name + ADVISORY_LOCK_SUFFIX)
    try:
        lock_fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o644)
    except OSError as exc:
        raise RuntimeError(f"Cannot create lock file {lock_path}: {exc}") from exc

    try:
        deadline = time.monotonic() + timeout
        acquired = False
        while time.monotonic() < deadline:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
                break
            except BlockingIOError:
                time.sleep(0.1)

        if not acquired:
            exc = RuntimeError(
                f"Could not acquire advisory lock for {db_path} "
                f"within {timeout}s"
            )
            os.close(lock_fd)
            raise exc

        try:
            yield
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)

    except RuntimeError:
        raise
    except Exception:
        os.close(lock_fd)
        raise


# ---------------------------------------------------------------------------
# Disk space accounting
# ---------------------------------------------------------------------------


def _required_disk_mb(db_size_mb: float, operation: MaintenanceOperation) -> float:
    """Calculate total disk space required for maintenance.

    Accounts for:
    - Original database backup (one copy)
    - Temporary maintained database (one copy)
    - SQLite journal/WAL overhead
    - Safety margin for intermediate operations

    For VACUUM, the temporary copy can be up to the original size.
    A simple 2x check is insufficient because we need *simultaneous*
    space for: original + backup + temp copy + overhead.
    """
    base = db_size_mb

    if operation == MaintenanceOperation.VACUUM:
        # Need: original (stays) + backup (1x) + temp copy (up to 1x)
        # during VACUUM of the copy + overhead + margin
        required = base * 3.0 + SQLITE_OVERHEAD_MARGIN_MB
    elif operation in (MaintenanceOperation.ANALYZE, MaintenanceOperation.OPTIMIZE):
        # ANALYZE/OPTIMIZE modify the copy in-place; need backup + copy
        required = base * 2.0 + SQLITE_OVERHEAD_MARGIN_MB
    else:
        required = base + SQLITE_OVERHEAD_MARGIN_MB

    return required


# ---------------------------------------------------------------------------
# WAL/SHM helper
# ---------------------------------------------------------------------------


def _wal_shm_paths(db_path: Path) -> list[Path]:
    """Return list of WAL and SHM sidecar paths for *db_path*."""
    return [
        db_path.with_name(db_path.name + "-wal"),
        db_path.with_name(db_path.name + "-shm"),
    ]


def _move_wal_shm(src: Path, dst: Path) -> list[str]:
    """Move WAL and SHM files from *src* directory to *dst* directory.

    Returns a list of info messages about what was moved.
    """
    msgs: list[str] = []
    for sidecar in _wal_shm_paths(src):
        if sidecar.exists():
            dst_sidecar = dst.parent / sidecar.name
            try:
                shutil.move(str(sidecar), str(dst_sidecar))
                msgs.append(f"Moved WAL/SHM sidecar: {sidecar.name}")
            except OSError as exc:
                msgs.append(f"Failed to move WAL/SHM sidecar {sidecar.name}: {exc}")
    return msgs


# ---------------------------------------------------------------------------
# Snapshot before maintenance
# ---------------------------------------------------------------------------


class SourceSnapshot:
    """Identity and state of the source cache before maintenance."""

    __slots__ = (
        "fingerprint",
        "mtime_ns",
        "path",
        "schema_version",
        "size_bytes",
        "source_fingerprint",
    )

    def __init__(
        self,
        path: Path,
        size_bytes: int,
        mtime_ns: int,
        fingerprint: str,
        schema_version: str | None = None,
        source_fingerprint: str | None = None,
    ) -> None:
        self.path = path
        self.size_bytes = size_bytes
        self.mtime_ns = mtime_ns
        self.fingerprint = fingerprint
        self.schema_version = schema_version
        self.source_fingerprint = source_fingerprint


def _snapshot_source(db_path: Path) -> SourceSnapshot:
    """Record source cache identity before maintenance."""
    resolved = db_path.resolve()
    stat_result = resolved.stat()
    content_hash = hashlib.sha256()
    with open(resolved, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            content_hash.update(chunk)

    return SourceSnapshot(
        path=resolved,
        size_bytes=stat_result.st_size,
        mtime_ns=stat_result.st_mtime_ns,
        fingerprint=content_hash.hexdigest(),
    )


# ---------------------------------------------------------------------------
# Backup
# ---------------------------------------------------------------------------


def _create_timestamped_backup(
    db_path: Path,
    backup_dir: Path,
    clock: Clock,
) -> Path | None:
    """Create a timestamped backup using SQLite backup API.

    Uses microseconds in the timestamp to prevent collisions.
    Never overwrites an existing backup file.

    Args:
        db_path: Path to the original database.
        backup_dir: Directory to place the backup.
        clock: Injectable time source.

    Returns:
        Path to the backup, or None on failure.
    """
    now = clock.utc_now()
    timestamp = now.strftime("%Y%m%dT%H%M%S_%f")
    backup_path = backup_dir / f"{db_path.stem}.{timestamp}.bak"

    # Never overwrite existing backup — with microsecond precision this
    # should be extremely unlikely, but guard anyway.
    if backup_path.exists():
        return None

    try:
        src_conn = sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True)
        try:
            dst_conn = sqlite3.connect(str(backup_path))
            try:
                src_conn.backup(dst_conn)
                dst_conn.commit()
            finally:
                dst_conn.close()
        finally:
            src_conn.close()
    except Exception:
        return None

    return backup_path


# ---------------------------------------------------------------------------
# Copy-on-write maintenance
# ---------------------------------------------------------------------------


def _maintain_copy(
    src_path: Path,
    operation: MaintenanceOperation,
) -> tuple[Path, list[str]]:
    """Produce a maintained temporary copy of the source database.

    Steps:
    1. Create a temporary copy via SQLite backup API
    2. Run the maintenance operation (ANALYZE, OPTIMIZE, or VACUUM) on
       the copy
    3. Run integrity checks on the copy

    Args:
        src_path: Path to the source database.
        operation: The maintenance operation to perform.

    Returns:
        Tuple of (temp_copy_path, messages).

    Raises:
        RuntimeError: If maintenance or validation fails.
    """
    messages: list[str] = []
    tmp_path = src_path.with_name(f"{src_path.stem}.maintaining{src_path.suffix}")

    # Step 1: Create consistent temporary copy via backup API
    try:
        src_conn = sqlite3.connect(src_path.as_uri() + "?mode=ro", uri=True)
        try:
            dst_conn = sqlite3.connect(str(tmp_path))
            try:
                src_conn.backup(dst_conn)
                dst_conn.commit()
                messages.append(f"Temporary copy created: {tmp_path}")
            finally:
                dst_conn.close()
        finally:
            src_conn.close()
    except Exception as exc:
        _cleanup_temp(tmp_path)
        raise RuntimeError(f"Failed to create temporary copy: {exc}") from exc

    # Step 2: Run maintenance on the copy
    try:
        maint_conn = sqlite3.connect(str(tmp_path))
        try:
            if operation == MaintenanceOperation.ANALYZE:
                maint_conn.execute("ANALYZE")
                maint_conn.commit()
                messages.append("ANALYZE completed on temporary copy")
            elif operation == MaintenanceOperation.OPTIMIZE:
                maint_conn.execute("PRAGMA optimize")
                maint_conn.commit()
                messages.append("PRAGMA optimize completed on temporary copy")
            elif operation == MaintenanceOperation.VACUUM:
                # VACUUM the copy in-place
                maint_conn.execute("VACUUM")
                maint_conn.commit()
                messages.append("VACUUM completed on temporary copy")
        finally:
            maint_conn.close()
    except Exception as exc:
        _cleanup_temp(tmp_path)
        raise RuntimeError(
            f"{operation.name} on temporary copy failed: {exc}"
        ) from exc

    # Step 3: Validate the maintained copy
    validation_ok, validation_msgs = _run_validation(tmp_path)
    messages.extend(validation_msgs)
    if not validation_ok:
        _cleanup_temp(tmp_path)
        raise RuntimeError("Post-maintenance validation failed on temporary copy")

    return tmp_path, messages


def _run_validation(db_path: Path) -> tuple[bool, list[str]]:
    """Run integrity, foreign-key, and metadata checks on a database.

    Args:
        db_path: Path to the database to validate.

    Returns:
        Tuple of (ok: bool, messages: list[str]).
    """
    msgs: list[str] = []
    uri = f"{db_path.as_uri()}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True)
    except sqlite3.DatabaseError as exc:
        msgs.append(f"Cannot open DB for validation: {exc}")
        return False, msgs

    try:
        conn.execute("PRAGMA query_only = ON;")

        # integrity_check
        try:
            rows = conn.execute("PRAGMA integrity_check;").fetchall()
            if not all(r[0] == "ok" for r in rows):
                bad = [r[0] for r in rows if r[0] != "ok"]
                msgs.append(f"Integrity check failed: {bad}")
                return False, msgs
        except (sqlite3.OperationalError, sqlite3.DatabaseError) as exc:
            msgs.append(f"Integrity check error: {exc}")
            return False, msgs

        # quick_check
        try:
            qc_row = conn.execute("PRAGMA quick_check;").fetchone()
            if qc_row is not None and qc_row[0] != "ok":
                msgs.append(f"Quick check failed: {qc_row[0]}")
                return False, msgs
        except (sqlite3.OperationalError, sqlite3.DatabaseError) as exc:
            msgs.append(f"Quick check error: {exc}")
            return False, msgs

        # foreign_key_check
        try:
            fk_rows = conn.execute("PRAGMA foreign_key_check;").fetchall()
            if len(fk_rows) > 0:
                msgs.append(f"Foreign key violations: {len(fk_rows)}")
                return False, msgs
        except (sqlite3.OperationalError, sqlite3.DatabaseError) as exc:
            msgs.append(f"Foreign key check error: {exc}")
            return False, msgs

        # Schema and metadata
        try:
            row = conn.execute(
                "SELECT cache_schema_version, source_fingerprint "
                "FROM cache_metadata WHERE id = 1 LIMIT 1"
            ).fetchone()
            if row is None:
                msgs.append("Missing canonical metadata row after maintenance")
                return False, msgs
            if not row[0] or not row[1]:
                msgs.append("Missing schema version or source fingerprint after maintenance")
                return False, msgs
        except (sqlite3.OperationalError, sqlite3.DatabaseError) as exc:
            msgs.append(f"Metadata check error: {exc}")
            return False, msgs

        msgs.append("Post-maintenance validation passed")
        return True, msgs
    finally:
        conn.close()


def _cleanup_temp(tmp_path: Path) -> None:
    """Safely remove a temporary database file and its sidecars."""
    with contextlib.suppress(OSError):
        tmp_path.unlink()
    for sidecar in _wal_shm_paths(tmp_path):
        with contextlib.suppress(OSError):
            sidecar.unlink()


# ---------------------------------------------------------------------------
# Promotion
# ---------------------------------------------------------------------------


def _promote_validated_copy(
    original: Path,
    tmp_copy: Path,
    backup_dir: Path,
    clock: Clock,
) -> tuple[Path, Path, list[str]]:
    """Atomically promote a validated temporary copy.

    Steps:
    1. Rename original to a unique timestamped backup
    2. Rename temporary copy to original path
    3. Fsync the promoted file and containing directory
    4. On failure, restore the original from backup

    Args:
        original: Path to the original database.
        tmp_copy: Path to the validated temporary copy.
        backup_dir: Directory for the original backup.
        clock: Injectable time source.

    Returns:
        Tuple of (original_backup_path, promoted_path, messages).

    Raises:
        RuntimeError: If promotion fails and cannot be rolled back.
    """
    messages: list[str] = []
    now = clock.utc_now()
    timestamp = now.strftime("%Y%m%dT%H%M%S_%f")
    original_backup = backup_dir / f"{original.stem}.original.{timestamp}.bak"

    # Step 1: Rename original to backup
    try:
        os.rename(str(original), str(original_backup))
        messages.append(f"Original renamed to backup: {original_backup}")
    except OSError as exc:
        raise RuntimeError(f"Cannot rename original to backup: {exc}") from exc

    # Step 2: Rename temporary copy to original path
    try:
        os.rename(str(tmp_copy), str(original))
        messages.append(f"Validated copy promoted: {original}")
    except OSError as exc:
        # Attempt to restore original from backup
        try:
            os.rename(str(original_backup), str(original))
        except OSError as restore_exc:
            raise RuntimeError(
                f"Promotion failed AND original restore failed. "
                f"Backup at: {original_backup}, "
                f"Temp copy at: {tmp_copy}, "
                f"Restore error: {restore_exc}"
            ) from restore_exc
        raise RuntimeError(
            f"Cannot promote validated copy: {exc}. Original restored."
        ) from exc

    # Step 3: Fsync the promoted file
    try:
        fd = os.open(str(original), os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError as exc:
        messages.append(f"Fsync warning: {exc}")

    # Step 4: Fsync the containing directory
    try:
        dir_fd = os.open(str(original.parent), os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except OSError as exc:
        messages.append(f"Directory fsync warning: {exc}")

    # Step 5: Move WAL/SHM sidecars from original backup to promoted DB
    wal_shm_msgs = _move_wal_shm(original_backup, original)
    messages.extend(wal_shm_msgs)

    return original_backup, original, messages


def _rollback_promotion(
    original: Path,
    original_backup: Path,
) -> list[str]:
    """Restore original database from backup after promotion failure.

    Args:
        original: Target path to restore to.
        original_backup: Path to the backup file.

    Returns:
        Messages describing the rollback.
    """
    msgs: list[str] = []
    # Remove failed promoted file if it exists
    if original.exists():
        try:
            original.unlink()
            msgs.append("Removed failed promoted file")
        except OSError as exc:
            msgs.append(f"Could not remove failed promoted file: {exc}")

    # Restore original from backup
    try:
        shutil.copy2(str(original_backup), str(original))
        msgs.append(f"Original restored from backup: {original_backup}")
    except Exception as exc:
        msgs.append(f"Restore from backup failed: {exc}")
        raise RuntimeError(
            f"CRITICAL: Original DB at {original_backup}, "
            f"target at {original} may be missing. Restore error: {exc}"
        ) from exc

    return msgs


# ---------------------------------------------------------------------------
# Execute operation (the safe copy-on-write flow)
# ---------------------------------------------------------------------------


def _do_execute(
    request: MaintenanceRequest,
    evidence: MaintenanceEvidence,
    operation: MaintenanceOperation,
    clock: Clock,
) -> MaintenanceResult:
    """Execute a maintenance operation using the safe copy-on-write flow.

    The flow (M60-06):

    1. Acquire exclusive advisory lock file
    2. Re-inspect the source cache after lock acquisition
    3. Record source identity, size, mtime, fingerprint, metadata
    4. Check disk space for all required artifacts
    5. Create timestamped backup of original
    6. Produce and maintain a temporary copy via SQLite backup API
    7. Validate the temporary copy (integrity, FK, schema, metadata)
    8. Re-check that source did not change during maintenance
    9. Rename original to unique timestamped backup
    10. Atomically promote validated temporary copy
    11. Fsync promoted file and containing directory
    12. Restore original automatically if promotion fails
    13. Release advisory lock

    Never copies a backup over an open SQLite connection.
    """
    resolved = request.db_path.resolve()
    executed_at = clock.utc_now()
    messages: list[str] = []

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

    # --- 3. Schema version (full string comparison) ---
    if evidence.schema_version is None or evidence.schema_version not in request.accepted_schema_versions:
        messages.append(
            f"Unsupported schema version: {evidence.schema_version!r}. "
            f"Accepted: {sorted(request.accepted_schema_versions)}"
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

    # --- 4. Identity validation ---
    if evidence.identity is not None:
        id_check = evidence.identity
        if not id_check.has_supported_schema:
            messages.append("Identity check: unsupported schema version")
            return MaintenanceResult(
                request=request,
                verdict=MaintenanceVerdict.RED_IDENTITY_FAILURE,
                evidence=evidence,
                operation=operation,
                executed_at=executed_at,
                operation_ok=False,
                backup_path=None,
                messages=messages,
            )
        if not id_check.has_cache_metadata_table:
            messages.append("Identity check: missing cache_metadata table")
            return MaintenanceResult(
                request=request,
                verdict=MaintenanceVerdict.RED_IDENTITY_FAILURE,
                evidence=evidence,
                operation=operation,
                executed_at=executed_at,
                operation_ok=False,
                backup_path=None,
                messages=messages,
            )
        if not id_check.has_source_fingerprint:
            messages.append("Identity check: missing source fingerprint")
            return MaintenanceResult(
                request=request,
                verdict=MaintenanceVerdict.RED_IDENTITY_FAILURE,
                evidence=evidence,
                operation=operation,
                executed_at=executed_at,
                operation_ok=False,
                backup_path=None,
                messages=messages,
            )

    # --- 5. Integrity pre-check ---
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

    # --- 6. Disk space ---
    needed_mb = _required_disk_mb(evidence.db_size_mb, operation)
    if evidence.free_mb < needed_mb:
        messages.append(
            f"Insufficient disk: {evidence.free_mb:.1f} MB free, "
            f"need at least {needed_mb:.1f} MB "
            f"(original={evidence.db_size_mb:.1f} MB, "
            f"operation={operation.name})"
        )
        return MaintenanceResult(
            request=request,
            verdict=MaintenanceVerdict.RED_INSUFFICIENT_DISK,
            evidence=evidence,
            operation=operation,
            executed_at=executed_at,
            operation_ok=False,
            backup_path=None,
            messages=messages,
        )

    # --- 7. Acquire advisory lock ---
    lock_exit_stack: list[contextlib._GeneratorContextManager] = []
    try:
        lock_ctx = _advisory_lock(resolved)
        lock_ctx.__enter__()
        lock_exit_stack.append(lock_ctx)
    except RuntimeError as exc:
        messages.append(f"Advisory lock acquisition failed: {exc}")
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
        # --- 7b. Re-inspect after lock acquisition ---
        post_lock_evidence = inspect_cache(
            resolved,
            accepted_schema_versions=request.accepted_schema_versions,
            allowed_roots=request.allowed_roots,
        )
        if post_lock_evidence.integrity_ok is False:
            messages.append("Post-lock integrity check failed — source may have changed")
            return MaintenanceResult(
                request=request,
                verdict=MaintenanceVerdict.RED_INTEGRITY_FAILURE,
                evidence=post_lock_evidence,
                operation=operation,
                executed_at=clock.utc_now(),
                operation_ok=False,
                backup_path=None,
                messages=messages,
            )

        # --- 8. Record source snapshot ---
        source_snapshot = _snapshot_source(resolved)

        # --- 9. Create backup ---
        if request.backup_dir is not None:
            backup_parent = request.backup_dir.resolve()
            backup_parent.mkdir(parents=True, exist_ok=True)
        else:
            backup_parent = resolved.parent

        backup_path = _create_timestamped_backup(resolved, backup_parent, clock)
        if backup_path is None:
            messages.append("Failed to create backup before maintenance")
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

        # --- 10. Produce and maintain a temporary copy ---
        try:
            tmp_copy, maint_msgs = _maintain_copy(resolved, operation)
            messages.extend(maint_msgs)
        except RuntimeError as exc:
            messages.append(str(exc))
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

        # --- 11. Re-check that source did not change ---
        current_snapshot = _snapshot_source(resolved)
        if (current_snapshot.size_bytes != source_snapshot.size_bytes
                or current_snapshot.mtime_ns != source_snapshot.mtime_ns):
            messages.append(
                "Source cache changed during maintenance — aborting promotion"
            )
            _cleanup_temp(tmp_copy)
            return MaintenanceResult(
                request=request,
                verdict=MaintenanceVerdict.RED_SOURCE_CHANGED,
                evidence=evidence,
                operation=operation,
                executed_at=clock.utc_now(),
                operation_ok=False,
                backup_path=backup_path,
                messages=messages,
            )

        # --- 12. Promote the validated copy ---
        try:
            original_backup_path, promoted_path, promo_msgs = _promote_validated_copy(
                resolved, tmp_copy, backup_parent, clock
            )
            messages.extend(promo_msgs)
        except RuntimeError as exc:
            messages.append(str(exc))
            # Rollback: restore from backup
            try:
                _rollback_promotion(resolved, backup_path)
                messages.append("Original restored from backup after failed promotion")
            except RuntimeError as rollback_exc:
                messages.append(str(rollback_exc))
            return MaintenanceResult(
                request=request,
                verdict=MaintenanceVerdict.RED_PROMOTION_FAILURE,
                evidence=evidence,
                operation=operation,
                executed_at=executed_at,
                operation_ok=False,
                backup_path=backup_path,
                messages=messages,
            )

    finally:
        # Advisory lock is released here
        for ctx in lock_exit_stack:
            ctx.__exit__(None, None, None)

    messages.append(f"{operation.name} completed successfully via copy-on-write")
    return MaintenanceResult(
        request=request,
        verdict=MaintenanceVerdict.GREEN_NO_ACTION,
        evidence=evidence,
        operation=operation,
        executed_at=executed_at,
        operation_ok=True,
        backup_path=backup_path,
        promoted_path=promoted_path,
        original_backup_path=original_backup_path,
        messages=messages,
    )


# ---------------------------------------------------------------------------
# Public operation entry points
# ---------------------------------------------------------------------------


def execute_analyze(
    request: MaintenanceRequest,
    evidence: MaintenanceEvidence,
) -> MaintenanceResult:
    """Run ANALYZE on a cache database using copy-on-write."""
    return _do_execute(request, evidence, MaintenanceOperation.ANALYZE, request.clock)


def execute_optimize(
    request: MaintenanceRequest,
    evidence: MaintenanceEvidence,
) -> MaintenanceResult:
    """Run PRAGMA optimize on a cache database using copy-on-write."""
    return _do_execute(request, evidence, MaintenanceOperation.OPTIMIZE, request.clock)


def execute_vacuum(
    request: MaintenanceRequest,
    evidence: MaintenanceEvidence,
) -> MaintenanceResult:
    """Run VACUUM on a cache database using copy-on-write."""
    return _do_execute(request, evidence, MaintenanceOperation.VACUUM, request.clock)


# ---------------------------------------------------------------------------
# Verdict helper
# ---------------------------------------------------------------------------


def _verdict_from_evidence(
    evidence: MaintenanceEvidence,
    accepted_versions: frozenset[str] = SUPPORTED_SCHEMA_VERSIONS,
) -> MaintenanceVerdict:
    """Derive a typed verdict from inspection evidence."""
    # Check identity first if available
    if evidence.identity is not None and not evidence.identity.has_supported_schema and evidence.db_size_mb > 0:
        return MaintenanceVerdict.RED_UNSUPPORTED_SCHEMA

    # Schema check (backward compat if identity is None)
    if evidence.schema_version is None and evidence.db_size_mb > 0:
        return MaintenanceVerdict.RED_UNSUPPORTED_SCHEMA
    if (
        evidence.schema_version is not None
        and evidence.schema_version not in accepted_versions
    ):
        return MaintenanceVerdict.RED_UNSUPPORTED_SCHEMA

    # Integrity checks — None means check failed (fail-closed)
    if evidence.integrity_ok is False or evidence.integrity_ok is None:
        return MaintenanceVerdict.RED_INTEGRITY_FAILURE
    if evidence.foreign_keys_ok is False or evidence.foreign_keys_ok is None:
        return MaintenanceVerdict.RED_INTEGRITY_FAILURE
    if evidence.quick_check_ok is False or evidence.quick_check_ok is None:
        return MaintenanceVerdict.RED_INTEGRITY_FAILURE

    # Rebuildability
    if not evidence.rebuildable and evidence.db_size_mb > 0:
        return MaintenanceVerdict.YELLOW_REBUILD_RECOMMENDED

    # Disk space
    if evidence.free_mb < evidence.db_size_mb * VACUUM_DISK_MULTIPLIER and evidence.db_size_mb > 0:
        return MaintenanceVerdict.YELLOW_VACUUM_RECOMMENDED

    return MaintenanceVerdict.GREEN_NO_ACTION


# ---------------------------------------------------------------------------
# High-level runner
# ---------------------------------------------------------------------------


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
        clock = request.clock

        # Always start with path safety check
        if not is_safe_cache_path(db_path):
            return MaintenanceResult(
                request=request,
                verdict=MaintenanceVerdict.RED_UNSAFE_PATH,
                evidence=inspect_cache(
                    db_path,
                    accepted_schema_versions=request.accepted_schema_versions,
                    allowed_roots=request.allowed_roots,
                ),
                operation=None,
                executed_at=clock.utc_now(),
                operation_ok=None,
                backup_path=None,
                messages=[f"Unsafe cache path: {db_path}"],
            )

        # Always inspect first
        evidence = inspect_cache(
            db_path,
            accepted_schema_versions=request.accepted_schema_versions,
            allowed_roots=request.allowed_roots,
        )

        if mode == MaintenanceMode.INSPECT:
            return MaintenanceResult(
                request=request,
                verdict=_verdict_from_evidence(
                    evidence, request.accepted_schema_versions
                ),
                evidence=evidence,
                operation=None,
                executed_at=clock.utc_now(),
                operation_ok=None,
                backup_path=None,
                messages=["Inspection completed"],
            )

        if mode == MaintenanceMode.DRY_RUN:
            verdict = _verdict_from_evidence(
                evidence, request.accepted_schema_versions
            )
            return MaintenanceResult(
                request=request,
                verdict=verdict,
                evidence=evidence,
                operation=None,
                executed_at=clock.utc_now(),
                operation_ok=None,
                backup_path=None,
                messages=["Dry-run completed — no mutations performed"],
            )

        if mode == MaintenanceMode.EXECUTE_ANALYZE:
            return execute_analyze(request, evidence)

        if mode == MaintenanceMode.EXECUTE_OPTIMIZE:
            return execute_optimize(request, evidence)

        if mode == MaintenanceMode.EXECUTE_VACUUM:
            return execute_vacuum(request, evidence)

        msg = f"Unknown mode: {mode}"
        raise ValueError(msg)
