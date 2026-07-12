"""Dual-protocol request normalization for the root-executor daemon.

Accepts either the legacy host-daemon protocol ({category, args, resource_key})
or the versioned hermes-root-executor.v1 protocol (see hermes_root.schema) and
normalizes both into a single internal request model. Fail-closed on anything
that does not match one of the two known shapes.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from hermes_root.schema import SCHEMA_VERSION
from hermes_root.validate import (
    MAX_ARG_LEN,
    MAX_ARGV_LENGTH,
    MAX_CORRELATION_ID_LEN,
    MAX_CWD_LEN,
    MAX_REQUEST_ID_LEN,
    MAX_RESOURCE_KEY_LEN,
    MAX_TASK_NAME_LEN,
    MAX_TIMEOUT,
    MIN_TIMEOUT,
)

LEGACY_CATEGORIES = frozenset({"docker", "systemd", "fs_stat", "fs_ls"})
VALID_EXECUTION_CLASSES = frozenset({"A0", "A1", "A2", "A3"})

_V1_ALLOWED_FIELDS = frozenset({
    "schema_version", "request_id", "correlation_id", "issue_number", "task_name",
    "execution_class", "action", "resource_key", "argv", "cwd", "timeout",
    "approval_reference",
})
_V1_REQUIRED_STR_FIELDS = (
    ("request_id", MAX_REQUEST_ID_LEN),
    ("correlation_id", MAX_CORRELATION_ID_LEN),
    ("task_name", MAX_TASK_NAME_LEN),
    ("resource_key", MAX_RESOURCE_KEY_LEN),
    ("action", 256),
    ("cwd", MAX_CWD_LEN),
)


class ProtocolError(Exception):
    """Raised when a request cannot be normalized. Callers must fail closed."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


@dataclass
class NormalizedRequest:
    legacy_protocol: bool
    request_id: str
    correlation_id: str
    action: str
    resource_key: str
    argv: list[str]
    execution_class: str
    approval_reference: str | None
    issue_number: int | None
    task_name: str | None
    cwd: str | None
    timeout: int
    category: str | None = None  # legacy only


def normalize_request(payload: dict[str, Any]) -> NormalizedRequest:
    if not isinstance(payload, dict):
        raise ProtocolError("invalid_payload")

    has_schema_version = "schema_version" in payload
    has_category = "category" in payload

    if has_schema_version:
        return _normalize_v1(payload)
    if has_category:
        return _normalize_legacy(payload)
    raise ProtocolError("invalid_protocol")


def _normalize_legacy(payload: dict[str, Any]) -> NormalizedRequest:
    category = payload.get("category")
    args = payload.get("args")

    if category not in LEGACY_CATEGORIES:
        raise ProtocolError("unknown_category")
    if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
        raise ProtocolError("invalid_args")

    resource_key = payload.get("resource_key")
    if not resource_key:
        arg0 = args[0] if len(args) > 0 else ""
        arg1 = args[1] if len(args) > 1 else ""
        resource_key = f"{category}:{arg0}:{arg1}"

    return NormalizedRequest(
        legacy_protocol=True,
        request_id=str(uuid.uuid4()),
        correlation_id=str(uuid.uuid4()),
        action=category,
        resource_key=resource_key,
        argv=args,
        execution_class="LEGACY",
        approval_reference=None,
        issue_number=None,
        task_name=None,
        cwd=None,
        timeout=30,
        category=category,
    )


def _normalize_v1(payload: dict[str, Any]) -> NormalizedRequest:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ProtocolError("unknown_schema_version")

    extra = set(payload.keys()) - _V1_ALLOWED_FIELDS
    if extra:
        raise ProtocolError("unknown_field")

    for field_name, max_len in _V1_REQUIRED_STR_FIELDS:
        if field_name not in payload:
            raise ProtocolError("missing_required_field")
        value = payload[field_name]
        if not isinstance(value, str) or not value.strip() or len(value) > max_len:
            raise ProtocolError("invalid_field_type")

    if "execution_class" not in payload:
        raise ProtocolError("missing_required_field")
    execution_class = payload["execution_class"]
    if execution_class not in VALID_EXECUTION_CLASSES:
        raise ProtocolError("invalid_execution_class")

    if "issue_number" not in payload:
        raise ProtocolError("missing_required_field")
    issue_number = payload["issue_number"]
    if not isinstance(issue_number, int) or isinstance(issue_number, bool) or issue_number < 0:
        raise ProtocolError("invalid_field_type")

    if "argv" not in payload:
        raise ProtocolError("missing_required_field")
    argv = payload["argv"]
    if (
        not isinstance(argv, list)
        or len(argv) > MAX_ARGV_LENGTH
        or not all(isinstance(a, str) and len(a) <= MAX_ARG_LEN for a in argv)
    ):
        raise ProtocolError("invalid_argv")

    cwd = payload["cwd"]
    if not cwd.startswith("/"):
        raise ProtocolError("invalid_cwd")

    if "timeout" not in payload:
        raise ProtocolError("missing_required_field")
    timeout = payload["timeout"]
    if not isinstance(timeout, int) or isinstance(timeout, bool) or not (MIN_TIMEOUT <= timeout <= MAX_TIMEOUT):
        raise ProtocolError("invalid_timeout")

    approval_reference = payload.get("approval_reference")
    if approval_reference is not None and not isinstance(approval_reference, str):
        raise ProtocolError("invalid_field_type")

    return NormalizedRequest(
        legacy_protocol=False,
        request_id=payload["request_id"],
        correlation_id=payload["correlation_id"],
        action=payload["action"],
        resource_key=payload["resource_key"],
        argv=argv,
        execution_class=execution_class,
        approval_reference=approval_reference,
        issue_number=issue_number,
        task_name=payload["task_name"],
        cwd=cwd,
        timeout=timeout,
        category=None,
    )
