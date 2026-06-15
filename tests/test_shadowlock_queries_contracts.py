from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import shadowlock.shadowlock_indexer as indexer
import shadowlock.shadowlock_indexer_queries as queries


def _now(days_delta: int = 0, seconds_delta: int = 0) -> str:
    return (
        datetime.now(UTC) + timedelta(days=days_delta, seconds=seconds_delta)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")


def _configure_db(tmp_path: Path, monkeypatch) -> Path:
    db = tmp_path / "shadowlock.db"
    monkeypatch.setattr(indexer, "DB_PATH", db)
    monkeypatch.setattr(queries, "DB_PATH", db)
    indexer.init_db()
    return db


class TestShadowlockQueriesContracts:
    def test_public_queries_cover_recent_outcome_baseline_and_events(self, tmp_path: Path, monkeypatch) -> None:
        db = _configure_db(tmp_path, monkeypatch)
        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO episodes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "ep-old",
                    "bot-a",
                    "pass",
                    1.0,
                    0.1,
                    "high",
                    0.0,
                    10,
                    "hold",
                    "trigger-1",
                    None,
                    _now(days_delta=-60),
                    None,
                    None,
                    0,
                    "{}",
                ),
            )
            cur.execute(
                "INSERT INTO episodes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "ep-1",
                    "bot-a",
                    "fail",
                    2.0,
                    -0.2,
                    "medium",
                    0.0,
                    8,
                    "watch",
                    "trigger-2",
                    None,
                    _now(seconds_delta=-60),
                    None,
                    None,
                    1,
                    "{}",
                ),
            )
            cur.execute(
                "INSERT INTO episodes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "ep-2",
                    "bot-a",
                    "pass",
                    3.0,
                    0.4,
                    "medium",
                    0.0,
                    6,
                    "watch",
                    "trigger-3",
                    None,
                    _now(),
                    None,
                    None,
                    0,
                    "{}",
                ),
            )
            cur.execute(
                "INSERT INTO forensics_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "run-1",
                    _now(),
                    '["bot-a"]',
                    1,
                    "bot-a",
                    0.99,
                    "{}",
                    "{}",
                ),
            )
            cur.execute(
                "INSERT INTO shadowlock_events (sequence_number, episode_id, event_type, bot_name, target_bot, timestamp_utc, schema_version, entry_sha256, raw_entry) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (1, "ep-1", "self_improvement_episode", "bot-a", "bot-a", _now(seconds_delta=-60), "1.0", "sha1", "{}"),
            )
            cur.execute(
                "INSERT INTO shadowlock_events (sequence_number, episode_id, event_type, bot_name, target_bot, timestamp_utc, schema_version, entry_sha256, raw_entry) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (2, "ep-2", "forensics_run_complete", "bot-a", None, _now(), "1.0", "sha2", "{}"),
            )
            conn.commit()
        finally:
            conn.close()

        recent = queries.get_recent_episodes("bot-a", days=30)
        assert [row["episode_id"] for row in recent] == ["ep-2", "ep-1"]

        by_outcome = queries.get_episodes_by_outcome("bot-a", "fail")
        assert [row["episode_id"] for row in by_outcome] == ["ep-1"]

        hard_stop = queries.get_hard_stop_episodes("bot-a", within_days=30)
        assert [row["episode_id"] for row in hard_stop] == ["ep-1"]

        baseline = queries.get_baseline_PF("bot-a")
        assert baseline == 2.0

        assert queries.episode_id_exists("ep-1") is True
        assert queries.episode_id_exists("missing") is False

        recent_events = queries.get_recent_events("bot-a", limit=10)
        assert [row["sequence_number"] for row in recent_events] == [2, 1]
        assert queries.get_recent_events(limit=1)[0]["sequence_number"] == 2
        assert queries.get_forensics_runs(limit=1)[0]["run_id"] == "run-1"

    def test_missing_db_returns_empty_results(self, tmp_path: Path, monkeypatch) -> None:
        missing = tmp_path / "missing.db"
        monkeypatch.setattr(queries, "DB_PATH", missing)
        assert queries.get_recent_episodes("bot-a") == []
        assert queries.get_episodes_by_outcome("bot-a", "pass") == []
        assert queries.get_hard_stop_episodes("bot-a") == []
        assert queries.get_forensics_runs() == []
        assert queries.get_recent_events() == []
        assert queries.get_baseline_PF("bot-a") is None
        assert queries.episode_id_exists("ep-1") is False
