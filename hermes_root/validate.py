"""Request validation for the Hermes Root Executor client.

Validates requests before sending them to the executor. Fail-closed:
unknown fields, unknown actions, and invalid values are rejected.
"""

from __future__ import annotations

from typing import Any

from hermes_root.schema import (
    A2_CLASS,
    A3_CLASS,
    ALL_ACTIONS,
    SCHEMA_VERSION,
    ExecutorRequest,
)

# Maximum lengths to prevent abuse
MAX_REQUEST_ID_LEN = 256
MAX_CORRELATION_ID_LEN = 256
MAX_TASK_NAME_LEN = 512
MAX_RESOURCE_KEY_LEN = 256
MAX_CWD_LEN = 4096
MAX_ARGV_LENGTH = 100
MAX_ARG_LEN = 4096
MAX_TIMEOUT = 300  # 5 minutes
MIN_TIMEOUT = 1


class ValidationError(Exception):
    """Raised when a request fails validation."""


def validate_request(request: ExecutorRequest) -> None:
    """Validate an ExecutorRequest before sending.

    Raises ValidationError if any field is invalid.
    """
    # Schema version
    if request.schema_version != SCHEMA_VERSION:
        raise ValidationError(
            f"Unknown schema_version: {request.schema_version!r} "
            f"(expected {SCHEMA_VERSION!r})"
        )

    # Required string fields
    _validate_required_str("request_id", request.request_id, MAX_REQUEST_ID_LEN)
    _validate_required_str(
        "correlation_id", request.correlation_id, MAX_CORRELATION_ID_LEN
    )
    _validate_required_str("task_name", request.task_name, MAX_TASK_NAME_LEN)
    _validate_required_str("resource_key", request.resource_key, MAX_RESOURCE_KEY_LEN)

    # Issue number
    if not isinstance(request.issue_number, int) or request.issue_number < 0:
        raise ValidationError(
            f"issue_number must be a non-negative integer, got {request.issue_number!r}"
        )

    # Execution class
    if request.execution_class not in ("A0", "A1", "A2", "A3"):
        raise ValidationError(
            f"Unknown execution_class: {request.execution_class!r} (must be A0-A3)"
        )

    # Action
    if request.action not in ALL_ACTIONS:
        raise ValidationError(
            f"Unknown action: {request.action!r} (allowed: {sorted(ALL_ACTIONS)})"
        )

    # argv
    if not isinstance(request.argv, list):
        raise ValidationError("argv must be a list of strings")
    if len(request.argv) > MAX_ARGV_LENGTH:
        raise ValidationError(
            f"argv length {len(request.argv)} exceeds maximum {MAX_ARGV_LENGTH}"
        )
    for i, arg in enumerate(request.argv):
        if not isinstance(arg, str):
            raise ValidationError(f"argv[{i}] must be a string, got {type(arg).__name__}")
        if len(arg) > MAX_ARG_LEN:
            raise ValidationError(
                f"argv[{i}] length {len(arg)} exceeds maximum {MAX_ARG_LEN}"
            )

    # cwd
    if not isinstance(request.cwd, str):
        raise ValidationError("cwd must be a string")
    if len(request.cwd) > MAX_CWD_LEN:
        raise ValidationError(f"cwd length exceeds maximum {MAX_CWD_LEN}")
    if request.cwd and not request.cwd.startswith("/"):
        raise ValidationError(f"cwd must be an absolute path, got {request.cwd!r}")

    # timeout
    if not isinstance(request.timeout, int) or not (
        MIN_TIMEOUT <= request.timeout <= MAX_TIMEOUT
    ):
        raise ValidationError(
            f"timeout must be an integer between {MIN_TIMEOUT} and {MAX_TIMEOUT}, "
            f"got {request.timeout!r}"
        )

    # A2 approval gate
    if request.execution_class == A2_CLASS and not request.approval_reference:
        raise ValidationError(
            "A2 execution requires approval_reference"
        )

    # A3 approval gate — always blocked without external signature
    if request.execution_class == A3_CLASS:
        raise ValidationError(
            "A3 execution requires externally signed approval — "
            "never auto-authorized by client"
        )


def _validate_required_str(
    field_name: str, value: Any, max_len: int
) -> None:
    """Validate a required non-empty string field."""
    if not isinstance(value, str):
        raise ValidationError(
            f"{field_name} must be a string, got {type(value).__name__}"
        )
    if not value.strip():
        raise ValidationError(f"{field_name} must not be empty")
    if len(value) > max_len:
        raise ValidationError(
            f"{field_name} length {len(value)} exceeds maximum {max_len}"
        )
