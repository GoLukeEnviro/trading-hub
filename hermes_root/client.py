"""Hermes Root Executor Client — AF_UNIX transport layer.

Handles socket communication with the hermes-root-executor.service daemon.
Stdlib-only, no external dependencies.
"""

from __future__ import annotations

import json
import socket
from typing import Any

from hermes_root.schema import (
    CONNECT_TIMEOUT,
    MAX_RESPONSE_BYTES,
    READ_TIMEOUT,
    ExecutorRequest,
    ExecutorResponse,
)
from hermes_root.redact import redact_argv, redact_dict


class ExecutorClientError(Exception):
    """Raised when the client cannot communicate with the executor."""


class ExecutorTimeoutError(ExecutorClientError):
    """Raised when the executor does not respond within the timeout."""


class ExecutorConnectionError(ExecutorClientError):
    """Raised when the socket cannot be reached."""


class ExecutorProtocolError(ExecutorClientError):
    """Raised when the response cannot be parsed."""


def send_request(
    socket_path: str,
    request: ExecutorRequest,
    connect_timeout: float = CONNECT_TIMEOUT,
    read_timeout: float = READ_TIMEOUT,
) -> ExecutorResponse:
    """Send a structured request to the root executor and return the response.

    Args:
        socket_path: Path to the executor's Unix domain socket.
        request: Structured ExecutorRequest with all required fields.
        connect_timeout: Seconds to wait for socket connection.
        read_timeout: Seconds to wait for response data.

    Returns:
        ExecutorResponse with decision, reason, and result.

    Raises:
        ExecutorConnectionError: Socket unreachable or connection refused.
        ExecutorTimeoutError: No response within timeout.
        ExecutorProtocolError: Response is not valid JSON or missing required fields.
    """
    # Redact secrets in argv before sending (defense in depth — executor also redacts)
    safe_request = request.to_dict()
    safe_request["argv"] = redact_argv(request.argv)

    payload = (json.dumps(safe_request) + "\n").encode("utf-8")

    sock: socket.socket | None = None
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(connect_timeout)
        sock.connect(socket_path)
        sock.settimeout(read_timeout)
        sock.sendall(payload)

        chunks: list[bytes] = []
        total = 0
        while True:
            try:
                data = sock.recv(4096)
            except socket.timeout:
                raise ExecutorTimeoutError(
                    f"Executor did not respond within {read_timeout}s"
                )
            if not data:
                break
            chunks.append(data)
            total += len(data)
            if total > MAX_RESPONSE_BYTES:
                raise ExecutorProtocolError(
                    f"Response exceeds {MAX_RESPONSE_BYTES} bytes"
                )
            if b"\n" in data:
                break

        raw = b"".join(chunks).decode("utf-8", errors="replace").strip()
        if not raw:
            raise ExecutorProtocolError("Empty response from executor")

        try:
            response_dict = json.loads(raw)
        except json.JSONDecodeError as e:
            raise ExecutorProtocolError(f"Invalid JSON response: {e}")

        response = ExecutorResponse.from_dict(response_dict)

        # Redact any secrets in the result before returning to caller
        if response.result:
            response.result = redact_dict(response.result)

        return response

    except FileNotFoundError:
        raise ExecutorConnectionError(
            f"Executor socket not found at {socket_path}"
        )
    except ConnectionRefusedError:
        raise ExecutorConnectionError(
            f"Executor socket refused connection at {socket_path}"
        )
    except socket.timeout:
        raise ExecutorTimeoutError(
            f"Connection to executor timed out after {connect_timeout}s"
        )
    except OSError as e:
        raise ExecutorConnectionError(f"Socket error: {e}")
    finally:
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
