"""Tests for controller baseline reconciliation (issue #175)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

# Import the reconciliation module
from orchestrator.control.reconcile_controller_baseline import (
    _atomic_write,
    _file_sha256,
    _load_json,
    _safe_backup,
    _update_field,
    _validate_path_safety,
    _validate_queue,
    _validate_sha,
    _validate_state,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _valid_state(**overrides: str | None) -> dict:
    data: dict = {
        "schema_version": 1,
        "project": "trading-hub / SI v2",
        "controller_mode": "continuous_implementation",
        "controller_status": "PAUSED",
        "operation_level": "L3_REPOSITORY_ONLY",
        "runtime_policy": "FORBIDDEN",
        "merge_policy": "HUMAN_ONLY",
        "current_epic": None,
        "canonical_main_commit": "a" * 64,
        "active_work_item_id": None,
        "active_branch": None,
        "active_worktree": None,
        "active_pr": None,
        "last_completed_work_item_id": "test",
        "last_run_id": None,
        "last_run_status": None,
        "consecutive_failures": 0,
        "pause_reason": "Testing",
        "updated_at": "2026-06-12T00:00:00Z",
    }
    data.update(overrides)
    return data


def _valid_queue(**overrides: str | None) -> dict:
    data: dict = {
        "schema_version": 1,
        "epic_id": None,
        "base_commit": "a" * 64,
        "branch": None,
        "worktree": None,
        "items": [],
    }
    data.update(overrides)
    return data


# ---------------------------------------------------------------------------
# SHA validation tests
# ---------------------------------------------------------------------------


class TestSHAValidation:
    def test_valid_sha(self) -> None:
        _validate_sha("a" * 64)

    def test_short_sha_raises(self) -> None:
        with pytest.raises(ValueError):
            _validate_sha("a" * 63)

    def test_uppercase_raises(self) -> None:
        with pytest.raises(ValueError):
            _validate_sha("A" * 64)


# ---------------------------------------------------------------------------
# State validation tests
# ---------------------------------------------------------------------------


class TestStateValidation:
    def test_valid_paused(self) -> None:
        state = _valid_state(controller_status="PAUSED")
        _validate_state(state, Path("/tmp/test.json"))

    def test_valid_idle(self) -> None:
        state = _valid_state(controller_status="IDLE")
        _validate_state(state, Path("/tmp/test.json"))

    def test_invalid_running(self) -> None:
        state = _valid_state(controller_status="RUNNING")
        with pytest.raises(ValueError, match="controller_status"):
            _validate_state(state, Path("/tmp/test.json"))

    def test_active_branch_raises(self) -> None:
        state = _valid_state(active_branch="feature/xyz")
        with pytest.raises(ValueError, match="active"):
            _validate_state(state, Path("/tmp/test.json"))

    def test_active_work_item_raises(self) -> None:
        state = _valid_state(active_work_item_id="ITEM-001")
        with pytest.raises(ValueError, match="active"):
            _validate_state(state, Path("/tmp/test.json"))


# ---------------------------------------------------------------------------
# Queue validation tests
# ---------------------------------------------------------------------------


class TestQueueValidation:
    def test_valid_empty(self) -> None:
        queue = _valid_queue()
        _validate_queue(queue, Path("/tmp/test.json"))

    def test_non_empty_raises(self) -> None:
        queue = _valid_queue(items=[{"id": "item-1"}])
        with pytest.raises(ValueError, match="empty"):
            _validate_queue(queue, Path("/tmp/test.json"))

    def test_invalid_items_type_raises(self) -> None:
        queue = _valid_queue(items="not-a-list")
        with pytest.raises(ValueError, match="list"):
            _validate_queue(queue, Path("/tmp/test.json"))


# ---------------------------------------------------------------------------
# JSON load tests
# ---------------------------------------------------------------------------


class TestLoadJSON:
    def test_load_valid(self, tmp_path: Path) -> None:
        p = tmp_path / "test.json"
        p.write_text('{"key": "value"}')
        data = _load_json(p, "TEST")
        assert data == {"key": "value"}

    def test_missing_file_raises(self) -> None:
        with pytest.raises(FileNotFoundError):
            _load_json(Path("/tmp/nonexistent.json"), "TEST")

    def test_malformed_json_raises(self, tmp_path: Path) -> None:
        p = tmp_path / "bad.json"
        p.write_text("not json")
        with pytest.raises(ValueError, match="Cannot parse"):
            _load_json(p, "TEST")


# ---------------------------------------------------------------------------
# Backup tests
# ---------------------------------------------------------------------------


class TestBackup:
    def test_backup_created(self, tmp_path: Path) -> None:
        src = tmp_path / "STATE.json"
        src.write_text('{"key": "value"}')
        backup_dir = tmp_path / "backups"
        backup = _safe_backup(src, backup_dir, "20260612T000000Z")
        assert backup.exists()
        assert backup.read_text() == '{"key": "value"}'


# ---------------------------------------------------------------------------
# Atomic write tests
# ---------------------------------------------------------------------------


class TestAtomicWrite:
    def test_writes_correctly(self, tmp_path: Path) -> None:
        p = tmp_path / "test.json"
        _atomic_write(p, {"key": "value"})
        assert p.exists()
        assert json.loads(p.read_text()) == {"key": "value"}

    def test_idempotent(self, tmp_path: Path) -> None:
        p = tmp_path / "test.json"
        _atomic_write(p, {"key": "value"})
        _atomic_write(p, {"key": "value"})
        assert json.loads(p.read_text()) == {"key": "value"}


# ---------------------------------------------------------------------------
# Update field tests
# ---------------------------------------------------------------------------


class TestUpdateField:
    def test_updates_existing_field(self) -> None:
        data = {"key": "old"}
        _update_field(data, "key", "new")
        assert data["key"] == "new"

    def test_missing_field_raises(self) -> None:
        data = {"other": "value"}
        with pytest.raises(ValueError, match="not found"):
            _update_field(data, "key", "value")


# ---------------------------------------------------------------------------
# Path safety tests
# ---------------------------------------------------------------------------


class TestPathSafety:
    def test_safe_path(self, tmp_path: Path) -> None:
        p = tmp_path / "STATE.json"
        p.write_text("{}")
        _validate_path_safety(p)

    def test_symlink_raises(self, tmp_path: Path) -> None:
        target = tmp_path / "target.json"
        target.write_text("{}")
        link = tmp_path / "link.json"
        link.symlink_to(target)
        with pytest.raises(ValueError, match="symlink"):
            _validate_path_safety(link)


# ---------------------------------------------------------------------------
# File checksum tests
# ---------------------------------------------------------------------------


class TestFileSHA256:
    def test_checksum_matches(self, tmp_path: Path) -> None:
        p = tmp_path / "test.json"
        content = '{"a": 1}'
        p.write_text(content)
        expected = hashlib.sha256(content.encode()).hexdigest()
        assert _file_sha256(p) == expected


# ---------------------------------------------------------------------------
# No-runtime import test
# ---------------------------------------------------------------------------


class TestNoRuntime:
    def test_no_runtime_imports(self) -> None:
        import orchestrator.control.reconcile_controller_baseline as mod
        src = mod.__file__ or ""
        with open(src) as f:
            content = f.read()
        for forbidden in ("docker", "freqtrade", "exchange"):
            for line in content.splitlines():
                stripped = line.strip()
                if (stripped.startswith("import ") or stripped.startswith("from ")) and forbidden in stripped:
                    raise AssertionError(
                        f"Forbidden import in reconcile_controller_baseline: {stripped}"
                    )
