"""Root-executor daemon: AF_UNIX server with legacy + hermes-root-executor.v1 dual-protocol dispatch.

Phase A (legacy) replicates the production host daemon
(/usr/local/sbin/hermes-root-executor) behaviour exactly: same categories,
same socket contract, same locking/timeout/kill-switch/audit semantics.
Phase B (v1) adds the versioned protocol on top via protocol.py / policy.py /
actions.py, without changing legacy behaviour or granting legacy requests any
new capability.

This module is not installed or started against the production socket by
this change — see scripts/install-hermes-root-executor.sh for the deployment
contract, which is a separate, explicitly-gated step.
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import socket
import struct
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hermes_root import actions, audit, policy, protocol, redact
from hermes_root.schema import MAX_RESPONSE_BYTES, SCHEMA_VERSION

DAEMON_VERSION = "2.0.0-repo"
DEFAULT_SOCKET_PATH = "/run/hermes-root-executor/executor.sock"
DEFAULT_LOCK_DIR = "/run/hermes-root-executor/locks"
DEFAULT_KILL_SWITCH_PATH = "/etc/hermes-root-executor/DISABLED"
DEFAULT_ALLOWED_UIDS = frozenset({10000})
COMMAND_TIMEOUT_SECONDS = 30
RECV_BUFFER = 65536

LEGACY_CATEGORY_BINARIES: dict[str, list[str]] = {
    "docker": ["docker"],
    "systemd": ["systemctl"],
    "fs_stat": ["stat"],
    "fs_ls": ["ls", "-la"],
}


def _safe_key(resource_key: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in resource_key)


class RootExecutorDaemon:
    """Handles one normalized request at a time; the socket loop is a thin
    wrapper around handle_payload() so request handling can be unit-tested
    without a real AF_UNIX connection."""

    def __init__(
        self,
        *,
        socket_path: str = DEFAULT_SOCKET_PATH,
        lock_dir: str = DEFAULT_LOCK_DIR,
        kill_switch_path: str = DEFAULT_KILL_SWITCH_PATH,
        allowed_uids: frozenset[int] = DEFAULT_ALLOWED_UIDS,
        audit_path: str = audit.DEFAULT_AUDIT_PATH,
        repository_commit: str = "unknown",
        command_timeout: int = COMMAND_TIMEOUT_SECONDS,
    ) -> None:
        self.socket_path = socket_path
        self.lock_dir = lock_dir
        self.kill_switch_path = kill_switch_path
        self.allowed_uids = allowed_uids
        self.audit_path = audit_path
        self.repository_commit = repository_commit
        self.command_timeout = command_timeout
        self._server: socket.socket | None = None
        self._running = False

    # ------------------------------------------------------------------
    # Core request handling
    # ------------------------------------------------------------------

    def handle_payload(self, raw: bytes, *, peer_pid: int, peer_uid: int) -> dict[str, Any]:
        if peer_uid not in self.allowed_uids:
            return {"decision": "BLOCKED", "reason": "peer_uid_not_allowed"}

        if len(raw) > MAX_RESPONSE_BYTES:
            return {"decision": "BLOCKED", "reason": "payload_too_large"}

        try:
            payload = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {"decision": "BLOCKED", "reason": "invalid_json"}

        if os.path.exists(self.kill_switch_path):
            return {"decision": "BLOCKED", "reason": "emergency_disable_switch_active"}

        try:
            norm = protocol.normalize_request(payload)
        except protocol.ProtocolError as exc:
            return {"decision": "BLOCKED", "reason": exc.reason}

        if norm.legacy_protocol:
            return self._handle_legacy(norm, peer_pid=peer_pid, peer_uid=peer_uid)
        return self._handle_v1(norm, peer_pid=peer_pid, peer_uid=peer_uid)

    # ------------------------------------------------------------------
    # Legacy path — must match the production host daemon exactly
    # ------------------------------------------------------------------

    def _handle_legacy(self, norm: protocol.NormalizedRequest, *, peer_pid: int, peer_uid: int) -> dict[str, Any]:
        binary = LEGACY_CATEGORY_BINARIES.get(norm.category)
        if binary is None:
            self._audit_legacy(norm, peer_pid, peer_uid, decision="BLOCKED", reason="unknown_category")
            return {"decision": "BLOCKED", "reason": "unknown_category"}

        argv = [*binary, *norm.argv]
        lock_fd = self._acquire_lock(norm.resource_key)
        if lock_fd is None:
            self._audit_legacy(norm, peer_pid, peer_uid, decision="BLOCKED", reason="resource_locked")
            return {"decision": "BLOCKED", "reason": "resource_locked"}

        try:
            try:
                result = subprocess.run(argv, capture_output=True, text=True, timeout=self.command_timeout)
            except subprocess.TimeoutExpired:
                self._cleanup_after_timeout(norm.category, norm.argv, norm.resource_key)
                self._audit_legacy(norm, peer_pid, peer_uid, decision="BLOCKED", reason="command_timeout")
                return {"decision": "BLOCKED", "reason": "command_timeout"}
        finally:
            self._release_lock(lock_fd)

        self._audit_legacy(
            norm, peer_pid, peer_uid, decision="ALLOWED", reason=None,
            returncode=result.returncode, stdout_len=len(result.stdout), stderr_len=len(result.stderr),
        )
        # Audit logs only the original lengths above (for accurate sizing);
        # the client-facing response is redacted — secrets in command
        # output (e.g. a rendered docker-compose config with resolved
        # environment values) must never leave the executor process.
        return {
            "decision": "ALLOWED",
            "returncode": result.returncode,
            "stdout": redact.redact_text_output(result.stdout),
            "stderr": redact.redact_text_output(result.stderr),
        }

    def _audit_legacy(
        self, norm, peer_pid, peer_uid, *, decision, reason,
        returncode=None, stdout_len=None, stderr_len=None,
    ) -> None:
        audit.write_audit_entry(
            self.audit_path,
            request_id=norm.request_id,
            correlation_id=norm.correlation_id,
            issue_number=None,
            task_name=None,
            execution_class="LEGACY",
            action=norm.category or "unknown",
            category=norm.category,
            resource_key=norm.resource_key,
            peer_pid=peer_pid,
            peer_uid=peer_uid,
            legacy_protocol=True,
            approval_reference=None,
            decision=decision,
            reason=reason,
            returncode=returncode,
            duration_ms=0,
            stdout_len=stdout_len or 0,
            stderr_len=stderr_len or 0,
            timeout=self.command_timeout,
            daemon_version=DAEMON_VERSION,
            repository_commit=self.repository_commit,
        )

    def _cleanup_after_timeout(self, category: str, args: list[str], resource_key: str) -> None:
        if category == "docker" and args and args[0] == "run" and "-d" not in args and "--detach" not in args:
            try:
                subprocess.run(["docker", "rm", "-f", resource_key], timeout=10, capture_output=True)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # v1 path
    # ------------------------------------------------------------------

    def _handle_v1(self, norm: protocol.NormalizedRequest, *, peer_pid: int, peer_uid: int) -> dict[str, Any]:
        started_at = datetime.now(timezone.utc).isoformat()
        start = time.monotonic()

        is_mut = actions.is_mutating(norm.action)
        allowed, reason = policy.evaluate_gate(
            execution_class=norm.execution_class,
            is_mutating=is_mut,
            approval_reference=norm.approval_reference,
            issue_number=norm.issue_number,
            task_name=norm.task_name,
            kill_switch_active=os.path.exists(self.kill_switch_path),
        )
        if not allowed:
            return self._finish_v1(
                norm, peer_pid, peer_uid, decision="BLOCKED", reason=reason,
                returncode=None, stdout="", stderr="", started_at=started_at, start=start,
            )

        try:
            argv = actions.build_argv(norm.action, norm.argv)
        except actions.ActionError as exc:
            return self._finish_v1(
                norm, peer_pid, peer_uid, decision="BLOCKED", reason=exc.reason,
                returncode=None, stdout="", stderr="", started_at=started_at, start=start,
            )

        if norm.action == "executor_health":
            return self._finish_v1(
                norm, peer_pid, peer_uid, decision="ALLOWED", reason="ok",
                returncode=0, stdout="healthy", stderr="", started_at=started_at, start=start,
            )

        lock_fd = self._acquire_lock(norm.resource_key)
        if lock_fd is None:
            return self._finish_v1(
                norm, peer_pid, peer_uid, decision="BLOCKED", reason="resource_locked",
                returncode=None, stdout="", stderr="", started_at=started_at, start=start,
            )
        try:
            try:
                result = subprocess.run(argv, capture_output=True, text=True, timeout=norm.timeout)
            except subprocess.TimeoutExpired:
                return self._finish_v1(
                    norm, peer_pid, peer_uid, decision="BLOCKED", reason="command_timeout",
                    returncode=None, stdout="", stderr="", started_at=started_at, start=start,
                )
        finally:
            self._release_lock(lock_fd)

        return self._finish_v1(
            norm, peer_pid, peer_uid, decision="ALLOWED", reason="ok",
            returncode=result.returncode, stdout=result.stdout, stderr=result.stderr,
            started_at=started_at, start=start,
        )

    def _finish_v1(
        self, norm, peer_pid, peer_uid, *, decision, reason, returncode, stdout, stderr, started_at, start,
    ) -> dict[str, Any]:
        finished_at = datetime.now(timezone.utc).isoformat()
        duration_ms = int((time.monotonic() - start) * 1000)
        audit_id = audit.write_audit_entry(
            self.audit_path,
            request_id=norm.request_id,
            correlation_id=norm.correlation_id,
            issue_number=norm.issue_number,
            task_name=norm.task_name,
            execution_class=norm.execution_class,
            action=norm.action,
            category=None,
            resource_key=norm.resource_key,
            peer_pid=peer_pid,
            peer_uid=peer_uid,
            legacy_protocol=False,
            approval_reference=norm.approval_reference,
            decision=decision,
            reason=reason,
            returncode=returncode,
            duration_ms=duration_ms,
            stdout_len=len(stdout or ""),
            stderr_len=len(stderr or ""),
            timeout=norm.timeout,
            daemon_version=DAEMON_VERSION,
            repository_commit=self.repository_commit,
        )
        # audit_id/duration/lengths above are computed from the original,
        # unredacted stdout/stderr; only the client-facing response is
        # redacted — secrets in command output must never leave the
        # executor process.
        return {
            "schema_version": SCHEMA_VERSION,
            "request_id": norm.request_id,
            "correlation_id": norm.correlation_id,
            "decision": decision,
            "reason": reason,
            "returncode": returncode,
            "stdout": redact.redact_text_output(stdout),
            "stderr": redact.redact_text_output(stderr),
            "started_at": started_at,
            "finished_at": finished_at,
            "duration_ms": duration_ms,
            "resource_key": norm.resource_key,
            "action": norm.action,
            "execution_class": norm.execution_class,
            "audit_id": audit_id,
        }

    # ------------------------------------------------------------------
    # Locking (fcntl.flock, identical semantics to the legacy daemon)
    # ------------------------------------------------------------------

    def _acquire_lock(self, resource_key: str) -> int | None:
        Path(self.lock_dir).mkdir(parents=True, exist_ok=True)
        safe = _safe_key(resource_key)
        lock_path = os.path.join(self.lock_dir, f"{safe}.lock")
        fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(fd)
            return None
        return fd

    def _release_lock(self, fd: int) -> None:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)

    # ------------------------------------------------------------------
    # Socket server loop — not exercised by most unit tests, but proven by
    # test_real_socket_end_to_end in tests/test_hermes_root_daemon.py
    # ------------------------------------------------------------------

    def serve_forever(self) -> None:
        sock_dir = Path(self.socket_path).parent
        sock_dir.mkdir(parents=True, exist_ok=True)
        if os.path.exists(self.socket_path):
            os.unlink(self.socket_path)
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(self.socket_path)
        os.chmod(self.socket_path, 0o660)
        srv.listen(8)
        self._server = srv
        self._running = True
        try:
            while self._running:
                try:
                    conn, _ = srv.accept()
                except (OSError, ValueError):
                    # Raised when stop() closes the listening socket while
                    # accept() is blocked — expected during shutdown.
                    break
                threading.Thread(target=self._handle_conn, args=(conn,), daemon=True).start()
        finally:
            srv.close()

    def _handle_conn(self, conn: socket.socket) -> None:
        try:
            creds = conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
            peer_pid, peer_uid, _peer_gid = struct.unpack("3i", creds)
            raw = conn.recv(RECV_BUFFER)
            response = self.handle_payload(raw, peer_pid=peer_pid, peer_uid=peer_uid)
            conn.sendall(json.dumps(response).encode() + b"\n")
        except OSError:
            # Peer disconnected, or the socket was torn down mid-request
            # (e.g. daemon.stop() during shutdown) — not an error worth
            # surfacing, the caller simply gets no response.
            pass
        finally:
            conn.close()

    def stop(self) -> None:
        self._running = False
        if self._server is not None:
            try:
                self._server.close()
            except OSError:
                pass


_COMMIT_SHA_RE = re.compile(r"[0-9a-f]{7,40}")


def main() -> None:  # pragma: no cover - exercised via installer/systemd, not unit tests
    """Entry point for the systemd-managed deployment.

    repository_commit is required, not defaulted: it must come from
    HERMES_ROOT_EXECUTOR_REPOSITORY_COMMIT (populated by the installer via
    a systemd EnvironmentFile=). A missing or malformed value fails closed
    at startup rather than silently logging "unknown" in every audit entry
    forever, as happened before this fix.
    """
    if os.geteuid() != 0:
        raise SystemExit("hermes_root.daemon must run as root")

    repository_commit = os.environ.get(
        "HERMES_ROOT_EXECUTOR_REPOSITORY_COMMIT", ""
    ).strip()
    if not _COMMIT_SHA_RE.fullmatch(repository_commit):
        raise SystemExit(
            "HERMES_ROOT_EXECUTOR_REPOSITORY_COMMIT must be set to a valid "
            "git commit SHA (7-40 hex characters) via the systemd "
            f"EnvironmentFile=; got {repository_commit!r}"
        )

    daemon = RootExecutorDaemon(repository_commit=repository_commit)
    daemon.serve_forever()


if __name__ == "__main__":  # pragma: no cover
    main()
