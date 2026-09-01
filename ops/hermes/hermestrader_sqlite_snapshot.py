#!/usr/bin/env python3
"""Create one consistent SQLite snapshot with a single backup API step."""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path
from urllib.parse import quote


def fail(reason: str, detail: str) -> int:
    print(f"{reason}: {detail}", file=sys.stderr)
    return 1


def readonly_uri(path: Path) -> str:
    return f"file:{quote(path.as_posix(), safe='/')}?mode=ro"


def snapshot(source: Path, destination: Path) -> dict[str, object]:
    if not source.is_absolute() or not destination.is_absolute():
        raise ValueError("SOURCE_AND_DESTINATION_MUST_BE_ABSOLUTE")
    if not source.is_file():
        raise ValueError(f"SOURCE_NOT_REGULAR_FILE: {source}")
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"DESTINATION_EXISTS: {destination}")
    if not destination.parent.is_dir():
        raise ValueError(f"DESTINATION_PARENT_MISSING: {destination.parent}")

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
        # lock is therefore held for the complete copy instead of being
        # released between incremental steps that restart on external writes.
        source_connection.backup(destination_connection, pages=-1, sleep=0)
        destination_connection.commit()
        integrity_rows = destination_connection.execute("PRAGMA integrity_check").fetchall()
        if integrity_rows != [("ok",)]:
            raise sqlite3.DatabaseError(f"integrity_check returned {integrity_rows!r}")
    finally:
        if destination_connection is not None:
            destination_connection.close()
        if source_connection is not None:
            source_connection.close()

    os.chmod(destination, 0o600)
    descriptor = os.open(destination, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)

    return {
        "source": str(source),
        "destination": str(destination),
        "method": "sqlite_backup_full_step",
        "source_journal_mode": journal_mode,
        "source_page_count": page_count,
        "destination_bytes": destination.stat().st_size,
        "integrity_check": "ok",
    }


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
