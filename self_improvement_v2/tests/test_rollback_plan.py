"""Unit tests for the RollbackPlanManager."""

from __future__ import annotations

from pathlib import Path

from si_v2.deploy.rollback_plan import (
    ConfigSnapshot,
    RollbackPlan,
    RollbackPlanManager,
)


def _sample_config() -> dict[str, str | int | float | bool]:
    return {
        "stoploss": -0.02,
        "max_open_trades": 3,
        "stake_amount": 20.0,
        "dry_run": True,
    }


class TestRollbackPlanInMemory:
    """RollbackPlanManager in-memory behaviour."""

    def test_take_snapshot_records_snapshot(self) -> None:
        mgr = RollbackPlanManager()
        snap = mgr.take_snapshot("bot_a", _sample_config(), "before_change")
        assert isinstance(snap, ConfigSnapshot)
        assert snap.bot_id == "bot_a"
        assert snap.source_label == "before_change"
        assert snap.config_copy == _sample_config()
        # Hash is the SHA256 hex digest (64 chars)
        assert len(snap.config_hash) == 64
        # Recorded internally
        assert mgr.get_snapshots("bot_a") == [snap]

    def test_take_snapshot_copies_config(self) -> None:
        mgr = RollbackPlanManager()
        cfg = _sample_config()
        snap = mgr.take_snapshot("bot_a", cfg, "label")
        cfg["stoploss"] = -0.99
        # The snapshot's copy must be unaffected by later mutation
        assert snap.config_copy["stoploss"] == -0.02

    def test_record_snapshot_appends(self) -> None:
        mgr = RollbackPlanManager()
        snap = ConfigSnapshot(
            bot_id="bot_a",
            timestamp_utc="2026-01-01T00:00:00+00:00",
            config_hash="deadbeef",
            config_copy=_sample_config(),
            source_label="manual",
        )
        mgr.record_snapshot(snap)
        assert mgr.get_snapshots("bot_a") == [snap]

    def test_build_rollback_plan_uses_latest_snapshot(self) -> None:
        mgr = RollbackPlanManager()
        mgr.take_snapshot("bot_a", {"stoploss": -0.01}, "v1")
        mgr.take_snapshot("bot_a", {"stoploss": -0.02}, "v2")
        plan = mgr.build_rollback_plan(
            bot_id="bot_a",
            target_candidate_sha="sha-bad",
            reason="regression",
        )
        assert isinstance(plan, RollbackPlan)
        assert plan.bot_id == "bot_a"
        assert plan.target_candidate_sha == "sha-bad"
        assert plan.reason == "regression"
        assert plan.snapshot.source_label == "v2"
        assert plan.snapshot.config_copy == {"stoploss": -0.02}

    def test_build_rollback_plan_returns_none_without_snapshot(self) -> None:
        mgr = RollbackPlanManager()
        plan = mgr.build_rollback_plan("nonexistent", "sha", "r")
        assert plan is None

    def test_simulate_rollback_returns_copy(self) -> None:
        mgr = RollbackPlanManager()
        mgr.take_snapshot("bot_a", _sample_config(), "label")
        plan = mgr.build_rollback_plan("bot_a", "sha", "r")
        assert plan is not None
        restored = mgr.simulate_rollback(plan)
        assert restored == _sample_config()
        # The returned dict is a copy
        restored["stoploss"] = -0.50
        assert plan.snapshot.config_copy["stoploss"] == -0.02

    def test_snapshots_isolated_per_bot(self) -> None:
        mgr = RollbackPlanManager()
        mgr.take_snapshot("bot_a", {"x": 1}, "l1")
        mgr.take_snapshot("bot_b", {"x": 2}, "l2")
        assert mgr.get_snapshots("bot_a")[0].config_copy == {"x": 1}
        assert mgr.get_snapshots("bot_b")[0].config_copy == {"x": 2}


class TestRollbackPlanFilePersistence:
    """RollbackPlanManager persists to disk when log_dir is set."""

    def test_persists_snapshots_and_plans(self, tmp_path: Path) -> None:
        mgr = RollbackPlanManager(log_dir=tmp_path)
        mgr.take_snapshot("bot_a", _sample_config(), "v1")
        mgr.take_snapshot("bot_a", {"stoploss": -0.99}, "v2")
        plan = mgr.build_rollback_plan("bot_a", "sha", "r")
        assert plan is not None

        snap_path = tmp_path / "snapshots_bot_a.jsonl"
        plan_path = tmp_path / "rollback_plans_bot_a.jsonl"
        assert snap_path.exists()
        assert plan_path.exists()
        # Snapshots file should have 2 lines
        with open(snap_path) as f:
            assert sum(1 for _ in f if _.strip()) == 2
        with open(plan_path) as f:
            assert sum(1 for _ in f if _.strip()) == 1

    def test_no_files_when_log_dir_is_none(self, tmp_path: Path) -> None:
        # Sanity: nothing should be written anywhere outside the log_dir
        mgr = RollbackPlanManager()
        mgr.take_snapshot("bot_a", _sample_config(), "v1")
        # tmp_path is unused; we just ensure no files appear inside it
        # from this manager
        assert list(tmp_path.iterdir()) == []
