from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import observation_watchdog as watchdog


@dataclass
class FakeCompletedProcess:
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""


@pytest.fixture()
def isolated_watchdog(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    runtime_root = tmp_path / "runtime"
    state_dir = runtime_root / "state"
    logs_dir = runtime_root / "logs"
    escalations_dir = runtime_root / "escalations"
    lock_dir = state_dir / "locks"

    for path in [state_dir, logs_dir, escalations_dir, lock_dir]:
        path.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(watchdog, "HEARTBEAT_FILE", str(state_dir / "heartbeat_observation.json"))
    monkeypatch.setattr(watchdog, "LOCK_DIR", str(lock_dir))
    monkeypatch.setattr(watchdog, "ESCALATIONS_DIR", str(escalations_dir))
    monkeypatch.setattr(watchdog, "LOG_FILE", str(logs_dir / "observation_watchdog.log"))

    fixed_now = datetime(2026, 6, 2, 16, 45, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(watchdog, "_utc_now", lambda: fixed_now)
    monkeypatch.setattr(watchdog, "_local_now", lambda: fixed_now)

    calls: list[tuple[list[str], dict[str, Any]]] = []

    def fake_run(cmd, *args, **kwargs):
        calls.append((list(cmd), kwargs))
        if cmd and cmd[0] == "curl":
            return FakeCompletedProcess(0, "ok", "")
        return FakeCompletedProcess(0, "", "")

    monkeypatch.setattr(watchdog.subprocess, "run", fake_run)

    return SimpleNamespace(
        runtime_root=runtime_root,
        state_dir=state_dir,
        logs_dir=logs_dir,
        escalations_dir=escalations_dir,
        lock_dir=lock_dir,
        fixed_now=fixed_now,
        calls=calls,
    )


def _write_heartbeat(path: Path, last_successful_cycle: str, overall_status: str | None = "healthy") -> None:
    payload: dict[str, Any] = {"last_successful_cycle": last_successful_cycle}
    if overall_status is not None:
        payload["overall_status"] = overall_status
    path.write_text(json.dumps(payload), encoding="utf-8")


def _latest_escalation(directory: Path) -> Path:
    files = sorted(directory.glob("watchdog_escalation_*.json"))
    assert files, f"no escalation files in {directory}"
    return files[-1]


def test_fresh_heartbeat_creates_no_escalation_and_releases_lock(isolated_watchdog):
    heartbeat_path = Path(watchdog.HEARTBEAT_FILE)
    fresh = (isolated_watchdog.fixed_now - timedelta(minutes=5)).isoformat(timespec="seconds")
    _write_heartbeat(heartbeat_path, fresh, "healthy")

    result = watchdog.run_watchdog()

    assert result["exit_code"] == 0
    assert result["escalation_path"] is None
    assert not list(isolated_watchdog.escalations_dir.glob("*.json"))
    assert not (isolated_watchdog.lock_dir / "watchdog.lock").exists()
    log_text = Path(watchdog.LOG_FILE).read_text(encoding="utf-8")
    assert "Heartbeat fresh" in log_text
    assert "Escalation triggered" not in log_text


def test_stale_heartbeat_writes_escalation_and_calls_webhook(isolated_watchdog, monkeypatch: pytest.MonkeyPatch):
    heartbeat_path = Path(watchdog.HEARTBEAT_FILE)
    stale = (isolated_watchdog.fixed_now - timedelta(minutes=20)).isoformat(timespec="seconds")
    _write_heartbeat(heartbeat_path, stale, "healthy")
    monkeypatch.setenv("HERMES_ALERT_WEBHOOK", "https://example.invalid/webhook")

    result = watchdog.run_watchdog()

    assert result["exit_code"] == 0
    assert result["escalation_path"] is not None
    escalation_path = Path(result["escalation_path"])
    assert escalation_path.exists()
    payload = json.loads(escalation_path.read_text(encoding="utf-8"))
    assert payload["agent_id"] == "hermes-trading-observation-watchdog-phase1"
    assert payload["severity"] == "critical"
    assert payload["reason"] == "observation_runner_heartbeat_stale"
    assert payload["details"]["heartbeat_file"] == str(heartbeat_path)
    assert payload["details"]["runner_last_status"] == "healthy"
    assert payload["details"]["age_seconds"] > watchdog.MAX_HEARTBEAT_AGE_SECONDS
    assert payload["details"]["threshold_seconds"] == watchdog.MAX_HEARTBEAT_AGE_SECONDS
    assert any(call and call[0][0] == "curl" for call in isolated_watchdog.calls)
    log_text = Path(watchdog.LOG_FILE).read_text(encoding="utf-8")
    assert "[ESCALATION] Heartbeat stale" in log_text
    assert "Escalation triggered" in log_text


def test_missing_heartbeat_file_triggers_missing_escalation(isolated_watchdog):
    result = watchdog.run_watchdog()

    assert result["exit_code"] == 0
    escalation_path = Path(result["escalation_path"])
    assert escalation_path.exists()
    payload = json.loads(escalation_path.read_text(encoding="utf-8"))
    assert payload["reason"] == "heartbeat_file_missing"
    assert payload["details"]["human_reason"] == "Heartbeat-Datei fehlt"
    assert payload["details"]["last_heartbeat"] is None
    assert payload["details"]["age_seconds"] is None


def test_corrupt_heartbeat_file_triggers_unreadable_escalation(isolated_watchdog):
    heartbeat_path = Path(watchdog.HEARTBEAT_FILE)
    heartbeat_path.write_text("{not-json", encoding="utf-8")

    result = watchdog.run_watchdog()

    assert result["exit_code"] == 0
    escalation_path = Path(result["escalation_path"])
    assert escalation_path.exists()
    payload = json.loads(escalation_path.read_text(encoding="utf-8"))
    assert payload["reason"] == "heartbeat_file_unreadable"
    assert payload["details"]["human_reason"] == "Heartbeat-Datei fehlt oder ist unlesbar"


def test_active_young_lock_skips_cycle_without_alarm(isolated_watchdog):
    heartbeat_path = Path(watchdog.HEARTBEAT_FILE)
    stale = (isolated_watchdog.fixed_now - timedelta(minutes=25)).isoformat(timespec="seconds")
    _write_heartbeat(heartbeat_path, stale, "healthy")

    lock_path = isolated_watchdog.lock_dir / "watchdog.lock"
    lock_path.mkdir(parents=True, exist_ok=True)
    (lock_path / "pid").write_text(str(os.getpid()), encoding="utf-8")
    (lock_path / "timestamp").write_text("2026-06-02T16:40:00Z", encoding="utf-8")
    mtime = (isolated_watchdog.fixed_now - timedelta(minutes=2)).timestamp()
    os.utime(lock_path, (mtime, mtime))

    result = watchdog.run_watchdog()

    assert result["exit_code"] == 0
    assert result["status"] == "skipped"
    assert result["escalation_path"] is None
    assert not list(isolated_watchdog.escalations_dir.glob("*.json"))
    assert lock_path.exists()


def test_stale_lock_is_taken_over_and_escales_once(isolated_watchdog, monkeypatch: pytest.MonkeyPatch):
    heartbeat_path = Path(watchdog.HEARTBEAT_FILE)
    fresh = (isolated_watchdog.fixed_now - timedelta(minutes=3)).isoformat(timespec="seconds")
    _write_heartbeat(heartbeat_path, fresh, "healthy")
    monkeypatch.setenv("HERMES_ALERT_WEBHOOK", "https://example.invalid/webhook")

    lock_path = isolated_watchdog.lock_dir / "watchdog.lock"
    lock_path.mkdir(parents=True, exist_ok=True)
    (lock_path / "pid").write_text("999999", encoding="utf-8")
    (lock_path / "timestamp").write_text("2026-06-02T16:00:00Z", encoding="utf-8")
    mtime = (isolated_watchdog.fixed_now - timedelta(minutes=16)).timestamp()
    os.utime(lock_path, (mtime, mtime))

    result = watchdog.run_watchdog()

    assert result["exit_code"] == 0
    assert result["escalation_path"] is not None
    payload = json.loads(Path(result["escalation_path"]).read_text(encoding="utf-8"))
    assert payload["reason"] == "watchdog_lock_stale"
    assert payload["details"]["human_reason"] == "Watchdog selbst möglicherweise abgestürzt"
    assert payload["details"]["watchdog_lock_age_seconds"] > 15 * 60
    assert any(call and call[0][0] == "curl" for call in isolated_watchdog.calls)
    assert not lock_path.exists()


def test_webhook_failure_logs_but_keeps_escalation_file(isolated_watchdog, monkeypatch: pytest.MonkeyPatch):
    heartbeat_path = Path(watchdog.HEARTBEAT_FILE)
    stale = (isolated_watchdog.fixed_now - timedelta(minutes=20)).isoformat(timespec="seconds")
    _write_heartbeat(heartbeat_path, stale, "healthy")
    monkeypatch.setenv("HERMES_ALERT_WEBHOOK", "https://example.invalid/webhook")

    def fail_run(cmd, *args, **kwargs):
        isolated_watchdog.calls.append((list(cmd), kwargs))
        if cmd and cmd[0] == "curl":
            return FakeCompletedProcess(1, "", "curl failed")
        return FakeCompletedProcess(0, "", "")

    monkeypatch.setattr(watchdog.subprocess, "run", fail_run)

    result = watchdog.run_watchdog()

    assert result["exit_code"] == 0
    assert result["escalation_path"] is not None
    assert Path(result["escalation_path"]).exists()
    log_text = Path(watchdog.LOG_FILE).read_text(encoding="utf-8")
    assert "Webhook POST failed" in log_text


def test_missing_webhook_url_skips_curl_call(isolated_watchdog, monkeypatch: pytest.MonkeyPatch):
    heartbeat_path = Path(watchdog.HEARTBEAT_FILE)
    stale = (isolated_watchdog.fixed_now - timedelta(minutes=18)).isoformat(timespec="seconds")
    _write_heartbeat(heartbeat_path, stale, "healthy")
    monkeypatch.delenv("HERMES_ALERT_WEBHOOK", raising=False)

    result = watchdog.run_watchdog()

    assert result["exit_code"] == 0
    assert result["escalation_path"] is not None
    assert Path(result["escalation_path"]).exists()
    assert not any(call and call[0][0] == "curl" for call in isolated_watchdog.calls)


def test_naive_last_successful_cycle_is_treated_as_utc(isolated_watchdog):
    heartbeat_path = Path(watchdog.HEARTBEAT_FILE)
    naive = (isolated_watchdog.fixed_now - timedelta(minutes=4)).replace(tzinfo=None).isoformat(timespec="seconds")
    _write_heartbeat(heartbeat_path, naive, "healthy")

    result = watchdog.run_watchdog()

    assert result["exit_code"] == 0
    assert result["escalation_path"] is None
    assert not list(isolated_watchdog.escalations_dir.glob("*.json"))
