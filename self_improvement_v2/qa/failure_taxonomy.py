"""Failure Taxonomy Loader.

Provides typed access to the failure taxonomy JSON for quality gate
and episode integrations.
"""

from __future__ import annotations

import json
from pathlib import Path


def load_taxonomy(
    path: Path | None = None,
) -> dict[str, object]:
    """Load the failure taxonomy JSON.

    Returns the full taxonomy dict with keys: schema_version, taxonomy, severity_definitions.
    """
    p = path or Path("self_improvement_v2/qa/failure_taxonomy.json")
    with open(p) as f:
        return dict(json.load(f))


def lookup_failure(
    taxonomy_id: str,
    taxonomy: dict[str, object] | None = None,
) -> dict[str, object] | None:
    """Look up a failure by its ID (e.g. 'JSON-001').

    Returns the entry dict or None if not found.
    """
    if taxonomy is None:
        taxonomy = load_taxonomy()
    entries = taxonomy.get("taxonomy", [])
    if not isinstance(entries, list):
        return None
    for entry in entries:
        if isinstance(entry, dict) and entry.get("id") == taxonomy_id:
            return entry
    return None


def failures_by_area(
    area: str,
    taxonomy: dict[str, object] | None = None,
) -> list[dict[str, object]]:
    """Get all failures for a given area (e.g. 'Rainbow', 'Evidence')."""
    if taxonomy is None:
        taxonomy = load_taxonomy()
    entries = taxonomy.get("taxonomy", [])
    if not isinstance(entries, list):
        return []
    return [
        entry
        for entry in entries
        if isinstance(entry, dict) and str(entry.get("area", "")).lower() == area.lower()
    ]


def failure_ids(
    taxonomy: dict[str, object] | None = None,
) -> list[str]:
    """Get all failure IDs as a list."""
    if taxonomy is None:
        taxonomy = load_taxonomy()
    entries = taxonomy.get("taxonomy", [])
    if not isinstance(entries, list):
        return []
    return [
        str(e["id"])
        for e in entries
        if isinstance(e, dict) and "id" in e
    ]
