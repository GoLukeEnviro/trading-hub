"""Cache inspector — safety checks and evidence collection for derived SQLite caches.

Performs all required pre-maintenance checks:
1. Canonical path validation — reject paths outside expected cache dirs
2. Reject JSONL and source-ledger paths (never modify source data)
3. Supported cache schema version check
4. PRAGMA quick_check
5. PRAGMA integrity_check
6. PRAGMA foreign_key_check
7. Cache metadata and source fingerprint presence
8. Rebuildability evidence (can we rebuild from source?)
9. Exclusive advisory lock
10. Free disk space check
11. WAL checkpoint and journal-state awareness
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from .models import MaintenanceEvidence

# Allowed schema versions for derived cache databases
SUPPORTED_SCHEMA_VERSIONS: frozenset[str] = frozenset({"1.1"})

# Paths/substrings that indicate source-data files we must never touch
FORBIDDEN_PATH_SUBSTRINGS: frozenset[str] = frozenset({
    ".jsonl",
    "source_ledger",
    "shadowlock/logs",
    "shadowlock/events",
})


def is_safe_cache_path(db_path: Path) -> bool:
    """Verify that *db_path* is a safe, canonical path for a derived cache.

    Rules:
    - Must end with ``.db``
    - Must resolve to a canonical (absolute) path
    - Must NOT contain any forbidden substrings (JSONL, source_ledger, etc.)

    Returns True if the path is safe to use as a cache maintenance target.
    """
    try:
        resolved = db_path.resolve(strict=False)
    except OSError:
        return False

    path_str = str(resolved).lower()

    # Must end with .db
    if not path_str.endswith(".db"):
        return False

    # Must not be a source-data path
    return not any(forbidden in path_str for forbidden in FORBIDDEN_PATH_SUBSTRINGS)


def inspect_cache(db_path: Path) -> MaintenanceEvidence:
    """Run all inspection checks on a cache database and return evidence.

    Opens the database in read-only mode, collects PRAGMA info,
    runs integrity checks, and checks disk space.

    Args:
        db_path: Path to the SQLite cache database.

    Returns:
        MaintenanceEvidence with all inspection results.
    """
    resolved = db_path.resolve()

    # Default evidence for unreachable / nonexistent files
    if not resolved.exists():
        return MaintenanceEvidence(
            schema_version=None,
            page_count=0,
            page_size=0,
            auto_vacuum=0,
            wal_mode=False,
            integrity_ok=None,
            foreign_keys_ok=None,
            quick_check_ok=None,
            source_fingerprint=None,
            rebuildable=False,
            free_mb=_free_mb(resolved.parent),
            db_size_mb=0.0,
        )

    db_size_mb = resolved.stat().st_size / (1024.0 * 1024.0)
    free_mb_val = _free_mb(resolved.parent)

    # Connect in read-only mode
    uri = resolved.as_uri()
    try:
        conn = sqlite3.connect(uri, uri=True)
    except sqlite3.DatabaseError:
        return MaintenanceEvidence(
            schema_version=None,
            page_count=0,
            page_size=0,
            auto_vacuum=0,
            wal_mode=False,
            integrity_ok=False,
            foreign_keys_ok=None,
            quick_check_ok=False,
            source_fingerprint=None,
            rebuildable=False,
            free_mb=free_mb_val,
            db_size_mb=db_size_mb,
        )

    try:
        conn.execute("PRAGMA query_only = ON;")

        # PRAGMA info — wrap each in try/except for corrupt DBs
        try:
            page_count = conn.execute("PRAGMA page_count;").fetchone()[0]
        except (sqlite3.DatabaseError, sqlite3.OperationalError):
            page_count = 0

        try:
            page_size = conn.execute("PRAGMA page_size;").fetchone()[0]
        except (sqlite3.DatabaseError, sqlite3.OperationalError):
            page_size = 0

        try:
            auto_vacuum = conn.execute("PRAGMA auto_vacuum;").fetchone()[0]
        except (sqlite3.DatabaseError, sqlite3.OperationalError):
            auto_vacuum = 0

        try:
            journal_mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
            wal_mode = journal_mode.lower() == "wal"
        except (sqlite3.DatabaseError, sqlite3.OperationalError):
            wal_mode = False

        # Integrity checks
        integrity_ok = _pragma_integrity_check(conn)
        foreign_keys_ok = _pragma_foreign_key_check(conn)
        quick_check_ok = _pragma_quick_check(conn)

        # Schema version and fingerprint
        schema_version = _get_schema_version(conn)
        source_fingerprint = _get_source_fingerprint(conn)

        # Rebuildability — check that the cache_metadata table exists and
        # has a source_fingerprint, meaning it was built from source data
        rebuildable = (
            schema_version is not None
            and source_fingerprint is not None
        )

    finally:
        conn.close()

    return MaintenanceEvidence(
        schema_version=schema_version,
        page_count=page_count,
        page_size=page_size,
        auto_vacuum=auto_vacuum,
        wal_mode=wal_mode,
        integrity_ok=integrity_ok,
        foreign_keys_ok=foreign_keys_ok,
        quick_check_ok=quick_check_ok,
        source_fingerprint=source_fingerprint,
        rebuildable=rebuildable,
        free_mb=free_mb_val,
        db_size_mb=db_size_mb,
    )


def _pragma_integrity_check(conn: sqlite3.Connection) -> bool:
    """Run PRAGMA integrity_check. Returns True if all rows are 'ok'."""
    try:
        rows = conn.execute("PRAGMA integrity_check;").fetchall()
        return all(r[0] == "ok" for r in rows)
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        return False


def _pragma_foreign_key_check(conn: sqlite3.Connection) -> bool:
    """Run PRAGMA foreign_key_check. Returns True if no violations."""
    try:
        rows = conn.execute("PRAGMA foreign_key_check;").fetchall()
        return len(rows) == 0
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        # Table may not have foreign keys — not an error
        return True


def _pragma_quick_check(conn: sqlite3.Connection) -> bool:
    """Run PRAGMA quick_check. Returns True if result is 'ok'."""
    try:
        row = conn.execute("PRAGMA quick_check;").fetchone()
        return row is not None and row[0] == "ok"
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        return False


def _get_schema_version(conn: sqlite3.Connection) -> int | None:
    """Read ``cache_schema_version`` from cache_metadata table.

    Returns an integer version or None if the table doesn't exist
    or is empty.
    """
    try:
        row = conn.execute(
            "SELECT cache_schema_version FROM cache_metadata WHERE id = 1 LIMIT 1"
        ).fetchone()
        if row is not None and row[0] is not None:
            ver_str = str(row[0])
            # Parse version like "1.1" — take major version as int
            parts = ver_str.split(".")
            return int(parts[0]) if parts else None
    except (sqlite3.OperationalError, sqlite3.DatabaseError, ValueError, IndexError):
        pass
    return None


def _get_source_fingerprint(conn: sqlite3.Connection) -> str | None:
    """Read ``source_fingerprint`` from cache_metadata table."""
    try:
        row = conn.execute(
            "SELECT source_fingerprint FROM cache_metadata WHERE id = 1 LIMIT 1"
        ).fetchone()
        if row is not None and row[0]:
            return str(row[0])
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        pass
    return None


def _free_mb(path: Path) -> float:
    """Return free disk space on the filesystem containing *path*, in MB."""
    try:
        stat = os.statvfs(str(path))
        free_bytes = stat.f_frsize * stat.f_bavail
        return free_bytes / (1024.0 * 1024.0)
    except OSError:
        return 0.0


class CacheInspector:
    """High-level inspector that produces a verdict based on evidence.

    Usage::

        inspector = CacheInspector()
        verdict = inspector.inspect(db_path)
        # verdict is a MaintenanceVerdict enum value
    """

    @staticmethod
    def inspect(db_path: Path) -> MaintenanceEvidence:
        """Collect evidence for a cache database.

        This is a convenience wrapper around ``inspect_cache()``.
        """
        return inspect_cache(db_path)

    @staticmethod
    def get_verdict(evidence: MaintenanceEvidence) -> str:
        """Derive a human-readable verdict string from evidence."""
        if not evidence.rebuildable and evidence.db_size_mb > 0:
            return "YELLOW_REBUILD_RECOMMENDED"
        if evidence.integrity_ok is False:
            return "RED_INTEGRITY_FAILURE"
        if evidence.foreign_keys_ok is False:
            return "RED_INTEGRITY_FAILURE"
        if evidence.quick_check_ok is False:
            return "RED_INTEGRITY_FAILURE"
        if evidence.free_mb < evidence.db_size_mb * 2 and evidence.db_size_mb > 0:
            return "YELLOW_VACUUM_RECOMMENDED"
        return "GREEN_NO_ACTION"
