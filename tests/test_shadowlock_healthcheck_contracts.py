from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import shadowlock.healthcheck as healthcheck


def _logdir(base: Path, when: dt.datetime) -> Path:
    return base / "logs" / str(when.year) / f"{when.month:02d}"


class TestShadowlockHealthcheckContracts:
    def test_missing_log_dir_is_unhealthy(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setattr(healthcheck, "BASEDIR", str(tmp_path / "shadowlock"))
        assert healthcheck.main() == 1

    def test_recent_heartbeat_is_healthy(self, tmp_path: Path, monkeypatch) -> None:
        base = tmp_path / "shadowlock"
        when = dt.datetime.utcnow()
        logdir = _logdir(base, when)
        logdir.mkdir(parents=True, exist_ok=True)
        heartbeat = {
            "event_type": "shadowlock_heartbeat",
            "timestamp_utc": when.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        (logdir / f"{when.day:02d}.jsonl").write_text(json.dumps(heartbeat) + "\n")
        monkeypatch.setattr(healthcheck, "BASEDIR", str(base))
        assert healthcheck.main() == 0

    def test_stale_heartbeat_is_unhealthy(self, tmp_path: Path, monkeypatch) -> None:
        base = tmp_path / "shadowlock"
        stale = dt.datetime.utcnow() - dt.timedelta(seconds=healthcheck.CUTOFF_SECONDS + 60)
        logdir = _logdir(base, stale)
        logdir.mkdir(parents=True, exist_ok=True)
        heartbeat = {
            "event_type": "shadowlock_heartbeat",
            "timestamp_utc": stale.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        (logdir / f"{stale.day:02d}.jsonl").write_text(json.dumps(heartbeat) + "\n")
        monkeypatch.setattr(healthcheck, "BASEDIR", str(base))
        assert healthcheck.main() == 1
