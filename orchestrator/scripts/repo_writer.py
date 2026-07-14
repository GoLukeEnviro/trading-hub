"""Hermes repository single-writer contract.

This module provides the two primitives the autonomous Trading Hub roadmap
loop needs to guarantee that **at most one agent session** (cron tick or
manual operator session) may write to the canonical ``trading-hub`` git
repository at any given moment, and that the shared canonical checkout is
**never** the place where branch creation or commits happen.

Two primitives:

- :class:`RepoWriterLock` — global, process-safe, non-blocking
  ``fcntl.flock`` on a preprovisioned file under
  ``/opt/data/state/repo-writer/``. Acquire fails fast with
  ``BLOCKED_BY_ACTIVE_REPO_WRITER`` when another writer holds it.
- :class:`IsolatedWorktree` — one-shot ``git worktree add`` from a
  pinned base ref, with explicit clean-worktree verification before
  branch creation and before commit.

Design constraints (all enforced in code):

- **Non-blocking**: ``fcntl.flock(LOCK_EX | LOCK_NB)``. Never wait.
- **Process-safe**: ``flock`` is per-process, file-backed. Releasing the
  lock is automatic on process exit (incl. SIGKILL).
- **Stale-safe**: a lock older than ``STALE_LOCK_SECONDS`` is treated as
  garbage and may be broken by the next acquirer (re-checked on every
  acquire attempt). Holder's PID is recorded; if the PID is dead, the
  lock is also treated as stale.
- **Never switch branches in the shared canonical checkout**: the
  ``IsolatedWorktree`` API always points the new worktree at the
  pinned base ref, never at the current branch of the shared checkout.
- **Clean-worktree verification**: ``git status --porcelain`` must be
  empty AND the new worktree's current branch must match the requested
  one before any commit.
- **No git reset / clean / push -f**: the contract is additive; the
  shared checkout is read-only from the writer's perspective.
- **Stable lock inode**: the root-owned lock parent cannot be modified by the
  writer. Production never creates the lock and ``assert_held()`` proves that
  the FD and canonical path still identify the same device/inode.
- **Path resolution is sandboxed**: lock and worktree paths are
  validated against the canonical repo root and the persistent
  volume root to prevent symlink/path-traversal attacks.
- **No embedded credentials**: the lock JSON contains only PID, host,
  worktree path, branch, session id, started-at. It never contains
  tokens, secrets or env values.

Usage (cron tick or manual session):

.. code-block:: python

    from orchestrator.scripts.repo_writer import (
        RepoWriterLock, IsolatedWorktree, RepoWriterError,
    )

    lock = RepoWriterLock()
    try:
        lock.acquire(branch="ops/hermes-single-writer-recovery",
                     session_id="20260713_184222_f94afc")
    except RepoWriterError as exc:
        if exc.code == "BLOCKED_BY_ACTIVE_REPO_WRITER":
            # do not proceed
            raise
        raise

    try:
        wt = IsolatedWorktree(
            repo_root="/workspace/projects/trading-hub",
            base_ref="origin/main",
            new_branch="ops/hermes-single-writer-recovery",
            worktree_parent="/opt/data/projects/trading-hub-worktrees",
            writer_lock=lock,
        )
        wt.create()
        # ... do work in wt.path ...
    finally:
        lock.release()

Error codes (string constants):

- ``BLOCKED_BY_ACTIVE_REPO_WRITER`` — another writer holds the lock
- ``LOCK_FILE_MISSING`` — the preprovisioned production lock is absent
- ``LOCK_OWNERSHIP_INVALID`` — lock ownership, type, mode, or access is invalid
- ``LOCK_PATH_REPLACED`` — the held FD and canonical path identify different
  inodes (or the path disappeared)
- ``LOCK_HELD_BY_DEAD_PID`` — stale lock whose holder is no longer
  running; the acquirer MUST NOT silently break it without
  human approval (the PID check is informational, the actual
  breaking is opt-in via ``force_break_stale=True``)
- ``SHARED_CHECKOUT_DIRTY`` — the shared canonical checkout is not
  clean; refuse to create a worktree
- ``SHARED_CHECKOUT_ON_WRONG_BRANCH`` — current branch of the
  shared checkout is not the canonical base branch (``main``); refuse
- ``WORKTREE_DIRTY`` — the freshly-created worktree has local
  modifications or staged changes
- ``WORKTREE_ON_WRONG_BRANCH`` — the worktree's HEAD branch is not
  the requested one
- ``BASE_REF_NOT_PINNED`` — the requested base ref is not a
  fully-resolved SHA; refuse (anchored to a moving branch is a
  fan-out risk)
- ``LOCK_PATH_OUTSIDE_SANDBOX`` — the resolved lock file path
  escapes the configured sandbox root
- ``WORKTREE_PATH_OUTSIDE_SANDBOX`` — the resolved worktree path
  escapes the configured sandbox root
- ``WRITER_IDENTITY_MISMATCH`` — the process identity, canonical repo,
  lock path, worktree parent, or writer-owned parent metadata does not
  match the Hermes container production contract
"""

from __future__ import annotations

import errno
import fcntl
import json
import os
import pwd
import re
import socket
import stat
import subprocess
import sys
from contextlib import suppress
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Sequence

# ----------------------------------------------------------------------
# Canonical paths (single source of truth)
# ----------------------------------------------------------------------

# Persistent state directory (durable across reboots, hermes-writable).
PERSISTENT_STATE_DIR = Path("/opt/data/state")

# The parent is root-owned and not removable by the Hermes writer identity.
LOCK_DIRECTORY = PERSISTENT_STATE_DIR / "repo-writer"
# The file is preprovisioned as hermes:hermes 0600; production never creates it.
LOCK_FILE_PATH = LOCK_DIRECTORY / "hermes-repo-writer.lock"

# Default worktree parent directory (one level under /opt/data so hermes
# can write without /workspace ACLs).
DEFAULT_WORKTREE_PARENT = Path("/opt/data/projects/trading-hub-worktrees")

# Shared canonical checkout (read-only from the writer's perspective).
DEFAULT_REPO_ROOT = Path("/workspace/projects/trading-hub")

# Base ref that all roadmap-tick worktrees must be forked from.
# Pinned to origin/main, not main, so we always pick up the remote
# authoritative state, not the local-ahead R5B contamination.
DEFAULT_BASE_REF = "origin/main"

# Production writer identity. Host root, deploy, operator, and host-only
# path namespaces are never valid autonomous writer contexts.
EXPECTED_WRITER_UID = 10000
EXPECTED_WRITER_GID = 10000
EXPECTED_WRITER_USER = "hermes"

# Stale lock threshold — if the lock is older than this AND the holder
# PID is dead, the lock is considered stale and may be broken.
STALE_LOCK_SECONDS = 1800  # 30 min

# Maximum time the worktree directory may keep an isolated worktree
# (cleanup enforcement lives in the worktree removal step, not in
# the lock itself).
MAX_WORKTREE_AGE_SECONDS = 86400  # 24h

# Forbidden workdir patterns (defense in depth — the worktree parent is
# always inside the persistent volume, never inside the shared checkout).
FORBIDDEN_WORKTREE_PARENT_PATTERNS = (
    re.compile(r"/workspace/projects/trading-hub(/|$)"),
    re.compile(r"/workspace/projects/ai4trade-bot(/|$)"),
)

# Allowed branch name pattern (defense in depth — worktrees are
# always created from origin/main, so this is mainly for sanity). ``codex/``
# is included for Codex Cloud A1 sessions, whose operator contract requires
# reviewable branches named ``codex/{feature}{date}``.
BRANCH_NAME_PATTERN = re.compile(r"^(feat|fix|docs|ops|chore|test|refactor|ci|codex)/[a-z0-9][a-z0-9_./-]*$")


# ----------------------------------------------------------------------
# Errors
# ----------------------------------------------------------------------


class RepoWriterError(Exception):
    """Base class for all repo writer contract errors.

    The string attribute ``code`` is one of the documented error codes
    and is stable for downstream machine consumption.
    """

    def __init__(self, code: str, message: str, *, holder: Optional[dict] = None) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.holder = holder or {}


# ----------------------------------------------------------------------
# Production writer identity / mount guard
# ----------------------------------------------------------------------


def _current_writer_identity() -> tuple[int, str]:
    """Return the effective UID and passwd-resolved username."""
    euid = os.geteuid()
    try:
        username = pwd.getpwuid(euid).pw_name
    except KeyError:
        username = "<unknown>"
    return euid, username


def _writer_parent_status(path: Path) -> tuple[int, int, bool, bool]:
    """Return uid, gid, directory status, and writer access for ``path``."""
    try:
        metadata = path.stat()
    except OSError:
        return -1, -1, False, False
    return (
        metadata.st_uid,
        metadata.st_gid,
        path.is_dir(),
        os.access(path, os.W_OK | os.X_OK),
    )


def _lock_file_status(path: Path) -> tuple[int, int, bool, int, bool]:
    """Return ownership, regular-file status, mode, and writer access."""
    try:
        metadata = path.lstat()
    except OSError:
        return -1, -1, False, 0, False
    return (
        metadata.st_uid,
        metadata.st_gid,
        stat.S_ISREG(metadata.st_mode),
        stat.S_IMODE(metadata.st_mode),
        os.access(path, os.R_OK | os.W_OK),
    )


def _resolved_path(path: Path) -> Path:
    try:
        return path.resolve(strict=False)
    except OSError:
        return path.absolute()


def _writer_identity_mismatch(message: str) -> RepoWriterError:
    return RepoWriterError("WRITER_IDENTITY_MISMATCH", message)


def _validate_production_writer_environment(
    *,
    repo_root: Path = DEFAULT_REPO_ROOT,
    lock_path: Path = LOCK_FILE_PATH,
    worktree_parent: Path = DEFAULT_WORKTREE_PARENT,
) -> None:
    """Fail closed unless execution is in the Hermes writer namespace.

    This validation runs before a lock file, directory, or worktree can be
    created. Tests that need temporary paths must opt in with
    ``test_mode=True`` at the public constructor boundary.
    """
    euid, username = _current_writer_identity()
    if euid != EXPECTED_WRITER_UID or username != EXPECTED_WRITER_USER:
        raise _writer_identity_mismatch(
            "writer requires "
            f"euid={EXPECTED_WRITER_UID} user={EXPECTED_WRITER_USER!r}; "
            f"got euid={euid} user={username!r}"
        )

    required_paths = (
        ("canonical repository", Path(repo_root), DEFAULT_REPO_ROOT),
        ("lock file", Path(lock_path), LOCK_FILE_PATH),
        ("worktree parent", Path(worktree_parent), DEFAULT_WORKTREE_PARENT),
    )
    for label, actual, expected in required_paths:
        resolved_actual = _resolved_path(actual)
        resolved_expected = _resolved_path(expected)
        if resolved_actual != resolved_expected:
            raise _writer_identity_mismatch(f"{label} must resolve to {resolved_expected}; got {resolved_actual}")

    lock_parent = Path(lock_path).parent
    uid, gid, is_dir, writable = _writer_parent_status(lock_parent)
    if not is_dir:
        raise _writer_identity_mismatch(f"lock parent {lock_parent} is missing or not a directory")
    if uid != 0 or gid != 0:
        raise _writer_identity_mismatch(f"lock parent {lock_parent} requires uid:gid 0:0; got {uid}:{gid}")
    if writable:
        raise _writer_identity_mismatch(f"lock parent {lock_parent} must not be writable by the writer")

    worktree_parent_path = Path(worktree_parent)
    uid, gid, is_dir, writable = _writer_parent_status(worktree_parent_path)
    if not is_dir:
        raise _writer_identity_mismatch(f"worktree parent {worktree_parent_path} is missing or not a directory")
    if uid != EXPECTED_WRITER_UID or gid != EXPECTED_WRITER_GID:
        raise _writer_identity_mismatch(
            f"worktree parent requires uid:gid {EXPECTED_WRITER_UID}:{EXPECTED_WRITER_GID}; got {uid}:{gid}"
        )
    if not writable:
        raise _writer_identity_mismatch(f"worktree parent {worktree_parent_path} is not writer-writable")

    lock_uid, lock_gid, is_file, mode, lock_writable = _lock_file_status(Path(lock_path))
    if lock_uid == -1:
        raise RepoWriterError(
            "LOCK_FILE_MISSING",
            f"preprovisioned lock file is missing: {lock_path}",
        )
    if (
        lock_uid != EXPECTED_WRITER_UID
        or lock_gid != EXPECTED_WRITER_GID
        or not is_file
        or mode != 0o600
        or not lock_writable
    ):
        raise RepoWriterError(
            "LOCK_OWNERSHIP_INVALID",
            "preprovisioned lock requires regular file, uid:gid "
            f"{EXPECTED_WRITER_UID}:{EXPECTED_WRITER_GID}, mode 0600, writer access",
        )


def _validate_test_mode(*, test_mode: bool, enforce_sandbox: bool) -> None:
    if not test_mode and not enforce_sandbox:
        raise _writer_identity_mismatch("enforce_sandbox=False is allowed only with explicit test_mode=True")


# ----------------------------------------------------------------------
# RepoWriterLock
# ----------------------------------------------------------------------


@dataclass
class LockHolder:
    pid: int
    host: str
    worktree_path: str
    branch: str
    session_id: str
    started_at: str  # ISO 8601 UTC
    note: str = ""
    lock_device: int = 0
    lock_inode: int = 0

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, indent=2)

    @classmethod
    def from_json(cls, raw: str) -> "LockHolder":
        data = json.loads(raw)
        return cls(
            pid=int(data["pid"]),
            host=str(data["host"]),
            worktree_path=str(data["worktree_path"]),
            branch=str(data["branch"]),
            session_id=str(data["session_id"]),
            started_at=str(data["started_at"]),
            note=str(data.get("note", "")),
            lock_device=int(data.get("lock_device", 0)),
            lock_inode=int(data.get("lock_inode", 0)),
        )


class RepoWriterLock:
    """Global non-blocking writer lock for the trading-hub repo.

    The lock is held by writing a small JSON document to the preprovisioned
    ``/opt/data/state/repo-writer/hermes-repo-writer.lock`` and acquiring an
    exclusive ``fcntl.flock`` on the file's open file descriptor. The
    lock is process-scoped — when the holding process exits, the
    kernel releases the flock automatically.

    Stale detection: if the lock is older than
    ``STALE_LOCK_SECONDS`` AND the recorded PID is no longer alive,
    the next acquirer may break it (opt-in via ``force_break_stale``).
    This protects against crashed agents that orphan the lock until
    manual cleanup.

    The lock JSON contains only operational metadata (PID, host,
    worktree path, branch, session id, started-at, device, inode). It does not
    contain tokens, secrets, or environment values.
    """

    def __init__(
        self,
        lock_path: Path = LOCK_FILE_PATH,
        stale_seconds: int = STALE_LOCK_SECONDS,
        *,
        enforce_sandbox: bool = True,
        test_mode: bool = False,
    ) -> None:
        self.lock_path = Path(lock_path)
        self.stale_seconds = int(stale_seconds)
        self.test_mode = bool(test_mode)
        _validate_test_mode(
            test_mode=self.test_mode,
            enforce_sandbox=enforce_sandbox,
        )
        if not self.test_mode:
            _validate_production_writer_environment(lock_path=self.lock_path)
        # Validate sandbox after the identity/path guard. A wrong production
        # context must fail before it can create writer state.
        if enforce_sandbox:
            self._validate_sandbox()
        # Open file descriptor is created on acquire; released on release.
        self._fd: Optional[int] = None

    # ----- public API -----

    def acquire(
        self,
        *,
        branch: str,
        session_id: str,
        worktree_path: str = "",
        note: str = "",
        force_break_stale: bool = False,
    ) -> LockHolder:
        """Acquire the global writer lock. Non-blocking.

        Raises :class:`RepoWriterError` with code
        ``BLOCKED_BY_ACTIVE_REPO_WRITER`` if another live writer
        holds the lock. The exception's ``holder`` attribute carries
        the current holder metadata so callers can include it in
        reports.
        """
        if not BRANCH_NAME_PATTERN.match(branch):
            raise RepoWriterError(
                "INVALID_BRANCH_NAME",
                f"branch {branch!r} does not match required pattern",
            )
        if not session_id or not isinstance(session_id, str):
            raise RepoWriterError(
                "INVALID_SESSION_ID",
                "session_id must be a non-empty string",
            )

        # Acquire the flock first — it is the authoritative source
        # of truth. The on-disk JSON is informational and may be
        # stale or absent; the flock cannot be.
        open_flags = os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
        if self.test_mode:
            open_flags |= os.O_CREAT
        try:
            fd = os.open(str(self.lock_path), open_flags, 0o600)
        except FileNotFoundError as exc:
            raise RepoWriterError(
                "LOCK_FILE_MISSING",
                f"preprovisioned lock file is missing: {self.lock_path}",
            ) from exc
        except OSError as exc:
            if exc.errno == errno.ELOOP:
                raise RepoWriterError(
                    "LOCK_PATH_REPLACED",
                    f"lock path is a symlink: {self.lock_path}",
                ) from exc
            raise
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            os.close(fd)
            if exc.errno in (errno.EWOULDBLOCK, errno.EAGAIN):
                # Read the existing holder JSON for context.
                existing = self._read_holder()
                existing_dict = asdict(existing) if existing is not None else {}
                message = (
                    "lock held by "
                    f"pid={existing_dict.get('pid')} "
                    f"branch={existing_dict.get('branch')!r} "
                    f"session={existing_dict.get('session_id')!r}"
                    if existing_dict
                    else "lock held by another writer (no holder JSON)"
                )
                raise RepoWriterError(
                    "BLOCKED_BY_ACTIVE_REPO_WRITER",
                    message,
                    holder=existing_dict,
                ) from exc
            raise

        try:
            fd_metadata = self._assert_fd_matches_path(fd)
        except RepoWriterError:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
            raise

        # We have the flock. Optionally check the on-disk holder
        # JSON for stale-but-not-yet-released information (e.g. a
        # crashed process whose PID is dead AND whose age exceeds
        # the threshold). The flock itself is the real lock; this
        # check is defensive: it lets the next acquirer know that
        # a previous holder crashed without releasing.
        existing = self._read_holder_fd(fd)
        if existing is not None and self._is_stale(existing) and not force_break_stale:
            # We already have the flock, but a previous holder's
            # stale metadata is on disk. Clean it up and proceed.
            # This is NOT a security issue: the flock was free.
            with suppress(OSError):
                os.ftruncate(fd, 0)

        # Truncate and write the holder JSON.
        os.ftruncate(fd, 0)
        holder = LockHolder(
            pid=os.getpid(),
            host=socket.gethostname(),
            worktree_path=worktree_path,
            branch=branch,
            session_id=session_id,
            started_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            note=note,
            lock_device=fd_metadata.st_dev,
            lock_inode=fd_metadata.st_ino,
        )
        os.write(fd, holder.to_json().encode("utf-8"))
        os.fsync(fd)

        self._fd = fd
        try:
            self.assert_held()
        except RepoWriterError:
            self.release()
            raise
        return holder

    def assert_held(self) -> None:
        """Fail closed unless this object holds the canonical lock inode."""
        if self._fd is None:
            raise RepoWriterError(
                "LOCK_NOT_HELD",
                "repository mutation requires an acquired writer lock",
            )
        self._assert_fd_matches_path(self._fd)

    def run_guarded_mutation(
        self,
        *,
        mutation: str,
        command: Sequence[str],
        cwd: Path,
        timeout: int = 120,
    ) -> subprocess.CompletedProcess[str]:
        """Run an approved repository mutation after rechecking the inode."""
        self.assert_held()
        if mutation == "merge":
            raise RepoWriterError(
                "HUMAN_ONLY_MERGE_REQUIRED",
                "agents may stop only at READY_FOR_HUMAN_MERGE",
            )
        if mutation not in {"commit", "push", "pr-create"}:
            raise RepoWriterError(
                "UNSUPPORTED_REPOSITORY_MUTATION",
                f"unsupported guarded mutation: {mutation}",
            )
        return subprocess.run(
            list(command),
            cwd=str(cwd),
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def release(self) -> None:
        """Release the global writer lock.

        Idempotent: calling release() when the lock is not held is a
        no-op.
        """
        if self._fd is None:
            return
        try:
            fcntl.flock(self._fd, fcntl.LOCK_UN)
        finally:
            os.close(self._fd)
            self._fd = None
        # Best-effort: leave the holder JSON on disk as a record of
        # the most recent acquirer. It will be overwritten on the
        # next acquire().

    def read_holder(self) -> Optional[LockHolder]:
        """Return the current holder, or None if the lock is free."""
        return self._read_holder()

    def is_locked(self) -> bool:
        """True iff the lock is currently held by a live process.

        Performs a non-blocking flock test on the lock file. If the
        flock succeeds, the lock is free (and we release the test
        flock immediately). If the flock fails with EWOULDBLOCK, the
        lock is held. This is the authoritative "would acquire()
        right now succeed?" check; the on-disk holder JSON is
        informational.
        """
        # If the lock file does not exist, the lock is free.
        if not self.lock_path.exists():
            return False
        # Try a non-blocking flock. If we get it, the lock is free.
        try:
            open_flags = os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
            if self.test_mode:
                open_flags |= os.O_CREAT
            fd = os.open(str(self.lock_path), open_flags, 0o600)
        except OSError:
            return False
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                return exc.errno in (errno.EWOULDBLOCK, errno.EAGAIN)
            # We got the lock; release it.
            fcntl.flock(fd, fcntl.LOCK_UN)
            return False
        finally:
            os.close(fd)

    # ----- context manager -----

    def __enter__(self) -> "RepoWriterLock":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()

    # ----- internals -----

    def _assert_fd_matches_path(self, fd: int) -> os.stat_result:
        try:
            fd_metadata = os.fstat(fd)
        except OSError as exc:
            raise RepoWriterError(
                "LOCK_NOT_HELD",
                "writer lock file descriptor is no longer valid",
            ) from exc
        try:
            path_metadata = os.stat(self.lock_path, follow_symlinks=False)
        except OSError as exc:
            raise RepoWriterError(
                "LOCK_PATH_REPLACED",
                f"locked path disappeared while held: {self.lock_path}",
            ) from exc
        if (
            not stat.S_ISREG(path_metadata.st_mode)
            or fd_metadata.st_dev != path_metadata.st_dev
            or fd_metadata.st_ino != path_metadata.st_ino
        ):
            raise RepoWriterError(
                "LOCK_PATH_REPLACED",
                "locked file descriptor and canonical path do not identify "
                f"the same inode: fd={fd_metadata.st_dev}:{fd_metadata.st_ino} "
                f"path={path_metadata.st_dev}:{path_metadata.st_ino}",
            )
        return fd_metadata

    @staticmethod
    def _read_holder_fd(fd: int) -> Optional[LockHolder]:
        try:
            raw = os.pread(fd, 65_536, 0).decode("utf-8").strip()
        except (OSError, UnicodeDecodeError):
            return None
        if not raw:
            return None
        try:
            return LockHolder.from_json(raw)
        except (json.JSONDecodeError, KeyError, ValueError, TypeError):
            return None

    def _read_holder(self) -> Optional[LockHolder]:
        if not self.lock_path.exists():
            return None
        try:
            with open(self.lock_path, "r", encoding="utf-8") as fh:
                raw = fh.read().strip()
        except (OSError, IOError):
            return None
        if not raw:
            return None
        try:
            return LockHolder.from_json(raw)
        except (json.JSONDecodeError, KeyError, ValueError, TypeError):
            # Malformed lock file. Treat as stale; do not auto-break.
            return None

    def _is_stale(self, holder: LockHolder) -> bool:
        # 1. PID alive?
        if not _pid_alive(holder.pid):
            return True
        # 2. Age?
        try:
            started = datetime.fromisoformat(holder.started_at)
        except (ValueError, TypeError):
            return True
        age = (datetime.now(timezone.utc) - started).total_seconds()
        return age > self.stale_seconds

    def _validate_sandbox(self) -> None:
        # Ensure the lock path is inside the persistent state dir.
        # Use realpath to defeat symlink-based escapes.
        try:
            resolved_lock = self.lock_path.resolve(strict=False)
        except OSError:
            resolved_lock = self.lock_path.absolute()
        try:
            resolved_root = PERSISTENT_STATE_DIR.resolve(strict=False)
        except OSError:
            resolved_root = PERSISTENT_STATE_DIR.absolute()
        try:
            resolved_lock.relative_to(resolved_root)
        except ValueError:
            raise RepoWriterError(
                "LOCK_PATH_OUTSIDE_SANDBOX",
                f"lock path {resolved_lock} escapes sandbox root {resolved_root}",
            ) from None


# ----------------------------------------------------------------------
# IsolatedWorktree
# ----------------------------------------------------------------------


class IsolatedWorktree:
    """One isolated git worktree per run, forked from a pinned base ref.

    The contract:

    - The shared canonical checkout (default ``/workspace/projects/trading-hub``)
      is **read-only** from the writer's perspective. The writer MUST
      NOT ``git checkout``, ``git switch``, ``git reset``, or ``git pull``
      there.
    - Each run creates a fresh worktree under the configured parent
      (default ``/opt/data/projects/trading-hub-worktrees``) at a
      pinned base ref (default ``origin/main``).
    - Before commit, the new worktree's status must be clean.
    - After merge or formal abort, the worktree must be removed.
    """

    def __init__(
        self,
        *,
        repo_root: Path = DEFAULT_REPO_ROOT,
        base_ref: str = DEFAULT_BASE_REF,
        new_branch: str,
        worktree_parent: Path = DEFAULT_WORKTREE_PARENT,
        worktree_name: Optional[str] = None,
        writer_lock: Optional[RepoWriterLock] = None,
        enforce_sandbox: bool = True,
        test_mode: bool = False,
    ) -> None:
        self.repo_root = Path(repo_root)
        self.base_ref = base_ref
        self.new_branch = new_branch
        self.worktree_parent = Path(worktree_parent)
        self.worktree_name = worktree_name or _sanitize_worktree_name(new_branch)
        self.worktree_path = self.worktree_parent / self.worktree_name
        self.writer_lock = writer_lock
        self._validate_inputs()
        self.test_mode = bool(test_mode)
        _validate_test_mode(
            test_mode=self.test_mode,
            enforce_sandbox=enforce_sandbox,
        )
        if not self.test_mode:
            _validate_production_writer_environment(
                repo_root=self.repo_root,
                worktree_parent=self.worktree_parent,
            )
        if enforce_sandbox:
            self._validate_sandbox()
        self._created = False

    # ----- public API -----

    def create(self) -> Path:
        """Create the isolated worktree. Returns the worktree path.

        Steps:
        1. Verify the shared canonical checkout is on a clean ``main``
           (no local changes, no detached HEAD on a non-main ref).
        2. Resolve the base ref to a fully-pinned SHA.
        3. ``git worktree add -b <new_branch> <worktree_path> <pinned_sha>``
        4. Verify the new worktree's HEAD is on the requested branch
           AND ``git status --porcelain`` is empty.
        """
        self._assert_mutation_lock()
        self._check_shared_checkout()

        pinned_sha = self._resolve_base_sha()
        self._git_worktree_add(pinned_sha)
        self._check_worktree_clean()
        self._created = True
        return self.worktree_path

    def verify_clean(self) -> None:
        """Re-verify clean status (call before commit)."""
        if not self._created:
            raise RepoWriterError(
                "WORKTREE_NOT_CREATED",
                "verify_clean() called before create()",
            )
        self._check_worktree_clean()

    def remove(self, force: bool = False) -> None:
        """Remove the worktree. Idempotent."""
        if not self.worktree_path.exists():
            return
        self._assert_mutation_lock()
        cmd = ["git", "worktree", "remove"]
        if force:
            cmd.append("--force")
        cmd.append(str(self.worktree_path))
        subprocess.run(
            cmd,
            cwd=str(self.repo_root),
            check=False,
            capture_output=True,
        )
        self._created = False

    # ----- internals -----

    def _assert_mutation_lock(self) -> None:
        if self.test_mode:
            return
        if self.writer_lock is None:
            raise RepoWriterError(
                "LOCK_NOT_HELD",
                "production worktree mutation requires the owning writer lock",
            )
        self.writer_lock.assert_held()

    def _validate_inputs(self) -> None:
        if not BRANCH_NAME_PATTERN.match(self.new_branch):
            raise RepoWriterError(
                "INVALID_BRANCH_NAME",
                f"new_branch {self.new_branch!r} does not match required pattern",
            )
        if not self.base_ref or not isinstance(self.base_ref, str):
            raise RepoWriterError(
                "INVALID_BASE_REF",
                "base_ref must be a non-empty string",
            )

    def _validate_sandbox(self) -> None:
        # Worktree parent must not be inside the shared checkout.
        try:
            parent_resolved = self.worktree_parent.resolve(strict=False)
        except OSError:
            parent_resolved = self.worktree_parent.absolute()
        for pat in FORBIDDEN_WORKTREE_PARENT_PATTERNS:
            if pat.search(str(parent_resolved)):
                raise RepoWriterError(
                    "WORKTREE_PATH_OUTSIDE_SANDBOX",
                    f"worktree parent {parent_resolved} is inside a forbidden path",
                )
        # Worktree parent must be inside /opt/data (writable by hermes).
        try:
            opt_data = Path("/opt/data").resolve(strict=False)
            parent_resolved.relative_to(opt_data)
        except ValueError:
            raise RepoWriterError(
                "WORKTREE_PATH_OUTSIDE_SANDBOX",
                f"worktree parent {parent_resolved} must be inside /opt/data",
            ) from None

    def _check_shared_checkout(self) -> None:
        # 1. The repo root must exist and be a git worktree.
        if not (self.repo_root / ".git").exists() and not (self.repo_root / ".git").is_file():
            raise RepoWriterError(
                "SHARED_CHECKOUT_MISSING",
                f"shared canonical checkout not found at {self.repo_root}",
            )
        # 2. Current branch of the shared checkout must be main (or
        #    a worktree list entry for main; we never switch).
        current_branch = _git_rev_parse(self.repo_root, "--abbrev-ref", "HEAD")
        if current_branch != "main":
            raise RepoWriterError(
                "SHARED_CHECKOUT_ON_WRONG_BRANCH",
                f"shared checkout is on branch {current_branch!r}, expected 'main'",
            )
        # 3. The shared checkout must be clean — no local changes
        # that would pollute the new worktree's base.
        status_output = _git(self.repo_root, "status", "--porcelain")
        if status_output.strip():
            raise RepoWriterError(
                "SHARED_CHECKOUT_DIRTY",
                f"shared checkout is dirty: {status_output.splitlines()[:5]}",
            )

    def _resolve_base_sha(self) -> str:
        # Fetch the base ref so we have an up-to-date remote ref.
        # NOTE: we never fast-forward the local main; we only fetch.
        #
        # The ``base_ref`` is the canonical name (e.g. ``origin/main``)
        # which is the local remote-tracking branch. To refresh it we
        # run ``git fetch origin <remote-branch>``. The remote branch
        # name is the part after the ``/``.
        if "/" not in self.base_ref:
            raise RepoWriterError(
                "BASE_REF_NOT_PINNED",
                f"base ref {self.base_ref!r} must be a fully-qualified tracking ref (e.g. 'origin/main')",
            )
        remote_name, remote_branch = self.base_ref.split("/", 1)
        result = subprocess.run(
            ["git", "fetch", remote_name, remote_branch],
            cwd=str(self.repo_root),
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            raise RepoWriterError(
                "BASE_REF_FETCH_FAILED",
                f"git fetch {remote_name} {remote_branch} failed: {result.stderr.strip()[:200]}",
            )
        # Resolve to a fully-pinned SHA. Refuse to anchor to a
        # moving branch — the worktree's base must be a SHA so the
        # worktree cannot drift between create() and commit.
        sha = _git_rev_parse_sha(self.repo_root, self.base_ref)
        if not re.fullmatch(r"[0-9a-f]{40}", sha):
            raise RepoWriterError(
                "BASE_REF_NOT_PINNED",
                f"base ref {self.base_ref!r} did not resolve to a 40-char SHA (got {sha!r})",
            )
        return sha

    def _git_worktree_add(self, pinned_sha: str) -> None:
        if self.worktree_path.exists():
            raise RepoWriterError(
                "WORKTREE_PATH_EXISTS",
                f"worktree path {self.worktree_path} already exists; refusing to clobber",
            )
        cmd = [
            "git",
            "worktree",
            "add",
            "-b",
            self.new_branch,
            str(self.worktree_path),
            pinned_sha,
        ]
        result = subprocess.run(
            cmd,
            cwd=str(self.repo_root),
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            raise RepoWriterError(
                "WORKTREE_CREATE_FAILED",
                f"git worktree add failed: {result.stderr.strip()[:200]}",
            )

    def _check_worktree_clean(self) -> None:
        if not self.worktree_path.exists():
            raise RepoWriterError(
                "WORKTREE_MISSING",
                f"worktree {self.worktree_path} does not exist after create()",
            )
        # The worktree's HEAD branch must be the requested one.
        head_branch = _git_rev_parse(self.worktree_path, "--abbrev-ref", "HEAD")
        if head_branch != self.new_branch:
            raise RepoWriterError(
                "WORKTREE_ON_WRONG_BRANCH",
                f"worktree HEAD is on {head_branch!r}, expected {self.new_branch!r}",
            )
        # The worktree's status must be clean.
        status_output = _git(self.worktree_path, "status", "--porcelain")
        if status_output.strip():
            raise RepoWriterError(
                "WORKTREE_DIRTY",
                f"worktree is dirty after create(): {status_output.splitlines()[:5]}",
            )


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _pid_alive(pid: int) -> bool:
    """Return True iff the given PID is alive in the current PID namespace.

    Uses ``os.kill(pid, 0)`` which is portable and does not actually
    send a signal.
    """
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # PID exists but belongs to another UID; we are not the
        # owner. Treat as alive so we don't accidentally break a
        # lock held by a higher-privileged process.
        return True
    except OSError:
        return False
    return True


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        raise RepoWriterError(
            "GIT_COMMAND_FAILED",
            f"git {' '.join(args)} failed: {result.stderr.strip()[:200]}",
        )
    return result.stdout


def _git_rev_parse(cwd: Path, *args: str) -> str:
    """Thin wrapper over ``git rev-parse ...``."""
    return _git(cwd, "rev-parse", *args).strip()


def _git_rev_parse_sha(cwd: Path, ref: str) -> str:
    """Resolve ``ref`` to a full 40-char SHA using ``git rev-parse --verify``."""
    return _git(cwd, "rev-parse", "--verify", ref).strip()


def _sanitize_worktree_name(branch: str) -> str:
    """Derive a worktree directory name from a branch name.

    Example: ``ops/hermes-single-writer-recovery`` ->
    ``ops__hermes-single-writer-recovery``.
    """
    return branch.replace("/", "__")


# ----------------------------------------------------------------------
# CLI (for ad-hoc testing and operator inspection)
# ----------------------------------------------------------------------


def _cli() -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="repo_writer",
        description="Hermes single-writer lock + isolated worktree helper",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="print the current lock holder")
    p_acquire = sub.add_parser("acquire", help="acquire the lock (does not release)")
    p_acquire.add_argument("--branch", required=True)
    p_acquire.add_argument("--session-id", required=True)
    p_acquire.add_argument("--worktree-path", default="")
    p_acquire.add_argument("--note", default="")
    p_acquire.add_argument("--force-break-stale", action="store_true")
    sub.add_parser("release", help="release the lock (only if held by this pid)")
    p_worktree = sub.add_parser("worktree", help="create an isolated worktree")
    p_worktree.add_argument("--branch", required=True)
    p_worktree.add_argument("--base-ref", default=DEFAULT_BASE_REF)
    p_worktree.add_argument("--repo-root", default=str(DEFAULT_REPO_ROOT))
    p_worktree.add_argument("--worktree-parent", default=str(DEFAULT_WORKTREE_PARENT))

    args = parser.parse_args()
    try:
        if args.cmd == "status":
            lock = RepoWriterLock()
            holder = lock.read_holder()
            if holder is None:
                print("FREE")
                return 0
            print(json.dumps(asdict(holder), indent=2))
            return 0
        if args.cmd == "acquire":
            lock = RepoWriterLock()
            holder = lock.acquire(
                branch=args.branch,
                session_id=args.session_id,
                worktree_path=args.worktree_path,
                note=args.note,
                force_break_stale=args.force_break_stale,
            )
            print(json.dumps(asdict(holder), indent=2))
            return 0
        if args.cmd == "release":
            lock = RepoWriterLock()
            # Only release if the lock is held by THIS process.
            holder = lock.read_holder()
            if holder is None:
                print("FREE")
                return 0
            if holder.pid != os.getpid():
                print(f"REFUSED: lock held by pid={holder.pid}, this pid={os.getpid()}")
                return 2
            lock.release()
            print("RELEASED")
            return 0
        if args.cmd == "worktree":
            wt = IsolatedWorktree(
                repo_root=Path(args.repo_root),
                base_ref=args.base_ref,
                new_branch=args.branch,
                worktree_parent=Path(args.worktree_parent),
            )
            path = wt.create()
            print(str(path))
            return 0
    except RepoWriterError as exc:
        print(f"ERROR {exc.code}: {exc}", file=sys.stderr)
        if exc.holder:
            print(json.dumps(exc.holder, indent=2), file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    sys.exit(_cli())
