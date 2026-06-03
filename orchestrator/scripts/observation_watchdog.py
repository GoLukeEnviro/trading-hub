#!/usr/bin/env python3
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HEARTBEAT_FILE = "/opt/data/profiles/orchestrator/state/heartbeat_observation.json"
LOCK_DIR = "/opt/data/profiles/orchestrator/state/locks/"
ESCALATIONS_DIR = "/opt/data/profiles/orchestrator/escalations/"
LOG_FILE = "/opt/data/profiles/orchestrator/logs/observation_watchdog.log"
WEBHOOK_URL_ENV = "HERMES_ALERT_WEBHOOK"

WATCHDOG_AGENT_ID = "hermes-trading-observation-watchdog-phase1"
LOCK_NAME = "watchdog.lock"
LOCK_STALE_SECONDS = 15 * 60
MAX_HEARTBEAT_AGE_SECONDS = 12 * 60  # 12 Minuten
_WEBHOOK_TIMEOUT_SECONDS = 5
_LOGGER_NAME = "observation_watchdog"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _local_now() -> datetime:
    return datetime.now().astimezone()


def _timestamp_for_payload() -> str:
    return _local_now().isoformat(timespec="seconds")


def _ensure_runtime_directories() -> None:
    Path(LOG_FILE).parent.mkdir(parents=True, exist_ok=True)
    Path(LOCK_DIR).mkdir(parents=True, exist_ok=True)
    Path(ESCALATIONS_DIR).mkdir(parents=True, exist_ok=True)


def _configure_logging() -> logging.Logger:
    _ensure_runtime_directories()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.FileHandler(LOG_FILE, encoding="utf-8")],
        force=True,
    )
    return logging.getLogger(_LOGGER_NAME)


def _lock_path() -> Path:
    return Path(os.path.join(LOCK_DIR, LOCK_NAME))


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            try:
                os.unlink(tmp_name)
            except FileNotFoundError:
                pass


def _parse_iso_datetime(value: str) -> datetime:
    normalized = value.strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _write_lock_metadata(lock_path: Path, timestamp: str) -> None:
    _write_text(lock_path / "pid", str(os.getpid()))
    _write_text(lock_path / "timestamp", timestamp)


def _acquire_lock(logger: logging.Logger) -> dict[str, Any]:
    lock_path = _lock_path()
    timestamp = _timestamp_for_payload()

    try:
        os.mkdir(lock_path)
        _write_lock_metadata(lock_path, timestamp)
        return {
            "status": "acquired",
            "lock_path": str(lock_path),
            "lock_taken_over": False,
            "lock_age_seconds": None,
        }
    except FileExistsError:
        try:
            lock_age_seconds = _utc_now().timestamp() - lock_path.stat().st_mtime
        except OSError as exc:
            logger.error("Failed to inspect watchdog lock: %s", exc)
            return {"status": "error", "exit_code": 1, "lock_path": str(lock_path)}

        if lock_age_seconds <= LOCK_STALE_SECONDS:
            return {
                "status": "skipped",
                "lock_path": str(lock_path),
                "lock_taken_over": False,
                "lock_age_seconds": lock_age_seconds,
            }

        try:
            shutil.rmtree(lock_path)
            os.mkdir(lock_path)
            _write_lock_metadata(lock_path, timestamp)
        except OSError as exc:
            logger.error("Failed to overwrite stale watchdog lock: %s", exc)
            return {"status": "error", "exit_code": 1, "lock_path": str(lock_path)}

        return {
            "status": "acquired",
            "lock_path": str(lock_path),
            "lock_taken_over": True,
            "lock_age_seconds": lock_age_seconds,
        }
    except OSError as exc:
        logger.error("Failed to acquire watchdog lock: %s", exc)
        return {"status": "error", "exit_code": 1, "lock_path": str(lock_path)}


def _release_lock(logger: logging.Logger) -> None:
    lock_path = _lock_path()
    try:
        shutil.rmtree(lock_path)
    except FileNotFoundError:
        return
    except OSError as exc:
        logger.warning("Failed to release watchdog lock: %s", exc)


def _load_heartbeat() -> dict[str, Any]:
    heartbeat_path = Path(HEARTBEAT_FILE)
    try:
        raw_payload = heartbeat_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {
            "status": "missing",
            "reason": "heartbeat_file_missing",
            "human_reason": "Heartbeat-Datei fehlt",
            "heartbeat_file": str(heartbeat_path),
        }
    except (OSError, UnicodeDecodeError):
        return {
            "status": "unreadable",
            "reason": "heartbeat_file_unreadable",
            "human_reason": "Heartbeat-Datei fehlt oder ist unlesbar",
            "heartbeat_file": str(heartbeat_path),
        }

    try:
        payload = json.loads(raw_payload)
    except json.JSONDecodeError:
        return {
            "status": "unreadable",
            "reason": "heartbeat_file_unreadable",
            "human_reason": "Heartbeat-Datei fehlt oder ist unlesbar",
            "heartbeat_file": str(heartbeat_path),
        }

    if not isinstance(payload, dict):
        return {
            "status": "unreadable",
            "reason": "heartbeat_file_unreadable",
            "human_reason": "Heartbeat-Datei fehlt oder ist unlesbar",
            "heartbeat_file": str(heartbeat_path),
        }

    last_successful_cycle = payload.get("last_successful_cycle")
    overall_status = payload.get("overall_status")
    if not isinstance(last_successful_cycle, str) or not last_successful_cycle.strip():
        return {
            "status": "invalid",
            "reason": "heartbeat_timestamp_unparsable",
            "human_reason": "Heartbeat last_successful_cycle fehlt oder ist ungültig",
            "heartbeat_file": str(heartbeat_path),
            "last_heartbeat": last_successful_cycle,
            "runner_last_status": overall_status if isinstance(overall_status, str) else None,
        }

    try:
        last_cycle_utc = _parse_iso_datetime(last_successful_cycle)
    except ValueError:
        return {
            "status": "invalid",
            "reason": "heartbeat_timestamp_unparsable",
            "human_reason": "Heartbeat last_successful_cycle fehlt oder ist ungültig",
            "heartbeat_file": str(heartbeat_path),
            "last_heartbeat": last_successful_cycle,
            "runner_last_status": overall_status if isinstance(overall_status, str) else None,
        }

    age_seconds = (_utc_now() - last_cycle_utc).total_seconds()
    return {
        "status": "fresh" if age_seconds <= MAX_HEARTBEAT_AGE_SECONDS else "stale",
        "reason": "observation_runner_heartbeat_stale",
        "human_reason": "Heartbeat älter als 12 Minuten",
        "heartbeat_file": str(heartbeat_path),
        "last_heartbeat": last_successful_cycle,
        "age_seconds": age_seconds,
        "runner_last_status": overall_status if isinstance(overall_status, str) else None,
    }


def _build_escalation_payload(
    timestamp: str,
    heartbeat_issue: dict[str, Any] | None,
    lock_issue: dict[str, Any] | None,
) -> dict[str, Any]:
    details: dict[str, Any] = {
        "heartbeat_file": str(Path(HEARTBEAT_FILE)),
        "last_heartbeat": None,
        "age_seconds": None,
        "threshold_seconds": MAX_HEARTBEAT_AGE_SECONDS,
        "runner_last_status": None,
    }

    if heartbeat_issue is not None:
        details["last_heartbeat"] = heartbeat_issue.get("last_heartbeat")
        details["age_seconds"] = heartbeat_issue.get("age_seconds")
        details["runner_last_status"] = heartbeat_issue.get("runner_last_status")
        details["heartbeat_issue_reason"] = heartbeat_issue.get("reason")
        details["heartbeat_human_reason"] = heartbeat_issue.get("human_reason")

    if lock_issue is not None:
        details["watchdog_lock_file"] = lock_issue.get("watchdog_lock_file")
        details["watchdog_lock_age_seconds"] = lock_issue.get("watchdog_lock_age_seconds")
        details["watchdog_lock_reason"] = lock_issue.get("reason")
        details["watchdog_lock_human_reason"] = lock_issue.get("human_reason")

    if lock_issue is not None:
        reason = str(lock_issue.get("reason") or "watchdog_lock_stale")
        human_reason = str(lock_issue.get("human_reason") or "Watchdog selbst möglicherweise abgestürzt")
    elif heartbeat_issue is not None:
        reason = str(heartbeat_issue.get("reason") or "observation_runner_heartbeat_stale")
        human_reason = str(heartbeat_issue.get("human_reason") or "Heartbeat-Probleme erkannt")
    else:
        reason = "observation_runner_heartbeat_stale"
        human_reason = "Heartbeat-Probleme erkannt"

    details["human_reason"] = human_reason

    suggested_actions = [
        "Prüfen, ob observation_runner.py noch läuft",
        "Cron-Logs des Runners prüfen: /opt/data/profiles/orchestrator/logs/observation.log",
        "Bei Bedarf observation_runner.py manuell starten oder Cron neu einrichten",
    ]
    if lock_issue is not None:
        suggested_actions = [
            "Prüfen, ob observation_watchdog.py noch läuft",
            "Cron-Logs des Watchdogs prüfen: /opt/data/profiles/orchestrator/logs/observation_watchdog.log",
            "Bei Bedarf den Watchdog-Cron prüfen oder den Lock nach Analyse entfernen",
        ]

    return {
        "timestamp": timestamp,
        "agent_id": WATCHDOG_AGENT_ID,
        "severity": "critical",
        "reason": reason,
        "details": details,
        "requires_human_attention": True,
        "suggested_actions": suggested_actions,
        "human_reason": human_reason,
    }


def _write_escalation(payload: dict[str, Any]) -> Path:
    timestamp = str(payload["timestamp"])
    path = Path(ESCALATIONS_DIR) / f"watchdog_escalation_{timestamp}.json"
    _write_json_atomic(path, payload)
    return path


def _send_webhook(logger: logging.Logger, escalation_path: Path) -> None:
    webhook_url = os.getenv(WEBHOOK_URL_ENV)
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
            timeout=_WEBHOOK_TIMEOUT_SECONDS,
            check=False,
        )
        if completed.returncode != 0:
            stderr = (completed.stderr or completed.stdout or "webhook failed").strip()
            logger.warning("Webhook POST failed: %s", stderr)
    except Exception as exc:
        logger.warning("Webhook POST failed: %s", exc)


def run_watchdog() -> dict[str, Any]:
    logger = _configure_logging()
    logger.info("Watchdog started")

    lock_state = _acquire_lock(logger)
    if lock_state.get("status") == "error":
        return {
            "status": "error",
            "exit_code": int(lock_state.get("exit_code", 1)),
            "timestamp": _timestamp_for_payload(),
            "lock_path": lock_state.get("lock_path"),
            "escalation_path": None,
        }

    if lock_state.get("status") == "skipped":
        logger.info("Another watchdog instance is active; skipping cycle.")
        return {
            "status": "skipped",
            "exit_code": 0,
            "timestamp": _timestamp_for_payload(),
            "lock_path": lock_state.get("lock_path"),
            "escalation_path": None,
            "heartbeat_state": None,
        }

    lock_owned = True
    lock_issue: dict[str, Any] | None = None
    heartbeat_issue: dict[str, Any] | None = None
    escalation_path: Path | None = None

    try:
        if lock_state.get("lock_taken_over"):
            lock_issue = {
                "reason": "watchdog_lock_stale",
                "human_reason": "Watchdog selbst möglicherweise abgestürzt",
                "watchdog_lock_file": lock_state.get("lock_path"),
                "watchdog_lock_age_seconds": lock_state.get("lock_age_seconds"),
            }

        heartbeat_issue = _load_heartbeat()
        if heartbeat_issue.get("status") == "fresh" and lock_issue is None:
            logger.info(
                "Heartbeat fresh: age=%s sec, threshold=%s sec",
                heartbeat_issue.get("age_seconds"),
                MAX_HEARTBEAT_AGE_SECONDS,
            )
            logger.info("Heartbeat fresh")
            return {
                "status": "completed",
                "exit_code": 0,
                "timestamp": _timestamp_for_payload(),
                "lock_path": lock_state.get("lock_path"),
                "escalation_path": None,
                "heartbeat_state": "fresh",
                "heartbeat_age_seconds": heartbeat_issue.get("age_seconds"),
            }

        if heartbeat_issue.get("status") in {"missing", "unreadable", "invalid", "stale"} or lock_issue is not None:
            timestamp = _timestamp_for_payload()
            payload = _build_escalation_payload(timestamp, heartbeat_issue, lock_issue)
            escalation_path = _write_escalation(payload)
            _send_webhook(logger, escalation_path)

            if lock_issue is not None:
                logger.warning(
                    "[ESCALATION] Watchdog lock stale: age=%s sec, threshold=%s sec",
                    lock_state.get("lock_age_seconds"),
                    LOCK_STALE_SECONDS,
                )
            elif heartbeat_issue.get("status") == "stale":
                logger.warning(
                    "[ESCALATION] Heartbeat stale: age=%s sec, threshold=%s sec",
                    heartbeat_issue.get("age_seconds"),
                    MAX_HEARTBEAT_AGE_SECONDS,
                )
            else:
                logger.warning(
                    "[ESCALATION] Heartbeat issue: %s",
                    heartbeat_issue.get("human_reason") or heartbeat_issue.get("reason"),
                )
            logger.info("Escalation triggered")
            return {
                "status": "completed",
                "exit_code": 0,
                "timestamp": timestamp,
                "lock_path": lock_state.get("lock_path"),
                "escalation_path": str(escalation_path),
                "heartbeat_state": heartbeat_issue.get("status"),
                "heartbeat_age_seconds": heartbeat_issue.get("age_seconds"),
                "reason": payload["reason"],
            }

        logger.info("Heartbeat fresh")
        return {
            "status": "completed",
            "exit_code": 0,
            "timestamp": _timestamp_for_payload(),
            "lock_path": lock_state.get("lock_path"),
            "escalation_path": None,
            "heartbeat_state": heartbeat_issue.get("status"),
            "heartbeat_age_seconds": heartbeat_issue.get("age_seconds"),
        }
    except Exception as exc:
        logger.exception("Watchdog internal error: %s", exc)
        return {
            "status": "error",
            "exit_code": 1,
            "timestamp": _timestamp_for_payload(),
            "lock_path": lock_state.get("lock_path"),
            "escalation_path": str(escalation_path) if escalation_path is not None else None,
            "heartbeat_state": heartbeat_issue.get("status") if heartbeat_issue else None,
        }
    finally:
        if lock_owned:
            _release_lock(logger)


def main() -> int:
    result = run_watchdog()
    return int(result.get("exit_code", 1))


if __name__ == "__main__":
    raise SystemExit(main())
