from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "orchestrator/scripts/si_v2_t4_watcher_job.sh"


def _make_stub(tmp_path: Path, exit_code: int, *lines: str) -> Path:
    stub = tmp_path / f"stub_{exit_code}.sh"
    body = ["#!/usr/bin/env bash", "set -euo pipefail"]
    body.extend(f"echo {line!r}" for line in lines)
    body.append(f"exit {exit_code}")
    stub.write_text("\n".join(body) + "\n", encoding="utf-8")
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    return stub


def _run_wrapper(tmp_path: Path, stub: Path) -> subprocess.CompletedProcess[str]:
    log_dir = tmp_path / "logs"
    env = os.environ.copy()
    env["SI_V2_REPO_ROOT"] = str(ROOT)
    env["SI_V2_T4_WATCHER_SCRIPT"] = str(stub)
    env["SI_V2_T4_WATCHER_LOG_DIR"] = str(log_dir)
    return subprocess.run(
        ["bash", str(WRAPPER)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_still_waiting_is_silent_and_ok(tmp_path: Path) -> None:
    stub = _make_stub(tmp_path, 0, "SI_V2_T4_STATUS=STILL_WAITING")
    result = _run_wrapper(tmp_path, stub)
    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""
    latest_log = (tmp_path / "logs/latest.log").read_text(encoding="utf-8")
    assert "underlying_exit_code=0" in latest_log
    assert "SI_V2_T4_STATUS=STILL_WAITING" in latest_log


def test_measurement_ready_alerts_without_scheduler_error(tmp_path: Path) -> None:
    stub = _make_stub(
        tmp_path,
        10,
        "SI_V2_T4_STATUS=MEASUREMENT_READY",
        "CANARY_CLOSED_SINCE_T3=1",
    )
    result = _run_wrapper(tmp_path, stub)
    assert result.returncode == 0
    assert "SI_V2_T4_WATCHER_ALERT=MEASUREMENT_READY" in result.stdout
    assert "SI_V2_T4_STATUS=MEASUREMENT_READY" in result.stdout
    latest_log = (tmp_path / "logs/latest.log").read_text(encoding="utf-8")
    assert "underlying_exit_code=10" in latest_log


def test_safety_blocked_stays_non_mutating_failure(tmp_path: Path) -> None:
    stub = _make_stub(tmp_path, 20, "SI_V2_T4_STATUS=SAFETY_BLOCKED")
    result = _run_wrapper(tmp_path, stub)
    assert result.returncode == 20
    assert "SI_V2_T4_WATCHER_ALERT=SAFETY_BLOCKED" in result.stdout
    latest_log = (tmp_path / "logs/latest.log").read_text(encoding="utf-8")
    assert "underlying_exit_code=20" in latest_log


def test_wrapper_declares_expected_log_path_contract() -> None:
    content = WRAPPER.read_text(encoding="utf-8")
    assert "/opt/data/logs/si-v2-t4-watcher" in content
    assert "SI_V2_T4_WATCHER_ALERT=MEASUREMENT_READY" in content
    assert "SI_V2_T4_WATCHER_ALERT=SAFETY_BLOCKED" in content
    assert "run_measurement_decision_engine_read_only" not in content
    assert "execute_apply" not in content
    assert "docker restart" not in content
