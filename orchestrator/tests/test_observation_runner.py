from __future__ import annotations

import importlib
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

import observation_common as oc
import observation_runner as runner


MAX_HISTORY_ENTRIES = runner.MAX_HISTORY_ENTRIES


@dataclass
class FakeCompletedProcess:
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""


@pytest.fixture()
def isolated_runner(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    runtime_root = tmp_path / "runtime"
    state_dir = runtime_root / "state"
    logs_dir = runtime_root / "logs"
    reports_dir = runtime_root / "reports"
    escalations_dir = runtime_root / "escalations"
    config_dir = runtime_root / "config"
    cron_dir = runtime_root / "cron"
    tmp_dir = runtime_root / "tmp"
    lock_dir = state_dir / "locks"

    for path in [state_dir, logs_dir, reports_dir, escalations_dir, config_dir, cron_dir, tmp_dir, lock_dir]:
        path.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(runner, "STATE_FILE", state_dir / "observation_state.json")
    monkeypatch.setattr(runner, "HEARTBEAT_FILE", state_dir / "heartbeat_observation.json")
    monkeypatch.setattr(runner, "LOCK_DIR", lock_dir)
    monkeypatch.setattr(runner, "REPORTS_DIR", reports_dir)
    monkeypatch.setattr(runner, "ESCALATIONS_DIR", escalations_dir)
    monkeypatch.setattr(runner, "LOG_FILE", logs_dir / "observation.log")
    monkeypatch.setattr(runner, "EXPECTED_STATE_FILE", config_dir / "expected_state.json")
    monkeypatch.setattr(runner, "CRON_REGISTRY_FILE", cron_dir / "jobs.json")
    monkeypatch.setattr(runner, "TMP_DIR", tmp_dir)

    monkeypatch.setattr(runner, "MAX_HISTORY_ENTRIES", MAX_HISTORY_ENTRIES)

    expected_state = oc.default_expected_state()
    expected_state["expected_containers"] = [
        "hermes-green",
        "trading-guardian",
        "freqtrade-regime-hybrid",
        "freqtrade-freqforge-canary",
        "freqtrade-freqforge",
        "freqtrade-webserver",
        "ai-hedge-fund-crypto",
        "freqai-rebel",
    ]
    oc.write_json_atomic(runner.EXPECTED_STATE_FILE, expected_state)

    return SimpleNamespace(
        runtime_root=runtime_root,
        state_dir=state_dir,
        logs_dir=logs_dir,
        reports_dir=reports_dir,
        escalations_dir=escalations_dir,
        config_dir=config_dir,
        cron_dir=cron_dir,
        tmp_dir=tmp_dir,
        lock_dir=lock_dir,
    )


@pytest.fixture()
def fake_subprocess(monkeypatch: pytest.MonkeyPatch):
    calls: list[tuple[list[str], dict[str, Any]]] = []

    def _fake_run(cmd, *args, **kwargs):
        calls.append((list(cmd), kwargs))
        if list(cmd)[:2] == ["docker", "ps"]:
            return FakeCompletedProcess(
                0,
                "NAMES\tSTATUS\tHEALTH\n"
                "hermes-green\tUp 2 hours\thealthy\n"
                "trading-guardian\tUp 2 hours\thealthy\n"
                "freqtrade-regime-hybrid\tUp 2 hours\thealthy\n"
                "freqtrade-freqforge-canary\tUp 2 hours\thealthy\n"
                "freqtrade-freqforge\tUp 2 hours\thealthy\n"
                "freqtrade-webserver\tUp 2 hours\thealthy\n"
                "ai-hedge-fund-crypto\tUp 2 hours\thealthy\n"
                "freqai-rebel\tUp 2 hours\thealthy\n",
                "",
            )
        if cmd and cmd[0] == "curl":
            return FakeCompletedProcess(0, "ok", "")
        return FakeCompletedProcess(0, "", "")

    monkeypatch.setattr(runner.subprocess, "run", _fake_run)
    return calls


def _write_registry(path: Path, jobs: list[dict[str, Any]]) -> None:
    oc.write_json_atomic(path, {"jobs": jobs})


def _read_latest_json(directory: Path) -> dict[str, Any]:
    files = sorted(directory.glob("*.json"))
    assert files, f"No json files in {directory}"
    return oc.read_json(files[-1])


def _cycle_with_registry(isolated_runner, fake_subprocess, registry_jobs: list[dict[str, Any]], **kwargs):
    _write_registry(isolated_runner.cron_dir / "jobs.json", registry_jobs)
    return runner.run_cycle(**kwargs)


def test_active_lock_causes_silent_skip(isolated_runner, fake_subprocess, monkeypatch):
    lock_path = isolated_runner.lock_dir / "observation.lock"
    lock_path.mkdir(parents=True, exist_ok=True)
    (lock_path / "pid").write_text(str(os.getpid()), encoding="utf-8")
    (lock_path / "timestamp").write_text("2026-06-02T15:00:00Z", encoding="utf-8")
    now = datetime.now(timezone.utc).timestamp()
    os.utime(lock_path, (now, now))
    monkeypatch.setattr(runner.os, "kill", lambda pid, sig: None)

    result = _cycle_with_registry(
        isolated_runner,
        fake_subprocess,
        [{"command": "cron_a", "schedule": "* * * * *", "owner": "hermes", "last_exitcode": 0}],
    )

    assert result["status"] == "skipped"
    assert result["exit_code"] == 0
    assert not list(isolated_runner.reports_dir.glob("*.json"))
    assert not list(isolated_runner.escalations_dir.glob("*.json"))


def test_stale_lock_creates_escalation_and_overwrites(isolated_runner, fake_subprocess, monkeypatch):
    lock_path = isolated_runner.lock_dir / "observation.lock"
    lock_path.mkdir(parents=True, exist_ok=True)
    (lock_path / "pid").write_text("999999", encoding="utf-8")
    (lock_path / "timestamp").write_text("2026-06-02T14:00:00Z", encoding="utf-8")
    old = (datetime.now(timezone.utc) - timedelta(minutes=11)).timestamp()
    os.utime(lock_path, (old, old))
    monkeypatch.setattr(runner.os, "kill", lambda pid, sig: (_ for _ in ()).throw(ProcessLookupError()))
    monkeypatch.setattr(runner, "_release_lock", lambda logger: None)

    result = _cycle_with_registry(
        isolated_runner,
        fake_subprocess,
        [{"command": "cron_a", "schedule": "* * * * *", "owner": "hermes", "last_exitcode": 0}],
    )

    assert result["status"] == "completed"
    assert result["escalation_path"] is not None
    assert Path(result["escalation_path"]).exists()
    escalation = oc.read_json(result["escalation_path"])
    assert escalation["issues"][0]["type"] == "D"
    assert "stale" in escalation["reason"].lower()
    assert (lock_path / "pid").exists()
    assert (lock_path / "timestamp").exists()


def test_missing_expected_state_sets_degraded_and_warns(monkeypatch, tmp_path, fake_subprocess):
    isolated = SimpleNamespace()
    runtime_root = tmp_path / "runtime"
    for sub in ["state/locks", "logs", "reports", "escalations", "config", "cron", "tmp"]:
        (runtime_root / sub).mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(runner, "STATE_FILE", runtime_root / "state" / "observation_state.json")
    monkeypatch.setattr(runner, "HEARTBEAT_FILE", runtime_root / "state" / "heartbeat_observation.json")
    monkeypatch.setattr(runner, "LOCK_DIR", runtime_root / "state" / "locks")
    monkeypatch.setattr(runner, "REPORTS_DIR", runtime_root / "reports")
    monkeypatch.setattr(runner, "ESCALATIONS_DIR", runtime_root / "escalations")
    monkeypatch.setattr(runner, "LOG_FILE", runtime_root / "logs" / "observation.log")
    monkeypatch.setattr(runner, "EXPECTED_STATE_FILE", runtime_root / "config" / "expected_state.json")
    monkeypatch.setattr(runner, "CRON_REGISTRY_FILE", runtime_root / "cron" / "jobs.json")
    monkeypatch.setattr(runner, "TMP_DIR", runtime_root / "tmp")
    monkeypatch.setattr(runner.os, "kill", lambda pid, sig: None)

    _write_registry(runner.CRON_REGISTRY_FILE, [{"command": "cron_a", "schedule": "* * * * *", "owner": "hermes", "last_exitcode": 0}])
    result = runner.run_cycle()

    report = oc.read_json(result["report_path"])
    assert report["config_missing"] is True
    assert report["system_health"]["overall_status"] == "degraded"
    assert any("expected_state" in warning.lower() for warning in report["warnings"])


def test_cron_registry_missing_uses_fallback(monkeypatch, tmp_path, fake_subprocess):
    runtime_root = tmp_path / "runtime"
    for sub in ["state/locks", "logs", "reports", "escalations", "config", "cron", "tmp"]:
        (runtime_root / sub).mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(runner, "STATE_FILE", runtime_root / "state" / "observation_state.json")
    monkeypatch.setattr(runner, "HEARTBEAT_FILE", runtime_root / "state" / "heartbeat_observation.json")
    monkeypatch.setattr(runner, "LOCK_DIR", runtime_root / "state" / "locks")
    monkeypatch.setattr(runner, "REPORTS_DIR", runtime_root / "reports")
    monkeypatch.setattr(runner, "ESCALATIONS_DIR", runtime_root / "escalations")
    monkeypatch.setattr(runner, "LOG_FILE", runtime_root / "logs" / "observation.log")
    monkeypatch.setattr(runner, "EXPECTED_STATE_FILE", runtime_root / "config" / "expected_state.json")
    monkeypatch.setattr(runner, "CRON_REGISTRY_FILE", runtime_root / "cron" / "jobs.json")
    monkeypatch.setattr(runner, "TMP_DIR", runtime_root / "tmp")
    monkeypatch.setattr(runner.os, "kill", lambda pid, sig: None)
    monkeypatch.setattr(oc, "load_cron_fallback", lambda: {"source": "fallback", "entries": [{"source": "crontab", "line": "* * * * * /bin/true"}]})

    result = runner.run_cycle()
    report = oc.read_json(result["report_path"])

    assert report["cron_source"] == "fallback_crontab"
    assert report["cron_jobs"]
    assert report["cron_jobs"][0]["source"] == "fallback"


def test_container_unhealthy_scores_issue_and_escalates(isolated_runner, fake_subprocess):
    _write_registry(
        isolated_runner.cron_dir / "jobs.json",
        [{"command": "cron_a", "schedule": "* * * * *", "owner": "hermes", "last_exitcode": 0}],
    )

    def _docker_ps(*args, **kwargs):
        return FakeCompletedProcess(
            0,
            "NAMES\tSTATUS\tHEALTH\n"
            "hermes-green\tUp 2 hours\thealthy\n"
            "trading-guardian\tUp 2 hours\thealthy\n"
            "freqtrade-regime-hybrid\tUp 2 hours\thealthy\n"
            "freqtrade-freqforge-canary\tUp 2 hours\tunhealthy\n"
            "freqtrade-freqforge\tUp 2 hours\thealthy\n"
            "freqtrade-webserver\tUp 2 hours\thealthy\n"
            "ai-hedge-fund-crypto\tUp 2 hours\thealthy\n"
            "freqai-rebel\tUp 2 hours\thealthy\n",
            "",
        )

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(runner.subprocess, "run", _docker_ps)
    try:
        result = runner.run_cycle()
        report = oc.read_json(result["report_path"])
    finally:
        monkeypatch.undo()

    assert report["system_health"]["container_score"] == 70
    assert report["system_health"]["overall_status"] == "degraded"
    issue = next(i for i in report["detected_issues"] if i["type"] == "A")
    assert issue["confidence"] == 90
    assert result["escalation_path"] is not None


def test_signal_stale_reduces_pipeline_score_and_creates_type_c_issue(isolated_runner, fake_subprocess):
    _write_registry(
        isolated_runner.cron_dir / "jobs.json",
        [{"command": "cron_a", "schedule": "* * * * *", "owner": "hermes", "last_exitcode": 0}],
    )
    signal = isolated_runner.state_dir / "signals" / "last_signal_001.json"
    signal.parent.mkdir(parents=True, exist_ok=True)
    signal.write_text("{}", encoding="utf-8")
    old = (datetime.now(timezone.utc) - timedelta(seconds=901)).timestamp()
    os.utime(signal, (old, old))

    result = runner.run_cycle()
    report = oc.read_json(result["report_path"])

    assert report["system_health"]["pipeline_score"] == 70
    issue = next(i for i in report["detected_issues"] if i["type"] == "C")
    assert "stale" in issue["description"].lower()
    assert issue["confidence"] >= 85


def test_webhook_called_on_critical(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    runtime_root = tmp_path / "runtime"
    for sub in ["state/locks", "logs", "reports", "escalations", "config", "cron", "tmp"]:
        (runtime_root / sub).mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(runner, "STATE_FILE", runtime_root / "state" / "observation_state.json")
    monkeypatch.setattr(runner, "HEARTBEAT_FILE", runtime_root / "state" / "heartbeat_observation.json")
    monkeypatch.setattr(runner, "LOCK_DIR", runtime_root / "state" / "locks")
    monkeypatch.setattr(runner, "REPORTS_DIR", runtime_root / "reports")
    monkeypatch.setattr(runner, "ESCALATIONS_DIR", runtime_root / "escalations")
    monkeypatch.setattr(runner, "LOG_FILE", runtime_root / "logs" / "observation.log")
    monkeypatch.setattr(runner, "EXPECTED_STATE_FILE", runtime_root / "config" / "expected_state.json")
    monkeypatch.setattr(runner, "CRON_REGISTRY_FILE", runtime_root / "cron" / "jobs.json")
    monkeypatch.setattr(runner, "TMP_DIR", runtime_root / "tmp")
    monkeypatch.setenv("HERMES_ALERT_WEBHOOK", "https://example.invalid/webhook")
    monkeypatch.setattr(runner.os, "kill", lambda pid, sig: None)

    _write_registry(
        runner.CRON_REGISTRY_FILE,
        [{"command": "cron_a", "schedule": "* * * * *", "owner": "hermes", "last_exitcode": 1}],
    )

    calls: list[list[str]] = []

    def _fake_run(cmd, *args, **kwargs):
        calls.append(list(cmd))
        if list(cmd)[:2] == ["docker", "ps"]:
            return FakeCompletedProcess(
                0,
                "NAMES\tSTATUS\tHEALTH\n"
                "hermes-green\tUp 2 hours\thealthy\n"
                "trading-guardian\tUp 2 hours\thealthy\n"
                "freqtrade-regime-hybrid\tUp 2 hours\thealthy\n"
                "freqtrade-freqforge-canary\tUp 2 hours\thealthy\n"
                "freqtrade-freqforge\tUp 2 hours\thealthy\n"
                "freqtrade-webserver\tUp 2 hours\thealthy\n"
                "ai-hedge-fund-crypto\tUp 2 hours\thealthy\n"
                "freqai-rebel\tUp 2 hours\thealthy\n",
                "",
            )
        if cmd and cmd[0] == "curl":
            return FakeCompletedProcess(0, "ok", "")
        return FakeCompletedProcess(0, "", "")

    monkeypatch.setattr(runner.subprocess, "run", _fake_run)
    result = runner.run_cycle()

    assert result["overall_status"] == "critical"
    assert any(call and call[0] == "curl" for call in calls)
    assert result["escalation_path"] is not None


def test_state_persistence_and_history_trim(isolated_runner, fake_subprocess):
    previous_history = [
        {
            "timestamp": f"2026-06-02T14:{i:02d}:00Z",
            "container_score": 100,
            "pipeline_score": 100,
            "overall_status": "healthy",
            "issues": [],
        }
        for i in range(MAX_HISTORY_ENTRIES + 10)
    ]
    oc.write_json_atomic(
        isolated_runner.state_dir / "observation_state.json",
        {
            "last_successful_cycle": "2026-06-02T14:00:00Z",
            "history": previous_history,
            "open_issues": [],
            "last_cron_exitcodes": {"cron_a": [{"timestamp": "2026-06-02T14:55:00Z", "exitcode": 1}]},
            "last_report_path": None,
            "last_escalation_path": None,
            "overall_status": "degraded",
        },
    )
    _write_registry(
        isolated_runner.cron_dir / "jobs.json",
        [{"command": "cron_a", "schedule": "* * * * *", "owner": "hermes", "last_exitcode": 1}],
    )

    result = runner.run_cycle()
    state = oc.read_json(result["state_path"])

    assert len(state["history"]) == MAX_HISTORY_ENTRIES
    assert state["last_successful_cycle"] == result["timestamp"]
    assert state["last_status"] == result["overall_status"]
    assert state["last_cron_exitcodes"]["cron_a"][-1]["exitcode"] == 1


def test_no_cron_jobs_results_in_critical_and_escalation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    runtime_root = tmp_path / "runtime"
    for sub in ["state/locks", "logs", "reports", "escalations", "config", "cron", "tmp"]:
        (runtime_root / sub).mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(runner, "STATE_FILE", runtime_root / "state" / "observation_state.json")
    monkeypatch.setattr(runner, "HEARTBEAT_FILE", runtime_root / "state" / "heartbeat_observation.json")
    monkeypatch.setattr(runner, "LOCK_DIR", runtime_root / "state" / "locks")
    monkeypatch.setattr(runner, "REPORTS_DIR", runtime_root / "reports")
    monkeypatch.setattr(runner, "ESCALATIONS_DIR", runtime_root / "escalations")
    monkeypatch.setattr(runner, "LOG_FILE", runtime_root / "logs" / "observation.log")
    monkeypatch.setattr(runner, "EXPECTED_STATE_FILE", runtime_root / "config" / "expected_state.json")
    monkeypatch.setattr(runner, "CRON_REGISTRY_FILE", runtime_root / "cron" / "jobs.json")
    monkeypatch.setattr(runner, "TMP_DIR", runtime_root / "tmp")
    monkeypatch.setattr(runner.os, "kill", lambda pid, sig: None)
    monkeypatch.setattr(oc, "load_cron_fallback", lambda: {"source": "fallback", "entries": []})

    def _fake_run(cmd, *args, **kwargs):
        if list(cmd)[:2] == ["docker", "ps"]:
            return FakeCompletedProcess(0, "NAMES\tSTATUS\tHEALTH\n", "")
        return FakeCompletedProcess(0, "", "")

    monkeypatch.setattr(runner.subprocess, "run", _fake_run)
    result = runner.run_cycle()
    report = oc.read_json(result["report_path"])

    assert report["cron_jobs"] == []
    assert report["system_health"]["pipeline_score"] == 0
    assert report["system_health"]["overall_status"] == "critical"
    assert result["escalation_path"] is not None


def test_report_and_heartbeat_written_on_success(isolated_runner, fake_subprocess):
    _write_registry(
        isolated_runner.cron_dir / "jobs.json",
        [{"command": "cron_a", "schedule": "* * * * *", "owner": "hermes", "last_exitcode": 0}],
    )
    result = runner.run_cycle()

    report = oc.read_json(result["report_path"])
    heartbeat = oc.read_json(isolated_runner.state_dir / "heartbeat_observation.json")

    assert report["timestamp"] == result["timestamp"]
    assert report["mode"] == "report_only"
    assert heartbeat["overall_status"] == report["system_health"]["overall_status"]
    assert heartbeat["last_successful_cycle"] == result["timestamp"]
    assert isolated_runner.logs_dir.joinpath("observation.log").exists()
