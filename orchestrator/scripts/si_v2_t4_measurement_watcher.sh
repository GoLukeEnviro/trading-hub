#!/usr/bin/env bash
#
# SI-v2 T4 Measurement Watcher — read-only scaffold
#
# Exit codes:
#   0  = STILL_WAITING
#   10 = MEASUREMENT_READY
#   20 = SAFETY_BLOCKED
#   30 = DATA_UNAVAILABLE
#   40 = SCRIPT_ERROR
#
# This watcher is detection-only. It MUST NOT execute the Measurement
# Decision Engine, apply a candidate, restart containers, or mutate runtime
# state. It inspects existing configs / SQLite DBs / state files read-only.

set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
DEFAULT_REPO_ROOT="$(git -C "${SCRIPT_DIR}/../.." rev-parse --show-toplevel 2>/dev/null || true)"
REPO_ROOT="${SI_V2_REPO_ROOT:-${DEFAULT_REPO_ROOT}}"

if [ -z "${REPO_ROOT}" ] || [ ! -d "${REPO_ROOT}" ]; then
  echo "SI_V2_T4_STATUS=SCRIPT_ERROR"
  echo "ERROR=repo_root_not_found"
  exit 40
fi

export SI_V2_REPO_ROOT="${REPO_ROOT}"

python3 - <<'PY'
from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

EXIT_STILL_WAITING = 0
EXIT_MEASUREMENT_READY = 10
EXIT_SAFETY_BLOCKED = 20
EXIT_DATA_UNAVAILABLE = 30
EXIT_SCRIPT_ERROR = 40

REPO_ROOT = Path(Path.cwd().anchor)  # placeholder overwritten below
REPO_ROOT = Path(__import__("os").environ["SI_V2_REPO_ROOT"]).resolve()

CONFIGS = {
    "control": REPO_ROOT / "freqforge/user_data/config.json",
    "canary": REPO_ROOT / "freqforge-canary/user_data/config.json",
    "regime_hybrid": REPO_ROOT / "freqtrade/bots/regime-hybrid/user_data/config.json",
    "freqai_rebel": REPO_ROOT / "freqtrade/bots/freqai-rebel/user_data/config.json",
}

PACK_PATH = REPO_ROOT / "self_improvement_v2/src/si_v2/measurement/final_decision_pack.py"
KILL_SWITCH_PRIMARY = REPO_ROOT / "self_improvement_v2/state/kill_switch.json"
KILL_SWITCH_GLOB_ROOT = REPO_ROOT / "self_improvement_v2/state"


def emit(**pairs: object) -> None:
    for key, value in pairs.items():
        print(f"{key}={value}")


def parse_scheduled_t3_utc() -> str:
    override = __import__("os").environ.get("SI_V2_T3_UTC")
    if override:
        return override
    if not PACK_PATH.exists():
        raise FileNotFoundError(f"missing_t3_source:{PACK_PATH}")
    text = PACK_PATH.read_text(encoding="utf-8")
    match = re.search(r'SCHEDULED_T3_UTC:\s*str\s*=\s*"([^"]+)"', text)
    if not match:
        raise ValueError("scheduled_t3_utc_not_found")
    return match.group(1)


def utc_to_db_timestamp(ts: str) -> str:
    return ts.replace("T", " ").removesuffix("Z")


def load_config(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"missing_config:{path}")
    return json.loads(path.read_text(encoding="utf-8"))


def db_path_from_url(config_path: Path, db_url: str | None) -> Path:
    if not db_url:
        raise ValueError(f"missing_db_url:{config_path}")
    prefix = "sqlite:////freqtrade/user_data/"
    if db_url.startswith(prefix):
        return (config_path.parent / db_url.removeprefix(prefix)).resolve()
    if db_url.startswith("sqlite:///"):
        return Path(db_url.removeprefix("sqlite:///"))
    raise ValueError(f"unsupported_db_url:{db_url}")


def query_count(db_path: Path, sql: str, params: tuple[object, ...]) -> int:
    if not db_path.exists():
        raise FileNotFoundError(f"missing_db:{db_path}")
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        row = conn.execute(sql, params).fetchone()
        return int(row[0] or 0)
    finally:
        conn.close()


def load_kill_switch_status() -> str:
    candidates: list[Path] = []
    if KILL_SWITCH_PRIMARY.exists():
        candidates.append(KILL_SWITCH_PRIMARY)
    if KILL_SWITCH_GLOB_ROOT.exists():
        candidates.extend(sorted(KILL_SWITCH_GLOB_ROOT.rglob("kill_switch*.json")))
    seen: set[Path] = set()
    ordered_candidates: list[Path] = []
    for path in candidates:
        if path not in seen:
            ordered_candidates.append(path)
            seen.add(path)
    if not ordered_candidates:
        return "NORMAL"
    for path in ordered_candidates:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            for key in ("status", "state", "mode", "kill_switch_status"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip().upper()
    return "UNKNOWN"


try:
    scheduled_t3_utc = parse_scheduled_t3_utc()
    db_t3 = utc_to_db_timestamp(scheduled_t3_utc)

    loaded_configs = {name: load_config(path) for name, path in CONFIGS.items()}
    dry_run_by_bot = {
        name: loaded_configs[name].get("dry_run") for name in loaded_configs
    }
    if any(value is not True for value in dry_run_by_bot.values()):
        emit(
            SI_V2_T4_STATUS="SAFETY_BLOCKED",
            T3_REFERENCE_UTC=scheduled_t3_utc,
            DRY_RUN_ALL_TRUE=False,
            DRY_RUN_BY_BOT=json.dumps(dry_run_by_bot, sort_keys=True),
            KILL_SWITCH_STATUS="SKIPPED_DUE_TO_DRY_RUN_BLOCK",
            MEASUREMENT_DECISION_ENGINE_ALLOWED=False,
            NEXT_STEP="investigate_safety_gate",
        )
        raise SystemExit(EXIT_SAFETY_BLOCKED)

    kill_switch_status = load_kill_switch_status()
    kill_switch_normal = kill_switch_status == "NORMAL"
    if not kill_switch_normal:
        emit(
            SI_V2_T4_STATUS="SAFETY_BLOCKED",
            T3_REFERENCE_UTC=scheduled_t3_utc,
            DRY_RUN_ALL_TRUE=True,
            DRY_RUN_BY_BOT=json.dumps(dry_run_by_bot, sort_keys=True),
            KILL_SWITCH_STATUS=kill_switch_status,
            MEASUREMENT_DECISION_ENGINE_ALLOWED=False,
            NEXT_STEP="investigate_safety_gate",
        )
        raise SystemExit(EXIT_SAFETY_BLOCKED)

    canary_db = db_path_from_url(CONFIGS["canary"], loaded_configs["canary"].get("db_url"))
    control_db = db_path_from_url(CONFIGS["control"], loaded_configs["control"].get("db_url"))

    canary_closed_since_t3 = query_count(
        canary_db,
        "SELECT COUNT(*) FROM trades WHERE is_open=0 AND close_date > ?",
        (db_t3,),
    )
    control_closed_since_t3 = query_count(
        control_db,
        "SELECT COUNT(*) FROM trades WHERE is_open=0 AND close_date > ?",
        (db_t3,),
    )
    canary_open_trades = query_count(
        canary_db,
        "SELECT COUNT(*) FROM trades WHERE is_open=1",
        (),
    )

    base_payload = dict(
        T3_REFERENCE_UTC=scheduled_t3_utc,
        CANARY_CLOSED_SINCE_T3=canary_closed_since_t3,
        CONTROL_CLOSED_SINCE_T3=control_closed_since_t3,
        CANARY_OPEN_TRADES=canary_open_trades,
        DRY_RUN_ALL_TRUE=True,
        DRY_RUN_BY_BOT=json.dumps(dry_run_by_bot, sort_keys=True),
        KILL_SWITCH_STATUS=kill_switch_status,
        CANARY_DB_PATH_REL=canary_db.relative_to(REPO_ROOT),
        CONTROL_DB_PATH_REL=control_db.relative_to(REPO_ROOT),
    )

    if canary_closed_since_t3 >= 1 and control_closed_since_t3 >= 1:
        emit(
            SI_V2_T4_STATUS="MEASUREMENT_READY",
            MEASUREMENT_DECISION_ENGINE_ALLOWED=True,
            NEXT_STEP="run_measurement_decision_engine_read_only",
            **base_payload,
        )
        raise SystemExit(EXIT_MEASUREMENT_READY)

    emit(
        SI_V2_T4_STATUS="STILL_WAITING",
        MEASUREMENT_DECISION_ENGINE_ALLOWED=False,
        NEXT_STEP="wait_for_canary_close",
        **base_payload,
    )
    raise SystemExit(EXIT_STILL_WAITING)
except SystemExit as exc:
    raise
except (FileNotFoundError, ValueError, json.JSONDecodeError, sqlite3.Error) as exc:
    emit(
        SI_V2_T4_STATUS="DATA_UNAVAILABLE",
        ERROR=str(exc),
        MEASUREMENT_DECISION_ENGINE_ALLOWED=False,
        NEXT_STEP="restore_runtime_data_access",
    )
    raise SystemExit(EXIT_DATA_UNAVAILABLE)
except Exception as exc:  # pragma: no cover - fail closed
    emit(
        SI_V2_T4_STATUS="SCRIPT_ERROR",
        ERROR=f"{type(exc).__name__}:{exc}",
    )
    raise SystemExit(EXIT_SCRIPT_ERROR)
PY
