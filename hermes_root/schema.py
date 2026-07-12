"""Hermes Root Executor Client — production AF_UNIX client for hermes-root-executor.service.

Implements the client-side contract for the UID-separated root executor
(ADR-2026-07-11-hermes-root-runtime-authority, R0). Communicates via a local
Unix domain socket with structured JSON-line protocol.

Security contract:
- No shell=True, no shell string concatenation
- Commands transmitted as structured argv lists
- Unknown fields and unknown actions fail-closed
- Secrets redacted before local output
- A2 blocked without approval_reference
- A3 blocked without external signature (never auto-authorized)
"""

from __future__ import annotations

import json
import os
import socket
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

SCHEMA_VERSION = "hermes-root-executor.v1"
DEFAULT_SOCKET_PATH = "/run/hermes-root-executor/executor.sock"
DEFAULT_TIMEOUT = 30
CONNECT_TIMEOUT = 10.0
READ_TIMEOUT = 35.0
MAX_RESPONSE_BYTES = 1_048_576  # 1 MiB

# Execution classes that require approval
A2_CLASS = "A2"
A3_CLASS = "A3"

# Read-only actions (always allowed in A1)
READONLY_ACTIONS = frozenset({
    "executor_health",
    "docker_ps",
    "docker_inspect",
    "systemctl_status",
    "docker_compose_config",
})

# Mutating actions (require A2 approval)
MUTATING_ACTIONS = frozenset({
    "docker_create",
    "docker_stop",
    "docker_remove",
    "systemctl_restart",
})

# All known actions
ALL_ACTIONS = READONLY_ACTIONS | MUTATING_ACTIONS

# Secret patterns for redaction
SECRET_KEY_PATTERNS = ("KEY", "SECRET", "TOKEN", "PASSWORD", "API_KEY", "AUTH")


@dataclass
class ExecutorRequest:
    """Structured request to the root executor."""

    request_id: str
    correlation_id: str
    issue_number: int
    task_name: str
    execution_class: str  # A0, A1, A2, A3
    resource_key: str
    action: str
    argv: list[str] = field(default_factory=list)
    cwd: str = "/"
    timeout: int = DEFAULT_TIMEOUT
    approval_reference: Optional[str] = None
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ExecutorRequest":
        return cls(
            request_id=d.get("request_id", ""),
            correlation_id=d.get("correlation_id", ""),
            issue_number=d.get("issue_number", 0),
            task_name=d.get("task_name", ""),
            execution_class=d.get("execution_class", "A0"),
            resource_key=d.get("resource_key", ""),
            action=d.get("action", ""),
            argv=d.get("argv", []),
            cwd=d.get("cwd", "/"),
            timeout=d.get("timeout", DEFAULT_TIMEOUT),
            approval_reference=d.get("approval_reference"),
            schema_version=d.get("schema_version", SCHEMA_VERSION),
        )


@dataclass
class ExecutorResponse:
    """Structured response from the root executor."""

    request_id: str = ""
    correlation_id: str = ""
    decision: str = "BLOCKED"  # ALLOWED or BLOCKED
    reason: str = ""
    result: dict[str, Any] = field(default_factory=dict)
    audit_seq: int = 0

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ExecutorResponse":
        return cls(
            request_id=d.get("request_id", ""),
            correlation_id=d.get("correlation_id", ""),
            decision=d.get("decision", "BLOCKED"),
            reason=d.get("reason", ""),
            result=d.get("result", {}),
            audit_seq=d.get("audit_seq", 0),
        )

    @property
    def is_allowed(self) -> bool:
        return self.decision == "ALLOWED"

    @property
    def is_blocked(self) -> bool:
        return self.decision != "ALLOWED"
