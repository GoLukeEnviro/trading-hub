from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SELF_IMPROVEMENT_SRC = ROOT / "self_improvement_v2" / "src"
if str(SELF_IMPROVEMENT_SRC) not in sys.path:
    sys.path.insert(0, str(SELF_IMPROVEMENT_SRC))

from si_v2.cron.schema import CronDefsLoader  # noqa: E402

WRAPPER = ROOT / "orchestrator" / "scripts" / "si_v2_t4_watcher_cron.sh"
CRON_DEF = ROOT / "self_improvement_v2" / "cron_defs" / "t4_watcher_jobs.yaml"

FORBIDDEN = (
    "docker restart",
    "docker compose up",
    "execute_apply",
    "rollback",
    "freqtrade trade",
)


def _make_stub(tmp_path: Path, *, rc: int, body: str) -> Path:
    script = tmp_path / "stub-watcher.sh"
    script.write_text(f"#!/usr/bin/env bash\nprintf '%s\\n' '{body}'\nexit {rc}\n")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return script


def _run_wrapper(tmp_path: Path, stub: Path) -> subprocess.CompletedProcess[str]:
    log_dir = tmp_path / "logs"
    env = os.environ.copy()
    env.update(
        {
            "SI_V2_T4_WATCHER_CMD": str(stub),
            "SI_V2_T4_LOG_DIR": str(log_dir),
            "SI_V2_T4_REPO_ROOT": "/home/hermes/projects/trading",
        }
    )
    return subprocess.run(
        ["bash", str(WRAPPER)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_wrapper_exists_and_is_safe() -> None:
    content = WRAPPER.read_text()
    assert WRAPPER.exists()
    for token in FORBIDDEN:
        assert token not in content



def test_cron_definition_is_disabled_and_read_only() -> None:
    defs = CronDefsLoader.load(CRON_DEF)
    assert len(defs.jobs) == 1
    job = defs.jobs[0]
    assert job.job_id == "si_v2_t4_measurement_watch"
    assert job.schedule == "*/30 * * * *"
    assert job.command == "orchestrator/scripts/si_v2_t4_watcher_cron.sh"
    assert job.enabled_default is False
    assert job.dry_run_only is True
    assert job.no_agent is True



def test_wrapper_treats_still_waiting_as_ok_and_silent(tmp_path: Path) -> None:
    stub = _make_stub(
        tmp_path,
        rc=0,
        body="SI_V2_T4_STATUS=STILL_WAITING\nNEXT_STEP=wait_for_canary_close",
    )
    proc = _run_wrapper(tmp_path, stub)
    assert proc.returncode == 0
    assert proc.stdout == ""
    cron_log = (tmp_path / "logs" / "cron.log").read_text()
    assert "status=STILL_WAITING" in cron_log
    run_logs = list((tmp_path / "logs" / "runs").glob("t4-watcher-*.log"))
    assert len(run_logs) == 1



def test_wrapper_emits_local_alert_for_measurement_ready(tmp_path: Path) -> None:
    stub = _make_stub(
        tmp_path,
        rc=10,
        body="SI_V2_T4_STATUS=MEASUREMENT_READY\nNEXT_STEP=run_measurement_decision_engine_read_only",
    )
    proc = _run_wrapper(tmp_path, stub)
    assert proc.returncode == 0
    assert "SI_V2_T4_ALERT=MEASUREMENT_READY" in proc.stdout
    alerts = list((tmp_path / "logs" / "alerts").glob("measurement_ready-*.log"))
    assert len(alerts) == 1
    assert "MEASUREMENT_READY" in alerts[0].read_text()



def test_wrapper_returns_error_for_data_unavailable(tmp_path: Path) -> None:
    stub = _make_stub(
        tmp_path,
        rc=30,
        body="SI_V2_T4_STATUS=DATA_UNAVAILABLE\nNEXT_STEP=inspect_data_sources",
    )
    proc = _run_wrapper(tmp_path, stub)
    assert proc.returncode == 1
    assert "SI_V2_T4_ALERT=DATA_UNAVAILABLE" in proc.stdout
    alerts = list((tmp_path / "logs" / "alerts").glob("data_unavailable-*.log"))
    assert len(alerts) == 1
    cron_log = (tmp_path / "logs" / "cron.log").read_text()
    assert "status=DATA_UNAVAILABLE" in cron_log
