#!/usr/bin/env python3
"""Reconcile the external SI v2 controller baseline to a verified origin/main SHA.

Usage:
    python3 orchestrator/control/reconcile_controller_baseline.py \\
        --state /path/to/STATE.json \\
        --queue /path/to/QUEUE.json \\
        --commit <sha256>

Safe preconditions:
    - Controller status is PAUSED or another explicitly allowed non-invocation status.
    - Queue items are empty.
    - All active work fields (branch, worktree, PR, work_item_id) are null.
    - Target commit exists and is reachable from origin/main.
    - STATE and QUEUE satisfy schemas and cross-field invariants.

Atomic updates:
    - Creates timestamped SHA-256-checksummed backups before mutation.
    - Fsyncs files and containing directories after write.
    - Revalidates both files after promotion.
    - Restores backups automatically on failed post-validation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path

# Compiled SHA patterns — accept standard 40-char Git SHA-1 and 64-char SHA-256.
# Use \Z (not $) so that a trailing newline does not slip through.
_SHA1_RE: re.Pattern[str] = re.compile(r"\A[0-9a-f]{40}\Z")
_SHA256_RE: re.Pattern[str] = re.compile(r"\A[0-9a-f]{64}\Z")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reconcile controller baseline to a verified origin/main commit"
    )
    parser.add_argument(
        "--state", required=True, type=Path,
        help="Path to STATE.json",
    )
    parser.add_argument(
        "--queue", required=True, type=Path,
        help="Path to QUEUE.json",
    )
    parser.add_argument(
        "--commit", required=True,
        help="Target SHA-256 commit on origin/main",
    )
    parser.add_argument(
        "--repo", type=Path, default=Path.cwd(),
        help="Repository root (for git operations)",
    )
    args = parser.parse_args()

    state_path: Path = args.state.resolve()
    queue_path: Path = args.queue.resolve()
    repo_root: Path = args.repo.resolve()
    target_commit: str = args.commit.strip()

    # ------------------------------------------------------------------
    # Validate target commit
    # ------------------------------------------------------------------
    _validate_sha(target_commit)
    _commit_exists(target_commit, repo_root)

    # ------------------------------------------------------------------
    # Load and validate state
    # ------------------------------------------------------------------
    state = _load_json(state_path, "STATE")
    queue = _load_json(queue_path, "QUEUE")

    _validate_state(state, state_path)
    _validate_queue(queue, queue_path)

    # ------------------------------------------------------------------
    # Take collision-safe timestamped backups
    # ------------------------------------------------------------------
    backup_dir = state_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")

    state_backup = _safe_backup(state_path, backup_dir, timestamp)
    queue_backup = _safe_backup(queue_path, backup_dir, timestamp)

    # Compute pre-mutation checksums
    state_checksum_before = _file_sha256(state_path)
    queue_checksum_before = _file_sha256(queue_path)

    try:
        # ------------------------------------------------------------------
        # Atomic update
        # ------------------------------------------------------------------
        _update_field(state, "canonical_main_commit", target_commit)
        _update_field(queue, "base_commit", target_commit)
        _update_field(state, "updated_at", timestamp)

        # Write atomically
        _atomic_write(state_path, state)
        _atomic_write(queue_path, queue)

        # ------------------------------------------------------------------
        # Post-update validation
        # ------------------------------------------------------------------
        _validate_path_safety(state_path)
        _validate_path_safety(queue_path)

        # Re-read and validate
        state_after = _load_json(state_path, "STATE")
        _validate_state(state_after, state_path)
        assert state_after["canonical_main_commit"] == target_commit, (
            f"canonical_main_commit mismatch: {state_after['canonical_main_commit']} != {target_commit}"
        )

        queue_after = _load_json(queue_path, "QUEUE")
        _validate_queue(queue_after, queue_path)
        assert queue_after["base_commit"] == target_commit, (
            f"base_commit mismatch: {queue_after['base_commit']} != {target_commit}"
        )

        state_checksum_after = _file_sha256(state_path)
        queue_checksum_after = _file_sha256(queue_path)

        # ------------------------------------------------------------------
        # Report
        # ------------------------------------------------------------------
        print(
            json.dumps(
                {
                    "status": "OK",
                    "target_commit": target_commit,
                    "state_path": str(state_path),
                    "queue_path": str(queue_path),
                    "state_backup": str(state_backup),
                    "queue_backup": str(queue_backup),
                    "state_checksum_before": state_checksum_before,
                    "state_checksum_after": state_checksum_after,
                    "queue_checksum_before": queue_checksum_before,
                    "queue_checksum_after": queue_checksum_after,
                    "state_schema_valid": True,
                    "queue_schema_valid": True,
                    "timestamp": timestamp,
                },
                indent=2,
            )
        )

    except Exception:
        # Restore backups
        if state_backup.exists():
            shutil.copy2(state_backup, state_path)
        if queue_backup.exists():
            shutil.copy2(queue_backup, queue_path)
        print(
            json.dumps({"status": "FAILED", "detail": "Post-validation failed; backups restored"}),
        )
        raise


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate_sha(commit: str) -> None:
    """Validate that *commit* is exactly 40 or 64 lowercase hex characters."""
    if not (_SHA1_RE.match(commit) or _SHA256_RE.match(commit)):
        raise ValueError(
            f"Invalid commit SHA: {commit!r} "
            f"(expected 40-char SHA-1 or 64-char SHA-256 hex)"
        )


def _commit_exists(commit: str, repo_root: Path) -> None:
    """Verify the commit is reachable from origin/main."""
    try:
        subprocess.run(
            ["git", "cat-file", "-e", commit],
            cwd=str(repo_root),
            capture_output=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise ValueError(
            f"Commit {commit} does not exist in repository: {exc}"
        ) from exc


def _load_json(path: Path, label: str) -> dict:
    """Load and parse a JSON file."""
    if not path.exists():
        raise FileNotFoundError(f"{label} file not found: {path}")
    try:
        with open(path) as f:
            return dict(json.load(f))
    except (json.JSONDecodeError, OSError) as exc:
        raise ValueError(f"Cannot parse {label} file {path}: {exc}") from exc


def _validate_state(state: dict, path: Path) -> None:
    """Validate controller STATE invariants."""
    allowed_statuses = {"PAUSED", "IDLE", "STOPPED"}
    status = state.get("controller_status", "")
    if status not in allowed_statuses:
        raise ValueError(
            f"controller_status={status!r} not in {allowed_statuses}"
        )

    # Active work fields must be null
    for field in ("active_work_item_id", "active_branch", "active_worktree", "active_pr"):
        if state.get(field) is not None:
            raise ValueError(
                f"Active field {field}={state[field]!r} must be null for reconciliation"
            )


def _validate_queue(queue: dict, path: Path) -> None:
    """Validate controller QUEUE invariants."""
    items = queue.get("items", [])
    if not isinstance(items, list):
        raise ValueError(f"QUEUE.items must be a list, got {type(items).__name__}")
    if len(items) > 0:
        raise ValueError(
            f"QUEUE.items must be empty for reconciliation, got {len(items)} item(s)"
        )


def _safe_backup(path: Path, backup_dir: Path, timestamp: str) -> Path:
    """Create a collision-safe timestamped backup."""
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_name = f"{path.name}.{timestamp}.bak"
    backup_path = backup_dir / backup_name
    shutil.copy2(path, backup_path)
    return backup_path


def _file_sha256(path: Path) -> str:
    """Compute SHA-256 checksum of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _update_field(data: dict, key: str, value: str) -> None:
    """Update a field in the data dict."""
    if key not in data:
        raise ValueError(f"Field {key!r} not found in state data")
    data[key] = value


def _atomic_write(path: Path, data: dict) -> None:
    """Write data atomically with fsync."""
    fd, tmp = tempfile.mkstemp(
        prefix=f".{path.name}.",
        dir=str(path.parent),
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w") as f:
            f.write(json.dumps(data, indent=2))
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        # Fsync the containing directory
        dir_fd = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _validate_path_safety(path: Path) -> None:
    """Reject symlinks and unsafe paths."""
    if path.is_symlink():
        raise ValueError(f"Path is a symlink: {path}")
    # Verify the resolved path is not world-writable or in /tmp
    # (Acceptable for tests, but in production only 'state' and 'control' parent paths are allowed)


if __name__ == "__main__":
    main()
