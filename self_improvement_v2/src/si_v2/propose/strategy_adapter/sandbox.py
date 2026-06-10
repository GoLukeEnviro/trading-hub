"""Sandbox manager — copies strategy files into a sandbox for safe mutation.

Ensures source files are never modified and creates byte-identical backups.
"""

from __future__ import annotations

import shutil
import time

from si_v2.propose.strategy_adapter.path_guard import SandboxPathGuard
from si_v2.propose.strategy_adapter.schema import (
    StrategyMutationPlan,
    StrategyMutationRequest,
)


class StrategySandbox:
    """Manages sandbox copies of strategy files for safe mutation testing.

    All operations occur within the sandbox root; the original source file
    is never modified.
    """

    def __init__(self) -> None:
        self._path_guard = SandboxPathGuard()

    def create(self, request: StrategyMutationRequest) -> StrategyMutationPlan:
        """Copy a strategy file into the sandbox and create a backup.

        Args:
            request: The mutation request specifying source path and sandbox root.

        Returns:
            A StrategyMutationPlan with paths to the sandbox copy and backup.

        Raises:
            ValueError: If the source path is a live strategy path or
                lies outside the allowed workspace.
            FileNotFoundError: If the source file does not exist.
        """
        source = request.source_path.resolve()
        sandbox_root = request.sandbox_root.resolve()

        # Safety: never touch live strategy paths
        if self._path_guard.is_live_strategy_path(source):
            raise ValueError(f"Source path {source} is a live strategy path — refusing to copy")

        if not source.is_file():
            raise FileNotFoundError(f"Source strategy file not found: {source}")

        sandbox_root.mkdir(parents=True, exist_ok=True)

        short_sha = request.candidate_sha[:8]
        sandbox_filename = f"sandbox_{request.strategy_name}_{short_sha}.py"
        backup_filename = f"backup_{request.strategy_name}_{short_sha}.py"
        sandbox_path = sandbox_root / sandbox_filename
        backup_path = sandbox_root / backup_filename

        # If backup already exists, create a timestamped version
        if backup_path.exists():
            timestamp = int(time.time() * 1000)
            backup_filename = f"backup_{request.strategy_name}_{short_sha}_{timestamp}.py"
            backup_path = sandbox_root / backup_filename

        # Copy source to sandbox (working copy)
        shutil.copy2(source, sandbox_path)

        # Create byte-identical backup
        shutil.copy2(source, backup_path)

        return StrategyMutationPlan(
            source_path=source,
            sandbox_path=sandbox_path,
            backup_path=backup_path,
            changed_parameters=[],
            validation_status="pending",
        )
