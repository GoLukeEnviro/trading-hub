"""Shadow logger for deploy-phase tracking.

Logs proposed mutations and their outcomes to JSONL files for later review,
without affecting live trading. Supports both file persistence and in-memory
mode for testing.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

# Phase identifiers for pipeline tracking
Phase = Literal["observe", "analyze", "propose", "backtest", "walk_forward", "approve", "deploy"]
Decision = Literal["hold", "mutate", "block", "pass", "fail"]


class ShadowLogger:
    """Logs mutation proposals and pipeline phases to JSONL files."""

    def __init__(self, log_dir: Path | None = None) -> None:
        """Initialize with an optional log directory.

        Args:
            log_dir: Directory for JSONL log files. If None, operates in
                     in-memory mode only (for testing).
        """
        self._log_dir = log_dir
        self._memory: dict[str, list[dict[str, str | dict[str, str | float | int] | None]]] = {}

    def log(
        self,
        bot_id: str,
        candidate_sha: str,
        params: dict[str, float | int],
        outcome: str | None,
        phase: str,
        decision: str,
        reason: str,
    ) -> None:
        """Log a pipeline event as a JSONL entry.

        Args:
            bot_id: Bot identifier.
            candidate_sha: SHA256 hash of the mutation candidate.
            params: Proposed parameters.
            outcome: Outcome description (optional).
            phase: Pipeline phase name.
            decision: Decision made in this phase.
            reason: Human-readable reason for the decision.
        """
        entry: dict[str, str | dict[str, str | float | int] | None] = {
            "timestamp_utc": datetime.now(UTC).isoformat(),
            "bot_id": bot_id,
            "candidate_sha": candidate_sha,
            "params": {k: v for k, v in params.items()},
            "outcome": outcome,
            "phase": phase,
            "decision": decision,
            "reason": reason,
        }

        if self._log_dir is not None:
            self._write_to_file(bot_id, entry)
        else:
            self._store_in_memory(bot_id, entry)

    def get_entries(self, bot_id: str) -> list[dict[str, str | dict[str, str | float | int] | None]]:
        """Retrieve all log entries for a bot.

        Reads from file if log_dir is set, otherwise from memory.

        Args:
            bot_id: Bot identifier to filter entries.

        Returns:
            List of log entry dictionaries for the specified bot.
        """
        if self._log_dir is not None:
            return self._read_from_file(bot_id)
        return list(self._memory.get(bot_id, []))

    def _write_to_file(
        self,
        bot_id: str,
        entry: dict[str, str | dict[str, str | float | int] | None],
    ) -> None:
        """Append an entry to the bot's JSONL file.

        Args:
            bot_id: Bot identifier (used in filename).
            entry: Log entry dictionary to write.
        """
        assert self._log_dir is not None  # for type narrowing
        self._log_dir.mkdir(parents=True, exist_ok=True)
        log_path = self._log_dir / f"shadow_{bot_id}.jsonl"
        with open(log_path, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def _read_from_file(self, bot_id: str) -> list[dict[str, str | dict[str, str | float | int] | None]]:
        """Read all entries for a bot from the JSONL file.

        Args:
            bot_id: Bot identifier (used in filename).

        Returns:
            List of log entry dictionaries.
        """
        assert self._log_dir is not None  # for type narrowing
        log_path = self._log_dir / f"shadow_{bot_id}.jsonl"
        entries: list[dict[str, str | dict[str, str | float | int] | None]] = []
        try:
            with open(log_path) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        entries.append(json.loads(line))
        except FileNotFoundError:
            pass
        return entries

    def _store_in_memory(
        self,
        bot_id: str,
        entry: dict[str, str | dict[str, str | float | int] | None],
    ) -> None:
        """Store an entry in memory (for testing mode).

        Args:
            bot_id: Bot identifier.
            entry: Log entry dictionary to store.
        """
        if bot_id not in self._memory:
            self._memory[bot_id] = []
        self._memory[bot_id].append(entry)
