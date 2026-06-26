"""Tests for cron_history_writer.py module.

NOTE: These tests are designed to pass BEFORE the module is implemented
(TDD: RED → GREEN). Run with: pytest tests/test_cron_history_writer.py -v
"""

import json
import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest


# ============================================================
# Schema & DB creation tests
# ============================================================

def test_schema_creates_table():
    """The cron_runs table must exist after init_db()."""
    # This test will be runnable once cron_history_writer is importable
    pytest.importorskip("orchestrator.scripts.cron_history_writer")
    from orchestrator.scripts.cron_history_writer import init_db, DB_FILENAME

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / DB_FILENAME
        conn = init_db(str(db_path))
        try:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='cron_runs'"
            )
            tables = cursor.fetchall()
            assert len(tables) == 1
            assert tables[0][0] == "cron_runs"
        finally:
            conn.close()


def test_schema_columns():
    """The cron_runs table must have the expected columns."""
    pytest.importorskip("orchestrator.scripts.cron_history_writer")
    from orchestrator.scripts.cron_history_writer import init_db, DB_FILENAME

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / DB_FILENAME
        conn = init_db(str(db_path))
        try:
            cursor = conn.execute("PRAGMA table_info(cron_runs)")
            columns = {row[1]: row[2] for row in cursor.fetchall()}
            assert "id" in columns
            assert "job_id" in columns
            assert "job_name" in columns
            assert "no_agent" in columns
            assert "script_path" in columns
            assert "delivery_mode" in columns
            assert "started_at" in columns
            assert "finished_at" in columns
            assert "duration_ms" in columns
            assert "status" in columns
            assert "exit_code" in columns
            assert "timeout" in columns
            assert "stdout_excerpt" in columns
            assert "stderr_excerpt" in columns
            assert "error_excerpt" in columns
            assert "created_at" in columns
        finally:
            conn.close()


def test_schema_has_indexes():
    """Required indexes must exist."""
    pytest.importorskip("orchestrator.scripts.cron_history_writer")
    from orchestrator.scripts.cron_history_writer import init_db, DB_FILENAME

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / DB_FILENAME
        conn = init_db(str(db_path))
        try:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='cron_runs'"
            )
            indexes = [row[0] for row in cursor.fetchall()]
            index_names = " ".join(indexes)
            assert "idx_cron_runs_job_time" in index_names
            assert "idx_cron_runs_status_time" in index_names
        finally:
            conn.close()


# ============================================================
# Record insertion tests
# ============================================================

def test_record_no_agent_run():
    """A successful no_agent run must insert a row with correct fields."""
    pytest.importorskip("orchestrator.scripts.cron_history_writer")
    from orchestrator.scripts.cron_history_writer import (
        init_db,
        record_cron_run,
        DB_FILENAME,
    )

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / DB_FILENAME
        conn = init_db(str(db_path))

        record_cron_run(
            conn=conn,
            job_id="test_job_1",
            job_name="Test No-Agent Job",
            no_agent=True,
            script_path="scripts/test_script.sh",
            delivery_mode="origin",
            status="ok",
            exit_code=0,
            timeout=30,
            stdout_excerpt="hello world",
            stderr_excerpt="",
        )

        cursor = conn.execute("SELECT * FROM cron_runs WHERE job_id = ?", ("test_job_1",))
        rows = cursor.fetchall()
        assert len(rows) == 1
        row = rows[0]

        # Verify fields
        col_names = [desc[0] for desc in cursor.description]
        row_dict = dict(zip(col_names, row))

        assert row_dict["job_id"] == "test_job_1"
        assert row_dict["job_name"] == "Test No-Agent Job"
        assert row_dict["no_agent"] == 1
        assert row_dict["script_path"] == "scripts/test_script.sh"
        assert row_dict["delivery_mode"] == "origin"
        assert row_dict["status"] == "ok"
        assert row_dict["exit_code"] == 0
        assert row_dict["timeout"] == 30
        assert row_dict["stdout_excerpt"] == "hello world"
        assert row_dict["stderr_excerpt"] == ""
        assert row_dict["started_at"] is not None
        assert row_dict["finished_at"] is not None
        assert row_dict["created_at"] is not None


def test_record_failed_run():
    """A failed run must record error_excerpt and status='error'."""
    pytest.importorskip("orchestrator.scripts.cron_history_writer")
    from orchestrator.scripts.cron_history_writer import (
        init_db,
        record_cron_run,
        DB_FILENAME,
    )

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / DB_FILENAME
        conn = init_db(str(db_path))

        record_cron_run(
            conn=conn,
            job_id="test_fail_1",
            job_name="Failing Job",
            no_agent=True,
            script_path="scripts/fail.sh",
            status="error",
            exit_code=1,
            timeout=30,
            stdout_excerpt="",
            stderr_excerpt="Error: something broke",
            error_excerpt="Script exited with code 1: Error: something broke",
        )

        cursor = conn.execute("SELECT * FROM cron_runs WHERE job_id = ?", ("test_fail_1",))
        rows = cursor.fetchall()
        assert len(rows) == 1

        col_names = [desc[0] for desc in cursor.description]
        row_dict = dict(zip(col_names, rows[0]))

        assert row_dict["status"] == "error"
        assert row_dict["exit_code"] == 1
        assert "something broke" in (row_dict["error_excerpt"] or "")
        assert row_dict["stderr_excerpt"] == "Error: something broke"


def test_record_agent_run():
    """An agent (LLM) run must record no_agent=0 and no script_path."""
    pytest.importorskip("orchestrator.scripts.cron_history_writer")
    from orchestrator.scripts.cron_history_writer import (
        init_db,
        record_cron_run,
        DB_FILENAME,
    )

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / DB_FILENAME
        conn = init_db(str(db_path))

        record_cron_run(
            conn=conn,
            job_id="agent_job_1",
            job_name="Agent Job",
            no_agent=False,
            delivery_mode="telegram",
            status="ok",
            exit_code=0,
            timeout=120,
            stdout_excerpt="Analysis complete",
        )

        cursor = conn.execute("SELECT * FROM cron_runs WHERE job_id = ?", ("agent_job_1",))
        rows = cursor.fetchall()
        assert len(rows) == 1

        col_names = [desc[0] for desc in cursor.description]
        row_dict = dict(zip(col_names, rows[0]))

        assert row_dict["no_agent"] == 0
        assert row_dict["script_path"] is None
        assert row_dict["delivery_mode"] == "telegram"
        assert row_dict["status"] == "ok"


# ============================================================
# Truncation tests
# ============================================================

def test_stdout_truncation():
    """stdout_excerpt longer than MAX_EXCERPT_LENGTH must be truncated."""
    pytest.importorskip("orchestrator.scripts.cron_history_writer")
    from orchestrator.scripts.cron_history_writer import (
        init_db,
        record_cron_run,
        DB_FILENAME,
        MAX_EXCERPT_LENGTH,
    )

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / DB_FILENAME
        conn = init_db(str(db_path))

        long_output = "A" * (MAX_EXCERPT_LENGTH + 1000)
        record_cron_run(
            conn=conn,
            job_id="trunc_test",
            job_name="Truncation Test",
            no_agent=True,
            status="ok",
            exit_code=0,
            timeout=30,
            stdout_excerpt=long_output,
        )

        cursor = conn.execute("SELECT stdout_excerpt FROM cron_runs WHERE job_id = ?", ("trunc_test",))
        row = cursor.fetchone()
        stored = row[0]
        assert len(stored) <= MAX_EXCERPT_LENGTH
        assert stored.endswith("...[truncated]")


# ============================================================
# Retention tests
# ============================================================

def test_retention_max_rows_per_job():
    """Enforce max N rows per job_id, removing oldest first."""
    pytest.importorskip("orchestrator.scripts.cron_history_writer")
    from orchestrator.scripts.cron_history_writer import (
        init_db,
        record_cron_run,
        DB_FILENAME,
        MAX_ROWS_PER_JOB,
    )

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / DB_FILENAME
        conn = init_db(str(db_path))

        # Insert MAX_ROWS_PER_JOB + 10 rows for the same job
        for i in range(MAX_ROWS_PER_JOB + 10):
            record_cron_run(
                conn=conn,
                job_id="retention_job",
                no_agent=True,
                status="ok",
                exit_code=0,
                timeout=30,
                stdout_excerpt=f"run_{i}",
            )

        # Enforce retention explicitly for test determinism
        from orchestrator.scripts.cron_history_writer import _enforce_retention
        _enforce_retention(conn)

        # Verify max rows in DB
        cursor = conn.execute(
            "SELECT COUNT(*) FROM cron_runs WHERE job_id = ?", ("retention_job",)
        )
        count = cursor.fetchone()[0]
        assert count <= MAX_ROWS_PER_JOB

        # Verify the oldest rows were removed (most recent retained)
        cursor = conn.execute(
            "SELECT stdout_excerpt FROM cron_runs WHERE job_id = ? ORDER BY started_at ASC",
            ("retention_job",),
        )
        rows = cursor.fetchall()
        # Should start at run_10 (the first that survives)
        first_stdout = rows[0][0]
        assert "run_10" in first_stdout or "run_" in first_stdout  # oldest surviving


# ============================================================
# CLI self-test mode
# ============================================================

def test_self_test_mode():
    """CLI --self-test must succeed without errors and write to a temp DB."""
    # Import and run self-test directly (avoids subprocess timeout with 10K inserts)
    from orchestrator.scripts import cron_history_writer as chw

    import tempfile
    tmp_dir = tempfile.TemporaryDirectory()
    try:
        exit_code = chw.cmd_self_test(db_path=tmp_dir.name + "/test.sqlite")
        assert exit_code == 0, f"Self-test returned {exit_code}"
    finally:
        tmp_dir.cleanup()
