"""Typed data contracts for the derived SQLite cache maintenance module.

Defines the maintenance verdict and mode enums, the injectable clock
protocol, and the request/evidence/identity/result dataclasses used
by the inspector and operations pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# Injectable clock
# ---------------------------------------------------------------------------


@runtime_checkable
class Clock(Protocol):
    """Protocol for injectable time sources.

    Implementations must return a timezone-aware UTC datetime.
    """

    def utc_now(self) -> datetime: ...


class RealClock:
    """Production clock that returns ``datetime.now(timezone.utc)``."""

    @staticmethod
    def utc_now() -> datetime:
        return datetime.now(UTC)


# ---------------------------------------------------------------------------
# Closed enums
# ---------------------------------------------------------------------------


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
    RED_IDENTITY_FAILURE = "RED_IDENTITY_FAILURE"
    RED_SOURCE_CHANGED = "RED_SOURCE_CHANGED"
    RED_PROMOTION_FAILURE = "RED_PROMOTION_FAILURE"


class MaintenanceMode(Enum):
    """Closed set of operation modes for a maintenance request."""

    INSPECT = "inspect"
    DRY_RUN = "dry-run"
    EXECUTE_ANALYZE = "execute-analyze"
    EXECUTE_OPTIMIZE = "execute-optimize"
    EXECUTE_VACUUM = "execute-vacuum"


class MaintenanceOperation(Enum):
    """The specific maintenance operation to perform."""

    ANALYZE = "ANALYZE"
    OPTIMIZE = "OPTIMIZE"
    VACUUM = "VACUUM"


class CacheKind(Enum):
    """Approved derived cache kinds that can be maintained."""

    SOURCE_REGIME_STATS = "source_regime_stats"

    @classmethod
    def from_path(cls, db_path: Path) -> CacheKind | None:
        """Infer cache kind from the database file stem."""
        stem = db_path.stem
        for kind in cls:
            if kind.value == stem:
                return kind
        return None


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class CacheIdentity:
    """Identity evidence that a target is a valid derived SI v2 cache.

    Every field must be satisfied for an identity check to pass.
    """

    is_file: bool
    is_db_suffix: bool
    has_supported_schema: bool
    has_cache_metadata_table: bool
    has_expected_data_tables: bool
    has_canonical_metadata_row: bool
    has_source_fingerprint: bool
    cache_schema_version: str | None
    source_fingerprint: str | None
    cache_kind: CacheKind | None
    in_allowed_root: bool


@dataclass
class MaintenanceRequest:
    """Parameters for a cache maintenance request.

    Attributes:
        db_path: Path to the SQLite cache database.
        mode: Operation mode — inspect, dry-run, or execute-*.
        force: Bypass confirmation prompts (for CLI automation).
        backup_dir: Optional explicit backup directory.
        allowed_roots: Optional list of allowed root directories. If
            provided, the cache path must be within one of these roots.
        clock: Injectable time source. Defaults to ``RealClock``.
        accepted_schema_versions: Set of accepted full version strings.
            Defaults to ``{"1.1"}``.
    """

    db_path: Path
    mode: MaintenanceMode
    force: bool = False
    backup_dir: Path | None = None
    allowed_roots: list[Path] | None = None
    clock: Clock = field(default_factory=RealClock)
    accepted_schema_versions: frozenset[str] = field(
        default_factory=lambda: frozenset({"1.1"})
    )


@dataclass
class MaintenanceEvidence:
    """Collected evidence from cache inspection.

    Attributes:
        schema_version: The full cache_schema_version string from
            cache_metadata, or None.
        page_count: SQLite PRAGMA page_count.
        page_size: SQLite PRAGMA page_size.
        auto_vacuum: PRAGMA auto_vacuum setting.
        wal_mode: True if journal_mode is 'wal'.
        integrity_ok: Result of PRAGMA integrity_check.
        foreign_keys_ok: Result of PRAGMA foreign_key_check.
        quick_check_ok: Result of PRAGMA quick_check.
        source_fingerprint: The source_fingerprint from cache_metadata.
        rebuildable: True if the cache has supported schema and
            source_fingerprint.
        free_mb: Free disk space on the DB filesystem in MB.
        db_size_mb: Size of the DB file in MB.
        identity: Complete CacheIdentity check result.
    """

    schema_version: str | None
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
    identity: CacheIdentity | None = None


@dataclass
class MaintenanceResult:
    """Complete result of a maintenance inspection or operation.

    Attributes:
        request: The original MaintenanceRequest.
        verdict: The final verdict.
        evidence: Collected evidence from cache inspection.
        operation: The operation performed, or None for inspect/dry-run.
        executed_at: UTC timestamp of execution.
        operation_ok: True if the operation succeeded, False if it
            failed, None for inspect/dry-run.
        backup_path: Path to any backup created, or None.
        promoted_path: Path of the promoted (new) database file, or
            None if no promotion occurred.
        original_backup_path: Path of the renamed original database, or
            None if no promotion occurred.
        messages: Human-readable messages.
    """

    request: MaintenanceRequest
    verdict: MaintenanceVerdict
    evidence: MaintenanceEvidence
    operation: MaintenanceOperation | None
    executed_at: datetime
    operation_ok: bool | None
    backup_path: Path | None
    promoted_path: Path | None = None
    original_backup_path: Path | None = None
    messages: list[str] = field(default_factory=list)
