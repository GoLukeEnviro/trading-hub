"""Sandbox path guard — validates paths stay within the sandbox.

Prevents path traversal, symlink escape, and protects live strategy
paths from accidental mutation.
"""

from __future__ import annotations

from pathlib import Path


class SandboxPathGuard:
    """Guards against unsafe path operations within the mutation sandbox.

    Ensures all file operations remain confined to the designated sandbox
    root directory and never touch live strategy paths.
    """

    @staticmethod
    def resolve_sandbox_path(proposed_path: Path, sandbox_root: Path) -> Path:
        """Resolve and validate a path is inside the sandbox root.

        Args:
            proposed_path: The path to validate (may be relative or absolute).
            sandbox_root: The allowed sandbox root directory.

        Returns:
            The resolved, absolute path if it is safe.

        Raises:
            ValueError: If the path resolves outside sandbox_root, contains
                path traversal components, or follows a symlink that escapes.
        """
        resolved = proposed_path.resolve()

        sandbox_resolved = sandbox_root.resolve()

        # Check that the resolved path starts with the sandbox root
        try:
            resolved.relative_to(sandbox_resolved)
        except ValueError:
            raise ValueError(
                f"Path {proposed_path} resolves to {resolved}, which is outside sandbox root {sandbox_root}"
            ) from None

        # Check for symlink escape: if the proposed path is a symlink,
        # verify its target also stays within the sandbox
        if proposed_path.is_symlink():
            target = proposed_path.readlink()
            if not target.is_absolute():  # noqa: SIM108
                target = (proposed_path.parent / target).resolve()
            else:
                target = target.resolve()
            try:
                target.relative_to(sandbox_resolved)
            except ValueError:
                raise ValueError(
                    f"Symlink at {proposed_path} resolves to {target}, which is outside sandbox root {sandbox_root}"
                ) from None

        return resolved

    @staticmethod
    def is_live_strategy_path(path: Path) -> bool:
        """Check if a path refers to a live Freqtrade strategy location.

        Args:
            path: The path to inspect.

        Returns:
            True if the path string contains 'user_data/strategies'
            or 'freqtrade/strategies' as a sub-path.
        """
        path_str = str(path.as_posix())
        return "user_data/strategies" in path_str or "freqtrade/strategies" in path_str

    @staticmethod
    def assert_sandbox_path(proposed_path: Path, sandbox_root: Path) -> None:
        """Assert that a proposed path is safe for sandbox operations.

        Args:
            proposed_path: The path to validate.
            sandbox_root: The allowed sandbox root directory.

        Raises:
            ValueError: If the path is unsafe (outside sandbox, traversal,
                symlink escape, or a live strategy path).
        """
        if SandboxPathGuard.is_live_strategy_path(proposed_path):
            raise ValueError(
                f"Path {proposed_path} refers to a live strategy path (user_data/strategies or freqtrade/strategies)"
            )
        SandboxPathGuard.resolve_sandbox_path(proposed_path, sandbox_root)
