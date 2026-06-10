"""Read-only Docker adapter protocol.

Defines the interface for Docker interactions. Only read-only methods
are permitted — no restart, stop, start, or rm operations.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class DockerAdapter(Protocol):
    """Protocol for read-only Docker operations."""

    def exec_readonly(self, container: str, command: list[str]) -> str:
        """Execute a read-only command inside a container and return stdout.

        Args:
            container: Container name or ID.
            command: Command and arguments to execute.

        Returns:
            Command stdout as a string.
        """
        ...

    def container_is_running(self, container: str) -> bool:
        """Check whether a container is currently running.

        Args:
            container: Container name or ID.

        Returns:
            True if the container is running.
        """
        ...

    def get_container_ip(self, container: str) -> str:
        """Get the IP address of a running container.

        Args:
            container: Container name or ID.

        Returns:
            IP address as a string.
        """
        ...
