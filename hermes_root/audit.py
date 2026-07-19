"""Durable append-only audit events for the root-executor daemon.

Each event is appended as one JSONL record, flushed from Python's userspace
buffer, and synced to the backing file before this module reports success.
New audit files also sync their parent directory so the directory entry is
durable. Existing lines are never rewritten or deleted.
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO

from hermes_root.redact import redact_dict

AUDIT_SCHEMA_VERSION = "hermes-root-executor-audit.v3"
DEFAULT_AUDIT_PATH = "/opt/data/hermes/audit/runtime-actions.jsonl"
AUDIT_EVENTS = frozenset(
    {"intent", "completion", "rejected", "execution_error", "timeout"}
)

_AUDIT_WRITE_LOCK = threading.Lock()


class AuditDurabilityError(RuntimeError):
    """The requested audit event did not cross its durability boundary."""

    def __init__(self, stage: str):
        self.stage = stage
        super().__init__(f"audit durability failed during {stage}")


def new_audit_id() -> str:
    """Return the stable identifier shared by an intent and terminal event."""
    return str(uuid.uuid4())


def _open_audit_stream(audit_path: str) -> TextIO:
    """Open an append-only UTF-8 stream with mode 0600 for new files."""
    fd = os.open(audit_path, os.O_CREAT | os.O_WRONLY | os.O_APPEND, 0o600)
    return os.fdopen(fd, "a", encoding="utf-8")


def _sync_parent_directory(path: Path) -> None:
    """Make creation of a new audit file durable in its parent directory."""
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    directory_fd = os.open(str(path.parent), flags)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def write_audit_entry(
    audit_path: str = DEFAULT_AUDIT_PATH,
    *,
    request_id: str,
    correlation_id: str,
    issue_number: int | None,
    task_name: str | None,
    execution_class: str,
    action: str,
    category: str | None,
    resource_key: str,
    peer_pid: int,
    peer_uid: int,
    legacy_protocol: bool,
    approval_reference: str | None,
    decision: str,
    reason: str | None,
    returncode: int | None,
    duration_ms: int,
    stdout_len: int,
    stderr_len: int,
    timeout: int,
    daemon_version: str,
    repository_commit: str,
    legacy_classification: str | None = None,
    event: str = "completion",
    audit_id: str | None = None,
) -> str:
    """Durably append one v3 audit event and return its stable audit ID.

    ``audit_id`` is generated for a single-event record when omitted. Approved
    subprocess executions pass one pre-generated ID to both their ``intent``
    and terminal event. Caller-controlled argv and subprocess output are never
    accepted by this interface.
    """
    if event not in AUDIT_EVENTS:
        raise ValueError(f"unsupported audit event: {event}")

    stable_audit_id = audit_id or new_audit_id()
    entry: dict[str, Any] = {
        "audit_schema_version": AUDIT_SCHEMA_VERSION,
        "audit_id": stable_audit_id,
        "audit_event_id": str(uuid.uuid4()),
        "event": event,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "request_id": request_id,
        "correlation_id": correlation_id,
        "issue_number": issue_number,
        "task_name": task_name,
        "execution_class": execution_class,
        "action": action,
        "category": category,
        "resource_key": resource_key,
        "peer_pid": peer_pid,
        "peer_uid": peer_uid,
        "legacy_protocol": legacy_protocol,
        "legacy_classification": legacy_classification,
        "approval_reference_redacted": "[PRESENT]" if approval_reference else None,
        "decision": decision,
        "reason": reason,
        "returncode": returncode,
        "duration_ms": duration_ms,
        "stdout_len": stdout_len,
        "stderr_len": stderr_len,
        "timeout": timeout,
        "daemon_version": daemon_version,
        "repository_commit": repository_commit,
        "durability_required": "flush+fsync",
    }
    entry = redact_dict(entry)
    encoded = json.dumps(entry, sort_keys=True, separators=(",", ":")) + "\n"

    path = Path(audit_path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise AuditDurabilityError("mkdir") from exc

    with _AUDIT_WRITE_LOCK:
        created = not path.exists()
        try:
            stream = _open_audit_stream(audit_path)
        except (OSError, ValueError) as exc:
            raise AuditDurabilityError("open") from exc

        try:
            try:
                written = stream.write(encoded)
                if written != len(encoded):
                    raise OSError("short audit write")
            except (OSError, ValueError) as exc:
                raise AuditDurabilityError("write") from exc

            try:
                stream.flush()
            except (OSError, ValueError) as exc:
                raise AuditDurabilityError("flush") from exc

            try:
                os.fsync(stream.fileno())
            except (OSError, ValueError) as exc:
                raise AuditDurabilityError("fsync") from exc

            if created:
                try:
                    _sync_parent_directory(path)
                except (OSError, ValueError) as exc:
                    raise AuditDurabilityError("directory_fsync") from exc
        finally:
            with suppress(OSError):
                stream.close()
            # A successful fsync is the durability boundary. A close error
            # after that boundary cannot make a privileged subprocess run
            # before its intent was durable.

    return stable_audit_id
