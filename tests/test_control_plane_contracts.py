from __future__ import annotations

import json
import sys
import subprocess
from pathlib import Path

import pytest

import orchestrator.control.reconcile_controller_baseline as reconcile
from orchestrator.control.scripts.validate_control_plane import load_json, validate


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2))


class TestControlPlaneContracts:
    def test_load_json_rejects_non_object(self, tmp_path: Path) -> None:
        path = tmp_path / "array.json"
        path.write_text("[]")
        with pytest.raises(ValueError, match="must contain a JSON object"):
            load_json(path)

    def test_validate_missing_schema_fails_closed(self, tmp_path: Path) -> None:
        config_root = tmp_path / "config"
        state_root = tmp_path / "state"
        _write_json(state_root / "STATE.json", {"controller_status": "PAUSED"})
        _write_json(state_root / "QUEUE.json", {"items": []})
        with pytest.raises(FileNotFoundError, match="State schema not found"):
            validate(config_root=config_root, state_root=state_root)

    def test_reconcile_restores_backups_on_post_validation_failure(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        state = tmp_path / "STATE.json"
        queue = tmp_path / "QUEUE.json"
        original_state = {
            "controller_status": "PAUSED",
            "active_work_item_id": None,
            "active_branch": None,
            "active_worktree": None,
            "active_pr": None,
            "canonical_main_commit": "a" * 64,
            "updated_at": "2026-06-15T00:00:00Z",
        }
        original_queue = {"items": [], "base_commit": "a" * 64}
        _write_json(state, original_state)
        _write_json(queue, original_queue)

        fake_repo = tmp_path / "repo"
        fake_repo.mkdir()

        def _fake_run(*args, **kwargs):
            return subprocess.CompletedProcess(args[0] if args else [], 0, stdout="", stderr="")

        monkeypatch.setattr(reconcile.subprocess, "run", _fake_run)

        original_validate_state = reconcile._validate_state
        original_validate_queue = reconcile._validate_queue
        monkeypatch.setattr(reconcile, "_validate_queue", lambda data, path: None)

        calls = {"count": 0}

        def _flaky_validate_state(data, path):
            calls["count"] += 1
            if calls["count"] >= 2:
                raise ValueError("forced post-validation failure")
            return original_validate_state(data, path)

        monkeypatch.setattr(reconcile, "_validate_state", _flaky_validate_state)
        monkeypatch.setattr(sys, "argv", [
            "reconcile_controller_baseline.py",
            "--state",
            str(state),
            "--queue",
            str(queue),
            "--commit",
            "b" * 64,
            "--repo",
            str(fake_repo),
        ])

        with pytest.raises(ValueError, match="forced post-validation failure"):
            reconcile.main()

        assert json.loads(state.read_text()) == original_state
        assert json.loads(queue.read_text()) == original_queue
        backups = list((tmp_path / "backups").glob("*.bak"))
        assert backups, "expected timestamped backups to be created"
