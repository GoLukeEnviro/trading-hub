"""Audit v2 writer for the root-executor daemon.

Appends structured JSONL entries to the same append-only audit file the
legacy host daemon has always written to. Existing lines are never rewritten
or deleted; this module only ever appends.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hermes_root.redact import redact_dict

AUDIT_SCHEMA_VERSION = "hermes-root-executor-audit.v2"
DEFAULT_AUDIT_PATH = "/opt/data/hermes/audit/runtime-actions.jsonl"


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
) -> str:
    """Append one v2 audit entry and return its audit_id."""
    audit_id = str(uuid.uuid4())
    entry: dict[str, Any] = {
        "audit_schema_version": AUDIT_SCHEMA_VERSION,
        "audit_id": audit_id,
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
    }
    entry = redact_dict(entry)

    Path(audit_path).parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(audit_path, os.O_CREAT | os.O_WRONLY | os.O_APPEND, 0o600)
    try:
        os.write(fd, (json.dumps(entry) + "\n").encode())
    finally:
        os.close(fd)
    return audit_id
