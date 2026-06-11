"""source_regime_stats — derived SQLite cache for attribution metrics.

Provides full rebuild, incremental update, CLI, and SQLite schema management.
"""

from __future__ import annotations

from .cli import build_parser, main
from .db import create_schema, integrity_check, open_db
from .rebuild import FullRebuilder
from .update import IncrementalUpdater

__all__ = [
    "FullRebuilder",
    "IncrementalUpdater",
    "build_parser",
    "create_schema",
    "integrity_check",
    "main",
    "open_db",
]
