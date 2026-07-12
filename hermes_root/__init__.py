"""Hermes Root Executor — production client for hermes-root-executor.service.

Provides a safe, validated AF_UNIX client for communicating with the
UID-separated root executor daemon on HermesTrader.

Modules:
    schema   — Request/Response dataclasses and constants
    client   — AF_UNIX transport layer
    validate — Request validation (fail-closed)
    redact   — Secret redaction for local output
    cli      — Command-line interface (hermes-root)
"""

from hermes_root.schema import (
    ExecutorRequest,
    ExecutorResponse,
    SCHEMA_VERSION,
    DEFAULT_SOCKET_PATH,
    DEFAULT_TIMEOUT,
    READONLY_ACTIONS,
    MUTATING_ACTIONS,
    ALL_ACTIONS,
)
from hermes_root.client import (
    send_request,
    ExecutorClientError,
    ExecutorTimeoutError,
    ExecutorConnectionError,
    ExecutorProtocolError,
)
from hermes_root.validate import validate_request, ValidationError
from hermes_root.redact import redact_dict, redact_argv, redact_value

__all__ = [
    "ExecutorRequest",
    "ExecutorResponse",
    "SCHEMA_VERSION",
    "DEFAULT_SOCKET_PATH",
    "DEFAULT_TIMEOUT",
    "READONLY_ACTIONS",
    "MUTATING_ACTIONS",
    "ALL_ACTIONS",
    "send_request",
    "validate_request",
    "ExecutorClientError",
    "ExecutorTimeoutError",
    "ExecutorConnectionError",
    "ExecutorProtocolError",
    "ValidationError",
    "redact_dict",
    "redact_argv",
    "redact_value",
]
