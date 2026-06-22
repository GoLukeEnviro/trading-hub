from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import observation_common as oc


def test_read_json_and_write_json_atomic_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "payload.json"
    payload = {"alpha": 1, "nested": {"beta": [1, 2, 3]}}

    oc.write_json_atomic(path, payload)

    assert path.exists()
    assert oc.read_json(path) == payload


def test_append_log_line_appends_newline(tmp_path: Path) -> None:
    log_path = tmp_path / "observation.log"
    log_path.write_text("first line\n", encoding="utf-8")

    oc.append_log_line(log_path, "second line")

    assert log_path.read_text(encoding="utf-8").splitlines() == ["first line", "second line"]


def test_parse_duration_from_status_handles_common_units() -> None:
    assert oc.parse_duration_from_status("Up 2 days") == 2 * 24 * 60 * 60
    assert oc.parse_duration_from_status("Up 5 hours") == 5 * 60 * 60
    assert oc.parse_duration_from_status("Up 17 minutes") == 17 * 60
    assert oc.parse_duration_from_status("Exited (0) 3 seconds ago") == 3


def test_parse_docker_ps_line_normalizes_status_and_health() -> None:
    parsed = oc.parse_docker_ps_line("freqtrade-webserver", "Up 5 days (healthy)", None)

    assert parsed["name"] == "freqtrade-webserver"
    assert parsed["state"] == "up"
    assert parsed["health"] == "healthy"
    assert parsed["duration_seconds"] == 5 * 24 * 60 * 60


def test_parse_docker_ps_line_prefers_unhealthy_over_healthy_substring() -> None:
    parsed = oc.parse_docker_ps_line("freqtrade-webserver", "Up 5 days (unhealthy)", None)

    assert parsed["health"] == "unhealthy"
    assert parsed["state"] == "up"


def test_acquire_and_release_lock(tmp_path: Path) -> None:
    lock_dir = tmp_path / "observation.lock"

    first = oc.acquire_lock(lock_dir, pid=1234, timestamp="2026-06-02T15:00:00Z")
    second = oc.acquire_lock(lock_dir, pid=5678, timestamp="2026-06-02T15:01:00Z")

    assert first is True
    assert second is False
    assert (lock_dir / "lock.json").exists()

    oc.release_lock(lock_dir)
    assert not lock_dir.exists()


def test_evaluate_container_health_counts_exited_containers() -> None:
    result = oc.evaluate_container_health(
        expected_containers=["a", "b"],
        docker_ps_rows=[
            {"name": "a", "status": "Up 2 hours", "health": "healthy"},
            {"name": "b", "status": "Exited (0) 3 minutes ago", "health": "none"},
        ],
    )

    assert result["missing_count"] == 0
    assert result["unhealthy_count"] == 1
    assert result["exited_count"] == 1
    assert result["container_score"] == 30


def test_evaluate_container_health_penalizes_missing_containers() -> None:
    result = oc.evaluate_container_health(
        expected_containers=["a", "b"],
        docker_ps_rows=[{"name": "a", "status": "Up 2 hours", "health": "healthy"}],
    )

    assert result["missing_count"] == 1
    assert result["unhealthy_count"] == 1
    assert result["exited_count"] == 0
    assert result["container_score"] == 70
    assert result["containers"][1]["state"] == "exited_or_missing"


def test_evaluate_signal_freshness_uses_latest_file(tmp_path: Path) -> None:
    older = tmp_path / "last_signal_2026-06-02T14-00-00.json"
    newer = tmp_path / "last_signal_2026-06-02T14-58-00.json"
    older.write_text("{}", encoding="utf-8")
    newer.write_text("{}", encoding="utf-8")

    reference_time = datetime(2026, 6, 2, 15, 0, 0, tzinfo=timezone.utc)
    os_time_newer = reference_time - timedelta(seconds=120)
    os_time_older = reference_time - timedelta(seconds=3600)
    os.utime(older, (os_time_older.timestamp(), os_time_older.timestamp()))
    os.utime(newer, (os_time_newer.timestamp(), os_time_newer.timestamp()))

    result = oc.evaluate_signal_freshness(str(tmp_path / "last_signal_*.json"), 600, reference_time=reference_time)

    assert result["latest_path"] == str(newer)
    assert result["age_seconds"] == 120
    assert result["stale"] is False


def test_evaluate_signal_freshness_marks_stale_latest_file(tmp_path: Path) -> None:
    signal = tmp_path / "last_signal_2026-06-02T14-40-00.json"
    signal.write_text("{}", encoding="utf-8")
    reference_time = datetime(2026, 6, 2, 15, 0, 0, tzinfo=timezone.utc)
    old = reference_time - timedelta(seconds=900)
    os.utime(signal, (old.timestamp(), old.timestamp()))

    result = oc.evaluate_signal_freshness(str(tmp_path / "last_signal_*.json"), 600, reference_time=reference_time)

    assert result["latest_path"] == str(signal)
    assert result["age_seconds"] == 900
    assert result["stale"] is True


def test_trim_history_keeps_last_items() -> None:
    history = [1, 2, 3, 4, 5]

    assert oc.trim_history(history, maxlen=3) == [3, 4, 5]
    assert oc.trim_history(history, maxlen=0) == []


def test_infer_job_exitcode_from_registry_fields() -> None:
    assert oc.infer_job_exitcode({"last_status": "ok", "last_error": None, "last_delivery_error": None}) == 0
    assert oc.infer_job_exitcode({"last_status": "ok", "last_error": "boom", "last_delivery_error": None}) == 1
    assert oc.infer_job_exitcode({"last_status": "failed", "last_error": None, "last_delivery_error": None}) == 1
    assert oc.infer_job_exitcode({"last_status": "scheduled", "last_error": None, "last_delivery_error": None}) is None


def test_resolve_signal_candidates_and_latest_mtime(tmp_path: Path) -> None:
    a = tmp_path / "last_signal_a.json"
    b = tmp_path / "last_signal_b.json"
    a.write_text("{}", encoding="utf-8")
    b.write_text("{}", encoding="utf-8")
    now = datetime(2026, 6, 2, 15, 0, 0, tzinfo=timezone.utc)
    older = now - timedelta(seconds=200)
    newer = now - timedelta(seconds=20)
    os.utime(a, (older.timestamp(), older.timestamp()))
    os.utime(b, (newer.timestamp(), newer.timestamp()))

    candidates = oc.resolve_signal_candidates(str(tmp_path / "last_signal_*.json"))
    latest = oc.latest_mtime(candidates)

    assert candidates == [str(a), str(b)] or candidates == [str(b), str(a)]
    assert latest == str(b)


def test_default_expected_state_is_conservative() -> None:
    payload = oc.default_expected_state()

    assert payload["needs_manual_review"] is True
    assert payload["comment"].startswith("⚠️ AUTO-GENERATED DEFAULT")
    assert payload["expected_containers"] == [
        "hermes-green",
        "trading-guardian",
        "trading-freqtrade-regime-hybrid-1",
        "trading-freqtrade-freqforge-canary-1",
        "trading-freqtrade-freqforge-1",
        "trading-freqtrade-webserver-1",
        "trading-ai-hedge-fund-1",
        "trading-freqai-rebel-1",
    ]
    assert len(payload["expected_cronjobs"]) == 6


def test_load_expected_state_reads_json_from_custom_path(tmp_path: Path) -> None:
    path = tmp_path / "expected_state.json"
    payload = oc.default_expected_state()
    oc.write_json_atomic(path, payload)

    assert oc.load_expected_state(path) == payload


def test_load_expected_state_can_fall_back_to_default_when_missing(tmp_path: Path) -> None:
    path = tmp_path / "missing_expected_state.json"

    assert oc.load_expected_state(path, allow_missing=True) == oc.default_expected_state()


def test_load_expected_state_can_fall_back_to_default_when_unreadable(tmp_path: Path) -> None:
    path = tmp_path / "unreadable_expected_state.json"
    path.write_bytes(b"\xff\xfe\xfd")

    assert oc.load_expected_state(path, allow_missing=True) == oc.default_expected_state()


def test_load_previous_state_returns_defaults_when_missing(tmp_path: Path) -> None:
    state = oc.load_previous_state(tmp_path / "missing_state.json")

    assert state["history"] == []
    assert state["open_issues"] == []
    assert state["overall_status"] == "healthy"


def test_load_cron_registry_reads_json_from_custom_path(tmp_path: Path) -> None:
    path = tmp_path / "jobs.json"
    payload = {"jobs": [{"name": "trading-pipeline", "schedule_display": "*/10 * * * *"}]}
    oc.write_json_atomic(path, payload)

    assert oc.load_cron_registry(path) == payload


def test_load_cron_fallback_parses_injected_text() -> None:
    result = oc.load_cron_fallback(
        crontab_text="# comment\n*/5 * * * * /opt/scripts/signal_fetcher.py\n",
        system_cron_texts={"/etc/cron.d/example": "0 * * * * root /opt/scripts/risk_check.sh\n"},
    )

    assert result["entries"] == [
        {"source": "crontab", "line": "*/5 * * * * /opt/scripts/signal_fetcher.py"},
        {"source": "/etc/cron.d/example", "line": "0 * * * * root /opt/scripts/risk_check.sh"},
    ]
