from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import shadowlock.shadowlock_indexer as indexer


def _configure(tmp_path: Path, monkeypatch) -> tuple[Path, Path, Path]:
    base = tmp_path / "shadowlock"
    logs = base / "logs"
    state = base / "state"
    db = state / "shadowlock.db"
    monkeypatch.setattr(indexer, "LOGS_DIR", logs)
    monkeypatch.setattr(indexer, "STATE_PATH", state / "indexer.state")
    monkeypatch.setattr(indexer, "DB_PATH", db)
    logs.mkdir(parents=True, exist_ok=True)
    state.mkdir(parents=True, exist_ok=True)
    return base, logs, state


def _jsonl_line(event: dict[str, object]) -> str:
    return json.dumps(event, sort_keys=True)


class TestShadowlockIndexerContracts:
    def test_rebuild_indexes_valid_rows_and_skips_corrupt_lines(self, tmp_path: Path, monkeypatch) -> None:
        _base, logs, _state = _configure(tmp_path, monkeypatch)
        jsonl = logs / "2026" / "06" / "15.jsonl"
        jsonl.parent.mkdir(parents=True, exist_ok=True)
        jsonl.write_text(
            "\n".join(
                [
                    _jsonl_line({
                        "schema_version": "1.0",
                        "event_type": "self_improvement_episode",
                        "episode_id": "ep-1",
                        "target_bot": "bot-a",
                        "timestamp_utc": "2026-06-15T12:00:00Z",
                        "outcome": "pass",
                        "PF": 1.2,
                    }),
                    "{not-json",
                    _jsonl_line({
                        "schema_version": "1.0",
                        "event_type": "forensics_run_complete",
                        "run_id": "run-1",
                        "timestamp_utc": "2026-06-15T12:01:00Z",
                        "bots_analyzed": ["bot-a"],
                        "candidates_found": 1,
                        "top_candidate_bot": "bot-a",
                        "top_candidate_priority_score": 0.99,
                    }),
                ]
            )
        )

        indexer.rebuild_index()

        conn = sqlite3.connect(str(indexer.DB_PATH))
        try:
            cur = conn.cursor()
            assert cur.execute("SELECT COUNT(*) FROM shadowlock_events").fetchone()[0] == 2
            assert cur.execute("SELECT COUNT(*) FROM episodes").fetchone()[0] == 1
            assert cur.execute("SELECT COUNT(*) FROM forensics_runs").fetchone()[0] == 1
            row = cur.execute("SELECT episode_id, target_bot, outcome FROM episodes").fetchone()
            assert row == ("ep-1", "bot-a", "pass")
        finally:
            conn.close()

    def test_update_index_uses_state_and_appends_only_new_file(self, tmp_path: Path, monkeypatch) -> None:
        _base, logs, state = _configure(tmp_path, monkeypatch)
        first = logs / "2026" / "06" / "14.jsonl"
        second = logs / "2026" / "06" / "15.jsonl"
        first.parent.mkdir(parents=True, exist_ok=True)
        first.write_text(
            _jsonl_line({
                "schema_version": "1.0",
                "event_type": "self_improvement_episode",
                "episode_id": "ep-1",
                "target_bot": "bot-a",
                "timestamp_utc": "2026-06-14T12:00:00Z",
                "outcome": "pass",
                "PF": 1.1,
            })
            + "\n"
        )

        indexer.rebuild_index()
        indexer.STATE_PATH.write_text(f"{first}:{1}")

        second.write_text(
            _jsonl_line({
                "schema_version": "1.0",
                "event_type": "self_improvement_episode",
                "episode_id": "ep-2",
                "target_bot": "bot-a",
                "timestamp_utc": "2026-06-15T12:00:00Z",
                "outcome": "fail",
                "PF": 0.5,
            })
            + "\n"
        )

        total = indexer.update_index()
        assert total == 1

        conn = sqlite3.connect(str(indexer.DB_PATH))
        try:
            cur = conn.cursor()
            assert cur.execute("SELECT COUNT(*) FROM shadowlock_events").fetchone()[0] == 2
            assert cur.execute("SELECT COUNT(*) FROM episodes").fetchone()[0] == 2
            assert indexer.STATE_PATH.read_text().startswith(str(second))
        finally:
            conn.close()
