from __future__ import annotations

import glob
import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

REPO_ROOT = Path("/home/hermes/projects/trading")
ORCHESTRATOR_ROOT = Path("/opt/data/profiles/orchestrator")
SCRIPT_DIR = REPO_ROOT / "orchestrator" / "scripts"
STATE_DIR = ORCHESTRATOR_ROOT / "state"
REPORTS_DIR = ORCHESTRATOR_ROOT / "reports"
LOG_DIR = ORCHESTRATOR_ROOT / "logs"
LOCK_DIR = STATE_DIR / "locks"
EXPECTED_STATE_PATH = ORCHESTRATOR_ROOT / "config" / "expected_state.json"
CRON_REGISTRY_PATH = ORCHESTRATOR_ROOT / "cron" / "jobs.json"
OBSERVATION_STATE_PATH = STATE_DIR / "observation_state.json"
OBSERVATION_LOG_PATH = LOG_DIR / "observation.log"
DEFAULT_SIGNAL_PATTERN = str(STATE_DIR / "signals" / "last_signal_*.json")
LOCK_METADATA_FILENAME = "lock.json"

DEFAULT_EXPECTED_CONTAINERS = [
    "hermes-green",
    "trading-guardian",
    "trading-freqtrade-regime-hybrid-1",
    "trading-freqtrade-freqforge-canary-1",
    "trading-freqtrade-freqforge-1",
    "trading-freqtrade-webserver-1",
    "trading-ai-hedge-fund-1",
    "trading-freqai-rebel-1",
]

DEFAULT_EXPECTED_CRONJOBS = [
    {
        "name": "portfolio-rebalancer",
        "command": "portfolio_rebalancer.py",
        "schedule": "0 6 * * 1",
        "owner": "hermes",
    },
    {
        "name": "autonomous-health-loop",
        "command": "autonomous-health-loop",
        "schedule": "every 60m",
        "owner": "hermes",
    },
    {
        "name": "trading-hub-deep-dive-validation",
        "command": "trading-hub-deep-dive-validation",
        "schedule": "0 9 * * *",
        "owner": "hermes",
    },
    {
        "name": "trading-pipeline",
        "command": "trading_pipeline.py",
        "schedule": "*/10 * * * *",
        "owner": "hermes",
    },
    {
        "name": "container-watchdog",
        "command": "container_watchdog.sh",
        "schedule": "*/30 * * * *",
        "owner": "hermes",
    },
    {
        "name": "critical-event-watchdog",
        "command": "critical_event_watchdog.py",
        "schedule": "*/10 * * * *",
        "owner": "hermes",
    },
]

_DURATION_PATTERN = re.compile(
    r"(?P<value>\d+)\s+(?P<unit>days?|hours?|minutes?|seconds?)",
    re.IGNORECASE,
)

_CONTAINER_HEALTH_PATTERN = re.compile(r"\((healthy|unhealthy|starting)\)", re.IGNORECASE)


def _coerce_path(path: Path | str) -> Path:
    return path if isinstance(path, Path) else Path(path)


def default_expected_state() -> dict[str, Any]:
    return {
        "comment": "⚠️ AUTO-GENERATED DEFAULT — Bitte manuell prüfen und anpassen! Diese Datei ist nur ein Startpunkt.",
        "generated_at": None,
        "generated_by": "hermes-trading-reliability-observation-agent-phase1-bootstrap",
        "needs_manual_review": True,
        "expected_containers": list(DEFAULT_EXPECTED_CONTAINERS),
        "expected_cronjobs": [dict(job) for job in DEFAULT_EXPECTED_CRONJOBS],
        "signal_pipeline_config": {
            "signal_file_pattern": str(STATE_DIR / "signals" / "last_signal_*.json"),
            "expected_max_age_seconds": 600,
        },
        "health_score_weights": {
            "unhealthy_container_penalty": 30,
            "exited_container_penalty": 40,
            "failed_cronjob_penalty": 20,
            "stale_signal_penalty": 30,
        },
    }


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def read_json(path: Path | str) -> Any:
    path = _coerce_path(path)
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json_atomic(path: Path | str, payload: Any) -> Path:
    path = _coerce_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(tmp_name, path)
        return path
    finally:
        if os.path.exists(tmp_name):
            try:
                os.unlink(tmp_name)
            except FileNotFoundError:
                pass


def append_log_line(path: Path | str, line: str) -> Path:
    path = _coerce_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line.rstrip("\n") + "\n")
    return path


def acquire_lock(lock_dir: Path | str, pid: int, timestamp: str) -> bool:
    lock_dir = _coerce_path(lock_dir)
    try:
        lock_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        return False

    metadata = {
        "pid": pid,
        "timestamp": timestamp,
    }
    write_json_atomic(lock_dir / LOCK_METADATA_FILENAME, metadata)
    return True


def release_lock(lock_dir: Path | str) -> None:
    lock_dir = _coerce_path(lock_dir)
    if not lock_dir.exists():
        return
    shutil.rmtree(lock_dir, ignore_errors=True)


def parse_duration_from_status(status_text: str) -> int | None:
    if not status_text:
        return None

    lowered = status_text.lower()
    if "less than a second" in lowered:
        return 0

    matches = _DURATION_PATTERN.findall(status_text)
    if not matches:
        return None

    total_seconds = 0
    for value, unit in matches:
        amount = int(value)
        unit = unit.lower()
        if unit.startswith("day"):
            total_seconds += amount * 24 * 60 * 60
        elif unit.startswith("hour"):
            total_seconds += amount * 60 * 60
        elif unit.startswith("minute"):
            total_seconds += amount * 60
        else:
            total_seconds += amount
    return total_seconds


def parse_docker_ps_line(name: str, status: str, health: str | None = None) -> dict[str, Any]:
    status_text = (status or "").strip()
    health_text = (health or "").strip().lower() if health else ""

    if not health_text:
        health_match = _CONTAINER_HEALTH_PATTERN.search(status_text)
        if health_match:
            health_text = health_match.group(1).lower()
        elif "unhealthy" in status_text.lower():
            health_text = "unhealthy"
        elif "healthy" in status_text.lower():
            health_text = "healthy"
        elif "starting" in status_text.lower():
            health_text = "starting"
        else:
            health_text = "none"

    lower = status_text.lower()
    if lower.startswith("up"):
        state = "up"
    elif lower.startswith("exited"):
        state = "exited"
    elif lower.startswith("restarting"):
        state = "restarting"
    else:
        state = "unknown"

    return {
        "name": name,
        "status": status_text,
        "health": health_text or "none",
        "state": state,
        "duration_seconds": parse_duration_from_status(status_text),
    }


def load_expected_state(path: Path | str = EXPECTED_STATE_PATH, allow_missing: bool = False) -> dict[str, Any]:
    path = _coerce_path(path)
    if not path.exists():
        if allow_missing:
            return default_expected_state()
        raise FileNotFoundError(path)

    try:
        payload = read_json(path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        if allow_missing:
            return default_expected_state()
        raise

    if not isinstance(payload, dict):
        raise ValueError(f"expected_state must be a JSON object, got {type(payload).__name__}")
    return payload


def load_cron_registry(path: Path | str = CRON_REGISTRY_PATH) -> dict[str, Any]:
    payload = read_json(path)
    if not isinstance(payload, dict):
        raise ValueError(f"cron registry must be a JSON object, got {type(payload).__name__}")
    return payload


def _parse_cron_lines(source: str, text: str, entries: list[dict[str, str]]) -> None:
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        entries.append({"source": source, "line": line})


def load_cron_fallback(
    crontab_text: str | None = None,
    system_cron_texts: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    entries: list[dict[str, str]] = []

    if crontab_text is None:
        crontab_bin = shutil.which("crontab")
        if crontab_bin:
            completed = subprocess.run(
                [crontab_bin, "-l"],
                capture_output=True,
                text=True,
                check=False,
            )
            if completed.returncode == 0:
                crontab_text = completed.stdout
            else:
                crontab_text = ""
        else:
            crontab_text = ""

    if crontab_text:
        _parse_cron_lines("crontab", crontab_text, entries)

    if system_cron_texts is None:
        system_cron_texts = {}
        for path in [Path("/etc/crontab")]:
            if path.is_file() and os.access(path, os.R_OK):
                try:
                    system_cron_texts[str(path)] = path.read_text(encoding="utf-8")
                except OSError:
                    continue
        cron_d = Path("/etc/cron.d")
        if cron_d.is_dir():
            for path in sorted(cron_d.iterdir()):
                if path.is_file() and os.access(path, os.R_OK):
                    try:
                        system_cron_texts[str(path)] = path.read_text(encoding="utf-8")
                    except OSError:
                        continue

    for source, text in system_cron_texts.items():
        _parse_cron_lines(source, text, entries)

    return {"source": "fallback", "entries": entries}


def _normalize_container_row(row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        name = row.get("name") or row.get("Names") or row.get("container")
        status = row.get("status") or row.get("Status") or ""
        health = row.get("health") or row.get("Health")
        return parse_docker_ps_line(str(name), str(status), None if health is None else str(health))
    if isinstance(row, (tuple, list)) and len(row) >= 2:
        name = str(row[0])
        status = str(row[1])
        health = str(row[2]) if len(row) >= 3 and row[2] is not None else None
        return parse_docker_ps_line(name, status, health)
    raise TypeError(f"Unsupported docker row type: {type(row).__name__}")


def evaluate_container_health(
    expected_containers: Sequence[str],
    docker_ps_rows: Iterable[Any],
) -> dict[str, Any]:
    rows_by_name: dict[str, dict[str, Any]] = {}
    for row in docker_ps_rows:
        normalized = _normalize_container_row(row)
        rows_by_name[normalized["name"]] = normalized

    container_details: list[dict[str, Any]] = []
    missing_containers: list[str] = []
    unhealthy_count = 0
    exited_count = 0

    for expected_name in expected_containers:
        row = rows_by_name.get(expected_name)
        if row is None:
            missing_containers.append(expected_name)
            unhealthy_count += 1
            container_details.append(
                {
                    "name": expected_name,
                    "status": "missing",
                    "health": "missing",
                    "state": "exited_or_missing",
                    "duration_seconds": None,
                }
            )
            continue

        container_details.append(row)
        state = row["state"]
        health = row["health"]
        if state in {"exited", "restarting"} or health in {"unhealthy", "starting"}:
            unhealthy_count += 1
        if state == "exited":
            exited_count += 1

    container_score = max(0, 100 - (unhealthy_count * 30) - (exited_count * 40))

    return {
        "containers": container_details,
        "missing_containers": missing_containers,
        "missing_count": len(missing_containers),
        "unhealthy_count": unhealthy_count,
        "exited_count": exited_count,
        "container_score": container_score,
    }


def resolve_signal_candidates(pattern: str) -> list[str]:
    return sorted(glob.glob(pattern))


def latest_mtime(paths: Sequence[str | Path]) -> str | None:
    resolved: list[Path] = []
    for path in paths:
        candidate = _coerce_path(path)
        if candidate.exists():
            resolved.append(candidate)
    if not resolved:
        return None
    return str(max(resolved, key=lambda p: p.stat().st_mtime))


def evaluate_signal_freshness(
    signal_pattern: str,
    max_age_seconds: int,
    reference_time: datetime | None = None,
) -> dict[str, Any]:
    candidates = resolve_signal_candidates(signal_pattern)
    if not candidates:
        return {
            "matches": [],
            "latest_path": None,
            "latest_mtime": None,
            "age_seconds": None,
            "stale": True,
        }

    latest_path = latest_mtime(candidates)
    if latest_path is None:
        return {
            "matches": candidates,
            "latest_path": None,
            "latest_mtime": None,
            "age_seconds": None,
            "stale": True,
        }

    latest_stat = Path(latest_path).stat().st_mtime
    ref = reference_time or utcnow()
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    else:
        ref = ref.astimezone(timezone.utc)
    latest_dt = datetime.fromtimestamp(latest_stat, tz=timezone.utc)
    age_seconds = int((ref - latest_dt).total_seconds())

    return {
        "matches": candidates,
        "latest_path": latest_path,
        "latest_mtime": latest_stat,
        "age_seconds": age_seconds,
        "stale": age_seconds > max_age_seconds,
    }


def load_previous_state(path: Path | str = OBSERVATION_STATE_PATH) -> dict[str, Any]:
    path = _coerce_path(path)
    if not path.exists():
        return {
            "last_successful_cycle": None,
            "history": [],
            "open_issues": [],
            "last_cron_exitcodes": {},
            "last_report_path": None,
            "last_escalation_path": None,
            "overall_status": "healthy",
        }

    payload = read_json(path)
    if not isinstance(payload, dict):
        raise ValueError(f"observation state must be a JSON object, got {type(payload).__name__}")
    return payload


def trim_history(history: Sequence[Any] | None, maxlen: int = 10) -> list[Any]:
    if not history or maxlen <= 0:
        return []
    return list(history)[-maxlen:]


def infer_job_exitcode(job_record: Mapping[str, Any] | None) -> int | None:
    if not job_record:
        return None

    status = str(job_record.get("last_status") or "").lower()
    last_error = job_record.get("last_error")
    delivery_error = job_record.get("last_delivery_error")

    if last_error is not None or delivery_error is not None:
        return 1
    if status in {"ok", "success", "passed", "completed", "done"}:
        return 0
    if status in {"failed", "error", "timeout", "crashed", "cancelled"}:
        return 1
    return None
