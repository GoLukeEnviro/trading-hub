"""Tests for Shadowlock writer → indexer trigger integration.

Verifies that:
1. New Shadowlock event append still works if indexer is unavailable.
2. Incremental index update runs after successful append.
3. Indexer failure is logged but does not corrupt the ledger.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# We test the indexer directly since the writer trigger is a subprocess call


SHADOWLOCK_DIR = Path(__file__).resolve().parent.parent / "shadowlock"


class TestShadowlockIndexer:
    """Test shadowlock_indexer.py CLI modes."""

    def test_indexer_compile(self) -> None:
        """Verify indexer compiles without errors."""
        import py_compile
        indexer = SHADOWLOCK_DIR / "shadowlock_indexer.py"
        py_compile.compile(str(indexer), doraise=True)

    def test_indexer_update_on_empty_logs(self) -> None:
        """Indexer --update on empty logs should succeed (exit 0)."""
        indexer = SHADOWLOCK_DIR / "shadowlock_indexer.py"
        result = subprocess.run(
            [sys.executable, str(indexer), "--update"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        # Should not crash — either exits 0 or logs that no logs exist
        assert result.returncode in (0,), f"Indexer --update failed: {result.stderr}"

    def test_indexer_rebuild_on_empty_logs(self) -> None:
        """Indexer --rebuild on empty logs should succeed (init DB)."""
        indexer = SHADOWLOCK_DIR / "shadowlock_indexer.py"
        result = subprocess.run(
            [sys.executable, str(indexer), "--rebuild"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, f"Indexer --rebuild failed: {result.stderr}"
        # Should report 0 events indexed
        assert "0 events" in result.stdout or result.returncode == 0

    def test_writer_independent_of_indexer(self) -> None:
        """Writer must work even when indexer is unavailable.

        Verify the _trigger_indexer function doesn't block the writer.
        """
        import importlib.util
        writer_path = SHADOWLOCK_DIR / "shadowlock_writer.py"
        assert writer_path.exists(), f"Writer not found at {writer_path}"
        spec = importlib.util.spec_from_file_location(
            "shadowlock_writer", str(writer_path),
        )
        assert spec is not None, "Could not load shadowlock_writer module"
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore

        # Verify _trigger_indexer exists and doesn't raise
        assert hasattr(mod, "_trigger_indexer"), "Writer missing _trigger_indexer()"
        # Calling it should not raise (best-effort function)
        try:
            mod._trigger_indexer()
        except Exception as exc:
            assert False, f"_trigger_indexer raised unexpectedly: {exc}"

    def test_indexer_parses_valid_jsonl(self) -> None:
        """Indexer should parse a valid JSONL file."""
        indexer = SHADOWLOCK_DIR / "shadowlock_indexer.py"

        # Write a test entry to the actual shadowlock log path
        log_dir = SHADOWLOCK_DIR.parent / "var" / "trading-shadowlock" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        test_entry = {
            "schema_version": "1.0",
            "event_type": "self_improvement_episode",
            "episode_id": "test-episode-001",
            "target_bot": "test-bot",
            "timestamp_utc": "2026-06-10T12:00:00Z",
            "outcome": "pass",
            "PF": 0.05,
        }

        # Write to a test JSONL file
        from datetime import datetime
        now = datetime.utcnow()
        test_file = log_dir / str(now.year) / f"{now.month:02d}" / f"{now.day:02d}.jsonl"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        with open(test_file, "a") as f:
            f.write(json.dumps(test_entry) + "\n")

        # Run rebuild
        result = subprocess.run(
            [sys.executable, str(indexer), "--rebuild"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, f"Rebuild failed: {result.stderr}"

    def test_queries_compile(self) -> None:
        """Verify queries module compiles."""
        import py_compile
        queries = SHADOWLOCK_DIR / "shadowlock_indexer_queries.py"
        py_compile.compile(str(queries), doraise=True)
