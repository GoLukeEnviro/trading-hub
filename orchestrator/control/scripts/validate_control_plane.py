#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

VALID_ITEM_STATUSES = {"READY", "BLOCKED", "IN_PROGRESS", "COMPLETED", "FAILED", "PAUSED"}

def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value

def validate(control_root: Path) -> None:
    state = load_json(control_root / "STATE.json")
    queue = load_json(control_root / "QUEUE.json")
    required_state = {"schema_version", "project", "controller_status", "operation_level", "runtime_policy", "merge_policy", "current_epic", "canonical_main_commit", "updated_at"}
    missing_state = sorted(required_state - state.keys())
    if missing_state:
        raise ValueError(f"STATE.json missing fields: {missing_state}")
    if state["runtime_policy"] != "FORBIDDEN":
        raise ValueError("runtime_policy must remain FORBIDDEN")
    if state["merge_policy"] != "HUMAN_ONLY":
        raise ValueError("merge_policy must remain HUMAN_ONLY")
    items = queue.get("items")
    if not isinstance(items, list):
        raise ValueError("QUEUE.json items must be a list")
    if not items:
        print("Queue is empty; no items to validate")
        return
    ids: set[str] = set()
    statuses: dict[str, str] = {}
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Every queue item must be an object")
        item_id = item.get("id")
        status = item.get("status")
        if not isinstance(item_id, str) or not item_id:
            raise ValueError("Every queue item requires a non-empty string id")
        if item_id in ids:
            raise ValueError(f"Duplicate queue item id: {item_id}")
        if status not in VALID_ITEM_STATUSES:
            raise ValueError(f"Invalid status for {item_id}: {status}")
        ids.add(item_id)
        statuses[item_id] = status
    for item in items:
        item_id = item["id"]
        dependencies = item.get("depends_on", [])
        if not isinstance(dependencies, list):
            raise ValueError(f"{item_id}.depends_on must be a list")
        unknown = sorted(set(dependencies) - ids)
        if unknown:
            raise ValueError(f"{item_id} has unknown dependencies: {unknown}")
        if item["status"] == "READY":
            incomplete = [dep for dep in dependencies if statuses[dep] != "DONE"]
            if incomplete:
                raise ValueError(f"{item_id} is READY but dependencies are not DONE: {incomplete}")
    print("Control-plane validation passed")

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--control-root", type=Path, required=True)
    args = parser.parse_args()
    validate(args.control_root)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
