from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = {
    "active_cycle_cron": ROOT / "orchestrator/scripts/si_v2_active_cycle_cron.sh",
    "active_cycle_runner": ROOT / "orchestrator/scripts/si-v2-active-cycle-runner.sh",
    "t4_watcher": ROOT / "orchestrator/scripts/si_v2_t4_measurement_watcher.sh",
}

FORBIDDEN_TOKENS = [
    "docker restart",
    "docker compose up",
    "execute_apply",
    "run_controlled_apply",
    "execute_canary_rollback",
    'dry_run": false',
    "APPROVE_SI_V2_RUNTIME_ACTUATOR_ACTIVATION=APPROVE",
]

STATUS_KEYS = [
    "SI_V2_T4_STATUS=",
    "CANARY_CLOSED_SINCE_T3=",
    "CONTROL_CLOSED_SINCE_T3=",
    "CANARY_OPEN_TRADES=",
    "MEASUREMENT_DECISION_ENGINE_ALLOWED=",
]

SECRET_MARKERS = [
    "gho_",
    "-----BEGIN",
    '"password": "',
    '"api_key": "',
    '"secret": "',
]


def _read(name: str) -> str:
    return SCRIPTS[name].read_text(encoding="utf-8")


def test_scheduler_scripts_exist() -> None:
    missing = [str(path) for path in SCRIPTS.values() if not path.exists()]
    assert not missing, f"missing scripts: {missing}"


def test_scheduler_scripts_contain_no_forbidden_tokens() -> None:
    combined = "\n".join(_read(name) for name in SCRIPTS)
    for token in FORBIDDEN_TOKENS:
        assert token not in combined, f"forbidden token leaked into scheduler scripts: {token}"


def test_scheduler_scripts_contain_no_secret_markers() -> None:
    combined = "\n".join(_read(name) for name in SCRIPTS)
    for marker in SECRET_MARKERS:
        assert marker not in combined, f"secret marker found in script content: {marker}"


def test_t4_watcher_declares_required_exit_codes() -> None:
    watcher = _read("t4_watcher")
    for code in ("0", "10", "20", "30", "40"):
        assert f"= {code}" in watcher or f"={code}" in watcher


def test_t4_watcher_emits_required_status_keys() -> None:
    watcher = _read("t4_watcher")
    for key in STATUS_KEYS:
        assert key in watcher, f"missing status key in watcher: {key}"


def test_active_cycle_wrapper_points_to_python_runner() -> None:
    runner = _read("active_cycle_runner")
    assert 'RUNNER="src/si_v2/loop/active_cycle_runner.py"' in runner
    assert 'PYTHONPATH=src "${VENV_PY}" "${RUNNER}"' in runner


def test_active_cycle_cron_points_to_runtime_wrapper() -> None:
    cron = _read("active_cycle_cron")
    assert "/opt/data/scripts/si-v2-active-cycle-runner.sh" in cron
    assert "cron.log" in cron


def test_t4_watcher_does_not_execute_decision_engine() -> None:
    watcher = _read("t4_watcher")
    assert "run_measurement_decision_engine_read_only" in watcher
    assert "decision_engine.py" not in watcher
    assert "python -m" not in watcher
