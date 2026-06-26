"""Tests for heartbeat_writer.py path resolution.

These tests verify that heartbeat_writer.py:
1. Uses /opt/data/profiles/orchestrator/state/ as default DB path
2. Respects HERMES_HEARTBEAT_DB_PATH env var override
3. Fails clearly when DB path is unwritable

Run with: pytest tests/test_heartbeat_writer_paths.py -v
"""

import os
import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest


# ============================================================
# DB_PATH resolution tests
# ============================================================

def test_default_db_path_is_writable():
    """Default DB_PATH must be under /opt/data/profiles/orchestrator/state/."""
    pytest.importorskip("orchestrator.scripts.heartbeat_writer")
    from orchestrator.scripts.heartbeat_writer import DB_PATH

    path_str = str(DB_PATH)
    assert "/opt/data/profiles/orchestrator/state/" in path_str, (
        f"DB_PATH should be in canonical state dir, got: {path_str}"
    )
    assert "/home/hermes/projects/trading/" not in path_str, (
        f"DB_PATH must not be in project tree (read-only mount): {path_str}"
    )


def test_default_db_path_detection():
    """Without env var, DB_PATH must be the canonical default."""
    # Unset any existing override
    old_val = os.environ.pop("HERMES_HEARTBEAT_DB_PATH", None)
    try:
        # Fresh import to pick up clean env
        import importlib
        import orchestrator.scripts.heartbeat_writer as hw
        importlib.reload(hw)

        assert "hermes_heartbeat.sqlite" in str(hw.DB_PATH)
        assert hw.DB_PATH.parent.name == "state"
    finally:
        if old_val is not None:
            os.environ["HERMES_HEARTBEAT_DB_PATH"] = old_val


def test_env_var_override():
    """HERMES_HEARTBEAT_DB_PATH must override the default path."""
    old_val = os.environ.pop("HERMES_HEARTBEAT_DB_PATH", None)
    try:
        os.environ["HERMES_HEARTBEAT_DB_PATH"] = "/tmp/test_custom_heartbeat.sqlite"
        import importlib
        import orchestrator.scripts.heartbeat_writer as hw
        importlib.reload(hw)

        assert str(hw.DB_PATH) == "/tmp/test_custom_heartbeat.sqlite"
    finally:
        if old_val is not None:
            os.environ["HERMES_HEARTBEAT_DB_PATH"] = old_val
        else:
            os.environ.pop("HERMES_HEARTBEAT_DB_PATH", None)


def test_db_path_creation():
    """init_db() must create the parent directory and the database file."""
    pytest.importorskip("orchestrator.scripts.heartbeat_writer")

    with tempfile.TemporaryDirectory() as tmp:
        custom_path = Path(tmp) / "subdir" / "test_heartbeat.sqlite"

        os.environ["HERMES_HEARTBEAT_DB_PATH"] = str(custom_path)
        try:
            import importlib
            import orchestrator.scripts.heartbeat_writer as hw
            importlib.reload(hw)

            conn = hw.init_db()
            try:
                assert custom_path.exists(), f"DB file not created at {custom_path}"
                # Verify table exists
                cursor = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='heartbeats'"
                )
                assert len(cursor.fetchall()) == 1
            finally:
                conn.close()
        finally:
            os.environ.pop("HERMES_HEARTBEAT_DB_PATH", None)


# ============================================================
# Schema tests
# ============================================================

def test_heartbeat_schema_columns():
    """The heartbeats table must have expected columns."""
    pytest.importorskip("orchestrator.scripts.heartbeat_writer")

    with tempfile.TemporaryDirectory() as tmp:
        custom_path = Path(tmp) / "test_schema.sqlite"
        os.environ["HERMES_HEARTBEAT_DB_PATH"] = str(custom_path)
        try:
            import importlib
            import orchestrator.scripts.heartbeat_writer as hw
            importlib.reload(hw)

            conn = hw.init_db()
            try:
                cursor = conn.execute("PRAGMA table_info(heartbeats)")
                columns = {row[1] for row in cursor.fetchall()}
                required = {"id", "timestamp", "bot_name", "container_name",
                           "api_port", "api_ok", "status", "open_trades", "raw_json"}
                missing = required - columns
                assert not missing, f"Missing columns: {missing}"
            finally:
                conn.close()
        finally:
            os.environ.pop("HERMES_HEARTBEAT_DB_PATH", None)


# ============================================================
# Error handling tests
# ============================================================

def test_init_db_fails_on_unwritable_path():
    """init_db() must raise an exception on unwritable path."""
    pytest.importorskip("orchestrator.scripts.heartbeat_writer")

    with tempfile.TemporaryDirectory() as tmp:
        # Create a read-only directory
        ro_dir = Path(tmp) / "readonly"
        ro_dir.mkdir()
        ro_dir.chmod(0o444)
        unwritable_path = ro_dir / "test.sqlite"

        os.environ["HERMES_HEARTBEAT_DB_PATH"] = str(unwritable_path)
        try:
            import importlib
            import orchestrator.scripts.heartbeat_writer as hw
            importlib.reload(hw)

            with pytest.raises((PermissionError, OSError, sqlite3.OperationalError)):
                hw.init_db()
        finally:
            os.environ.pop("HERMES_HEARTBEAT_DB_PATH", None)
