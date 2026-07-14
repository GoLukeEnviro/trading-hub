"""Regression tests for the stable Hermes repository-writer lock inode."""

from __future__ import annotations

from pathlib import Path

import pytest

import orchestrator.scripts.repo_writer as repo_writer
from orchestrator.scripts.repo_writer import (
    IsolatedWorktree,
    RepoWriterError,
    RepoWriterLock,
)


def _production_guard(
    monkeypatch: pytest.MonkeyPatch,
    *,
    lock_status: tuple[int, int, bool, int, bool],
) -> None:
    monkeypatch.setattr(
        repo_writer,
        "_current_writer_identity",
        lambda: (10000, "hermes"),
    )

    def parent_status(path: Path) -> tuple[int, int, bool, bool]:
        if path == repo_writer.LOCK_FILE_PATH.parent:
            return (0, 0, True, False)
        return (10000, 10000, True, True)

    monkeypatch.setattr(repo_writer, "_writer_parent_status", parent_status)
    monkeypatch.setattr(
        repo_writer,
        "_lock_file_status",
        lambda _path: lock_status,
        raising=False,
    )


def test_production_lock_uses_root_owned_stable_parent() -> None:
    assert Path("/opt/data/state/repo-writer/hermes-repo-writer.lock") == repo_writer.LOCK_FILE_PATH


def test_production_guard_rejects_missing_preprovisioned_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _production_guard(
        monkeypatch,
        lock_status=(-1, -1, False, 0, False),
    )

    with pytest.raises(RepoWriterError) as exc_info:
        repo_writer._validate_production_writer_environment()

    assert exc_info.value.code == "LOCK_FILE_MISSING"


@pytest.mark.parametrize(
    "lock_status",
    [
        (0, 0, True, 0o600, False),
        (10000, 10000, True, 0o644, True),
        (10000, 10000, False, 0o600, True),
        (10000, 10000, True, 0o600, False),
    ],
)
def test_production_guard_rejects_invalid_lock_metadata(
    monkeypatch: pytest.MonkeyPatch,
    lock_status: tuple[int, int, bool, int, bool],
) -> None:
    _production_guard(monkeypatch, lock_status=lock_status)

    with pytest.raises(RepoWriterError) as exc_info:
        repo_writer._validate_production_writer_environment()

    assert exc_info.value.code == "LOCK_OWNERSHIP_INVALID"


def test_production_guard_accepts_preprovisioned_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _production_guard(
        monkeypatch,
        lock_status=(10000, 10000, True, 0o600, True),
    )

    repo_writer._validate_production_writer_environment()


def test_holder_records_locked_device_and_inode(tmp_path: Path) -> None:
    path = tmp_path / "writer.lock"
    lock = RepoWriterLock(
        lock_path=path,
        enforce_sandbox=False,
        test_mode=True,
    )
    holder = lock.acquire(branch="fix/inode-metadata", session_id="inode")
    try:
        metadata = path.stat()
        assert holder.lock_device == metadata.st_dev
        assert holder.lock_inode == metadata.st_ino
        lock.assert_held()
    finally:
        lock.release()


def test_assert_held_fails_closed_when_lock_path_is_replaced(
    tmp_path: Path,
) -> None:
    path = tmp_path / "writer.lock"
    lock = RepoWriterLock(
        lock_path=path,
        enforce_sandbox=False,
        test_mode=True,
    )
    lock.acquire(branch="fix/inode-replacement", session_id="replacement")
    try:
        path.unlink()
        path.touch(mode=0o600)
        with pytest.raises(RepoWriterError) as exc_info:
            lock.assert_held()
        assert exc_info.value.code == "LOCK_PATH_REPLACED"
    finally:
        lock.release()


def test_assert_held_requires_an_acquired_lock(tmp_path: Path) -> None:
    lock = RepoWriterLock(
        lock_path=tmp_path / "writer.lock",
        enforce_sandbox=False,
        test_mode=True,
    )
    with pytest.raises(RepoWriterError) as exc_info:
        lock.assert_held()
    assert exc_info.value.code == "LOCK_NOT_HELD"


def test_production_worktree_mutation_requires_owning_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _production_guard(
        monkeypatch,
        lock_status=(10000, 10000, True, 0o600, True),
    )
    worktree = IsolatedWorktree(new_branch="fix/mutation-lock-required")

    with pytest.raises(RepoWriterError) as exc_info:
        worktree.create()

    assert exc_info.value.code == "LOCK_NOT_HELD"


def test_guarded_push_rechecks_inode_before_subprocess(tmp_path: Path) -> None:
    path = tmp_path / "writer.lock"
    lock = RepoWriterLock(
        lock_path=path,
        enforce_sandbox=False,
        test_mode=True,
    )
    lock.acquire(branch="fix/guarded-push", session_id="guarded-push")
    try:
        path.unlink()
        path.touch(mode=0o600)
        with pytest.raises(RepoWriterError) as exc_info:
            lock.run_guarded_mutation(
                mutation="push",
                command=("must-not-run",),
                cwd=tmp_path,
            )
        assert exc_info.value.code == "LOCK_PATH_REPLACED"
    finally:
        lock.release()


def test_guarded_merge_is_always_human_only(tmp_path: Path) -> None:
    lock = RepoWriterLock(
        lock_path=tmp_path / "writer.lock",
        enforce_sandbox=False,
        test_mode=True,
    )
    lock.acquire(branch="fix/human-only-merge", session_id="human-only")
    try:
        with pytest.raises(RepoWriterError) as exc_info:
            lock.run_guarded_mutation(
                mutation="merge",
                command=("gh", "pr", "merge", "1"),
                cwd=tmp_path,
            )
        assert exc_info.value.code == "HUMAN_ONLY_MERGE_REQUIRED"
    finally:
        lock.release()
