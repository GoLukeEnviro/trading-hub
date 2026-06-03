#!/usr/bin/env python3
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import observation_common as oc

STATE_FILE = Path("/opt/data/profiles/orchestrator/state/observation_state.json")
HEARTBEAT_FILE = Path("/opt/data/profiles/orchestrator/state/heartbeat_observation.json")
LOCK_DIR = Path("/opt/data/profiles/orchestrator/state/locks")
REPORTS_DIR = Path("/opt/data/profiles/orchestrator/reports")
ESCALATIONS_DIR = Path("/opt/data/profiles/orchestrator/escalations")
LOG_FILE = Path("/opt/data/profiles/orchestrator/logs/observation.log")
EXPECTED_STATE_FILE = Path("/opt/data/profiles/orchestrator/config/expected_state.json")
CRON_REGISTRY_FILE = Path("/opt/data/profiles/orchestrator/cron/jobs.json")
TMP_DIR = Path("/opt/data/profiles/orchestrator/state/tmp")

AGENT_ID = "task-2-runner"
MODE = "report_only"
MAX_HISTORY_ENTRIES = 50
MAX_CRON_HISTORY_ENTRIES = 10
LOCK_STALE_SECONDS = 10 * 60
DOCKER_TIMEOUT_SECONDS = 10
CRON_TIMEOUT_SECONDS = 10
WEBHOOK_TIMEOUT_SECONDS = 5
NEXT_CYCLE_SECONDS = 300

_LOGGER_NAME = "observation_runner"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso_now() -> str:
    return _utcnow().isoformat().replace("+00:00", "Z")


def _cycle_stamp(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).strftime("%Y%m%d-%H%M%S")


def _ensure_directories() -> None:
    for path in [STATE_FILE.parent, HEARTBEAT_FILE.parent, LOCK_DIR, REPORTS_DIR, ESCALATIONS_DIR, LOG_FILE.parent, TMP_DIR]:
        path.mkdir(parents=True, exist_ok=True)


def _configure_logging() -> logging.Logger:
    _ensure_directories()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.FileHandler(LOG_FILE, encoding="utf-8")],
        force=True,
    )
    return logging.getLogger(_LOGGER_NAME)


def _lock_path() -> Path:
    return LOCK_DIR / "observation.lock"


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _process_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    except OSError:
        return False


def _lock_age_seconds(path: Path, reference: datetime) -> float:
    try:
        return reference.timestamp() - path.stat().st_mtime
    except OSError:
        return float("inf")


def _write_lock_metadata(lock_dir: Path, timestamp: str) -> None:
    (lock_dir / "pid").write_text(str(os.getpid()), encoding="utf-8")
    (lock_dir / "timestamp").write_text(timestamp, encoding="utf-8")


def _acquire_lock(logger: logging.Logger, timestamp: str) -> tuple[bool, dict[str, Any] | None, bool]:
    lock_dir = _lock_path()
    try:
        os.mkdir(lock_dir)
        _write_lock_metadata(lock_dir, timestamp)
        return True, None, False
    except FileExistsError:
        pass

    existing_pid_text = _read_text(lock_dir / "pid")
    try:
        existing_pid = int(existing_pid_text)
    except (TypeError, ValueError):
        existing_pid = None

    age_seconds = _lock_age_seconds(lock_dir, _utcnow())
    running = existing_pid is not None and _process_running(existing_pid)
    stale = age_seconds > LOCK_STALE_SECONDS

    if running and not stale:
        logger.info("[INFO] Existing observation lock is active; skipping cycle.")
        return False, None, True

    reason = "Agent lock stale – möglicher Absturz"
    if not stale and not running:
        reason = "Agent lock defekt – Prozess nicht mehr aktiv"
    logger.warning(reason)

    takeover_issue = {
        "key": "lock",
        "type": "D",
        "description": reason,
        "confidence": 100,
        "first_seen": timestamp,
        "occurrences_last_30min": 1,
    }

    try:
        shutil.rmtree(lock_dir, ignore_errors=True)
        os.mkdir(lock_dir)
        _write_lock_metadata(lock_dir, timestamp)
    except OSError as exc:
        logger.error("Failed to overwrite stale lock: %s", exc)
        raise

    return True, takeover_issue, False


def _release_lock(logger: logging.Logger) -> None:
    lock_dir = _lock_path()
    try:
        shutil.rmtree(lock_dir, ignore_errors=True)
    except OSError as exc:
        logger.warning("Failed to release observation lock: %s", exc)


def _load_expected_state(logger: logging.Logger) -> tuple[dict[str, Any], bool, list[str]]:
    warnings: list[str] = []
    config_missing = False
    try:
        expected_state = oc.load_expected_state(EXPECTED_STATE_FILE, allow_missing=True)
    except Exception as exc:  # pragma: no cover - defensive, hard to trigger in tests
        logger.warning("expected_state load failed; using default: %s", exc)
        expected_state = oc.default_expected_state()
        config_missing = True
        warnings.append("expected_state.json unavailable; using default_expected_state()")
        return expected_state, config_missing, warnings

    if not EXPECTED_STATE_FILE.exists():
        config_missing = True
        warnings.append("expected_state.json missing; using default_expected_state()")
        logger.warning("expected_state.json missing; using default_expected_state()")
    else:
        try:
            oc.read_json(EXPECTED_STATE_FILE)
        except Exception:
            config_missing = True
            warnings.append("expected_state.json unreadable; using default_expected_state()")
            logger.warning("expected_state.json unreadable; using default_expected_state()")
            expected_state = oc.default_expected_state()

    return expected_state, config_missing, warnings


def _normalize_registry_jobs(payload: Any) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    if not isinstance(payload, dict):
        return jobs
    raw_jobs = payload.get("jobs") or []
    if not isinstance(raw_jobs, list):
        return jobs
    for raw in raw_jobs:
        if not isinstance(raw, dict):
            continue
        command = str(raw.get("command") or raw.get("name") or "").strip()
        schedule = str(raw.get("schedule") or raw.get("schedule_display") or "").strip()
        owner = str(raw.get("owner") or "unknown").strip() or "unknown"
        last_exitcode = raw.get("last_exitcode") if "last_exitcode" in raw else None
        if last_exitcode is not None:
            try:
                last_exitcode = int(last_exitcode)
            except (TypeError, ValueError):
                last_exitcode = None
        jobs.append(
            {
                "command": command,
                "schedule": schedule,
                "owner": owner,
                "last_exitcode": last_exitcode,
                "last_run": raw.get("last_run"),
                "source": "registry",
            }
        )
    return jobs


def _parse_fallback_line(entry: Any) -> dict[str, Any] | None:
    if isinstance(entry, dict):
        line = str(entry.get("line") or "").strip()
        source = str(entry.get("source") or "fallback")
    else:
        line = str(entry).strip()
        source = "fallback"
    if not line:
        return None

    tokens = line.split()
    if len(tokens) < 6:
        return None

    schedule = " ".join(tokens[:5])
    command_tokens = tokens[5:]
    owner = "unknown"
    if source != "crontab" and len(tokens) >= 7:
        owner = tokens[5]
        command_tokens = tokens[6:]

    return {
        "command": " ".join(command_tokens).strip(),
        "schedule": schedule,
        "owner": owner,
        "last_exitcode": None,
        "last_run": None,
        "source": "fallback",
        "raw_line": line,
    }


def _normalize_fallback_jobs(payload: Any) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    entries = []
    if isinstance(payload, dict):
        entries = payload.get("entries") or []
    if not isinstance(entries, list):
        return jobs
    for entry in entries:
        parsed = _parse_fallback_line(entry)
        if parsed and parsed["command"]:
            jobs.append(parsed)
    return jobs


def _load_cron_jobs(logger: logging.Logger) -> tuple[list[dict[str, Any]], str, list[str]]:
    warnings: list[str] = []
    jobs: list[dict[str, Any]] = []
    cron_source = "registry"
    try:
        registry_payload = oc.load_cron_registry(CRON_REGISTRY_FILE)
        jobs = _normalize_registry_jobs(registry_payload)
    except Exception as exc:
        warnings.append(f"cron registry unavailable: {exc}")
        logger.warning("cron registry unavailable; falling back to crontab: %s", exc)

    if not jobs:
        cron_source = "fallback_crontab"
        try:
            fallback_payload = oc.load_cron_fallback()
            jobs = _normalize_fallback_jobs(fallback_payload)
            if not jobs:
                warnings.append("cron fallback returned no jobs")
                logger.warning("cron fallback returned no jobs")
        except Exception as exc:
            warnings.append(f"cron fallback failed: {exc}")
            logger.error("cron fallback failed: %s", exc)
            jobs = []
    return jobs, cron_source, warnings


_DOCKER_HEADER_NAMES = {"NAMES", "CONTAINER ID", "CONTAINER"}


def _parse_docker_ps_output(output: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        upper = line.upper()
        if any(upper.startswith(header) for header in _DOCKER_HEADER_NAMES):
            continue

        parts = [part.strip() for part in line.split("\t") if part is not None]
        if len(parts) < 3:
            import re

            parts = [part.strip() for part in re.split(r"\s{2,}", line) if part.strip()]
        if len(parts) < 2:
            continue
        name = parts[0]
        status = parts[1]
        health = parts[2] if len(parts) >= 3 else ""
        rows.append({"name": name, "status": status, "health": health})
    return rows


def _collect_docker_ps(logger: logging.Logger) -> tuple[list[dict[str, str]], str | None]:
    cmd = ["docker", "ps", "--format", "table {{.Names}}\t{{.Status}}"]
    try:
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=DOCKER_TIMEOUT_SECONDS,
            check=False,
        )
    except Exception as exc:
        logger.error("docker ps failed: %s", exc)
        return [], str(exc)

    if completed.returncode != 0:
        error = (completed.stderr or completed.stdout or "docker ps failed").strip()
        logger.error("docker ps returned non-zero exit code: %s", error)
        return [], error

    return _parse_docker_ps_output(completed.stdout), None


def _known_expected_containers(expected_state: dict[str, Any]) -> list[str]:
    containers = expected_state.get("expected_containers")
    if isinstance(containers, list) and containers:
        return [str(name) for name in containers if str(name).strip()]
    fallback = oc.default_expected_state().get("expected_containers", [])
    return [str(name) for name in fallback]


def _signal_config(expected_state: dict[str, Any]) -> dict[str, Any]:
    signal_cfg = expected_state.get("signal_pipeline_config")
    return signal_cfg if isinstance(signal_cfg, dict) else {}


def _cron_job_key(job: dict[str, Any]) -> str:
    command = str(job.get("command") or "").strip()
    if command:
        return command
    return str(job.get("owner") or "unknown")


def _previous_issue_map(previous_state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    mapped: dict[str, dict[str, Any]] = {}
    for issue in previous_state.get("open_issues", []) or []:
        if not isinstance(issue, dict):
            continue
        key = str(issue.get("key") or "").strip()
        if key:
            mapped[key] = issue
    return mapped


def _previous_cron_history(previous_state: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    history = previous_state.get("last_cron_exitcodes", {})
    normalized: dict[str, list[dict[str, Any]]] = {}
    if not isinstance(history, dict):
        return normalized
    for key, entries in history.items():
        if not isinstance(entries, list):
            continue
        normalized[str(key)] = [entry for entry in entries if isinstance(entry, dict)]
    return normalized


def _count_issue_occurrences(history: list[dict[str, Any]], key: str, current_ts: datetime) -> int:
    threshold = current_ts - timedelta(minutes=30)
    count = 1
    for cycle in history:
        if not isinstance(cycle, dict):
            continue
        cycle_ts_text = cycle.get("timestamp")
        issue_keys = cycle.get("issue_keys") or []
        if not isinstance(issue_keys, list):
            continue
        if key not in {str(item) for item in issue_keys}:
            continue
        try:
            cycle_ts = datetime.fromisoformat(str(cycle_ts_text).replace("Z", "+00:00"))
        except Exception:
            continue
        if cycle_ts.tzinfo is None:
            cycle_ts = cycle_ts.replace(tzinfo=timezone.utc)
        else:
            cycle_ts = cycle_ts.astimezone(timezone.utc)
        if cycle_ts >= threshold:
            count += 1
    return count


def _build_container_issues(
    container_rows: list[dict[str, Any]],
    logger: logging.Logger,
    existing_issue_count: int,
) -> list[dict[str, Any]]:
    problematic_rows: list[dict[str, Any]] = []
    for row in container_rows:
        state = str(row.get("state") or "")
        health = str(row.get("health") or "")
        if state in {"exited", "restarting", "exited_or_missing"} or health in {"unhealthy", "starting", "missing"}:
            problematic_rows.append(row)

    if not problematic_rows:
        return []

    confidence = 95 if len(problematic_rows) > 2 else 90
    issues: list[dict[str, Any]] = []
    for row in problematic_rows:
        name = str(row.get("name") or "unknown")
        state = str(row.get("state") or "unknown")
        health = str(row.get("health") or "unknown")
        duration = row.get("duration_seconds")
        if existing_issue_count > 0:
            logger.info("[INFO] Container issue detected for %s (%s/%s).", name, state, health)
        issues.append(
            {
                "key": f"container:{name}",
                "type": "A",
                "description": f"Container {name} is {state} (health={health}).",
                "confidence": confidence,
                "first_seen": None,
                "occurrences_last_30min": 0,
                "meta": {"duration_seconds": duration},
            }
        )
    return issues


def _build_cron_issues(
    cron_jobs: list[dict[str, Any]],
    previous_cron_history: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for job in cron_jobs:
        exitcode = job.get("last_exitcode")
        if exitcode is None:
            continue
        try:
            exitcode_int = int(exitcode)
        except (TypeError, ValueError):
            continue
        if exitcode_int == 0:
            continue

        key = _cron_job_key(job)
        previous_history = previous_cron_history.get(key, [])
        repeated = False
        if previous_history:
            last_entry = previous_history[-1]
            last_exitcode = last_entry.get("exitcode")
            try:
                repeated = last_exitcode is not None and int(last_exitcode) != 0
            except (TypeError, ValueError):
                repeated = False

        issues.append(
            {
                "key": f"cron:{key}",
                "type": "B",
                "description": f"Cron job {key} failed with exit code {exitcode_int}.",
                "confidence": 95 if repeated else 85,
                "first_seen": None,
                "occurrences_last_30min": 0,
                "meta": {"exitcode": exitcode_int, "schedule": job.get("schedule")},
            }
        )
    return issues


def _build_signal_issue(signal_result: dict[str, Any], expected_max_age: int) -> dict[str, Any] | None:
    if not signal_result.get("stale"):
        return None
    age_seconds = signal_result.get("age_seconds")
    try:
        age_int = int(age_seconds) if age_seconds is not None else expected_max_age + 1
    except (TypeError, ValueError):
        age_int = expected_max_age + 1
    confidence = 90 if age_int > int(expected_max_age * 1.5) else 85
    return {
        "key": "signal:freshness",
        "type": "C",
        "description": f"Signal freshness stale: age {age_int}s exceeds expected {expected_max_age}s.",
        "confidence": confidence,
        "first_seen": None,
        "occurrences_last_30min": 0,
        "meta": {"age_seconds": age_int, "expected_max_age_seconds": expected_max_age},
    }


def _load_previous_state_safe(logger: logging.Logger) -> dict[str, Any]:
    try:
        previous_state = oc.load_previous_state(STATE_FILE)
        if not isinstance(previous_state, dict):
            raise ValueError("previous state is not a JSON object")
        return previous_state
    except Exception as exc:
        logger.warning("previous state unavailable; starting fresh: %s", exc)
        return {
            "last_successful_cycle": None,
            "history": [],
            "open_issues": [],
            "last_cron_exitcodes": {},
            "last_report_path": None,
            "last_escalation_path": None,
            "overall_status": "healthy",
        }


def _build_state_history_entry(
    timestamp: str,
    container_score: int,
    pipeline_score: int,
    overall_status: str,
    issue_keys: list[str],
    warnings: list[str],
) -> dict[str, Any]:
    return {
        "timestamp": timestamp,
        "container_score": container_score,
        "pipeline_score": pipeline_score,
        "overall_status": overall_status,
        "issue_keys": issue_keys,
        "warnings": warnings,
    }


def _compact_state_snapshot(state: dict[str, Any], history_tail: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "last_successful_cycle": state.get("last_successful_cycle"),
        "last_cycle": state.get("last_cycle"),
        "last_status": state.get("last_status"),
        "overall_status": state.get("overall_status"),
        "open_issues": state.get("open_issues", [])[:5],
        "history_tail": history_tail,
        "last_report_path": state.get("last_report_path"),
        "last_escalation_path": state.get("last_escalation_path"),
    }


def _send_webhook(logger: logging.Logger, escalation_path: Path) -> None:
    webhook_url = os.getenv("HERMES_ALERT_WEBHOOK")
    if not webhook_url:
        return

    cmd = [
        "curl",
        "-X",
        "POST",
        "-H",
        "Content-Type: application/json",
        "-d",
        f"@{escalation_path}",
        webhook_url,
    ]
    try:
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=WEBHOOK_TIMEOUT_SECONDS,
            check=False,
        )
        if completed.returncode != 0:
            stderr = (completed.stderr or completed.stdout or "webhook failed").strip()
            logger.warning("Webhook POST failed: %s", stderr)
    except Exception as exc:
        logger.warning("Webhook POST failed: %s", exc)


def _build_escalation_payload(
    timestamp: str,
    cycle_id: str,
    reason: str,
    overall_status: str,
    issues: list[dict[str, Any]],
    report_path: str,
    config_missing: bool,
    cron_source: str,
    state_snapshot: dict[str, Any],
) -> dict[str, Any]:
    return {
        "timestamp": timestamp,
        "agent_id": AGENT_ID,
        "cycle_id": cycle_id,
        "mode": MODE,
        "severity": "critical" if overall_status == "critical" else "warning",
        "reason": reason,
        "overall_status": overall_status,
        "report_path": report_path,
        "config_missing": config_missing,
        "cron_source": cron_source,
        "issues": issues,
        "state_snapshot": state_snapshot,
    }


def _build_report_payload(
    timestamp: str,
    cycle_id: str,
    overall_status: str,
    container_score: int,
    pipeline_score: int,
    container_result: dict[str, Any],
    cron_jobs: list[dict[str, Any]],
    cron_source: str,
    issues: list[dict[str, Any]],
    warnings: list[str],
    config_missing: bool,
    escalation_triggered: bool,
    escalation_file: str | None,
    recommendation_for_human: str,
    state_snapshot: dict[str, Any],
) -> dict[str, Any]:
    return {
        "timestamp": timestamp,
        "agent_id": AGENT_ID,
        "cycle_id": cycle_id,
        "mode": MODE,
        "cron_source": cron_source,
        "cron_jobs": cron_jobs,
        "config_missing": config_missing,
        "warnings": warnings,
        "system_health": {
            "container_score": container_score,
            "pipeline_score": pipeline_score,
            "overall_status": overall_status,
            "container_result": container_result,
        },
        "detected_issues": issues,
        "escalation_triggered": escalation_triggered,
        "escalation_file": escalation_file,
        "recommendation_for_human": recommendation_for_human,
        "next_cycle_in_seconds": NEXT_CYCLE_SECONDS,
        "state_snapshot": state_snapshot,
    }


def run_cycle() -> dict[str, Any]:
    logger = _configure_logging()
    timestamp = _iso_now()
    cycle_id = _cycle_stamp(_utcnow())
    lock_acquired = False
    escalation_path: Path | None = None
    report_path: Path | None = None
    state_path: Path | None = None
    heartbeat_path: Path | None = None

    try:
        lock_acquired, takeover_issue, skipped = _acquire_lock(logger, timestamp)
        if skipped:
            return {
                "status": "skipped",
                "exit_code": 0,
                "timestamp": timestamp,
                "cycle_id": cycle_id,
                "report_path": None,
                "escalation_path": None,
                "state_path": None,
                "heartbeat_path": None,
                "overall_status": "skipped",
            }

        expected_state, config_missing, warnings = _load_expected_state(logger)
        previous_state = _load_previous_state_safe(logger)
        previous_open_issues = _previous_issue_map(previous_state)
        previous_history = previous_state.get("history", []) if isinstance(previous_state.get("history", []), list) else []
        previous_cron_history = _previous_cron_history(previous_state)

        cron_jobs, cron_source, cron_warnings = _load_cron_jobs(logger)
        warnings.extend(cron_warnings)
        if cron_source == "fallback_crontab":
            warnings.append("cron registry unavailable or empty; fallback_crontab used")

        expected_containers = _known_expected_containers(expected_state)
        container_result: dict[str, Any] = {
            "containers": [],
            "missing_containers": [],
            "missing_count": 0,
            "unhealthy_count": 0,
            "exited_count": 0,
            "container_score": 0,
        }
        container_error: str | None = None
        container_issues: list[dict[str, Any]] = []
        docker_rows: list[dict[str, str]] = []
        try:
            docker_rows, container_error = _collect_docker_ps(logger)
            if container_error is None:
                container_result = oc.evaluate_container_health(expected_containers, docker_rows)
                container_issues = _build_container_issues(
                    list(container_result.get("containers", [])),
                    logger,
                    len(previous_open_issues),
                )
            else:
                container_result = {
                    "containers": [],
                    "missing_containers": expected_containers,
                    "missing_count": len(expected_containers),
                    "unhealthy_count": len(expected_containers),
                    "exited_count": 0,
                    "container_score": 0,
                }
        except Exception as exc:
            container_error = str(exc)
            logger.error("Container monitoring failed: %s", exc)
            container_result = {
                "containers": [],
                "missing_containers": expected_containers,
                "missing_count": len(expected_containers),
                "unhealthy_count": len(expected_containers),
                "exited_count": 0,
                "container_score": 0,
            }
            container_issues = [
                {
                    "key": "container:monitoring",
                    "type": "A",
                    "description": f"Container monitoring failed: {exc}",
                    "confidence": 100,
                    "first_seen": None,
                    "occurrences_last_30min": 0,
                    "meta": {"error": str(exc)},
                }
            ]

        signal_issue: dict[str, Any] | None = None
        signal_result: dict[str, Any] = {"stale": False}
        signal_cfg = _signal_config(expected_state)
        signal_pattern = str(signal_cfg.get("signal_file_pattern") or "").strip()
        expected_max_age_seconds = int(signal_cfg.get("expected_max_age_seconds") or 0)
        signal_check_failed = False
        if signal_pattern:
            try:
                signal_result = oc.evaluate_signal_freshness(signal_pattern, expected_max_age_seconds, reference_time=_utcnow())
                signal_issue = _build_signal_issue(signal_result, expected_max_age_seconds)
            except Exception as exc:
                signal_check_failed = True
                logger.error("Signal freshness monitoring failed: %s", exc)
                signal_result = {"stale": True, "age_seconds": None, "error": str(exc)}
                signal_issue = {
                    "key": "signal:monitoring",
                    "type": "C",
                    "description": f"Signal freshness monitoring failed: {exc}",
                    "confidence": 100,
                    "first_seen": None,
                    "occurrences_last_30min": 0,
                    "meta": {"error": str(exc)},
                }
        else:
            warnings.append("signal_file_pattern not configured; freshness check skipped")

        cron_issues = _build_cron_issues(cron_jobs, previous_cron_history)
        if not cron_jobs:
            cron_issues = [
                {
                    "key": "cron:registry",
                    "type": "B",
                    "description": "No cron jobs could be loaded from registry or fallback.",
                    "confidence": 100,
                    "first_seen": None,
                    "occurrences_last_30min": 0,
                    "meta": {"cron_source": cron_source},
                }
            ]

        issues: list[dict[str, Any]] = []
        if takeover_issue is not None:
            issues.append(takeover_issue)
        issues.extend(container_issues)
        issues.extend(cron_issues)
        if signal_issue is not None:
            issues.append(signal_issue)

        for issue in issues:
            key = str(issue.get("key") or "").strip()
            if not key:
                continue
            previous_issue = previous_open_issues.get(key)
            if previous_issue:
                issue["first_seen"] = previous_issue.get("first_seen") or timestamp
            else:
                issue["first_seen"] = timestamp
            issue["occurrences_last_30min"] = _count_issue_occurrences(previous_history, key, _utcnow())
            if issue["type"] == "B" and previous_issue:
                issue["confidence"] = max(int(issue.get("confidence", 85)), 95)

        failed_cronjobs = 0
        for job in cron_jobs:
            last_exitcode = job.get("last_exitcode")
            if last_exitcode is None:
                continue
            try:
                if int(last_exitcode) != 0:
                    failed_cronjobs += 1
            except (TypeError, ValueError):
                continue
        stale = 1 if signal_issue is not None else 0
        if cron_jobs:
            pipeline_score = max(0, 100 - (failed_cronjobs * 20) - (stale * 30))
        else:
            pipeline_score = 0
        if signal_check_failed:
            pipeline_score = 0

        unhealthy_count = int(container_result.get("unhealthy_count") or 0)
        exited_count = int(container_result.get("exited_count") or 0)
        container_score = int(container_result.get("container_score") or 0)
        if container_error is not None:
            container_score = 0

        min_score = min(container_score, pipeline_score)
        if min_score <= 50:
            overall_status = "critical"
        elif min_score <= 79:
            overall_status = "degraded"
        else:
            overall_status = "healthy"
        if config_missing and overall_status == "healthy" and container_score >= 80 and pipeline_score >= 80:
            overall_status = "degraded"

        if any(issue.get("confidence", 0) >= 85 for issue in issues):
            escalation_triggered = True
        else:
            escalation_triggered = overall_status == "critical"

        issue_keys = [str(issue.get("key") or "") for issue in issues if issue.get("key")]
        current_cycle_history = _build_state_history_entry(
            timestamp=timestamp,
            container_score=container_score,
            pipeline_score=pipeline_score,
            overall_status=overall_status,
            issue_keys=issue_keys,
            warnings=warnings,
        )

        history = list(previous_history) if isinstance(previous_history, list) else []
        history.append(current_cycle_history)
        history = oc.trim_history(history, maxlen=MAX_HISTORY_ENTRIES)

        last_cron_exitcodes = _previous_cron_history(previous_state)
        for job in cron_jobs:
            key = _cron_job_key(job)
            exitcode = job.get("last_exitcode")
            if exitcode is None:
                continue
            try:
                exitcode_int = int(exitcode)
            except (TypeError, ValueError):
                continue
            history_for_job = list(last_cron_exitcodes.get(key, []))
            history_for_job.append({"timestamp": timestamp, "exitcode": exitcode_int})
            last_cron_exitcodes[key] = oc.trim_history(history_for_job, maxlen=MAX_CRON_HISTORY_ENTRIES)

        open_issues = [
            {
                "key": issue["key"],
                "type": issue["type"],
                "description": issue["description"],
                "confidence": issue["confidence"],
                "first_seen": issue["first_seen"],
                "occurrences_last_30min": issue["occurrences_last_30min"],
            }
            for issue in issues
        ]

        state = dict(previous_state)
        state.update(
            {
                "last_cycle": timestamp,
                "last_successful_cycle": timestamp,
                "last_status": overall_status,
                "overall_status": overall_status,
                "history": history,
                "open_issues": open_issues,
                "last_cron_exitcodes": last_cron_exitcodes,
                "last_report_path": None,
                "last_escalation_path": None,
            }
        )

        history_tail = history[-3:]
        state_snapshot = _compact_state_snapshot(state, history_tail)
        recommendation_for_human = (
            "Investigate immediately; review the escalation file and the observation log."
            if overall_status == "critical"
            else "Review the warnings; no active fixes were applied."
            if overall_status == "degraded"
            else "No immediate action required."
        )

        report_path = REPORTS_DIR / f"report_{cycle_id}.json"
        escalation_path = ESCALATIONS_DIR / f"escalation_{cycle_id}.json" if escalation_triggered else None
        report = _build_report_payload(
            timestamp=timestamp,
            cycle_id=cycle_id,
            overall_status=overall_status,
            container_score=container_score,
            pipeline_score=pipeline_score,
            container_result=container_result,
            cron_jobs=cron_jobs,
            cron_source=cron_source,
            issues=open_issues,
            warnings=warnings,
            config_missing=config_missing,
            escalation_triggered=escalation_triggered,
            escalation_file=str(escalation_path) if escalation_path is not None else None,
            recommendation_for_human=recommendation_for_human,
            state_snapshot=state_snapshot,
        )

        oc.write_json_atomic(report_path, report)
        state["last_report_path"] = str(report_path)
        state_path = oc.write_json_atomic(STATE_FILE, state)
        heartbeat_path = oc.write_json_atomic(
            HEARTBEAT_FILE,
            {
                "last_successful_cycle": timestamp,
                "overall_status": overall_status,
            },
        )

        if escalation_triggered and escalation_path is not None:
            escalation_reason_parts = []
            if takeover_issue is not None:
                escalation_reason_parts.append(str(takeover_issue.get("description") or "Agent lock takeover"))
            if overall_status == "critical":
                escalation_reason_parts.append("critical overall status")
            if any(issue.get("confidence", 0) >= 85 for issue in issues):
                escalation_reason_parts.append("issue confidence >= 85")
            escalation_reason = "; ".join(part for part in escalation_reason_parts if part)
            escalation = _build_escalation_payload(
                timestamp=timestamp,
                cycle_id=cycle_id,
                reason=escalation_reason or "observation escalation",
                overall_status=overall_status,
                issues=open_issues,
                report_path=str(report_path),
                config_missing=config_missing,
                cron_source=cron_source,
                state_snapshot=state_snapshot,
            )
            oc.write_json_atomic(escalation_path, escalation)
            state["last_escalation_path"] = str(escalation_path)
            oc.write_json_atomic(STATE_FILE, state)
            _send_webhook(logger, escalation_path)
            logger.warning("[ESCALATION] Cycle %s escalated. Status: %s", cycle_id, overall_status)

        logger.info("[INFO] Cycle %s completed. Status: %s", cycle_id, overall_status)

        state["last_escalation_path"] = str(escalation_path) if escalation_path is not None else None
        oc.write_json_atomic(STATE_FILE, state)
        return {
            "status": "completed",
            "exit_code": 0,
            "timestamp": timestamp,
            "cycle_id": cycle_id,
            "report_path": str(report_path),
            "escalation_path": str(escalation_path) if escalation_path is not None else None,
            "state_path": str(STATE_FILE),
            "heartbeat_path": str(HEARTBEAT_FILE),
            "overall_status": overall_status,
            "config_missing": config_missing,
            "cron_source": cron_source,
            "warnings": warnings,
        }
    except SystemExit:
        raise
    except Exception as exc:
        logger.exception("Severe internal error in observation runner: %s", exc)
        return {
            "status": "error",
            "exit_code": 1,
            "timestamp": timestamp,
            "cycle_id": cycle_id,
            "report_path": str(report_path) if report_path is not None else None,
            "escalation_path": str(escalation_path) if escalation_path is not None else None,
            "state_path": str(state_path) if state_path is not None else None,
            "heartbeat_path": str(heartbeat_path) if heartbeat_path is not None else None,
            "overall_status": "critical",
        }
    finally:
        if lock_acquired:
            _release_lock(logger)


def main() -> int:
    result = run_cycle()
    return int(result.get("exit_code", 1))


if __name__ == "__main__":
    raise SystemExit(main())
