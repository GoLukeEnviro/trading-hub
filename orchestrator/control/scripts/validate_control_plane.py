#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Canonical status vocabularies
# ---------------------------------------------------------------------------

VALID_CONTROLLER_STATUSES = frozenset({
    "READY", "RUNNING", "BLOCKED", "IN_PROGRESS", "COMPLETED", "FAILED", "PAUSED", "COMPLETE"
})

IDLE_STATUSES = frozenset({"PAUSED", "COMPLETE"})
ACTIVE_STATUSES = frozenset({"READY", "RUNNING", "IN_PROGRESS"})

VALID_ITEM_STATUSES = frozenset({
    "READY", "BLOCKED", "IN_PROGRESS", "COMPLETED", "FAILED", "PAUSED"
})


# ---------------------------------------------------------------------------
# Schema-driven manual validation helpers
# ---------------------------------------------------------------------------

def _check_type(value: object, type_spec: str | list[str]) -> bool:
    """Check *value* against a JSON-Schema ``type`` spec."""
    if isinstance(type_spec, str):
        type_spec = [type_spec]
    for t in type_spec:
        if t == "string" and isinstance(value, str):
            return True
        if t == "integer" and isinstance(value, int) and not isinstance(value, bool):
            return True
        if t == "number" and isinstance(value, (int, float)) and not isinstance(value, bool):
            return True
        if t == "boolean" and isinstance(value, bool):
            return True
        if t == "array" and isinstance(value, list):
            return True
        if t == "object" and isinstance(value, dict):
            return True
        if t == "null" and value is None:
            return True
    return False


def _validate_against_schema(data: dict, schema: dict, path: str = "") -> list[str]:
    """Minimal JSON-Schema draft-07 validator. Returns list of error strings."""
    errors: list[str] = []

    # type
    if "type" in schema:
        type_spec = schema["type"]
        if not _check_type(data, type_spec):
            errors.append(f"{path or '/'}: expected type {type_spec}, got {type(data).__name__}")
            return errors  # type mismatch => skip further checks

    # const
    if "const" in schema and data != schema["const"]:
        errors.append(f"{path or '/'}: expected const {schema['const']!r}, got {data!r}")

    # enum
    if "enum" in schema and data not in schema["enum"]:
        errors.append(f"{path or '/'}: value {data!r} not in enum {schema['enum']}")

    # minLength (strings only)
    if "minLength" in schema and isinstance(data, str) and len(data) < schema["minLength"]:
        errors.append(f"{path or '/'}: string length {len(data)} < minLength {schema['minLength']}")

    # minimum
    if "minimum" in schema and isinstance(data, (int, float)) and data < schema["minimum"]:
        errors.append(f"{path or '/'}: value {data} < minimum {schema['minimum']}")

    # pattern
    if "pattern" in schema and isinstance(data, str):
        if not re.search(schema["pattern"], data):
            errors.append(f"{path or '/'}: string {data!r} does not match pattern {schema['pattern']!r}")

    # minItems (arrays)
    if "minItems" in schema and isinstance(data, list) and len(data) < schema["minItems"]:
        errors.append(f"{path or '/'}: array length {len(data)} < minItems {schema['minItems']}")

    # For objects: check required, properties, additionalProperties
    if isinstance(data, dict):
        required = schema.get("required", [])
        for field in required:
            if field not in data:
                errors.append(f"{path}.{field}: required field missing")

        props = schema.get("properties", {})
        for key, value in data.items():
            if key in props:
                sub_path = f"{path}.{key}" if path else key
                errors.extend(_validate_against_schema(value, props[key], sub_path))
            elif "additionalProperties" in schema and schema["additionalProperties"] is False:
                if key not in props:
                    errors.append(f"{path}.{key}: additional property not allowed")

    # For arrays: validate items
    if isinstance(data, list) and "items" in schema:
        for i, item in enumerate(data):
            sub_path = f"{path}[{i}]"
            errors.extend(_validate_against_schema(item, schema["items"], sub_path))

    return errors


# ---------------------------------------------------------------------------
# Cross-field invariants
# ---------------------------------------------------------------------------

def _check_cross_field_invariants(state: dict, queue: dict) -> list[str]:
    """Validate idle/active mode consistency. Returns list of error strings."""
    errors: list[str] = []
    status = state.get("controller_status")
    current_epic = state.get("current_epic")
    active_work_item_id = state.get("active_work_item_id")
    items = queue.get("items", [])

    if status in IDLE_STATUSES:
        # IDLE mode: must not have active epic
        if current_epic is not None:
            errors.append(
                f"IDLE state ({status}) must not have current_epic set, "
                f"got {current_epic!r}"
            )
        # PAUSED with active work item is inconsistent
        if status == "PAUSED" and active_work_item_id is not None:
            errors.append(
                f"PAUSED state must not have active_work_item_id set, "
                f"got {active_work_item_id!r}"
            )

    elif status in ACTIVE_STATUSES:
        # ACTIVE mode: must have current_epic
        if not isinstance(current_epic, str) or not current_epic:
            errors.append(
                f"ACTIVE state ({status}) requires current_epic to be a non-empty string, "
                f"got {current_epic!r}"
            )
        # ACTIVE mode: must have non-empty queue
        if not items:
            errors.append(
                f"ACTIVE state ({status}) requires at least one queue item, "
                f"but queue.items is empty"
            )
        # ACTIVE mode: queue epic_id/branch/worktree must be non-null
        for field in ("epic_id", "branch", "worktree"):
            val = queue.get(field)
            if val is None:
                errors.append(
                    f"ACTIVE state ({status}) requires queue.{field} to be non-null"
                )
    # BLOCKED, FAILED are neutral — no strict idle/active constraint

    return errors


# ---------------------------------------------------------------------------
# Dependency completion check
# ---------------------------------------------------------------------------

def _check_dependencies(items: list[dict]) -> list[str]:
    """Verify that READY items have all dependencies COMPLETED."""
    errors: list[str] = []
    item_ids: set[str] = set()
    statuses: dict[str, str] = {}

    for item in items:
        item_id = item.get("id")
        if not isinstance(item_id, str) or not item_id:
            continue
        if item_id in item_ids:
            errors.append(f"Duplicate queue item id: {item_id}")
        item_ids.add(item_id)
        statuses[item_id] = item.get("status", "")

    for item in items:
        item_id = item.get("id", "")
        status = item.get("status", "")
        if status != "READY":
            continue
        dependencies = item.get("depends_on", [])
        if not isinstance(dependencies, list):
            continue
        unknown = sorted(set(dependencies) - item_ids)
        if unknown:
            errors.append(f"{item_id} has unknown dependencies: {unknown}")
        incomplete = [
            dep for dep in dependencies
            if dep in statuses and statuses[dep] != "COMPLETED"
        ]
        if incomplete:
            errors.append(
                f"{item_id} is READY but dependencies not COMPLETED: {incomplete}"
            )

    return errors


# ---------------------------------------------------------------------------
# Top-level validation
# ---------------------------------------------------------------------------

def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def validate(*, config_root: Path, state_root: Path) -> None:
    """Run full control-plane validation. Raises ValueError on any failure."""
    all_errors: list[str] = []

    # --- Load schemas ---
    state_schema_path = config_root / "schemas" / "state.schema.json"
    queue_schema_path = config_root / "schemas" / "queue.schema.json"

    if not state_schema_path.exists():
        raise FileNotFoundError(f"State schema not found: {state_schema_path}")
    if not queue_schema_path.exists():
        raise FileNotFoundError(f"Queue schema not found: {queue_schema_path}")

    state_schema = load_json(state_schema_path)
    queue_schema = load_json(queue_schema_path)

    # --- Load data ---
    state_path = state_root / "STATE.json"
    queue_path = state_root / "QUEUE.json"

    if not state_path.exists():
        raise FileNotFoundError(f"STATE.json not found: {state_path}")
    if not queue_path.exists():
        raise FileNotFoundError(f"QUEUE.json not found: {queue_path}")

    state = load_json(state_path)
    queue = load_json(queue_path)

    # --- Schema validation ---
    state_errors = _validate_against_schema(state, state_schema, "STATE")
    all_errors.extend(state_errors)

    queue_errors = _validate_against_schema(queue, queue_schema, "QUEUE")
    all_errors.extend(queue_errors)

    # Only proceed to cross-field and dependency checks if schema is valid
    if not state_errors and not queue_errors:
        # --- Cross-field invariants ---
        cross_errors = _check_cross_field_invariants(state, queue)
        all_errors.extend(cross_errors)

        # --- Dependency checks (only if items exist) ---
        items = queue.get("items", [])
        if items:
            dep_errors = _check_dependencies(items)
            all_errors.extend(dep_errors)

    # --- Report ---
    if all_errors:
        error_lines = "\n  ".join(all_errors)
        raise ValueError(f"Control-plane validation failed ({len(all_errors)} error(s)):\n  {error_lines}")

    # Summarise result
    status = state.get("controller_status", "UNKNOWN")
    n_items = len(queue.get("items", []))
    if status in IDLE_STATUSES:
        print(f"Control-plane validation passed (IDLE mode, status={status})")
    elif status in ACTIVE_STATUSES:
        print(f"Control-plane validation passed (ACTIVE mode, status={status}, {n_items} queue item(s))")
    else:
        print(f"Control-plane validation passed (status={status})")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate SI v2 controller state and queue against schemas."
    )
    parser.add_argument(
        "--config-root",
        type=Path,
        default=None,
        help="Path to repo orchestrator/control/ (schemas, scripts, prompts).",
    )
    parser.add_argument(
        "--state-root",
        type=Path,
        default=None,
        help="Path to mutable runtime state dir (STATE.json, QUEUE.json).",
    )
    parser.add_argument(
        "--control-root",
        type=Path,
        default=None,
        help="Legacy: sets both --config-root and --state-root to the same path.",
    )
    args = parser.parse_args()

    if args.control_root:
        config_root = args.control_root
        state_root = args.control_root
    elif args.config_root and args.state_root:
        config_root = args.config_root
        state_root = args.state_root
    elif args.config_root:
        config_root = args.config_root
        state_root = args.config_root
    else:
        parser.error("Provide --control-root or --config-root (and optionally --state-root).")

    try:
        validate(config_root=config_root, state_root=state_root)
    except (ValueError, FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
