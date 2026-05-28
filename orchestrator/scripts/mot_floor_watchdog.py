#!/usr/bin/env python3
"""Simple max_open_trades floor watchdog.

Checks every 10 minutes:
- FreqForge >= 5
- Canary >= 3
- Regime-Hybrid >= 5
- Rebel stays at 0

Single-writer rule: this script never writes config files directly.
All max_open_trades changes flow through system_optimizer.restore_bot_limit(),
which owns the config write path.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from system_optimizer import (
    BASELINE_MAX_OPEN_TRADES,
    FLEET_BOTS,
    PERMANENT_QUARANTINE_FILE,
    read_bot_config,
    restore_bot_limit,
    _normalized_quarantine_key,
)

BASE = "/home/hermes/projects/trading"
STATE_DIR = os.path.join(BASE, "orchestrator/state")
MANUAL_LOCK_FILE = os.path.join(STATE_DIR, "manual_max_open_trades_locks.json")
TARGETS = {
    "FreqForge": 5,
    "Canary": 3,
    "Regime-Hybrid": 5,
    "Rebel": 0,
}


def _load_json(path: str, default):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def _manual_lock_active(label: str) -> bool:
    data = _load_json(MANUAL_LOCK_FILE, {})
    norm = _normalized_quarantine_key(label)
    for key, value in data.items():
        if _normalized_quarantine_key(str(key)) != norm:
            continue
        if isinstance(value, dict):
            return bool(value.get("locked") or value.get("manual_lock") or value.get("enabled"))
        return bool(value)
    return False


def _permanent_lock_active(label: str) -> bool:
    data = _load_json(PERMANENT_QUARANTINE_FILE, {})
    norm = _normalized_quarantine_key(label)
    for key, value in data.items():
        if _normalized_quarantine_key(str(key)) != norm:
            continue
        return isinstance(value, dict) and value.get("quarantine_type") == "permanent"
    return False


def main() -> int:
    restored = []
    skipped = []
    clean = []

    for container, info in FLEET_BOTS.items():
        label = info["label"]
        if label not in TARGETS:
            continue
        target = TARGETS[label]
        cfg = read_bot_config(container, info)
        if cfg is None:
            skipped.append(f"{label}: config unreadable")
            continue
        current = cfg.get("max_open_trades")

        if current is None:
            skipped.append(f"{label}: max_open_trades missing")
            continue
        if current >= target:
            clean.append(f"{label}={current}")
            continue
        if _manual_lock_active(label):
            skipped.append(f"{label}: manual lock active ({current}<{target})")
            continue
        if _permanent_lock_active(label):
            skipped.append(f"{label}: permanent lock active ({current}<{target})")
            continue

        reason = f"floor-watchdog restore ({current}->{target})"
        if restore_bot_limit(container, info, target, reason):
            restored.append(f"{label}:{current}->{target}")
        else:
            skipped.append(f"{label}: restore failed ({current}->{target})")

    if restored:
        print("RESTORED " + ", ".join(restored))
    elif skipped:
        print("NOOP " + " | ".join(skipped))
    else:
        print("OK " + ", ".join(clean))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
