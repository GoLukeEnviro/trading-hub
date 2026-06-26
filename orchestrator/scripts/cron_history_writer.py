#!/usr/bin/env python3
"""
cron_history_writer.py

Persists one row per cron execution to a SQLite database, providing
multi-run execution history for both no_agent and agent/LLM cron jobs.

Features:
  - SQLite-backed cron_runs table with schema migration
  - Secret redaction before persistence
  - Size-capped stdout/stderr/error excerpts
  - Retention policy (max rows per job, max age)
  - Best-effort: never raises, never blocks cron execution
  - CLI --self-test mode for validation

Canonical DB path:
  /opt/data/profiles/orchestrator/state/cron_history.sqlite

Usage as module:
  from cron_history_writer import record_cron_run, init_db
  conn = init_db()
  record_cron_run(conn=conn, job_id="...", ...)

Usage as CLI:
  python3 cron_history_writer.py --self-test
  python3 cron_history_writer.py --dry-run
"""

import json
import os
import re
import sqlite3
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DB_FILENAME = "cron_history.sqlite"

# Canonical state directory (always writable in cron runtime)
STATE_DIR = Path(os.environ.get(
    "HERMES_STATE_DIR",
    "/opt/data/profiles/orchestrator/state"
))

DEFAULT_DB_PATH = STATE_DIR / DB_FILENAME

# Override via env var for testing
DB_PATH = Path(os.environ.get("HERMES_CRON_HISTORY_DB", str(DEFAULT_DB_PATH)))

# Excerpt size cap (characters)
MAX_EXCERPT_LENGTH = 4096

# Retention: max rows per job_id
MAX_ROWS_PER_JOB = 10000

# Retention: max age in days
MAX_AGE_DAYS = 90

SCHEMA = """
CREATE TABLE IF NOT EXISTS cron_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id          TEXT NOT NULL,
    job_name        TEXT,
    no_agent        INTEGER,
    script_path     TEXT,
    delivery_mode   TEXT,
    started_at      TEXT NOT NULL,
    finished_at     TEXT,
    duration_ms     INTEGER,
    status          TEXT NOT NULL,
    exit_code       INTEGER,
    timeout         INTEGER,
    stdout_excerpt  TEXT,
    stderr_excerpt  TEXT,
    error_excerpt   TEXT,
    created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_cron_runs_job_time
    ON cron_runs(job_id, started_at);

CREATE INDEX IF NOT EXISTS idx_cron_runs_status_time
    ON cron_runs(status, started_at);
"""

# ---------------------------------------------------------------------------
# Redaction helpers
# ---------------------------------------------------------------------------

_REDACTION_PATTERNS = [
    # API keys and tokens (alphanumeric, 20-60 chars)
    (re.compile(r'(?i)(api[_-]?key|apikey)\s*[:=]\s*["\']?[a-z0-9_\-]{20,60}["\']?'),
     r'\1=***REDACTED***'),
    # Bearer/Authorization tokens
    (re.compile(r'(?i)(bearer|token|auth)\s+[a-z0-9_\-\.]{20,200}'),
     r'\1 ***REDACTED***'),
    # Private keys (BEGIN ... KEY)
    (re.compile(r'-----BEGIN\s+.+?KEY-----'),
     '-----BEGIN REDACTED KEY-----'),
    # Password fields in JSON
    (re.compile(r'(?i)"password"\s*:\s*"[^"]{3,}"'),
     '"password": "***REDACTED***"'),
    # Telegram bot tokens (botNNNN:...)
    (re.compile(r'\d{7,10}:[a-z0-9_-]{30,45}'),
     '***REDACTED***'),
    # URLs with credentials
    (re.compile(r'https?://[^:@\s]+:[^@\s]+@'),
     'https://***:***@'),
]


def redact_output(text: str) -> str:
    """Redact likely secrets from output text.

    Returns the redacted string. Returns empty string if input is None/empty.
    """
    if not text:
        return text or ""
    result = text
    for pattern, replacement in _REDACTION_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


def _truncate(text: str, max_len: int = MAX_EXCERPT_LENGTH) -> str:
    """Truncate text to max_len with a suffix indicator.

    Returns the original text if within limit.
    """
    if not text:
        return text or ""
    if len(text) <= max_len:
        return text
    return text[: max_len - len("...[truncated]")] + "...[truncated]"


# ---------------------------------------------------------------------------
# Database functions
# ---------------------------------------------------------------------------

def init_db(db_path: str | Path | None = None) -> sqlite3.Connection:
    """Initialize the cron history database.

    Creates parent directory if needed, applies schema, and enables WAL mode
    for safe concurrent access.

    Args:
        db_path: Override path. Defaults to DB_PATH.

    Returns:
        sqlite3.Connection

    Raises:
        sqlite3.Error: On schema/connection failure.
        PermissionError: On unwritable parent directory.
    """
    path = Path(db_path) if db_path else DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def _enforce_retention(conn: sqlite3.Connection) -> None:
    """Remove old rows per retention policy.

    - Removes rows older than MAX_AGE_DAYS.
    - Removes oldest rows per job_id exceeding MAX_ROWS_PER_JOB.
    """
    now = datetime.now(timezone.utc).isoformat()

    # Age-based retention
    conn.execute(
        """
        DELETE FROM cron_runs
        WHERE created_at < datetime(?, '-' || ? || ' days')
        """,
        (now, str(MAX_AGE_DAYS)),
    )

    # Per-job row cap: keep only the MAX_ROWS_PER_JOB most recent per job_id
    conn.execute(
        """
        DELETE FROM cron_runs
        WHERE id NOT IN (
            SELECT id FROM (
                SELECT id, row_number() OVER (
                    PARTITION BY job_id ORDER BY started_at DESC
                ) AS rn
                FROM cron_runs
            ) WHERE rn <= ?
        )
        """,
        (MAX_ROWS_PER_JOB,),
    )

    conn.commit()


def record_cron_run(
    conn: sqlite3.Connection | None = None,
    *,
    job_id: str,
    job_name: str | None = None,
    no_agent: bool = False,
    script_path: str | None = None,
    delivery_mode: str | None = None,
    status: str = "ok",
    exit_code: int | None = None,
    timeout: int | None = None,
    started_at: str | None = None,
    finished_at: str | None = None,
    stdout_excerpt: str | None = None,
    stderr_excerpt: str | None = None,
    error_excerpt: str | None = None,
) -> bool:
    """Record a single cron execution in the history database.

    This is best-effort: never raises, never blocks cron execution.
    Returns True on success, False on failure (logged to stderr).

    Args:
        conn: SQLite connection (created by init_db() if None).
        job_id: Unique job identifier.
        job_name: Human-friendly job name.
        no_agent: True if no_agent (script-only) job.
        script_path: Path to the script (for no_agent jobs).
        delivery_mode: Delivery target (origin, telegram, local, etc.).
        status: 'ok' or 'error'.
        exit_code: Script exit code.
        timeout: Script timeout in seconds.
        started_at: ISO timestamp of start. Default: now.
        finished_at: ISO timestamp of finish. Default: now.
        stdout_excerpt: Excerpt of stdout (redacted and truncated).
        stderr_excerpt: Excerpt of stderr (redacted and truncated).
        error_excerpt: Error message (redacted and truncated).

    Returns:
        True if inserted successfully, False on error.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    started = started_at or now_iso
    finished = finished_at or now_iso

    # Calculate duration in ms
    duration_ms = None
    try:
        if started_at and finished_at:
            t0 = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
            t1 = datetime.fromisoformat(finished_at.replace("Z", "+00:00"))
            duration_ms = int((t1 - t0).total_seconds() * 1000)
    except (ValueError, TypeError):
        pass

    # Redact and truncate excerpts
    stdout_clean = _truncate(redact_output(stdout_excerpt)) if stdout_excerpt is not None else None
    stderr_clean = _truncate(redact_output(stderr_excerpt)) if stderr_excerpt is not None else None
    error_clean = _truncate(redact_output(error_excerpt)) if error_excerpt is not None else None

    try:
        if conn is None:
            conn = init_db()
            should_close = True
        else:
            should_close = False

        conn.execute(
            """
            INSERT INTO cron_runs
                (job_id, job_name, no_agent, script_path, delivery_mode,
                 started_at, finished_at, duration_ms, status, exit_code,
                 timeout, stdout_excerpt, stderr_excerpt, error_excerpt, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                job_name,
                1 if no_agent else 0,
                script_path,
                delivery_mode,
                started,
                finished,
                duration_ms,
                status,
                exit_code,
                timeout,
                stdout_clean,
                stderr_clean,
                error_clean,
                now_iso,
            ),
        )
        conn.commit()

        # Enforce retention periodically (every 100 inserts per job_id)
        # to avoid O(n^2) overhead on bulk inserts.
        cursor = conn.execute(
            "SELECT COUNT(*) FROM cron_runs WHERE job_id = ?", (job_id,)
        )
        row_count = cursor.fetchone()[0]
        if row_count > 0 and row_count % 100 == 0:
            _enforce_retention(conn)

        if should_close:
            conn.close()
        return True

    except Exception as exc:
        msg = f"[cron_history_writer] Failed to record run for job {job_id}: {exc}"
        print(msg, file=sys.stderr)
        return False


# ---------------------------------------------------------------------------
# Scheduler integration helper
# ---------------------------------------------------------------------------

def run_with_history(
    job: dict,
    *,
    no_agent: bool = False,
    status: str = "ok",
    exit_code: int | None = None,
    stdout_text: str | None = None,
    stderr_text: str | None = None,
    error_text: str | None = None,
    started_at: str | None = None,
    finished_at: str | None = None,
) -> bool:
    """Convenience wrapper that records history for a job dict from the scheduler.

    Extracts fields from the job dict automatically:
      - job_id = job["id"]
      - job_name = job.get("name") or job.get("prompt")
      - script_path = job.get("script")
      - delivery_mode from job's deliver config
      - timeout = job's script timeout

    This is designed to be called from the scheduler's _process_job() after
    the job completes. Best-effort only.

    Args:
        job: Scheduler job dict.
        no_agent: True if no_agent job.
        status: 'ok' or 'error'.
        exit_code: Script exit code.
        stdout_text: Raw stdout output (will be redacted/truncated).
        stderr_text: Raw stderr output (will be redacted/truncated).
        error_text: Error message (will be redacted/truncated).
        started_at: ISO timestamp of start.
        finished_at: ISO timestamp of finish.

    Returns:
        True if recorded successfully, False on error.
    """
    job_id = job.get("id", "?")
    job_name = str(job.get("name") or job.get("prompt") or job_id)

    # Determine delivery mode
    delivery = job.get("deliver") or "origin"
    if isinstance(delivery, dict):
        delivery = delivery.get("mode", "origin")

    # Script timeout
    timeout = None
    schedule = job.get("schedule", {}) or {}
    if isinstance(schedule, dict) and schedule.get("timeout"):
        timeout = schedule["timeout"]

    return record_cron_run(
        job_id=job_id,
        job_name=job_name,
        no_agent=no_agent,
        script_path=job.get("script"),
        delivery_mode=str(delivery) if delivery else None,
        status=status,
        exit_code=exit_code,
        timeout=timeout,
        started_at=started_at,
        finished_at=finished_at,
        stdout_excerpt=stdout_text,
        stderr_excerpt=stderr_text,
        error_excerpt=error_text,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def cmd_self_test(db_path: str | None = None) -> int:
    """Run self-test against a temporary or specified database."""
    if db_path:
        test_db = Path(db_path)
        test_db.parent.mkdir(parents=True, exist_ok=True)
        tmp_dir = None
    else:
        tmp_dir = tempfile.TemporaryDirectory()
        test_db = Path(tmp_dir.name) / DB_FILENAME

    print(f"[cron_history_writer] Self-test DB: {test_db}")
    conn = init_db(test_db)

    # Test 1: Schema creation
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='cron_runs'"
    )
    assert len(cursor.fetchall()) == 1, "cron_runs table not created"
    print("[OK] Schema creation")

    # Test 2: Insert a successful no_agent run
    t0 = datetime.now(timezone.utc).isoformat()
    ok = record_cron_run(
        conn=conn,
        job_id="self_test_no_agent",
        job_name="Self-Test No-Agent",
        no_agent=True,
        script_path="scripts/test.sh",
        delivery_mode="origin",
        status="ok",
        exit_code=0,
        timeout=30,
        stdout_excerpt="Self-test OK",
        started_at=t0,
        finished_at=datetime.now(timezone.utc).isoformat(),
    )
    assert ok, "Failed to record no_agent run"
    print("[OK] Insert no_agent run")

    # Test 3: Insert a failed run
    ok = record_cron_run(
        conn=conn,
        job_id="self_test_fail",
        job_name="Self-Test Fail",
        no_agent=True,
        status="error",
        exit_code=1,
        timeout=30,
        error_excerpt="Script exited with code 1",
        started_at=t0,
    )
    assert ok, "Failed to record failed run"
    print("[OK] Insert failed run")

    # Test 4: Verify rows
    cursor = conn.execute("SELECT COUNT(*) FROM cron_runs")
    count = cursor.fetchone()[0]
    assert count >= 2, f"Expected >= 2 rows, got {count}"
    print(f"[OK] Row count: {count}")

    # Test 5: Secret redaction
    ok = record_cron_run(
        conn=conn,
        job_id="self_test_redact",
        no_agent=True,
        status="ok",
        exit_code=0,
        stdout_excerpt='api_key = "abcdef1234567890abcdef1234567890abcdef12"',
        started_at=t0,
    )
    assert ok, "Failed redaction test insert"
    cursor = conn.execute(
        "SELECT stdout_excerpt FROM cron_runs WHERE job_id = ?",
        ("self_test_redact",),
    )
    row = cursor.fetchone()
    assert row is not None
    stored = row[0]
    assert "***REDACTED***" in stored, f"Secret not redacted: {stored}"
    print("[OK] Secret redaction")

    # Test 6: Retention — inserts many rows, then enforces retention
    for i in range(MAX_ROWS_PER_JOB + 5):
        record_cron_run(
            conn=conn,
            job_id="self_test_retention",
            no_agent=True,
            status="ok",
            exit_code=0,
            stdout_excerpt=f"run_{i}",
            started_at=datetime.now(timezone.utc).isoformat(),
        )

    # Explicitly enforce retention after bulk insert
    conn.execute(
        "DELETE FROM cron_runs WHERE id NOT IN ("
        "SELECT id FROM ("
        "SELECT id, row_number() OVER ("
        "PARTITION BY job_id ORDER BY started_at DESC"
        ") AS rn FROM cron_runs"
        ") WHERE rn <= ?"
        ")", (MAX_ROWS_PER_JOB,)
    )
    conn.commit()
    cursor = conn.execute(
        "SELECT COUNT(*) FROM cron_runs WHERE job_id = ?",
        ("self_test_retention",),
    )
    ret_count = cursor.fetchone()[0]
    assert ret_count <= MAX_ROWS_PER_JOB, (
        f"Retention failed: {ret_count} rows > {MAX_ROWS_PER_JOB}"
    )
    print(f"[OK] Retention: {ret_count} rows ≤ {MAX_ROWS_PER_JOB}")

    conn.close()
    if tmp_dir:
        tmp_dir.cleanup()

    print("\n[cron_history_writer] SELF-TEST PASSED")
    return 0


def main() -> int:
    """CLI entry point."""
    args = [a for a in sys.argv[1:] if a]
    if not args:
        print("Usage: cron_history_writer.py --self-test [--db PATH]", file=sys.stderr)
        print("       cron_history_writer.py --dry-run", file=sys.stderr)
        return 1

    if "--self-test" in args:
        db_idx = None
        if "--db" in args:
            db_idx = args.index("--db") + 1
        db_path = args[db_idx] if db_idx and db_idx < len(args) else None
        return cmd_self_test(db_path)

    if "--dry-run" in args:
        print("[cron_history_writer] Dry-run mode: no database writes performed")
        print(f"[cron_history_writer] Canonical DB path: {DB_PATH}")
        print(f"[cron_history_writer] State dir: {STATE_DIR}")
        print(f"[cron_history_writer] MAX_EXCERPT_LENGTH: {MAX_EXCERPT_LENGTH}")
        print(f"[cron_history_writer] MAX_ROWS_PER_JOB: {MAX_ROWS_PER_JOB}")
        print(f"[cron_history_writer] MAX_AGE_DAYS: {MAX_AGE_DAYS}")
        return 0

    print(f"Unknown args: {args}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
