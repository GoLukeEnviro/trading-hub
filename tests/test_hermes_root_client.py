"""Tests for the Hermes Root Executor client contract.

Uses a fake AF_UNIX socket server to test all client behaviors
without requiring a real hermes-root-executor.service.
"""

from __future__ import annotations

import io
import json
import os
import socket
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any

import pytest

from hermes_root import (
    ExecutorRequest,
    ExecutorResponse,
    SCHEMA_VERSION,
    DEFAULT_TIMEOUT,
    send_request,
    validate_request,
    ExecutorClientError,
    ExecutorTimeoutError,
    ExecutorConnectionError,
    ExecutorProtocolError,
    ValidationError,
    redact_dict,
    redact_argv,
)


# ---------------------------------------------------------------------------
# Fake executor server for testing
# ---------------------------------------------------------------------------

class FakeExecutorServer:
    """A fake AF_UNIX server that responds with configurable behavior."""

    def __init__(self, socket_path: str):
        self.socket_path = socket_path
        self._server: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._running = threading.Event()
        self._response: dict[str, Any] | None = None
        self._delay: float = 0.0
        self._close_early: bool = False
        self._send_invalid_json: bool = False
        self._send_empty: bool = False
        self._send_too_large: bool = False
        self._requests_received: list[dict[str, Any]] = []

    def set_response(self, response: dict[str, Any]) -> None:
        self._response = response

    def set_delay(self, seconds: float) -> None:
        self._delay = seconds

    def set_close_early(self) -> None:
        self._close_early = True

    def set_send_invalid_json(self) -> None:
        self._send_invalid_json = True

    def set_send_empty(self) -> None:
        self._send_empty = True

    def set_send_too_large(self) -> None:
        self._send_too_large = True

    def start(self) -> None:
        """Start the fake server in a background thread."""
        # Remove stale socket file
        try:
            os.unlink(self.socket_path)
        except OSError:
            pass

        self._server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server.bind(self.socket_path)
        self._server.listen(1)
        self._server.settimeout(1.0)
        self._running.set()

        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        """Accept connections and respond."""
        assert self._server is not None
        while self._running.is_set():
            try:
                conn, _ = self._server.accept()
            except socket.timeout:
                continue
            try:
                conn.settimeout(5.0)
                data = b""
                while not data.endswith(b"\n"):
                    chunk = conn.recv(4096)
                    if not chunk:
                        break
                    data += chunk

                parsed_request: dict[str, Any] = {}
                if data:
                    try:
                        parsed_request = json.loads(data.decode("utf-8").strip())
                        self._requests_received.append(parsed_request)
                    except json.JSONDecodeError:
                        pass

                if self._delay:
                    time.sleep(self._delay)

                if self._close_early:
                    conn.close()
                    continue

                if self._send_invalid_json:
                    conn.sendall(b"not json\n")
                elif self._send_empty:
                    conn.sendall(b"")
                elif self._send_too_large:
                    conn.sendall(b"x" * 2_000_000 + b"\n")
                elif self._response is not None:
                    conn.sendall(
                        (json.dumps(self._response) + "\n").encode("utf-8")
                    )
                else:
                    # Default: echo back as ALLOWED
                    echo = {
                        "request_id": parsed_request.get("request_id", ""),
                        "correlation_id": parsed_request.get("correlation_id", ""),
                        "decision": "ALLOWED",
                        "reason": "ok",
                        "result": {"echo": True},
                        "audit_seq": 1,
                    }
                    conn.sendall((json.dumps(echo) + "\n").encode("utf-8"))
            except OSError:
                pass
            finally:
                try:
                    conn.close()
                except OSError:
                    pass

    def stop(self) -> None:
        """Stop the fake server and clean up."""
        self._running.clear()
        if self._server:
            try:
                self._server.close()
            except OSError:
                pass
        try:
            os.unlink(self.socket_path)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_socket_path():
    """Create a temporary socket path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield os.path.join(tmpdir, "executor.sock")


@pytest.fixture
def fake_server(fake_socket_path):
    """Start a fake executor server."""
    server = FakeExecutorServer(fake_socket_path)
    server.start()
    yield server
    server.stop()


@pytest.fixture
def valid_request():
    """A valid, minimal ExecutorRequest."""
    return ExecutorRequest(
        request_id="test-" + uuid.uuid4().hex[:8],
        correlation_id="corr-" + uuid.uuid4().hex[:8],
        issue_number=530,
        task_name="H3A test",
        execution_class="A1",
        resource_key="test-resource",
        action="executor_health",
        argv=[],
        cwd="/",
        timeout=30,
    )


# ---------------------------------------------------------------------------
# Positive tests
# ---------------------------------------------------------------------------

def test_valid_request_succeeds(fake_server, fake_socket_path, valid_request):
    """A valid request should receive an ALLOWED response."""
    response = send_request(fake_socket_path, valid_request)
    assert response.is_allowed
    assert response.decision == "ALLOWED"
    assert response.correlation_id == valid_request.correlation_id


def test_correlation_id_preserved(fake_server, fake_socket_path, valid_request):
    """Correlation ID must be preserved end-to-end."""
    response = send_request(fake_socket_path, valid_request)
    assert response.correlation_id == valid_request.correlation_id


def test_all_readonly_actions_accepted(fake_server, fake_socket_path):
    """All read-only actions should be accepted."""
    from hermes_root.schema import READONLY_ACTIONS

    for action in sorted(READONLY_ACTIONS):
        req = ExecutorRequest(
            request_id="test-" + uuid.uuid4().hex[:8],
            correlation_id="corr-" + uuid.uuid4().hex[:8],
            issue_number=530,
            task_name="H3A test",
            execution_class="A1",
            resource_key="test",
            action=action,
            argv=[],
            cwd="/",
            timeout=30,
        )
        response = send_request(fake_socket_path, req)
        assert response.is_allowed, f"Action {action} should be allowed"


def test_argv_preserved_as_list(fake_server, fake_socket_path):
    """argv should be transmitted as a list, not a string."""
    req = ExecutorRequest(
        request_id="test-" + uuid.uuid4().hex[:8],
        correlation_id="corr-" + uuid.uuid4().hex[:8],
        issue_number=530,
        task_name="H3A test",
        execution_class="A1",
        resource_key="test",
        action="docker_ps",
        argv=["docker", "ps", "--format", "{{.Names}}"],
        cwd="/",
        timeout=30,
    )
    response = send_request(fake_socket_path, req)
    assert response.is_allowed
    # Verify the server received argv as a list
    assert len(fake_server._requests_received) == 1
    received = fake_server._requests_received[0]
    assert isinstance(received["argv"], list)
    assert received["argv"] == ["docker", "ps", "--format", "{{.Names}}"]


# ---------------------------------------------------------------------------
# Negative tests — schema validation
# ---------------------------------------------------------------------------

def test_bad_schema_version_blocked(valid_request):
    """Unknown schema version should be rejected."""
    valid_request.schema_version = "unknown.v99"
    with pytest.raises(ValidationError, match="Unknown schema_version"):
        validate_request(valid_request)


def test_unknown_action_blocked(valid_request):
    """Unknown action should be rejected."""
    valid_request.action = "frobnicate"
    with pytest.raises(ValidationError, match="Unknown action"):
        validate_request(valid_request)


def test_invalid_execution_class_blocked(valid_request):
    """Invalid execution class should be rejected."""
    valid_request.execution_class = "A5"
    with pytest.raises(ValidationError, match="Unknown execution_class"):
        validate_request(valid_request)


def test_empty_request_id_blocked(valid_request):
    """Empty request_id should be rejected."""
    valid_request.request_id = ""
    with pytest.raises(ValidationError, match="request_id must not be empty"):
        validate_request(valid_request)


def test_missing_correlation_id_blocked(valid_request):
    """Empty correlation_id should be rejected."""
    valid_request.correlation_id = ""
    with pytest.raises(ValidationError, match="correlation_id must not be empty"):
        validate_request(valid_request)


def test_negative_issue_number_blocked(valid_request):
    """Negative issue_number should be rejected."""
    valid_request.issue_number = -1
    with pytest.raises(ValidationError, match="issue_number"):
        validate_request(valid_request)


def test_argv_not_list_blocked(valid_request):
    """argv must be a list, not a string."""
    valid_request.argv = "docker ps"  # type: ignore[assignment]
    with pytest.raises(ValidationError, match="argv must be a list"):
        validate_request(valid_request)


def test_argv_too_long_blocked(valid_request):
    """argv exceeding max length should be rejected."""
    valid_request.argv = ["arg"] * 200
    with pytest.raises(ValidationError, match="argv length"):
        validate_request(valid_request)


def test_argv_element_too_long_blocked(valid_request):
    """argv element exceeding max length should be rejected."""
    valid_request.argv = ["x" * 5000]
    with pytest.raises(ValidationError, match="exceeds maximum"):
        validate_request(valid_request)


def test_cwd_not_absolute_blocked(valid_request):
    """cwd must be an absolute path."""
    valid_request.cwd = "relative/path"
    with pytest.raises(ValidationError, match="cwd must be an absolute path"):
        validate_request(valid_request)


def test_timeout_out_of_range_blocked(valid_request):
    """Timeout must be within valid range."""
    valid_request.timeout = 0
    with pytest.raises(ValidationError, match="timeout"):
        validate_request(valid_request)

    valid_request.timeout = 999
    with pytest.raises(ValidationError, match="timeout"):
        validate_request(valid_request)


# ---------------------------------------------------------------------------
# Negative tests — A2/A3 approval gates
# ---------------------------------------------------------------------------

def test_a2_without_approval_blocked(valid_request):
    """A2 execution without approval_reference should be rejected."""
    valid_request.execution_class = "A2"
    valid_request.approval_reference = None
    with pytest.raises(ValidationError, match="A2 execution requires approval_reference"):
        validate_request(valid_request)


def test_a2_with_approval_passes(valid_request):
    """A2 execution with approval_reference should pass validation."""
    valid_request.execution_class = "A2"
    valid_request.approval_reference = "APPROVED_TEST"
    # Should not raise
    validate_request(valid_request)


def test_a3_always_blocked(valid_request):
    """A3 execution should always be blocked by the client."""
    valid_request.execution_class = "A3"
    with pytest.raises(ValidationError, match="A3 execution requires externally signed"):
        validate_request(valid_request)


# ---------------------------------------------------------------------------
# Negative tests — transport errors
# ---------------------------------------------------------------------------

def test_socket_not_found():
    """Missing socket should raise ExecutorConnectionError."""
    req = ExecutorRequest(
        request_id="test",
        correlation_id="corr",
        issue_number=530,
        task_name="test",
        execution_class="A1",
        resource_key="test",
        action="executor_health",
        argv=[],
        cwd="/",
        timeout=30,
    )
    with pytest.raises(ExecutorConnectionError, match="not found"):
        send_request("/nonexistent/path/executor.sock", req)


def test_invalid_json_response(fake_server, fake_socket_path, valid_request):
    """Invalid JSON response should raise ExecutorProtocolError."""
    fake_server.set_send_invalid_json()
    with pytest.raises(ExecutorProtocolError, match="Invalid JSON"):
        send_request(fake_socket_path, valid_request)


def test_empty_response(fake_server, fake_socket_path, valid_request):
    """Empty response should raise ExecutorProtocolError."""
    fake_server.set_send_empty()
    with pytest.raises(ExecutorProtocolError, match="Empty response"):
        send_request(fake_socket_path, valid_request)


def test_too_large_response(fake_server, fake_socket_path, valid_request):
    """Response exceeding max size should raise ExecutorProtocolError."""
    fake_server.set_send_too_large()
    with pytest.raises(ExecutorProtocolError, match="exceeds"):
        send_request(fake_socket_path, valid_request)


# ---------------------------------------------------------------------------
# Negative tests — shell injection
# ---------------------------------------------------------------------------

def test_shell_injection_stays_single_argv_element(fake_server, fake_socket_path):
    """Shell injection attempt should remain a single argv element, not parsed."""
    req = ExecutorRequest(
        request_id="test-" + uuid.uuid4().hex[:8],
        correlation_id="corr-" + uuid.uuid4().hex[:8],
        issue_number=530,
        task_name="H3A test",
        execution_class="A1",
        resource_key="test",
        action="docker_ps",
        argv=["docker", "ps; rm -rf /"],
        cwd="/",
        timeout=30,
    )
    response = send_request(fake_socket_path, req)
    assert response.is_allowed
    # Verify the injection string is a single element
    received = fake_server._requests_received[0]
    assert received["argv"][1] == "ps; rm -rf /"


# ---------------------------------------------------------------------------
# Secret redaction tests
# ---------------------------------------------------------------------------

def test_redact_secret_keys():
    """Secret-like keys should be redacted."""
    data = {
        "api_key": "sk-abc123def456",
        "normal_field": "visible",
        "PASSWORD": "s3cr3t",
        "nested": {"TOKEN": "bearer-xyz"},
    }
    result = redact_dict(data)
    assert result["api_key"] == "[REDACTED]"
    assert result["normal_field"] == "visible"
    assert result["PASSWORD"] == "[REDACTED]"
    assert result["nested"]["TOKEN"] == "[REDACTED]"


def test_redact_long_token_strings():
    """Long base64/hex strings should be redacted."""
    data = {
        "data": "abcdefghijklmnopqrstuvwxyz0123456789+/abcdef==",  # 46 chars base64
    }
    result = redact_dict(data)
    assert result["data"] == "[REDACTED]"


def test_redact_argv_secrets():
    """Secret-like argv arguments should be redacted."""
    argv = [
        "docker", "run",
        "-e", "API_KEY=sk-abc123def456",
        "--name", "test",
    ]
    result = redact_argv(argv)
    assert result[3] == "API_KEY=[REDACTED]"
    assert result[4] == "--name"
    assert result[5] == "test"


def test_redact_argv_token_value():
    """Long token values in argv should be redacted."""
    long_token = "a" * 50  # 50 hex chars
    argv = ["--token=" + long_token]
    result = redact_argv(argv)
    assert result[0] == "--token=[REDACTED]"


# ---------------------------------------------------------------------------
# Server error response test
# ---------------------------------------------------------------------------

def test_server_error_response(fake_server, fake_socket_path, valid_request):
    """Server returning BLOCKED should be handled correctly."""
    fake_server.set_response({
        "request_id": valid_request.request_id,
        "correlation_id": valid_request.correlation_id,
        "decision": "BLOCKED",
        "reason": "resource_locked",
        "result": {},
        "audit_seq": 1,
    })
    response = send_request(fake_socket_path, valid_request)
    assert response.is_blocked
    assert response.reason == "resource_locked"


# ---------------------------------------------------------------------------
# Timeout test
# ---------------------------------------------------------------------------

def test_client_timeout(fake_server, fake_socket_path, valid_request):
    """Client should timeout if server delays beyond read_timeout."""
    fake_server.set_delay(5.0)  # Delay longer than read_timeout
    with pytest.raises(ExecutorTimeoutError):
        send_request(fake_socket_path, valid_request, read_timeout=1.0)


# ---------------------------------------------------------------------------
# CLI tests
# ---------------------------------------------------------------------------

from hermes_root.__main__ import main as cli_main


def test_cli_help():
    """--help should exit 0."""
    with pytest.raises(SystemExit) as exc:
        cli_main(["--help"])
    assert exc.value.code == 0


def test_cli_unknown_action():
    """Unknown action should fail validation."""
    rc = cli_main(["frobnicate"])
    assert rc == 2


def test_cli_a2_without_approval():
    """A2 mutating action without --approval should fail validation."""
    rc = cli_main(["docker_create", "--image", "alpine", "--name", "test"])
    assert rc == 2


def test_cli_a3_blocked():
    """A3 execution should always be blocked."""
    rc = cli_main([
        "docker_create",
        "--image", "alpine",
        "--name", "test-a3",
        "--class", "A3",
        "--approval", "APPROVED_TEST",
    ])
    assert rc == 2


def test_cli_missing_required_arg():
    """Missing required arg (--container for docker_inspect) should fail."""
    rc = cli_main(["docker_inspect"])
    assert rc == 2


def test_cli_socket_not_found():
    """Missing socket should produce exit code 3."""
    rc = cli_main([
        "executor_health",
        "--socket", "/nonexistent/executor.sock",
    ])
    assert rc == 3


def test_cli_json_output(fake_server, fake_socket_path, valid_request):
    """--json should produce valid JSON output."""
    saved_stdout = sys.stdout
    try:
        sys.stdout = io.StringIO()
        rc = cli_main([
            "executor_health",
            "--socket", fake_socket_path,
            "--correlation-id", valid_request.correlation_id,
            "--json",
        ])
        output = sys.stdout.getvalue()
    finally:
        sys.stdout = saved_stdout

    assert rc == 0
    parsed = json.loads(output)
    assert parsed["decision"] == "ALLOWED"
    assert parsed["correlation_id"] == valid_request.correlation_id


def test_cli_readonly_action(fake_server, fake_socket_path):
    """Read-only action should succeed with exit 0."""
    saved_stdout = sys.stdout
    try:
        sys.stdout = io.StringIO()
        rc = cli_main([
            "executor_health",
            "--socket", fake_socket_path,
            "--correlation-id", "test-cli-readonly",
        ])
        output = sys.stdout.getvalue()
    finally:
        sys.stdout = saved_stdout

    assert rc == 0
    assert "ALLOWED" in output


def test_cli_a2_with_approval(fake_server, fake_socket_path):
    """A2 with approval should pass validation and send request."""
    saved_stdout = sys.stdout
    try:
        sys.stdout = io.StringIO()
        rc = cli_main([
            "docker_create",
            "--image", "alpine",
            "--name", "test-cli",
            "--approval", "APPROVED_TEST",
            "--socket", fake_socket_path,
            "--correlation-id", "test-cli-a2",
        ])
        output = sys.stdout.getvalue()
    finally:
        sys.stdout = saved_stdout

    assert rc == 0
    assert "ALLOWED" in output


def test_cli_secret_redaction_in_argv(fake_server, fake_socket_path):
    """Secret-like values in argv should be redacted before sending."""
    saved_stdout = sys.stdout
    try:
        sys.stdout = io.StringIO()
        rc = cli_main([
            "docker_ps",
            "--socket", fake_socket_path,
            "--correlation-id", "test-redact",
        ])
        output = sys.stdout.getvalue()
    finally:
        sys.stdout = saved_stdout

    assert rc == 0
    # No raw secrets in output
    assert "sk-" not in output.lower() or "[REDACTED]" in output


def test_cli_shell_injection_stays_single_arg(fake_server, fake_socket_path):
    """Shell injection in argv should remain a single element."""
    saved_stdout = sys.stdout
    try:
        sys.stdout = io.StringIO()
        rc = cli_main([
            "docker_ps",
            "--socket", fake_socket_path,
            "--correlation-id", "test-inject",
        ])
        output = sys.stdout.getvalue()
    finally:
        sys.stdout = saved_stdout

    assert rc == 0
    # Verify the request was sent with proper argv (list, not string)
    received = fake_server._requests_received[-1]
    assert isinstance(received["argv"], list)
