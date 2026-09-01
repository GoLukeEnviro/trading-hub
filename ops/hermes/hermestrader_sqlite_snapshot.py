#!/usr/bin/env python3
"""Create a bounded, consistent SQLite snapshot without mutating its source."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
from pathlib import Path
from urllib.parse import quote

COPY_CHUNK_BYTES = 1024 * 1024


def fail(reason: str, detail: str) -> int:
    print(f"{reason}: {detail}", file=sys.stderr)
    return 1


def readonly_uri(path: Path, *, immutable: bool = False) -> str:
    suffix = "&immutable=1" if immutable else ""
    return f"file:{quote(path.as_posix(), safe='/')}?mode=ro{suffix}"


def verify_destination(destination: Path, *, immutable: bool = False) -> None:
    connection = sqlite3.connect(readonly_uri(destination, immutable=immutable), uri=True, timeout=30)
    try:
        rows = connection.execute("PRAGMA integrity_check").fetchall()
    finally:
        connection.close()
    if rows != [("ok",)]:
        raise sqlite3.DatabaseError(f"integrity_check returned {rows!r}")


def fsync_file(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def snapshot_with_backup_api(source: Path, destination: Path) -> dict[str, object]:
    source_connection: sqlite3.Connection | None = None
    destination_connection: sqlite3.Connection | None = None
    try:
        source_connection = sqlite3.connect(readonly_uri(source), uri=True, timeout=30)
        source_connection.execute("PRAGMA query_only=ON")
        source_connection.execute("PRAGMA busy_timeout=30000")
        journal_mode = str(source_connection.execute("PRAGMA journal_mode").fetchone()[0])
        page_count = int(source_connection.execute("PRAGMA page_count").fetchone()[0])

        destination_connection = sqlite3.connect(destination, timeout=30)
        destination_connection.execute("PRAGMA busy_timeout=30000")

        # pages=-1 maps to one sqlite3_backup_step(..., -1). The source read
        # lock is held for the complete copy, avoiding restart starvation when
        # an active WAL writer changes the source during incremental steps.
        source_connection.backup(destination_connection, pages=-1, sleep=0)
        destination_connection.commit()
        verify_destination(destination)
    finally:
        if destination_connection is not None:
            destination_connection.close()
        if source_connection is not None:
            source_connection.close()

    os.chmod(destination, 0o600)
    fsync_file(destination)
    return {
        "source": str(source),
        "destination": str(destination),
        "method": "sqlite_backup_full_step",
        "source_journal_mode": journal_mode,
        "source_page_count": page_count,
        "destination_bytes": destination.stat().st_size,
        "integrity_check": "ok",
    }


def file_identity(stat_result: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        stat_result.st_dev,
        stat_result.st_ino,
        stat_result.st_size,
        stat_result.st_mtime_ns,
        stat_result.st_ctime_ns,
    )


def transaction_sidecars(source: Path) -> tuple[bool, bool, bool]:
    return tuple(Path(f"{source}{suffix}").exists() for suffix in ("-wal", "-shm", "-journal"))


def snapshot_with_stable_raw_copy(source: Path, destination: Path) -> dict[str, object]:
    before_sidecars = transaction_sidecars(source)
    if any(before_sidecars):
        raise sqlite3.OperationalError(f"transaction sidecar appeared before stable copy: {before_sidecars}")

    copy_digest = hashlib.sha256()
    source_digest = hashlib.sha256()
    source_descriptor = os.open(source, os.O_RDONLY)
    destination_descriptor: int | None = None
    try:
        before = os.fstat(source_descriptor)
        destination_descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        while chunk := os.read(source_descriptor, COPY_CHUNK_BYTES):
            copy_digest.update(chunk)
            view = memoryview(chunk)
            while view:
                written = os.write(destination_descriptor, view)
                view = view[written:]
        os.fsync(destination_descriptor)
        os.close(destination_descriptor)
        destination_descriptor = None

        after_sidecars = transaction_sidecars(source)
        after = os.fstat(source_descriptor)
        if any(after_sidecars):
            raise sqlite3.OperationalError(f"transaction sidecar appeared during stable copy: {after_sidecars}")
        if file_identity(before) != file_identity(after):
            raise sqlite3.OperationalError("source identity or metadata changed during stable copy")

        os.lseek(source_descriptor, 0, os.SEEK_SET)
        while chunk := os.read(source_descriptor, COPY_CHUNK_BYTES):
            source_digest.update(chunk)
        final_sidecars = transaction_sidecars(source)
        final = os.fstat(source_descriptor)
        if any(final_sidecars):
            raise sqlite3.OperationalError(
                f"transaction sidecar appeared during source verification: {final_sidecars}"
            )
        if file_identity(before) != file_identity(final):
            raise sqlite3.OperationalError("source identity or metadata changed during verification")
        if source_digest.digest() != copy_digest.digest():
            raise sqlite3.OperationalError("source content changed during stable copy")
    finally:
        if destination_descriptor is not None:
            os.close(destination_descriptor)
        os.close(source_descriptor)

    # immutable=1 prevents SQLite from trying to create a WAL sidecar while
    # validating a WAL-header database whose transaction sidecars are absent.
    verify_destination(destination, immutable=True)
    os.chmod(destination, 0o600)
    fsync_file(destination)
    header = destination.read_bytes()[:100]
    wal_header = len(header) >= 20 and header[18:20] == b"\x02\x02"
    page_count = int.from_bytes(header[28:32], "big") if len(header) >= 32 else 0
    return {
        "source": str(source),
        "destination": str(destination),
        "method": "sqlite_stable_raw_copy",
        "source_journal_mode": "wal-header" if wal_header else "rollback-header",
        "source_page_count": page_count,
        "destination_bytes": destination.stat().st_size,
        "integrity_check": "ok",
    }


def snapshot(source: Path, destination: Path) -> dict[str, object]:
    if not source.is_absolute() or not destination.is_absolute():
        raise ValueError("SOURCE_AND_DESTINATION_MUST_BE_ABSOLUTE")
    if not source.is_file():
        raise ValueError(f"SOURCE_NOT_REGULAR_FILE: {source}")
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"DESTINATION_EXISTS: {destination}")
    if not destination.parent.is_dir():
        raise ValueError(f"DESTINATION_PARENT_MISSING: {destination.parent}")

    wal_exists, shm_exists, journal_exists = transaction_sidecars(source)
    if wal_exists != shm_exists:
        raise sqlite3.OperationalError(
            f"incomplete WAL sidecars: wal={wal_exists} shm={shm_exists}"
        )
    try:
        if wal_exists or journal_exists:
            return snapshot_with_backup_api(source, destination)
        return snapshot_with_stable_raw_copy(source, destination)
    except Exception:
        destination.unlink(missing_ok=True)
        raise


def main() -> int:
    if len(sys.argv) != 3:
        print(f"usage: {sys.argv[0]} SOURCE DESTINATION", file=sys.stderr)
        return 64
    os.umask(0o077)
    try:
        result = snapshot(Path(sys.argv[1]), Path(sys.argv[2]))
    except FileExistsError as exc:
        return fail("DESTINATION_EXISTS", str(exc).removeprefix("DESTINATION_EXISTS: "))
    except ValueError as exc:
        return fail("SQLITE_SNAPSHOT_INVALID", str(exc))
    except (OSError, sqlite3.Error) as exc:
        return fail("SQLITE_SNAPSHOT_FAILED", str(exc))
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
