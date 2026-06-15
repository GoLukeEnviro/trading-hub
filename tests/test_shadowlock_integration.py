"""Safe Shadowlock integration smoke tests using temporary data only."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SHADOWLOCK_DIR = Path(__file__).resolve().parent.parent / "shadowlock"


class TestShadowlockIntegration:
    def test_indexer_compile(self) -> None:
        import py_compile

        indexer = SHADOWLOCK_DIR / "shadowlock_indexer.py"
        py_compile.compile(str(indexer), doraise=True)

    def test_queries_compile(self) -> None:
        import py_compile

        queries = SHADOWLOCK_DIR / "shadowlock_indexer_queries.py"
        py_compile.compile(str(queries), doraise=True)

    def test_writer_round_trip_on_temp_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import shadowlock.shadowlock_writer as writer

        base = tmp_path / "shadowlock"
        for sub in writer.REQUIRED_SUBDIRS:
            (base / sub).mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(writer, "_trigger_indexer", lambda: None)

        inbox = base / "inbox" / "smoke.json"
        inbox.write_text(
            json.dumps(
                {
                    "schema_version": writer.SCHEMA_VERSION,
                    "event_type": "default",
                    "timestamp_utc": "2026-06-15T12:00:00Z",
                    "bot_name": "smoke-bot",
                }
            )
        )

        assert writer.process_inbox_file(str(base), str(inbox)) is True
        log_file = base / "logs" / "2026" / "06" / "15.jsonl"
        assert log_file.exists()
        assert writer.read_sequence(str(base), "smoke-bot") == 1
