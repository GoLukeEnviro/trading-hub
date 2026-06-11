"""derived SQLite cache maintenance module for the trading-hub SI v2 system.

Provides manual, fail-closed maintenance commands for rebuildable derived
SQLite caches plus an inactive approval-gated job plan.
"""

from __future__ import annotations

from . import cli, models
from .inspector import CacheInspector, inspect_cache, is_safe_cache_path, validate_cache_identity
from .operations import MaintenanceRunner, execute_analyze, execute_optimize, execute_vacuum

__all__ = [
    "CacheInspector",
    "MaintenanceRunner",
    "cli",
    "execute_analyze",
    "execute_optimize",
    "execute_vacuum",
    "inspect_cache",
    "is_safe_cache_path",
    "models",
    "validate_cache_identity",
]
