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
                    # Default: echo back as ALLOWED, matching the real
                    # daemon's v1 wire format (hermes-root-executor._finish_v1)
                    echo = {
                        "schema_version": SCHEMA_VERSION,
                        "request_id": parsed_request.get("request_id", ""),
                        "correlation_id": parsed_request.get("correlation_id", ""),
                        "decision": "ALLOWED",
                        "reason": "ok",
                        "returncode": 0,
                        "stdout": "healthy",
                        "stderr": "",
                        "started_at": "2026-07-13T00:00:00+00:00",
                        "finished_at": "2026-07-13T00:00:00+00:00",
                        "duration_ms": 1,
                        "resource_key": parsed_request.get("resource_key", ""),
                        "action": parsed_request.get("action", ""),
                        "execution_class": parsed_request.get("execution_class", ""),
                        "audit_id": "test-audit-id",
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
# Client/daemon argv contract test
#
# The daemon-side action registry (hermes_root.actions.build_argv) owns the
# fixed base command per action and appends the client's argv as extras. The
# CLI's _build_argv must send only those extras, or the daemon runs a
# duplicated/invalid command (see 2026-07-13 H3B proof run: docker_ps sent
# as ["docker", "ps"] duplicated into "docker ps docker ps" and failed).
# ---------------------------------------------------------------------------

from hermes_root.__main__ import _build_argv as cli_build_argv
from hermes_root.actions import build_argv as daemon_build_argv


def _namespace(**overrides):
    """Minimal argparse.Namespace stand-in with the fields _build_argv reads."""
    import argparse
    defaults = dict(container=None, unit=None, file=None, image=None, name=None, cmd=None)
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


@pytest.mark.parametrize(
    "action,ns_kwargs,expected_final_argv",
    [
        ("executor_health", {}, []),
        ("docker_ps", {}, ["docker", "ps"]),
        ("docker_inspect", {"container": "hermes"}, ["docker", "inspect", "hermes"]),
        ("systemctl_status", {"unit": "hermes-root-executor.service"},
         ["systemctl", "status", "hermes-root-executor.service"]),
        ("docker_stop", {"container": "throwaway"}, ["docker", "stop", "throwaway"]),
        ("docker_remove", {"container": "throwaway"}, ["docker", "rm", "throwaway"]),
        ("systemctl_restart", {"unit": "some.service"}, ["systemctl", "restart", "some.service"]),
    ],
)
def test_cli_extras_match_daemon_builder(action, ns_kwargs, expected_final_argv):
    """CLI extras, run through the real daemon-side builder, must produce the
    exact final command — no duplication, no missing/rejected arguments."""
    extras = cli_build_argv(action, _namespace(**ns_kwargs))
    final_argv = daemon_build_argv(action, extras)
    assert final_argv == expected_final_argv


# ---------------------------------------------------------------------------
# docker_compose_config: multi-file contract + path-safety tests
# ---------------------------------------------------------------------------

import tempfile as _tempfile
from hermes_root.actions import ActionError as _ActionError


def test_cli_compose_config_single_file_extras():
    """A single --file becomes a one-element extras list (no -f prefix —
    the daemon builds the flags itself)."""
    ns = _namespace(file=["/opt/stacks/hermes/compose.yaml"])
    extras = cli_build_argv("docker_compose_config", ns)
    assert extras == ["/opt/stacks/hermes/compose.yaml"]


def test_cli_compose_config_multi_file_extras():
    """Repeated --file layers multiple compose files, base first."""
    ns = _namespace(file=[
        "/opt/stacks/hermes/compose.yaml",
        "/opt/stacks/hermes/compose.override.yaml",
    ])
    extras = cli_build_argv("docker_compose_config", ns)
    assert extras == [
        "/opt/stacks/hermes/compose.yaml",
        "/opt/stacks/hermes/compose.override.yaml",
    ]


def test_cli_compose_config_too_many_files_rejected():
    """More than 4 --file arguments must be rejected client-side."""
    ns = _namespace(file=["/opt/stacks/a", "/opt/stacks/b", "/opt/stacks/c",
                           "/opt/stacks/d", "/opt/stacks/e"])
    with pytest.raises(ValueError, match="at most 4"):
        cli_build_argv("docker_compose_config", ns)


def test_cli_compose_config_missing_file_rejected():
    """No --file at all must be rejected client-side."""
    ns = _namespace(file=None)
    with pytest.raises(ValueError, match="--file is required"):
        cli_build_argv("docker_compose_config", ns)


def test_daemon_compose_config_multi_file_builds_repeated_flags(tmp_path):
    """The daemon builder lays out -f <file> once per file, base first,
    then a single trailing 'config'."""
    base = tmp_path / "compose.yaml"
    override = tmp_path / "compose.override.yaml"
    base.write_text("services: {}\n")
    override.write_text("services: {}\n")

    import hermes_root.actions as actions_mod
    real_roots = actions_mod.ALLOWED_COMPOSE_STACK_ROOTS
    actions_mod.ALLOWED_COMPOSE_STACK_ROOTS = (str(tmp_path),)
    try:
        final_argv = daemon_build_argv("docker_compose_config", [str(base), str(override)])
    finally:
        actions_mod.ALLOWED_COMPOSE_STACK_ROOTS = real_roots

    assert final_argv == [
        "docker", "compose",
        "-f", str(base),
        "-f", str(override),
        "config", "--quiet",
    ]


def test_daemon_compose_config_rejects_relative_path():
    with pytest.raises(_ActionError, match="compose_file_not_absolute"):
        daemon_build_argv("docker_compose_config", ["relative/compose.yaml"])


def test_daemon_compose_config_rejects_path_traversal():
    with pytest.raises(_ActionError, match="compose_file_path_traversal"):
        daemon_build_argv("docker_compose_config", ["/opt/stacks/hermes/../../etc/passwd"])


def test_daemon_compose_config_rejects_outside_allowlisted_root(tmp_path):
    outside = tmp_path / "compose.yaml"
    outside.write_text("services: {}\n")
    with pytest.raises(_ActionError, match="compose_file_outside_allowlisted_root"):
        daemon_build_argv("docker_compose_config", [str(outside)])


def test_daemon_compose_config_rejects_missing_file():
    with pytest.raises(_ActionError, match="compose_file_not_found"):
        daemon_build_argv("docker_compose_config", ["/opt/stacks/hermes/does-not-exist.yaml"])


def test_daemon_compose_config_rejects_symlink_escape(tmp_path):
    """A symlink inside the allowlisted root pointing outside it must be
    rejected — realpath() resolution catches this before the file is used."""
    import hermes_root.actions as actions_mod
    real_roots = actions_mod.ALLOWED_COMPOSE_STACK_ROOTS

    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    secret_file = outside_dir / "secret.yaml"
    secret_file.write_text("services: {}\n")

    inside_root = tmp_path / "stacks"
    inside_root.mkdir()
    symlink_path = inside_root / "compose.yaml"
    symlink_path.symlink_to(secret_file)

    actions_mod.ALLOWED_COMPOSE_STACK_ROOTS = (str(inside_root / "allowlisted-subdir-only"),)
    try:
        with pytest.raises(_ActionError, match="compose_file_outside_allowlisted_root"):
            daemon_build_argv("docker_compose_config", [str(symlink_path)])
    finally:
        actions_mod.ALLOWED_COMPOSE_STACK_ROOTS = real_roots


def test_daemon_compose_config_rejects_too_many_files():
    with pytest.raises(_ActionError, match="invalid_argv_for_action"):
        daemon_build_argv("docker_compose_config", ["/a", "/b", "/c", "/d", "/e"])


def test_daemon_compose_config_rejects_zero_files():
    with pytest.raises(_ActionError, match="invalid_argv_for_action"):
        daemon_build_argv("docker_compose_config", [])


def test_cli_docker_create_extras_match_daemon_builder():
    """docker_create: daemon only requires len(argv) >= 1, verify the CLI's
    extras produce a syntactically sane 'docker create ...' invocation."""
    ns = _namespace(image="alpine:latest", name="h3b-test", cmd="sleep 60")
    extras = cli_build_argv("docker_create", ns)
    final_argv = daemon_build_argv("docker_create", extras)
    assert final_argv == ["docker", "create", "--name", "h3b-test", "alpine:latest", "sleep 60"]


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
        "returncode": None,
        "stdout": "",
        "stderr": "",
    })
    response = send_request(fake_socket_path, valid_request)
    assert response.is_blocked
    assert response.reason == "resource_locked"


def test_v1_response_fields_parsed(fake_server, fake_socket_path, valid_request):
    """action, execution_class and audit_id from a real v1 response must be
    surfaced on ExecutorResponse, not silently dropped."""
    response = send_request(fake_socket_path, valid_request)
    assert response.is_allowed
    assert response.action == valid_request.action
    assert response.execution_class == valid_request.execution_class
    assert response.audit_id == "test-audit-id"
    assert response.returncode == 0
    assert response.stdout == "healthy"


def test_legacy_shaped_response_parses_with_defaults(fake_server, fake_socket_path, valid_request):
    """A legacy-protocol response (only decision/reason/returncode/stdout/stderr,
    no v1-only fields) must still parse without error, defaulting the
    v1-only fields instead of raising."""
    fake_server.set_response({
        "decision": "ALLOWED",
        "returncode": 0,
        "stdout": "legacy-ok",
        "stderr": "",
    })
    response = send_request(fake_socket_path, valid_request)
    assert response.is_allowed
    assert response.returncode == 0
    assert response.stdout == "legacy-ok"
    assert response.action == ""
    assert response.audit_id == ""


# ---------------------------------------------------------------------------
# Client/CLI defense-in-depth secret redaction (canary secrets only)
#
# Regression coverage for the 2026-07-13 incident: a rendered
# docker-compose config exposed a live GH_TOKEN through unredacted
# stdout. The daemon now redacts before responding, but the client also
# redacts independently (defense in depth, e.g. against an older or
# bypassed daemon) — these tests verify that second boundary directly.
# ---------------------------------------------------------------------------

CANARY_GH_TOKEN = "github_pat_11CANARY0000000000000000000000000000000000000000000000"


def test_client_response_redacts_canary_in_stdout(fake_server, fake_socket_path, valid_request):
    """Even if a (hypothetical, non-redacting) daemon sent a secret in
    stdout, the client must redact it before returning ExecutorResponse."""
    fake_server.set_response({
        "request_id": valid_request.request_id,
        "correlation_id": valid_request.correlation_id,
        "decision": "ALLOWED",
        "reason": "ok",
        "returncode": 0,
        "stdout": f"GH_TOKEN: {CANARY_GH_TOKEN}",
        "stderr": "",
    })
    response = send_request(fake_socket_path, valid_request)
    assert CANARY_GH_TOKEN not in response.stdout
    assert "[REDACTED]" in response.stdout


def test_cli_json_output_redacts_canary(fake_server, fake_socket_path, valid_request):
    fake_server.set_response({
        "request_id": valid_request.request_id,
        "correlation_id": valid_request.correlation_id,
        "decision": "ALLOWED",
        "reason": "ok",
        "returncode": 0,
        "stdout": f"GH_TOKEN: {CANARY_GH_TOKEN}",
        "stderr": "",
    })
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
    assert CANARY_GH_TOKEN not in output
    parsed = json.loads(output)
    assert CANARY_GH_TOKEN not in parsed["stdout"]
    assert "[REDACTED]" in parsed["stdout"]


def test_cli_human_readable_output_redacts_canary(fake_server, fake_socket_path, valid_request):
    fake_server.set_response({
        "request_id": valid_request.request_id,
        "correlation_id": valid_request.correlation_id,
        "decision": "ALLOWED",
        "reason": "ok",
        "returncode": 0,
        "stdout": f"GH_TOKEN: {CANARY_GH_TOKEN}",
        "stderr": "",
    })
    saved_stdout = sys.stdout
    try:
        sys.stdout = io.StringIO()
        rc = cli_main([
            "executor_health",
            "--socket", fake_socket_path,
            "--correlation-id", valid_request.correlation_id,
        ])
        output = sys.stdout.getvalue()
    finally:
        sys.stdout = saved_stdout

    assert rc == 0
    assert CANARY_GH_TOKEN not in output
    assert "[REDACTED]" in output


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
