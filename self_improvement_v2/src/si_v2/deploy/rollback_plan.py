"""Rollback plan manager — simulation only, no live restore.

Provides a RollbackPlanManager that records in-memory snapshots of bot
configurations and can build a RollbackPlan that "would" restore a bot
to a prior state. The simulate_rollback() helper returns the snapshot's
config_copy without writing to any live path. All file I/O is opt-in
and must be rooted at a caller-supplied tmp_path for tests.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict


class ConfigSnapshot(BaseModel):
    """An immutable point-in-time copy of a bot's configuration."""

    model_config = ConfigDict(strict=False)

    bot_id: str
    timestamp_utc: str
    config_hash: str
    config_copy: dict[str, str | int | float | bool]
    source_label: str


class RollbackPlan(BaseModel):
    """A plan describing how to roll a bot back to a prior snapshot.

    The plan is a pure data object — it does not perform any I/O and
    is safe to persist alongside shadow logs.
    """

    model_config = ConfigDict(strict=False)

    bot_id: str
    target_candidate_sha: str
    snapshot: ConfigSnapshot
    reason: str
    created_at_utc: str


class RollbackPlanManager:
    """Manages config snapshots and rollback plans in memory.

    The manager never writes to live Freqtrade config paths, never
    touches Docker, and never performs any network I/O. If a
    log_dir is supplied, snapshots and plans are persisted to
    caller-controlled tmp_path directories only.
    """

    def __init__(self, log_dir: Path | None = None) -> None:
        """Initialise an empty snapshot store.

        Args:
            log_dir: Optional directory used to persist snapshots/plans
                     to JSONL files. Tests should pass a tmp_path
                     fixture; production usage in this phase is
                     expected to be off in practice.
        """
        self._snapshots: dict[str, list[ConfigSnapshot]] = {}
        self._log_dir: Path | None = log_dir

    def take_snapshot(
        self,
        bot_id: str,
        config: dict[str, str | int | float | bool],
        source_label: str,
    ) -> ConfigSnapshot:
        """Capture a snapshot of the given bot configuration.

        Args:
            bot_id: Bot identifier.
            config: A deep copy of the bot's current configuration.
            source_label: Free-form label (e.g. "before_candidate_xyz").

        Returns:
            A ConfigSnapshot containing a copy of the config and its
            hash. The snapshot is also recorded in the manager.
        """
        config_copy: dict[str, str | int | float | bool] = dict(config)
        config_hash = self._hash_config(config_copy)
        snapshot = ConfigSnapshot(
            bot_id=bot_id,
            timestamp_utc=datetime.now(UTC).isoformat(),
            config_hash=config_hash,
            config_copy=config_copy,
            source_label=source_label,
        )
        self.record_snapshot(snapshot)
        return snapshot

    def record_snapshot(self, snapshot: ConfigSnapshot) -> None:
        """Append a snapshot to the in-memory store and (optionally) disk.

        Args:
            snapshot: The ConfigSnapshot to record.
        """
        self._snapshots.setdefault(snapshot.bot_id, []).append(snapshot)
        if self._log_dir is not None:
            self._write_snapshot_to_file(snapshot)

    def build_rollback_plan(
        self,
        bot_id: str,
        target_candidate_sha: str,
        reason: str,
    ) -> RollbackPlan | None:
        """Build a RollbackPlan targeting the most recent snapshot.

        Args:
            bot_id: Bot identifier.
            target_candidate_sha: SHA256 hash of the candidate being
                rolled back FROM.
            reason: Human-readable reason for the rollback plan.

        Returns:
            A RollbackPlan, or None if no snapshots exist for the bot.
        """
        snapshots = self._snapshots.get(bot_id, [])
        if not snapshots:
            return None

        latest = snapshots[-1]
        plan = RollbackPlan(
            bot_id=bot_id,
            target_candidate_sha=target_candidate_sha,
            snapshot=latest,
            reason=reason,
            created_at_utc=datetime.now(UTC).isoformat(),
        )

        if self._log_dir is not None:
            self._write_plan_to_file(plan)

        return plan

    def simulate_rollback(self, plan: RollbackPlan) -> dict[str, str | int | float | bool]:
        """Return the snapshot's config_copy without writing to disk.

        This is a pure simulation: it does NOT restore the live config
        and does NOT touch any I/O. The returned dict is a fresh copy
        of the snapshot's config_copy.

        Args:
            plan: The RollbackPlan to "execute" (in simulation only).

        Returns:
            A copy of the snapshot's config_copy that would be applied
            by a real rollback.
        """
        return dict(plan.snapshot.config_copy)

    def get_snapshots(self, bot_id: str) -> list[ConfigSnapshot]:
        """Return all snapshots recorded for a bot.

        Args:
            bot_id: Bot identifier.

        Returns:
            A list of ConfigSnapshot, oldest first.
        """
        return list(self._snapshots.get(bot_id, []))

    @staticmethod
    def _hash_config(config: dict[str, str | int | float | bool]) -> str:
        """Compute a stable SHA256 hash of a config dict.

        Args:
            config: Configuration dictionary to hash.

        Returns:
            Hex-encoded SHA256 digest (full 64 characters).
        """
        serialized = json.dumps(config, sort_keys=True)
        return hashlib.sha256(serialized.encode()).hexdigest()

    def _write_snapshot_to_file(self, snapshot: ConfigSnapshot) -> None:
        """Append a snapshot to a per-bot JSONL file under log_dir.

        Args:
            snapshot: The snapshot to persist.
        """
        assert self._log_dir is not None
        self._log_dir.mkdir(parents=True, exist_ok=True)
        path = self._log_dir / f"snapshots_{snapshot.bot_id}.jsonl"
        with open(path, "a") as f:
            f.write(snapshot.model_dump_json() + "\n")

    def _write_plan_to_file(self, plan: RollbackPlan) -> None:
        """Append a rollback plan to a per-bot JSONL file under log_dir.

        Args:
            plan: The plan to persist.
        """
        assert self._log_dir is not None
        self._log_dir.mkdir(parents=True, exist_ok=True)
        path = self._log_dir / f"rollback_plans_{plan.bot_id}.jsonl"
        with open(path, "a") as f:
            f.write(plan.model_dump_json() + "\n")
