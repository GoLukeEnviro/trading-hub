"""Typed data contracts for the derived SQLite cache maintenance module.

Defines the maintenance verdict enum, request/evidence/result dataclasses
used by the inspector and operations pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from pathlib import Path


class MaintenanceVerdict(Enum):
    """Verdict of a cache maintenance inspection or operation."""

    GREEN_NO_ACTION = "GREEN_NO_ACTION"
    GREEN_ANALYZE_RECOMMENDED = "GREEN_ANALYZE_RECOMMENDED"
    YELLOW_OPTIMIZE_RECOMMENDED = "YELLOW_OPTIMIZE_RECOMMENDED"
    YELLOW_VACUUM_RECOMMENDED = "YELLOW_VACUUM_RECOMMENDED"
    YELLOW_REBUILD_RECOMMENDED = "YELLOW_REBUILD_RECOMMENDED"
    RED_INTEGRITY_FAILURE = "RED_INTEGRITY_FAILURE"
    RED_UNSUPPORTED_SCHEMA = "RED_UNSUPPORTED_SCHEMA"
    RED_UNSAFE_PATH = "RED_UNSAFE_PATH"
    RED_LOCK_CONFLICT = "RED_LOCK_CONFLICT"
    RED_INSUFFICIENT_DISK = "RED_INSUFFICIENT_DISK"


class MaintenanceOperation(Enum):
    """The specific maintenance operation to perform."""

    ANALYZE = auto()
    OPTIMIZE = auto()
    VACUUM = auto()


@dataclass
class MaintenanceRequest:
    """Parameters for a cache maintenance request.

    Attributes:
        db_path: Path to the SQLite cache database.
        mode: Operation mode — inspect, dry-run, execute-analyze,
            execute-optimize, execute-vacuum.
        force: Bypass confirmation prompts (for CLI automation).
        backup_dir: Optional explicit backup directory.
    """

    db_path: Path
    mode: str  # inspect, dry-run, execute-analyze, execute-optimize, execute-vacuum
    force: bool = False
    backup_dir: Path | None = None


@dataclass
class MaintenanceEvidence:
    """Collected evidence from cache inspection.

    Attributes:
        schema_version: The cache_schema_version from cache_metadata, or None.
        page_count: SQLite PRAGMA page_count.
        page_size: SQLite PRAGMA page_size.
        auto_vacuum: PRAGMA auto_vacuum setting (0=none, 1=full, 2=incremental).
        wal_mode: True if journal_mode is 'wal'.
        integrity_ok: Result of PRAGMA integrity_check, or None if not run.
        foreign_keys_ok: Result of PRAGMA foreign_key_check, or None if not run.
        quick_check_ok: Result of PRAGMA quick_check, or None if not run.
        source_fingerprint: The source_fingerprint from cache_metadata, or None.
        rebuildable: True if the cache can be rebuilt from source data.
        free_mb: Free disk space on the DB filesystem in MB.
        db_size_mb: Size of the DB file in MB.
    """

    schema_version: int | None
    page_count: int
    page_size: int
    auto_vacuum: int
    wal_mode: bool
    integrity_ok: bool | None
    foreign_keys_ok: bool | None
    quick_check_ok: bool | None
    source_fingerprint: str | None
    rebuildable: bool
    free_mb: float
    db_size_mb: float


@dataclass
class MaintenanceResult:
    """Complete result of a maintenance inspection or operation.

    Attributes:
        request: The original MaintenanceRequest.
        verdict: The final verdict.
        evidence: Collected evidence from cache inspection.
        operation: The operation performed, or None for inspect/dry-run.
        executed_at: UTC timestamp of execution.
        operation_ok: True if the operation succeeded, False if it failed,
            None for inspect/dry-run.
        backup_path: Path to any backup created, or None.
        messages: Human-readable messages (warnings, errors, info).
    """

    request: MaintenanceRequest
    verdict: MaintenanceVerdict
    evidence: MaintenanceEvidence
    operation: MaintenanceOperation | None
    executed_at: datetime
    operation_ok: bool | None
    backup_path: Path | None
    messages: list[str] = field(default_factory=list)
