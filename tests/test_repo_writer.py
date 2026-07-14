"""Tests for orchestrator/scripts/repo_writer.py.

Covers the Hermes single-writer repository contract:

- RepoWriterLock: acquire / release / non-blocking / stale / context manager
- IsolatedWorktree: base-ref pinning, clean-worktree verification,
  sandbox enforcement, branch name validation
- RepoWriterError: code stability

Run with::

    pytest tests/test_repo_writer.py -v
"""

from __future__ import annotations

import errno
import fcntl
import json
import os
import shutil
import socket
import subprocess
import sys
import textwrap
import time
from pathlib import Path
from typing import Iterator

import pytest

# Make the orchestrator package importable.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import orchestrator.scripts.repo_writer as repo_writer  # noqa: E402
from orchestrator.scripts.repo_writer import (  # noqa: E402
    BRANCH_NAME_PATTERN,
    DEFAULT_BASE_REF,
    DEFAULT_REPO_ROOT,
    DEFAULT_WORKTREE_PARENT,
    LOCK_FILE_PATH,
    PERSISTENT_STATE_DIR,
    RepoWriterError,
    RepoWriterLock,
    IsolatedWorktree,
    LockHolder,
)


# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------

@pytest.fixture
def tmp_lock_path(tmp_path: Path) -> Path:
    """Per-test lock path under tmp_path, isolated from the production lock."""
    return tmp_path / "test-hermes-repo-writer.lock"


@pytest.fixture
def lock(tmp_lock_path: Path) -> RepoWriterLock:
    return RepoWriterLock(
        lock_path=tmp_lock_path,
        stale_seconds=60,
        enforce_sandbox=False,
        test_mode=True,
    )


@pytest.fixture
def sandbox_git_repo(tmp_path: Path) -> Path:
    """A throwaway bare-ish git repo to use as the shared canonical checkout.

    The repo has one initial commit on ``main`` and a tracking branch
    ``origin/main`` so ``origin/main`` resolves to a SHA.
    """
    repo = tmp_path / "shared-checkout"
    repo.mkdir()
    env = os.environ.copy()
    env["GIT_AUTHOR_NAME"] = "sandbox"
    env["GIT_AUTHOR_EMAIL"] = "sandbox@test.local"
    env["GIT_COMMITTER_NAME"] = "sandbox"
    env["GIT_COMMITTER_EMAIL"] = "sandbox@test.local"
    cwd = str(repo)

    # git init -b main
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=cwd, check=True, env=env)
    subprocess.run(["git", "config", "user.email", "sandbox@test.local"], cwd=cwd, check=True, env=env)
    subprocess.run(["git", "config", "user.name", "sandbox"], cwd=cwd, check=True, env=env)

    # Set up a fake origin so origin/main resolves.
    bare = tmp_path / "origin.git"
    bare.mkdir()
    subprocess.run(["git", "init", "-q", "--bare"], cwd=str(bare), check=True, env=env)
    subprocess.run(["git", "remote", "add", "origin", str(bare)], cwd=cwd, check=True, env=env)

    # Initial commit on main.
    (repo / "README.md").write_text("sandbox\n")
    subprocess.run(["git", "add", "README.md"], cwd=cwd, check=True, env=env)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=cwd, check=True, env=env)
    # Push to origin so origin/main is valid.
    subprocess.run(["git", "push", "-q", "origin", "main"], cwd=cwd, check=True, env=env)
    # Ensure origin/main is set as upstream.
    subprocess.run(
        ["git", "branch", "--set-upstream-to=origin/main", "main"],
        cwd=cwd,
        check=True,
        env=env,
    )
    return repo


@pytest.fixture
def sandbox_worktree_parent(tmp_path: Path) -> Path:
    parent = tmp_path / "worktrees"
    parent.mkdir()
    return parent


# ----------------------------------------------------------------------
# LockHolder
# ----------------------------------------------------------------------

class TestLockHolder:
    def test_roundtrip_json(self) -> None:
        h = LockHolder(
            pid=os.getpid(),
            host=socket.gethostname(),
            worktree_path="/opt/data/projects/trading-hub-worktrees/x",
            branch="ops/hermes-single-writer-recovery",
            session_id="20260713_184222_f94afc",
            started_at="2026-07-13T20:00:00+00:00",
            note="unit test",
        )
        raw = h.to_json()
        parsed = LockHolder.from_json(raw)
        assert parsed == h

    def test_from_json_missing_field_raises(self) -> None:
        with pytest.raises((KeyError, ValueError, TypeError, json.JSONDecodeError)):
            LockHolder.from_json('{"pid": 1}')

    def test_from_json_garbage_raises(self) -> None:
        with pytest.raises((json.JSONDecodeError, ValueError, TypeError, KeyError)):
            LockHolder.from_json("not-json-at-all")


# ----------------------------------------------------------------------
# RepoWriterLock — basic acquire / release
# ----------------------------------------------------------------------

class TestRepoWriterLockBasic:
    def test_acquire_and_release(self, lock: RepoWriterLock) -> None:
        holder = lock.acquire(
            branch="ops/repo-writer-test",
            session_id="test-session-1",
            worktree_path="/tmp/some-worktree",
        )
        assert holder.pid == os.getpid()
        assert holder.branch == "ops/repo-writer-test"
        assert holder.session_id == "test-session-1"
        assert lock.is_locked()
        # On-disk JSON has the same fields.
        on_disk = lock.read_holder()
        assert on_disk is not None
        assert on_disk.pid == holder.pid
        lock.release()
        # After release, the holder is still readable (we leave it
        # on disk as a record), but the lock is no longer held
        # because the flock was released.
        assert not lock.is_locked()

    def test_release_is_idempotent(self, lock: RepoWriterLock) -> None:
        lock.acquire(branch="ops/idempotent", session_id="s1")
        lock.release()
        lock.release()  # no-op, must not raise

    def test_context_manager_releases_on_exit(self, lock: RepoWriterLock) -> None:
        with lock as ctx:
            ctx.acquire(branch="ops/context-mgr", session_id="s2")
            assert ctx.is_locked()
        assert not lock.is_locked()

    def test_context_manager_releases_on_exception(self, lock: RepoWriterLock) -> None:
        with pytest.raises(RuntimeError, match="boom"):
            with lock as ctx:
                ctx.acquire(branch="ops/ctx-exc", session_id="s3")
                raise RuntimeError("boom")
        assert not lock.is_locked()

    def test_codex_cloud_branch_prefix_is_allowed(self, lock: RepoWriterLock) -> None:
        holder = lock.acquire(
            branch="codex/a1-writer-contract2026-07-14",
            session_id="codex-cloud-a1",
            worktree_path="/opt/data/projects/trading-hub-worktrees/codex-a1",
        )
        try:
            assert holder.branch == "codex/a1-writer-contract2026-07-14"
        finally:
            lock.release()


# ----------------------------------------------------------------------
# RepoWriterLock — non-blocking contention
# ----------------------------------------------------------------------

class TestRepoWriterLockContention:
    def test_second_acquire_blocks(self, lock: RepoWriterLock) -> None:
        lock.acquire(branch="ops/holder-a", session_id="sa")
        try:
            with pytest.raises(RepoWriterError) as ei:
                lock.acquire(branch="ops/holder-b", session_id="sb")
            assert ei.value.code == "BLOCKED_BY_ACTIVE_REPO_WRITER"
            assert ei.value.holder["pid"] == os.getpid()
            assert ei.value.holder["branch"] == "ops/holder-a"
        finally:
            lock.release()

    def test_concurrent_subprocess_blocks(self, lock: RepoWriterLock) -> None:
        # Acquire in parent.
        lock.acquire(branch="ops/parent", session_id="parent")
        try:
            # Try to acquire in a subprocess.
            script = textwrap.dedent(
                f"""
                import sys
                sys.path.insert(0, {str(_REPO_ROOT)!r})
                from orchestrator.scripts.repo_writer import RepoWriterLock, RepoWriterError
                lock = RepoWriterLock(lock_path={str(lock.lock_path)!r}, stale_seconds=60, enforce_sandbox=False, test_mode=True)
                try:
                    lock.acquire(branch="ops/child", session_id="child")
                    print("ACQUIRED")
                    sys.exit(0)
                except RepoWriterError as e:
                    print(f"BLOCKED {{e.code}}")
                    sys.exit(42)
                """
            )
            result = subprocess.run(
                [sys.executable, "-c", script],
                capture_output=True,
                text=True,
                timeout=10,
            )
            assert result.returncode == 42
            assert "BLOCKED" in result.stdout
        finally:
            lock.release()

        # After release, the subprocess can acquire.
        script2 = textwrap.dedent(
            f"""
            import sys
            sys.path.insert(0, {str(_REPO_ROOT)!r})
            from orchestrator.scripts.repo_writer import RepoWriterLock
            lock = RepoWriterLock(lock_path={str(lock.lock_path)!r}, stale_seconds=60, enforce_sandbox=False, test_mode=True)
            lock.acquire(branch="ops/child2", session_id="child2")
            print("ACQUIRED")
            lock.release()
            """
        )
        result2 = subprocess.run(
            [sys.executable, "-c", script2],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result2.returncode == 0
        assert "ACQUIRED" in result2.stdout


# ----------------------------------------------------------------------
# RepoWriterLock — stale handling
# ----------------------------------------------------------------------

class TestRepoWriterLockStale:
    def test_stale_lock_with_dead_pid_is_auto_cleaned(
        self, lock: RepoWriterLock
    ) -> None:
        # Write a holder with an obviously dead PID and an old timestamp.
        old_holder = LockHolder(
            pid=2_000_000,  # unused PID
            host="ghost",
            worktree_path="/nonexistent",
            branch="ops/stale-test",
            session_id="ghost-session",
            started_at="2020-01-01T00:00:00+00:00",  # ancient
        )
        lock.lock_path.write_text(old_holder.to_json())

        # Acquire should succeed: the flock is free, the on-disk
        # JSON is informational, and stale holder metadata is
        # cleaned up automatically.
        holder = lock.acquire(branch="ops/new", session_id="new")
        assert holder.session_id == "new"
        # The on-disk JSON should now be ours, not the ghost's.
        on_disk = lock.read_holder()
        assert on_disk is not None
        assert on_disk.session_id == "new"
        lock.release()

    def test_stale_lock_with_force_break_succeeds(self, lock: RepoWriterLock) -> None:
        # force_break_stale is now informational only — the flock
        # is the real lock. A stale holder JSON is auto-cleaned
        # even without force_break_stale=True.
        old_holder = LockHolder(
            pid=2_000_001,
            host="ghost",
            worktree_path="/nonexistent",
            branch="ops/stale-test",
            session_id="ghost-session",
            started_at="2020-01-01T00:00:00+00:00",
        )
        lock.lock_path.write_text(old_holder.to_json())

        holder = lock.acquire(
            branch="ops/forced",
            session_id="forced-session",
            force_break_stale=True,
        )
        assert holder.session_id == "forced-session"
        lock.release()

    def test_fresh_lock_with_dead_pid_auto_cleans(
        self, tmp_lock_path: Path
    ) -> None:
        # Holder PID is dead but the holder's started_at is recent
        # (e.g. kernel reused the PID). With stale_seconds=0, even
        # a fresh timestamp is stale, so the next acquirer cleans
        # up automatically.
        lock = RepoWriterLock(
            lock_path=tmp_lock_path,
            stale_seconds=0,
            enforce_sandbox=False,
            test_mode=True,
        )  # immediate staleness
        fresh_holder = LockHolder(
            pid=2_000_002,
            host="ghost",
            worktree_path="/nonexistent",
            branch="ops/recent",
            session_id="recent",
            started_at=time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
        )
        tmp_lock_path.write_text(fresh_holder.to_json())
        # With stale_seconds=0, even a fresh timestamp is stale.
        holder = lock.acquire(branch="ops/x", session_id="x")
        assert holder.session_id == "x"
        lock.release()

    def test_malformed_lock_file_treated_as_stale(
        self, lock: RepoWriterLock
    ) -> None:
        lock.lock_path.write_text("this is not json")
        # Malformed JSON is treated as "no holder" by _read_holder
        # (returns None), so a fresh acquire will succeed.
        holder = lock.acquire(branch="ops/after-malformed", session_id="s")
        assert holder.session_id == "s"
        lock.release()


# ----------------------------------------------------------------------
# RepoWriterLock — input validation
# ----------------------------------------------------------------------

class TestRepoWriterLockInputValidation:
    def test_invalid_branch_name_rejected(self, lock: RepoWriterLock) -> None:
        with pytest.raises(RepoWriterError) as ei:
            lock.acquire(branch="not-a-valid-branch", session_id="s")
        assert ei.value.code == "INVALID_BRANCH_NAME"

    def test_branch_name_with_path_traversal_rejected(
        self, lock: RepoWriterLock
    ) -> None:
        with pytest.raises(RepoWriterError) as ei:
            lock.acquire(branch="feat/../etc/passwd", session_id="s")
        assert ei.value.code == "INVALID_BRANCH_NAME"

    def test_empty_session_id_rejected(self, lock: RepoWriterLock) -> None:
        with pytest.raises(RepoWriterError) as ei:
            lock.acquire(branch="ops/x", session_id="")
        assert ei.value.code == "INVALID_SESSION_ID"

    def test_main_branch_itself_rejected(
        self, lock: RepoWriterLock
    ) -> None:
        # ``main`` does not match the (feat|fix|docs|ops|...)/... pattern.
        with pytest.raises(RepoWriterError) as ei:
            lock.acquire(branch="main", session_id="s")
        assert ei.value.code == "INVALID_BRANCH_NAME"


# ----------------------------------------------------------------------
# RepoWriterLock — sandbox
# ----------------------------------------------------------------------

class TestRepoWriterLockSandbox:
    def test_lock_path_outside_sandbox_rejected(
        self, tmp_path: Path
    ) -> None:
        # When enforce_sandbox=True (production default), a lock
        # path that escapes /opt/data/state/ is rejected.
        with pytest.raises(RepoWriterError) as ei:
            RepoWriterLock(
                lock_path=tmp_path / "x.lock",
                enforce_sandbox=True,
                test_mode=True,
            )
        assert ei.value.code == "LOCK_PATH_OUTSIDE_SANDBOX"

    def test_lock_path_inside_sandbox_accepted(
        self, valid_production_guard: None
    ) -> None:
        # The production lock path lives at
        # /opt/data/state/hermes-repo-writer.lock, which IS inside
        # the sandbox. The default constructor must succeed.
        # (We do not actually acquire the lock here — just construct
        # the object — to keep the test hermetic.)
        lock = RepoWriterLock()  # noqa: F841
        assert lock.lock_path == LOCK_FILE_PATH


# ----------------------------------------------------------------------
# Production writer identity / mount guard
# ----------------------------------------------------------------------

@pytest.fixture
def valid_production_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        repo_writer,
        "_current_writer_identity",
        lambda: (10000, "hermes"),
        raising=False,
    )
    monkeypatch.setattr(
        repo_writer,
        "_writer_parent_status",
        lambda _path: (10000, 10000, True, True),
        raising=False,
    )


class TestProductionWriterEnvironmentGuard:
    def test_root_identity_is_rejected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            repo_writer,
            "_current_writer_identity",
            lambda: (0, "root"),
            raising=False,
        )
        with pytest.raises(RepoWriterError) as ei:
            RepoWriterLock()
        assert ei.value.code == "WRITER_IDENTITY_MISMATCH"

    def test_wrong_username_is_rejected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            repo_writer,
            "_current_writer_identity",
            lambda: (10000, "deploy"),
            raising=False,
        )
        with pytest.raises(RepoWriterError) as ei:
            RepoWriterLock()
        assert ei.value.code == "WRITER_IDENTITY_MISMATCH"

    def test_wrong_lock_path_fails_before_creating_state(
        self,
        tmp_path: Path,
        valid_production_guard: None,
    ) -> None:
        missing_parent = tmp_path / "must-not-be-created"
        with pytest.raises(RepoWriterError) as ei:
            RepoWriterLock(lock_path=missing_parent / "writer.lock")
        assert ei.value.code == "WRITER_IDENTITY_MISMATCH"
        assert not missing_parent.exists()

    def test_host_repo_path_is_rejected(
        self, valid_production_guard: None
    ) -> None:
        with pytest.raises(RepoWriterError) as ei:
            IsolatedWorktree(
                repo_root=Path("/opt/data/projects/trading-hub"),
                base_ref="origin/main",
                new_branch="ops/wrong-host-repo",
                worktree_parent=DEFAULT_WORKTREE_PARENT,
            )
        assert ei.value.code == "WRITER_IDENTITY_MISMATCH"

    def test_wrong_worktree_parent_is_rejected(
        self, valid_production_guard: None
    ) -> None:
        with pytest.raises(RepoWriterError) as ei:
            IsolatedWorktree(
                repo_root=DEFAULT_REPO_ROOT,
                base_ref="origin/main",
                new_branch="ops/wrong-worktree-parent",
                worktree_parent=Path("/opt/data/projects/wrong-worktrees"),
            )
        assert ei.value.code == "WRITER_IDENTITY_MISMATCH"

    def test_wrong_parent_ownership_is_rejected(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            repo_writer,
            "_current_writer_identity",
            lambda: (10000, "hermes"),
            raising=False,
        )
        monkeypatch.setattr(
            repo_writer,
            "_writer_parent_status",
            lambda _path: (0, 0, True, True),
            raising=False,
        )
        with pytest.raises(RepoWriterError) as ei:
            RepoWriterLock()
        assert ei.value.code == "WRITER_IDENTITY_MISMATCH"

    def test_non_writable_parent_is_rejected(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            repo_writer,
            "_current_writer_identity",
            lambda: (10000, "hermes"),
            raising=False,
        )
        monkeypatch.setattr(
            repo_writer,
            "_writer_parent_status",
            lambda _path: (10000, 10000, True, False),
            raising=False,
        )
        with pytest.raises(RepoWriterError) as ei:
            RepoWriterLock()
        assert ei.value.code == "WRITER_IDENTITY_MISMATCH"

    def test_sandbox_opt_out_requires_explicit_test_mode(
        self, tmp_lock_path: Path
    ) -> None:
        with pytest.raises(RepoWriterError) as ei:
            RepoWriterLock(lock_path=tmp_lock_path, enforce_sandbox=False)
        assert ei.value.code == "WRITER_IDENTITY_MISMATCH"

    def test_explicit_test_mode_allows_temporary_paths(
        self, tmp_lock_path: Path
    ) -> None:
        lock = RepoWriterLock(
            lock_path=tmp_lock_path,
            enforce_sandbox=False,
            test_mode=True,
        )
        assert lock.lock_path == tmp_lock_path


# ----------------------------------------------------------------------
# IsolatedWorktree — input validation
# ----------------------------------------------------------------------

class TestIsolatedWorktreeInputValidation:
    def test_invalid_branch_rejected(
        self, sandbox_git_repo: Path, sandbox_worktree_parent: Path
    ) -> None:
        with pytest.raises(RepoWriterError) as ei:
            IsolatedWorktree(
                repo_root=sandbox_git_repo,
                base_ref="origin/main",
                new_branch="not-valid",
                worktree_parent=sandbox_worktree_parent,
                enforce_sandbox=False,
                test_mode=True,
            )
        assert ei.value.code == "INVALID_BRANCH_NAME"

    def test_codex_cloud_branch_prefix_is_allowed(
        self, sandbox_git_repo: Path, sandbox_worktree_parent: Path
    ) -> None:
        wt = IsolatedWorktree(
            repo_root=sandbox_git_repo,
            base_ref="origin/main",
            new_branch="codex/a1-writer-contract2026-07-14",
            worktree_parent=sandbox_worktree_parent,
            enforce_sandbox=False,
            test_mode=True,
        )
        assert wt.new_branch == "codex/a1-writer-contract2026-07-14"

    def test_empty_base_ref_rejected(
        self, sandbox_git_repo: Path, sandbox_worktree_parent: Path
    ) -> None:
        with pytest.raises(RepoWriterError) as ei:
            IsolatedWorktree(
                repo_root=sandbox_git_repo,
                base_ref="",
                new_branch="ops/x",
                worktree_parent=sandbox_worktree_parent,
                enforce_sandbox=False,
                test_mode=True,
            )
        assert ei.value.code == "INVALID_BASE_REF"


# ----------------------------------------------------------------------
# IsolatedWorktree — sandbox enforcement
# ----------------------------------------------------------------------

class TestIsolatedWorktreeSandbox:
    def test_worktree_parent_inside_shared_checkout_rejected(
        self, sandbox_git_repo: Path
    ) -> None:
        with pytest.raises(RepoWriterError) as ei:
            IsolatedWorktree(
                repo_root=sandbox_git_repo,
                base_ref="origin/main",
                new_branch="ops/x",
                worktree_parent=sandbox_git_repo / "subdir",
                test_mode=True,
            )
        assert ei.value.code == "WORKTREE_PATH_OUTSIDE_SANDBOX"

    def test_worktree_parent_outside_opt_data_rejected(
        self, sandbox_git_repo: Path
    ) -> None:
        with pytest.raises(RepoWriterError) as ei:
            IsolatedWorktree(
                repo_root=sandbox_git_repo,
                base_ref="origin/main",
                new_branch="ops/x",
                worktree_parent=Path("/var/tmp/hermes-wt"),
                test_mode=True,
            )
        assert ei.value.code == "WORKTREE_PATH_OUTSIDE_SANDBOX"


# ----------------------------------------------------------------------
# IsolatedWorktree — clean shared checkout verification
# ----------------------------------------------------------------------

class TestIsolatedWorktreeSharedCheckoutGuard:
    def test_shared_checkout_dirty_rejected(
        self, sandbox_git_repo: Path, sandbox_worktree_parent: Path
    ) -> None:
        (sandbox_git_repo / "dirty.txt").write_text("uncommitted")
        wt = IsolatedWorktree(
            repo_root=sandbox_git_repo,
            base_ref="origin/main",
            new_branch="ops/clean-test",
            worktree_parent=sandbox_worktree_parent,
            enforce_sandbox=False,
            test_mode=True,
        )
        with pytest.raises(RepoWriterError) as ei:
            wt.create()
        assert ei.value.code == "SHARED_CHECKOUT_DIRTY"

    def test_shared_checkout_on_wrong_branch_rejected(
        self, sandbox_git_repo: Path, sandbox_worktree_parent: Path
    ) -> None:
        # Create a non-main branch and switch to it.
        env = os.environ.copy()
        env["GIT_AUTHOR_NAME"] = "sandbox"
        env["GIT_AUTHOR_EMAIL"] = "sandbox@test.local"
        env["GIT_COMMITTER_NAME"] = "sandbox"
        env["GIT_COMMITTER_EMAIL"] = "sandbox@test.local"
        (sandbox_git_repo / "more.txt").write_text("more")
        subprocess.run(["git", "add", "more.txt"], cwd=str(sandbox_git_repo), check=True, env=env)
        subprocess.run(
            ["git", "commit", "-q", "-m", "more"],
            cwd=str(sandbox_git_repo),
            check=True,
            env=env,
        )
        subprocess.run(
            ["git", "checkout", "-q", "-b", "feat/other"],
            cwd=str(sandbox_git_repo),
            check=True,
            env=env,
        )
        wt = IsolatedWorktree(
            repo_root=sandbox_git_repo,
            base_ref="origin/main",
            new_branch="ops/another-test",
            worktree_parent=sandbox_worktree_parent,
            enforce_sandbox=False,
            test_mode=True,
        )
        with pytest.raises(RepoWriterError) as ei:
            wt.create()
        assert ei.value.code == "SHARED_CHECKOUT_ON_WRONG_BRANCH"


# ----------------------------------------------------------------------
# IsolatedWorktree — happy path
# ----------------------------------------------------------------------

class TestIsolatedWorktreeHappyPath:
    def test_create_and_clean_verify(
        self, sandbox_git_repo: Path, sandbox_worktree_parent: Path
    ) -> None:
        wt = IsolatedWorktree(
            repo_root=sandbox_git_repo,
            base_ref="origin/main",
            new_branch="ops/sandbox-recovery",
            worktree_parent=sandbox_worktree_parent,
            enforce_sandbox=False,
            test_mode=True,
        )
        path = wt.create()
        assert path.exists()
        assert path.is_dir()
        # The new worktree should be on the requested branch and clean.
        head_branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(path),
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        assert head_branch == "ops/sandbox-recovery"
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(path),
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        assert status == ""
        # Re-verify.
        wt.verify_clean()
        # Remove cleanly.
        wt.remove()
        assert not path.exists()

    def test_create_codex_cloud_branch(
        self, sandbox_git_repo: Path, sandbox_worktree_parent: Path
    ) -> None:
        wt = IsolatedWorktree(
            repo_root=sandbox_git_repo,
            base_ref="origin/main",
            new_branch="codex/a1-writer-contract2026-07-14",
            worktree_parent=sandbox_worktree_parent,
            enforce_sandbox=False,
            test_mode=True,
        )
        path = wt.create()
        head_branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(path),
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        assert head_branch == "codex/a1-writer-contract2026-07-14"
        wt.remove()

    def test_create_uses_pinned_sha(
        self, sandbox_git_repo: Path, sandbox_worktree_parent: Path
    ) -> None:
        # Get the SHA that origin/main points to.
        sha = subprocess.run(
            ["git", "rev-parse", "origin/main"],
            cwd=str(sandbox_git_repo),
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        wt = IsolatedWorktree(
            repo_root=sandbox_git_repo,
            base_ref="origin/main",
            new_branch="ops/sha-pinning",
            worktree_parent=sandbox_worktree_parent,
            enforce_sandbox=False,
            test_mode=True,
        )
        path = wt.create()
        head_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(path),
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        assert head_sha == sha
        wt.remove()

    def test_existing_worktree_path_rejected(
        self, sandbox_git_repo: Path, sandbox_worktree_parent: Path
    ) -> None:
        # Pre-create the worktree path with a file.
        wt_name = "ops__already-exists"
        (sandbox_worktree_parent / wt_name).mkdir()
        wt = IsolatedWorktree(
            repo_root=sandbox_git_repo,
            base_ref="origin/main",
            new_branch="ops/already-exists",
            worktree_parent=sandbox_worktree_parent,
            enforce_sandbox=False,
            test_mode=True,
        )
        with pytest.raises(RepoWriterError) as ei:
            wt.create()
        assert ei.value.code == "WORKTREE_PATH_EXISTS"

    def test_remove_idempotent(
        self, sandbox_git_repo: Path, sandbox_worktree_parent: Path
    ) -> None:
        wt = IsolatedWorktree(
            repo_root=sandbox_git_repo,
            base_ref="origin/main",
            new_branch="ops/idempotent-remove",
            worktree_parent=sandbox_worktree_parent,
            enforce_sandbox=False,
            test_mode=True,
        )
        wt.create()
        wt.remove()
        wt.remove()  # no-op
        wt.remove()  # no-op


# ----------------------------------------------------------------------
# End-to-end: lock + worktree together
# ----------------------------------------------------------------------

class TestLockAndWorktreeIntegration:
    def test_full_workflow(
        self,
        tmp_path: Path,
        sandbox_git_repo: Path,
        sandbox_worktree_parent: Path,
    ) -> None:
        lock = RepoWriterLock(lock_path=tmp_path / "e2e.lock", stale_seconds=60, enforce_sandbox=False, test_mode=True)
        # Outside the lock: cannot create worktree (the contract
        # requires the lock first). The worktree contract itself
        # does not require the lock, but the lock is the policy
        # gate. We test the components independently here.
        with lock as ctx:
            ctx.acquire(
                branch="ops/e2e",
                session_id="e2e-session",
                worktree_path=str(sandbox_worktree_parent / "e2e"),
            )
            wt = IsolatedWorktree(
                repo_root=sandbox_git_repo,
                base_ref="origin/main",
                new_branch="ops/e2e",
                worktree_parent=sandbox_worktree_parent,
                enforce_sandbox=False,
                test_mode=True,
            )
            path = wt.create()
            assert path.exists()
            wt.remove()
        # After exit, lock is free.
        assert not lock.is_locked()

    def test_lock_held_blocks_subsequent_writer(
        self,
        tmp_path: Path,
    ) -> None:
        # Two locks pointing at the same path simulate two writers.
        path = tmp_path / "shared.lock"
        a = RepoWriterLock(lock_path=path, stale_seconds=60, enforce_sandbox=False, test_mode=True)
        b = RepoWriterLock(lock_path=path, stale_seconds=60, enforce_sandbox=False, test_mode=True)
        a.acquire(branch="ops/alpha", session_id="alpha")
        try:
            with pytest.raises(RepoWriterError) as ei:
                b.acquire(branch="ops/beta", session_id="beta")
            assert ei.value.code == "BLOCKED_BY_ACTIVE_REPO_WRITER"
            assert ei.value.holder["branch"] == "ops/alpha"
        finally:
            a.release()
        # b can now acquire.
        b.acquire(branch="ops/beta", session_id="beta")
        b.release()
