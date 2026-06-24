from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import restore_cron_jobs as rc  # noqa: E402

PROTECTED = "64866012641a"


def _job(i: int) -> dict:
    return {"id": f"job{i}", "name": f"job{i}", "enabled": True}


def _si_v2() -> dict:
    return {"id": PROTECTED, "name": "si-v2-active-cycle (6h, log-only)", "enabled": True}


def _stale(idx: int) -> dict:
    return {"id": f"stale{idx}", "name": f"stale{idx}", "enabled": True}


# ── plan_merge: pure-function unit tests ───────────────────────────────────

def test_plan_refuses_backup_without_protected_id() -> None:
    live = [_si_v2()] + [_job(i) for i in range(57)]        # 58, has SI-v2
    stale_backup = [_job(i) for i in range(11)]             # 11, NO SI-v2
    plan = rc.plan_merge(live, stale_backup)
    assert plan["valid_backup"] is False
    assert plan["refuse_reason"] == "INVALID_BACKUP_NO_PROTECTED_JOB"
    assert plan["add"] == []


def test_invalid_backup_does_not_add_stale_jobs() -> None:
    live = [_si_v2()] + [_job(i) for i in range(57)]        # healthy 58
    stale_only = [_stale(k) for k in range(9)]              # 9 ids absent from live, NO SI-v2
    plan = rc.plan_merge(live, stale_only)
    assert plan["valid_backup"] is False
    assert plan["add"] == []
    assert len(plan["planned"]) == len(live)                # live untouched


def test_invalid_backup_broken_live_refuses() -> None:
    live = [_si_v2()] + [_job(i) for i in range(5)]         # <10 jobs, but has SI-v2
    stale_backup = [_job(i) for i in range(11)]             # NO SI-v2
    plan = rc.plan_merge(live, stale_backup)
    assert plan["valid_backup"] is False
    assert plan["refuse_reason"] == "INVALID_BACKUP_NO_PROTECTED_JOB"
    assert plan["add"] == []


def test_valid_backup_broken_live_merges_no_shrink() -> None:
    live = [_si_v2()] + [_job(i) for i in range(5)]         # 6 jobs incl SI-v2
    backup = [_si_v2()] + [_job(i) for i in range(57)]      # 58 incl SI-v2 (valid)
    plan = rc.plan_merge(live, backup)
    assert plan["valid_backup"] is True
    assert plan["refuse_reason"] is None
    assert len(plan["add"]) == 52                            # job6..job57 added; SI-v2 already present
    assert len(plan["planned"]) == 58
    assert len(plan["planned"]) >= len(live)                 # no shrink
    assert PROTECTED in plan["planned_ids"]


def test_valid_backup_restores_si_v2_when_missing_from_live() -> None:
    live = [_job(i) for i in range(10)]                     # 10 jobs, NO SI-v2
    backup = [_si_v2()] + [_job(i) for i in range(57)]      # valid (has SI-v2)
    plan = rc.plan_merge(live, backup)
    assert plan["valid_backup"] is True
    assert plan["refuse_reason"] is None
    assert PROTECTED in plan["planned_ids"]
    assert any(a["id"] == PROTECTED for a in plan["add"])   # SI-v2 restored from backup


def test_both_missing_si_v2_refuses() -> None:
    live = [_job(i) for i in range(10)]                     # no SI-v2
    backup = [_job(i) for i in range(11)]                   # no SI-v2
    plan = rc.plan_merge(live, backup)
    assert plan["valid_backup"] is False
    assert plan["refuse_reason"] == "INVALID_BACKUP_NO_PROTECTED_JOB"
    assert plan["add"] == []


def test_healthy_live_is_noop() -> None:
    live = [_si_v2()] + [_job(i) for i in range(57)]
    backup = list(live)                                     # identical, valid
    plan = rc.plan_merge(live, backup)
    assert plan["valid_backup"] is True
    assert plan["refuse_reason"] is None
    assert plan["add"] == []


def test_backup_is_valid_helper() -> None:
    assert rc.backup_is_valid([_si_v2(), _job(0)]) is True
    assert rc.backup_is_valid([_job(0), _job(1)]) is False


# ── main(): integration tests via env overrides + tmp_path (no live paths) ─

def _write_registry(path: Path, jobs: list[dict]) -> str:
    path.write_text(json.dumps({"jobs": jobs, "updated_at": "fixed"}))
    return path.read_text()


def _set_env(monkeypatch, db: Path, backup: Path, log: Path) -> None:
    monkeypatch.setenv("CRON_JOBS_DB", str(db))
    monkeypatch.setenv("CRON_JOBS_BACKUP", str(backup))
    monkeypatch.setenv("CRON_RESTORE_LOG", str(log))


def test_main_dry_run_never_writes(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "live.json"
    backup = tmp_path / "backup.json"
    log = tmp_path / "restore.log"
    before = _write_registry(db, [_job(i) for i in range(10)])           # live missing jobs
    _write_registry(backup, [_si_v2()] + [_job(i) for i in range(57)])   # valid backup
    _set_env(monkeypatch, db, backup, log)

    assert rc.main(["--dry-run"]) == 0
    assert db.read_text() == before                                      # untouched


def test_main_no_write_on_invalid_backup(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "live.json"
    backup = tmp_path / "backup.json"
    log = tmp_path / "restore.log"
    before = _write_registry(db, [_si_v2()] + [_job(i) for i in range(57)])  # healthy 58
    _write_registry(backup, [_job(i) for i in range(11)])                    # stale, no SI-v2
    _set_env(monkeypatch, db, backup, log)

    assert rc.main([]) == 0
    assert db.read_text() == before                                         # invalid -> no write


def test_main_merge_writes_and_asserts_si_v2(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "live.json"
    backup = tmp_path / "backup.json"
    log = tmp_path / "restore.log"
    _write_registry(db, [_job(i) for i in range(10)])                        # live: no SI-v2
    _write_registry(backup, [_si_v2()] + [_job(i) for i in range(57)])       # valid backup
    _set_env(monkeypatch, db, backup, log)

    assert rc.main([]) == 0
    after = json.loads(db.read_text())
    jobs = after["jobs"]
    assert any(j["id"] == PROTECTED for j in jobs)                           # SI-v2 present after write
    assert len(jobs) >= 10                                                   # no shrink
    # original live jobs preserved (add-only, nothing removed)
    assert all(any(j["id"] == f"job{i}" for j in jobs) for i in range(10))


def test_main_healthy_live_is_noop(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "live.json"
    backup = tmp_path / "backup.json"
    log = tmp_path / "restore.log"
    live = [_si_v2()] + [_job(i) for i in range(57)]
    before = _write_registry(db, live)
    _write_registry(backup, list(live))                                      # identical valid backup
    _set_env(monkeypatch, db, backup, log)

    assert rc.main([]) == 0
    assert db.read_text() == before                                          # nothing to add -> no write
