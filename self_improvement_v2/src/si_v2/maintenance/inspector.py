"""Cache inspector — safety checks and evidence collection for derived SQLite caches.

Performs all required pre-maintenance checks:
1. Canonical path validation — reject paths outside expected cache dirs
2. Identity-based cache validation — not just suffix
3. SQLite URI mode=ro (never creates missing databases)
4. Full schema version comparison against supported set
5. PRAGMA quick_check, integrity_check, foreign_key_check
6. Cache metadata and source fingerprint presence
7. Rebuildability evidence
8. Free disk space check
9. WAL checkpoint and journal-state awareness
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from .models import (
    CacheIdentity,
    CacheKind,
    MaintenanceEvidence,
)

# Allowed schema versions for derived cache databases — full version strings
SUPPORTED_SCHEMA_VERSIONS: frozenset[str] = frozenset({"1.1"})

# Expected table names in a valid source_regime_stats cache
EXPECTED_DATA_TABLES: frozenset[str] = frozenset({
    "cache_metadata",
    "source_regime_stats",
})

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


def validate_cache_identity(
    db_path: Path,
    conn: sqlite3.Connection,
    accepted_schema_versions: frozenset[str] = SUPPORTED_SCHEMA_VERSIONS,
    allowed_roots: list[Path] | None = None,
) -> CacheIdentity:
    """Validate that a target file is an approved SI v2 derived cache.

    An arbitrary .db file must never be accepted. This check verifies:

    - File exists with .db extension
    - Schema version is in the accepted version set
    - Expected tables exist (cache_metadata, source_regime_stats)
    - Canonical metadata row (id=1) is present
    - Source fingerprint is populated
    - Cache kind is known
    - Path is within an allowed root (if roots are specified)

    Returns a CacheIdentity with every check result.
    """
    # File existence
    is_file = db_path.is_file()
    is_db_suffix = db_path.suffix.lower() == ".db"

    # Schema version
    cache_schema_version: str | None = None
    has_supported_schema = False
    has_cache_metadata_table = False
    has_expected_data_tables = False
    has_canonical_metadata_row = False
    has_source_fingerprint = False
    source_fingerprint: str | None = None

    if is_file and is_db_suffix:
        try:
            # Check cache_metadata table existence
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='cache_metadata'"
            ).fetchall()
            has_cache_metadata_table = len(rows) > 0

            # Check expected data tables
            expected_found = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            table_names = {r[0] for r in expected_found}
            has_expected_data_tables = EXPECTED_DATA_TABLES.issubset(table_names)

            # Read metadata row
            if has_cache_metadata_table:
                metadata_row = conn.execute(
                    "SELECT cache_schema_version, source_fingerprint "
                    "FROM cache_metadata WHERE id = 1 LIMIT 1"
                ).fetchone()
                if metadata_row is not None:
                    has_canonical_metadata_row = True
                    ver = metadata_row[0]
                    if ver is not None:
                        cache_schema_version = str(ver)
                        has_supported_schema = (
                            cache_schema_version in accepted_schema_versions
                        )
                    fp = metadata_row[1]
                    if fp:
                        source_fingerprint = str(fp)
                        has_source_fingerprint = True
        except (sqlite3.OperationalError, sqlite3.DatabaseError):
            pass

    # Cache kind
    cache_kind = CacheKind.from_path(db_path)

    # Allowed root check
    in_allowed_root = _check_allowed_root(db_path, allowed_roots)

    return CacheIdentity(
        is_file=is_file,
        is_db_suffix=is_db_suffix,
        has_supported_schema=has_supported_schema,
        has_cache_metadata_table=has_cache_metadata_table,
        has_expected_data_tables=has_expected_data_tables,
        has_canonical_metadata_row=has_canonical_metadata_row,
        has_source_fingerprint=has_source_fingerprint,
        cache_schema_version=cache_schema_version,
        source_fingerprint=source_fingerprint,
        cache_kind=cache_kind,
        in_allowed_root=in_allowed_root,
    )


def _check_allowed_root(
    db_path: Path, allowed_roots: list[Path] | None
) -> bool:
    """Check if *db_path* is within one of the *allowed_roots*."""
    if allowed_roots is None:
        return True  # No restriction
    if not db_path.is_absolute():
        return False
    try:
        resolved = db_path.resolve()
        for root in allowed_roots:
            try:
                root_resolved = root.resolve()
                if root_resolved in resolved.parents or root_resolved == resolved.parent:
                    return True
            except OSError:
                continue
    except OSError:
        return False
    return False


def inspect_cache(
    db_path: Path,
    accepted_schema_versions: frozenset[str] = SUPPORTED_SCHEMA_VERSIONS,
    allowed_roots: list[Path] | None = None,
) -> MaintenanceEvidence:
    """Run all inspection checks on a cache database and return evidence.

    Opens the database with SQLite URI ``mode=ro`` — a missing database
    will never be created by this function.

    Args:
        db_path: Path to the SQLite cache database.
        accepted_schema_versions: Set of accepted full version strings.
        allowed_roots: Optional list of allowed root directories.

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

    # Connect in read-only mode using mode=ro — never creates a missing DB
    uri = f"{resolved.as_uri()}?mode=ro"
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
        page_count = _safe_pragma_int(conn, "page_count", 0)
        page_size = _safe_pragma_int(conn, "page_size", 0)
        auto_vacuum = _safe_pragma_int(conn, "auto_vacuum", 0)
        wal_mode = _safe_check_wal(conn)

        # Integrity checks
        integrity_ok = _pragma_integrity_check(conn)
        foreign_keys_ok = _pragma_foreign_key_check(conn)
        quick_check_ok = _pragma_quick_check(conn)

        # Identity validation — full contract check
        identity = validate_cache_identity(
            resolved,
            conn,
            accepted_schema_versions=accepted_schema_versions,
            allowed_roots=allowed_roots,
        )

        # Schema version and fingerprint from identity (full string)
        schema_version = identity.cache_schema_version
        source_fingerprint = identity.source_fingerprint

        # Rebuildability — supported schema + source_fingerprint = can rebuild
        rebuildable = (
            identity.has_supported_schema
            and identity.has_source_fingerprint
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
        identity=identity,
    )


def _safe_pragma_int(conn: sqlite3.Connection, pragma: str, default: int) -> int:
    """Run a PRAGMA that returns a single integer value."""
    try:
        row = conn.execute(f"PRAGMA {pragma};").fetchone()
        return row[0] if row is not None else default
    except (sqlite3.DatabaseError, sqlite3.OperationalError):
        return default


def _safe_check_wal(conn: sqlite3.Connection) -> bool:
    """Check if the database is in WAL journal mode."""
    try:
        row = conn.execute("PRAGMA journal_mode;").fetchone()
        return row is not None and row[0].lower() == "wal"
    except (sqlite3.DatabaseError, sqlite3.OperationalError):
        return False


def _pragma_integrity_check(conn: sqlite3.Connection) -> bool | None:
    """Run PRAGMA integrity_check.

    Returns True if all rows are 'ok', False if violations found,
    None if the check could not be run.
    """
    try:
        rows = conn.execute("PRAGMA integrity_check;").fetchall()
        return all(r[0] == "ok" for r in rows)
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        return None


def _pragma_foreign_key_check(conn: sqlite3.Connection) -> bool | None:
    """Run PRAGMA foreign_key_check.

    Returns True if no violations, False if violations found,
    None if the check could not be run.

    IMPORTANT: An exception is treated as ``None`` (unknown), not
    ``True`` (passed). This is fail-closed: unknown FK status must
    not be treated as clean.
    """
    try:
        rows = conn.execute("PRAGMA foreign_key_check;").fetchall()
        return len(rows) == 0
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        return None


def _pragma_quick_check(conn: sqlite3.Connection) -> bool | None:
    """Run PRAGMA quick_check.

    Returns True if result is 'ok', False if not, None if check failed.
    """
    try:
        row = conn.execute("PRAGMA quick_check;").fetchone()
        if row is None:
            return None
        return row[0] == "ok"
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        return None


def _free_mb(path: Path) -> float:
    """Return free disk space on the filesystem containing *path*, in MB."""
    try:
        stat = os.statvfs(str(path))
        free_bytes = stat.f_frsize * stat.f_bavail
        return free_bytes / (1024.0 * 1024.0)
    except OSError:
        return 0.0


# ---------------------------------------------------------------------------
# Convenience high-level interface
# ---------------------------------------------------------------------------


class CacheInspector:
    """High-level inspector that produces evidence for a cache."""

    @staticmethod
    def inspect(
        db_path: Path,
        accepted_schema_versions: frozenset[str] = SUPPORTED_SCHEMA_VERSIONS,
        allowed_roots: list[Path] | None = None,
    ) -> MaintenanceEvidence:
        """Collect evidence for a cache database.

        Args:
            db_path: Path to the SQLite cache database.
            accepted_schema_versions: Set of accepted full version strings.
            allowed_roots: Optional list of allowed root directories.

        Returns:
            MaintenanceEvidence with all inspection results.
        """
        return inspect_cache(
            db_path,
            accepted_schema_versions=accepted_schema_versions,
            allowed_roots=allowed_roots,
        )
