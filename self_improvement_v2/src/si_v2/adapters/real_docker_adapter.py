"""Real Docker adapter prototype — gated behind SI_V2_ENABLE_REAL_ADAPTERS.

Extends RealDockerAdapterBase and implements the DockerAdapter protocol
with actual subprocess-based Docker commands. Instantiation requires
SI_V2_ENABLE_REAL_ADAPTERS=1 in the environment.
"""

from __future__ import annotations

import subprocess
import time

from si_v2.adapters.audit import AdapterAuditSink
from si_v2.adapters.call_budget import CallBudgetChecker, CallBudgetConfig
from si_v2.adapters.docker_adapter import DockerAdapter
from si_v2.adapters.real_base import RealDockerAdapterBase

# Timeouts for Docker operations (seconds)
_EXEC_TIMEOUT: int = 30
_INSPECT_TIMEOUT: int = 15


class RealDockerAdapter(RealDockerAdapterBase, DockerAdapter):
    """Concrete read-only Docker adapter using subprocess + docker CLI.

    Requires ``SI_V2_ENABLE_REAL_ADAPTERS=1`` to instantiate.
    All methods are read-only: exec, status check, IP lookup.

    Args:
        audit_sink: Where audit events are recorded.
        call_budget: Optional sliding-window rate limiter.
    """

    def __init__(
        self,
        audit_sink: AdapterAuditSink,
        call_budget: CallBudgetChecker | None = None,
    ) -> None:
        # Default budget: 10 calls/min (matching #20 contract)
        if call_budget is None:
            call_budget = CallBudgetChecker(
                CallBudgetConfig(
                    max_calls=10,
                    window_seconds=60.0,
                    component_name="RealDockerAdapter",
                )
            )
        super().__init__(audit_sink, call_budget)

    def exec_readonly(self, container: str, command: list[str]) -> str:
        """Execute a read-only command inside *container* and return stdout.

        Args:
            container: Container name or ID.
            command: Command and arguments to execute.

        Returns:
            Command stdout as a string.

        Raises:
            RuntimeError: If the container is not running.
            TimeoutError: If the command exceeds ``_EXEC_TIMEOUT``.
        """
        start = time.monotonic()
        method = "exec_readonly"
        if not self._check_budget(method):
            self._record_audit(method, False, "call budget exhausted")
            raise RuntimeError(f"Call budget exhausted for {method}")

        # Build docker-exec command (read-only, non-interactive)
        docker_cmd = [
            "docker",
            "exec",
            container,
            *command,
        ]
        try:
            result = subprocess.run(
                docker_cmd,
                capture_output=True,
                text=True,
                timeout=_EXEC_TIMEOUT,
            )
            duration = (time.monotonic() - start) * 1000.0
            if result.returncode != 0:
                err = result.stderr.strip() or f"exit code {result.returncode}"
                self._record_audit(
                    method, False, f"command failed: {err}", duration_ms=duration
                )
                # SECURITY: stderr may contain paths but not secrets in
                # read-only commands. If a secret pattern is detected the
                # caller is responsible for redaction.
                raise RuntimeError(
                    f"docker-exec failed: {err}"
                )
            self._record_audit(
                method, True, "ok", duration_ms=duration
            )
            return result.stdout
        except subprocess.TimeoutExpired:
            duration = (time.monotonic() - start) * 1000.0
            self._record_audit(
                method,
                False,
                f"timeout after {_EXEC_TIMEOUT}s",
                duration_ms=duration,
                error="TimeoutExpired",
            )
            raise TimeoutError(
                f"docker-exec timed out after {_EXEC_TIMEOUT}s"
            ) from None

    def container_is_running(self, container: str) -> bool:
        """Check whether *container* is currently running.

        Args:
            container: Container name or ID.

        Returns:
            True if the container is running.
        """
        start = time.monotonic()
        method = "container_is_running"
        if not self._check_budget(method):
            self._record_audit(method, False, "call budget exhausted")
            return False

        try:
            result = subprocess.run(
                ["docker", "inspect", "--format", "{{.State.Running}}", container],
                capture_output=True,
                text=True,
                timeout=_INSPECT_TIMEOUT,
            )
            duration = (time.monotonic() - start) * 1000.0
            is_running = result.returncode == 0 and result.stdout.strip() == "true"
            self._record_audit(
                method, True, str(is_running), duration_ms=duration
            )
            return is_running
        except subprocess.TimeoutExpired:
            duration = (time.monotonic() - start) * 1000.0
            self._record_audit(
                method,
                False,
                "timeout",
                duration_ms=duration,
                error="TimeoutExpired",
            )
            return False
        except OSError as exc:
            duration = (time.monotonic() - start) * 1000.0
            self._record_audit(
                method,
                False,
                str(exc),
                duration_ms=duration,
                error="OSError",
            )
            return False

    def get_container_ip(self, container: str) -> str:
        """Get the IP address of a running container.

        Args:
            container: Container name or ID.

        Returns:
            IP address as a string.

        Raises:
            RuntimeError: If the container is not found or has no IP.
        """
        start = time.monotonic()
        method = "get_container_ip"
        if not self._check_budget(method):
            self._record_audit(method, False, "call budget exhausted")
            raise RuntimeError(f"Call budget exhausted for {method}")

        try:
            result = subprocess.run(
                [
                    "docker",
                    "inspect",
                    "--format",
                    "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}",
                    container,
                ],
                capture_output=True,
                text=True,
                timeout=_INSPECT_TIMEOUT,
            )
            duration = (time.monotonic() - start) * 1000.0
            ip_addr = result.stdout.strip()
            if not ip_addr or result.returncode != 0:
                err = result.stderr.strip() or "no IP address found"
                self._record_audit(
                    method, False, err, duration_ms=duration
                )
                raise RuntimeError(f"Cannot get IP for {container}: {err}")
            self._record_audit(method, True, ip_addr, duration_ms=duration)
            return ip_addr
        except subprocess.TimeoutExpired:
            duration = (time.monotonic() - start) * 1000.0
            self._record_audit(
                method,
                False,
                "timeout",
                duration_ms=duration,
                error="TimeoutExpired",
            )
            raise TimeoutError(f"docker inspect timed out for {container}") from None
