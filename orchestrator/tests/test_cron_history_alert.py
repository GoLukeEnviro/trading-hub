"""Tests for cron_history_alert.py.

All tests use ``tmp_path`` SQLite fixtures so they do not touch any
runtime file. The tests are deterministic: every test sets an
explicit ``now_utc`` for cooldown math.

Run with: pytest orchestrator/tests/test_cron_history_alert.py -v
"""

from __future__ import annotations

import datetime as _dt
import json
import sqlite3
from pathlib import Path

import pytest

from orchestrator.scripts.cron_history_alert import (
    Alert,
    ERROR_STATUSES,
    FALLBACK_BUCKET_SECONDS,
    RunResult,
    build_dedup_key,
    cap_alerts,
    classify_status,
    discover_columns,
    empty_state,
    fetch_new_rows,
    filter_by_cooldown,
    is_within_lookback,
    load_state,
    render_json,
    render_text,
    run_alert_pipeline,
    save_state,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_db(path: Path, rows: list[dict]) -> None:
    """Build a minimal cron_runs table with the same schema as the
    production writer. ``rows`` is a list of dicts with the columns we
    exercise; missing columns are filled with sensible defaults.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(str(path))
    try:
        conn.executescript(
            """
            CREATE TABLE cron_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL,
                job_name TEXT,
                no_agent INTEGER,
                script_path TEXT,
                delivery_mode TEXT,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                duration_ms INTEGER,
                status TEXT NOT NULL,
                exit_code INTEGER,
                timeout INTEGER,
                stdout_excerpt TEXT,
                stderr_excerpt TEXT,
                error_excerpt TEXT,
                created_at TEXT NOT NULL
            );
            CREATE INDEX idx_cron_runs_job_time ON cron_runs(job_id, started_at);
            CREATE INDEX idx_cron_runs_status_time ON cron_runs(status, started_at);
            """
        )
        for r in rows:
            conn.execute(
                """
                INSERT INTO cron_runs (
                    id, job_id, job_name, no_agent, script_path, delivery_mode,
                    started_at, finished_at, duration_ms, status, exit_code,
                    timeout, stdout_excerpt, stderr_excerpt, error_excerpt,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    r.get("id"),
                    r["job_id"],
                    r.get("job_name", ""),
                    r.get("no_agent", 0),
                    r.get("script_path", ""),
                    r.get("delivery_mode", ""),
                    r["started_at"],
                    r.get("finished_at"),
                    r.get("duration_ms"),
                    r["status"],
                    r.get("exit_code"),
                    r.get("timeout", 0),
                    r.get("stdout_excerpt"),
                    r.get("stderr_excerpt"),
                    r.get("error_excerpt"),
                    r.get("created_at", r["started_at"]),
                ),
            )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def empty_db(tmp_path: Path) -> Path:
    db = tmp_path / "cron_history.sqlite"
    _make_db(db, [])
    return db


@pytest.fixture
def ok_db(tmp_path: Path) -> Path:
    db = tmp_path / "cron_history.sqlite"
    rows = [
        {
            "id": 1,
            "job_id": "a47e1c73e102",
            "job_name": "heartbeat",
            "started_at": "2026-06-26T13:45:08+00:00",
            "status": "ok",
            "created_at": "2026-06-26T13:45:08+00:00",
        },
        {
            "id": 2,
            "job_id": "b47e1c73e103",
            "job_name": "watchdog",
            "started_at": "2026-06-26T13:46:08+00:00",
            "status": "ok",
            "created_at": "2026-06-26T13:46:08+00:00",
        },
    ]
    _make_db(db, rows)
    return db


@pytest.fixture
def mixed_db(tmp_path: Path) -> Path:
    """DB with a mix of ok / error / failed / timeout / weird rows.

    Each row has a distinct ``created_at`` that is 5 seconds AFTER its
    ``started_at`` (mimicking real writer behaviour where the row is
    written just after the run starts). This avoids the lookback filter
    accidentally dropping the row when ``created_at`` is a fixed
    sentinel that happens to fall outside the test window.
    """
    db = tmp_path / "cron_history.sqlite"
    rows = [
        {"id": 1, "job_id": "ok1", "started_at": "2026-06-26T13:00:00+00:00",
         "status": "ok", "created_at": "2026-06-26T13:00:05+00:00"},
        {"id": 2, "job_id": "err1", "started_at": "2026-06-26T13:01:00+00:00",
         "status": "error", "error_excerpt": "boom",
         "created_at": "2026-06-26T13:01:05+00:00"},
        {"id": 3, "job_id": "err1", "started_at": "2026-06-26T13:02:00+00:00",
         "status": "error", "error_excerpt": "boom",
         "created_at": "2026-06-26T13:02:05+00:00"},
        {"id": 4, "job_id": "err2", "started_at": "2026-06-26T13:03:00+00:00",
         "status": "failed", "error_excerpt": "different",
         "created_at": "2026-06-26T13:03:05+00:00"},
        {"id": 5, "job_id": "err3", "started_at": "2026-06-26T13:04:00+00:00",
         "status": "timeout", "created_at": "2026-06-26T13:04:05+00:00"},
        {"id": 6, "job_id": "warn1", "started_at": "2026-06-26T13:05:00+00:00",
         "status": "weird_status", "created_at": "2026-06-26T13:05:05+00:00"},
        {"id": 7, "job_id": "ok2", "started_at": "2026-06-26T13:06:00+00:00",
         "status": "ok", "created_at": "2026-06-26T13:06:05+00:00"},
    ]
    _make_db(db, rows)
    return db


@pytest.fixture
def fixed_now() -> _dt.datetime:
    return _dt.datetime(2026, 6, 26, 14, 0, 0, tzinfo=_dt.timezone.utc)


@pytest.fixture
def date_spaced_db(tmp_path: Path) -> Path:
    """DB with one row each from: 14 hours ago, 90 minutes ago, 30 minutes
    ago, and 5 minutes ago. Fixed_now is 2026-06-26T14:00 UTC.
    """
    db = tmp_path / "cron_history.sqlite"
    rows = [
        # OLD: 14 hours ago -> outside any reasonable lookback window
        {"id": 1, "job_id": "old_err", "started_at": "2026-06-26T00:00:00+00:00",
         "created_at": "2026-06-26T00:00:00+00:00", "status": "error",
         "error_excerpt": "old", "job_name": "old_err"},
        # 90 minutes ago -> outside 60-min lookback
        {"id": 2, "job_id": "med_err", "started_at": "2026-06-26T12:30:00+00:00",
         "created_at": "2026-06-26T12:30:00+00:00", "status": "error",
         "error_excerpt": "medium", "job_name": "med_err"},
        # 30 minutes ago -> inside 60-min lookback
        {"id": 3, "job_id": "fresh_err", "started_at": "2026-06-26T13:30:00+00:00",
         "created_at": "2026-06-26T13:30:00+00:00", "status": "error",
         "error_excerpt": "fresh", "job_name": "fresh_err"},
        # 5 minutes ago -> inside lookback
        {"id": 4, "job_id": "latest_err", "started_at": "2026-06-26T13:55:00+00:00",
         "created_at": "2026-06-26T13:55:00+00:00", "status": "failed",
         "error_excerpt": "latest", "job_name": "latest_err"},
    ]
    _make_db(db, rows)
    return db


# ---------------------------------------------------------------------------
# classify_status
# ---------------------------------------------------------------------------


class TestClassifyStatus:
    def test_ok(self):
        assert classify_status("ok") == ("ok", "ok")
        assert classify_status("OK") == ("ok", "ok")

    def test_error(self):
        assert classify_status("error") == ("error", "error")

    def test_failed(self):
        assert classify_status("FAILED") == ("error", "failed")

    def test_timeout(self):
        assert classify_status("timeout") == ("error", "timeout")

    def test_unknown_status_is_warning(self):
        sev, label = classify_status("frobnicate")
        assert sev == "warning"
        assert "frobnicate" in label

    def test_empty_is_warning(self):
        sev, label = classify_status("")
        assert sev == "warning"
        assert "empty" in label

    def test_none_is_warning(self):
        sev, label = classify_status(None)
        assert sev == "warning"
        assert "empty" in label

    def test_all_error_statuses_constant(self):
        # Defensive: the constant is a stable contract.
        assert ERROR_STATUSES == frozenset({"error", "failed", "timeout"})


# ---------------------------------------------------------------------------
# build_dedup_key
# ---------------------------------------------------------------------------


class TestBuildDedupKey:
    def test_with_error_excerpt(self, fixed_now):
        row = {
            "job_id": "a47e1c73e102",
            "status": "error",
            "error_excerpt": "TypeError: boom",
            "started_at": "2026-06-26T13:00:00+00:00",
        }
        key = build_dedup_key(row, now_utc=fixed_now)
        assert key.startswith("a47e1c73e102|error|")
        # SHA1 prefix length is 12 chars
        assert len(key.split("|")[2]) == 12

    def test_same_excerpt_same_key(self, fixed_now):
        row = {
            "job_id": "a47e1c73e102",
            "status": "error",
            "error_excerpt": "boom",
            "started_at": "2026-06-26T13:00:00+00:00",
        }
        key1 = build_dedup_key(row, now_utc=fixed_now)
        key2 = build_dedup_key(row, now_utc=fixed_now)
        assert key1 == key2

    def test_different_excerpt_different_key(self, fixed_now):
        row1 = {"job_id": "x", "status": "error", "error_excerpt": "boom", "started_at": "2026-06-26T13:00:00+00:00"}
        row2 = {"job_id": "x", "status": "error", "error_excerpt": "different", "started_at": "2026-06-26T13:00:00+00:00"}
        assert build_dedup_key(row1, now_utc=fixed_now) != build_dedup_key(row2, now_utc=fixed_now)

    def test_fallback_when_no_error_excerpt(self, fixed_now):
        row = {"job_id": "x", "status": "error", "error_excerpt": "", "started_at": "2026-06-26T13:00:00+00:00"}
        key = build_dedup_key(row, now_utc=fixed_now)
        assert "bucket:" in key

    def test_fallback_buckets_within_window_share_key(self, fixed_now):
        # Two failures within the same FALLBACK_BUCKET_SECONDS window
        row_a = {"job_id": "x", "status": "error", "error_excerpt": "", "started_at": "2026-06-26T13:00:00+00:00"}
        row_b = {"job_id": "x", "status": "error", "error_excerpt": "", "started_at": "2026-06-26T13:04:00+00:00"}
        assert build_dedup_key(row_a, now_utc=fixed_now) == build_dedup_key(row_b, now_utc=fixed_now)

    def test_fallback_different_bucket_different_key(self, fixed_now):
        row_a = {"job_id": "x", "status": "error", "error_excerpt": "", "started_at": "2026-06-26T13:00:00+00:00"}
        row_b = {"job_id": "x", "status": "error", "error_excerpt": "", "started_at": "2026-06-26T13:10:00+00:00"}
        assert build_dedup_key(row_a, now_utc=fixed_now) != build_dedup_key(row_b, now_utc=fixed_now)


# ---------------------------------------------------------------------------
# discover_columns
# ---------------------------------------------------------------------------


class TestDiscoverColumns:
    def test_returns_known_columns(self, mixed_db):
        from orchestrator.scripts.cron_history_alert import open_db
        with open_db(mixed_db) as conn:
            cols = discover_columns(conn)
        assert "id" in cols
        assert "job_id" in cols
        assert "status" in cols
        assert "error_excerpt" in cols
        assert "started_at" in cols

    def test_missing_table_raises(self, tmp_path):
        from orchestrator.scripts.cron_history_alert import open_db
        # open_db opens read-only; verify that discover_columns raises a
        # clear error when the table does not exist. We don't try to
        # drop tables here because the read-only connection would refuse
        # the DROP. Instead, build a DB without the table at all.
        import sqlite3 as _sq
        db = tmp_path / "x.sqlite"
        conn = _sq.connect(str(db))
        try:
            # Create a different table; cron_runs will be missing.
            conn.execute("CREATE TABLE other_table (id INTEGER)")
            conn.commit()
        finally:
            conn.close()
        with open_db(db) as ro_conn:
            with pytest.raises(RuntimeError, match="required table missing"):
                discover_columns(ro_conn)


# ---------------------------------------------------------------------------
# fetch_new_rows
# ---------------------------------------------------------------------------


class TestFetchNewRows:
    def test_after_id_filtering(self, mixed_db):
        from orchestrator.scripts.cron_history_alert import open_db
        with open_db(mixed_db) as conn:
            cols = discover_columns(conn)
            rows = fetch_new_rows(conn, 3, known_columns=cols)
        ids = [r["id"] for r in rows]
        assert ids == [4, 5, 6, 7]

    def test_after_zero_returns_all(self, mixed_db):
        from orchestrator.scripts.cron_history_alert import open_db
        with open_db(mixed_db) as conn:
            cols = discover_columns(conn)
            rows = fetch_new_rows(conn, 0, known_columns=cols)
        assert len(rows) == 7

    def test_optional_columns_default_to_none(self, mixed_db):
        # If we pretend the schema does NOT have error_excerpt, fetch_new_rows
        # still returns rows with NULL-filled optional columns.
        from orchestrator.scripts.cron_history_alert import open_db
        with open_db(mixed_db) as conn:
            cols_no_excerpt = {k: v for k, v in discover_columns(conn).items() if k != "error_excerpt"}
            rows = fetch_new_rows(conn, 0, known_columns=cols_no_excerpt)
        # error_excerpt should be present as NULL (sqlite3.Row maps NULL -> None)
        for r in rows:
            assert r["error_excerpt"] is None


# ---------------------------------------------------------------------------
# State load / save
# ---------------------------------------------------------------------------


class TestStateLoadSave:
    def test_load_missing_returns_empty_state(self, tmp_path):
        s = load_state(tmp_path / "does_not_exist.json")
        assert s == empty_state()

    def test_load_valid_file(self, tmp_path):
        p = tmp_path / "state.json"
        p.write_text(json.dumps({"last_seen_id": 42, "last_run_utc": "x", "last_alerts": {"k": "v"}}))
        s = load_state(p)
        assert s["last_seen_id"] == 42
        assert s["last_alerts"] == {"k": "v"}

    def test_load_partial_file_backfills_defaults(self, tmp_path):
        p = tmp_path / "state.json"
        p.write_text(json.dumps({"last_seen_id": 7}))  # missing keys
        s = load_state(p)
        assert s["last_seen_id"] == 7
        assert s["last_run_utc"] is None
        assert s["last_alerts"] == {}

    def test_load_corrupt_raises(self, tmp_path):
        p = tmp_path / "state.json"
        p.write_text("not valid json {")
        with pytest.raises(RuntimeError, match="corrupted"):
            load_state(p)

    def test_save_creates_parent_dirs(self, tmp_path):
        p = tmp_path / "nested" / "deep" / "state.json"
        save_state(p, empty_state())
        assert p.exists()

    def test_save_atomic_no_torn_file(self, tmp_path):
        # Simulate a crash mid-write by checking the temp file pattern.
        p = tmp_path / "state.json"
        save_state(p, {"a": 1})
        # No temp files left over
        leftovers = list(p.parent.glob(".cron_history_alert_state.*.tmp"))
        assert leftovers == []
        # State is valid JSON
        assert json.loads(p.read_text()) == {"a": 1}


# ---------------------------------------------------------------------------
# Cooldown / dedup logic
# ---------------------------------------------------------------------------


def _make_alert(key: str, started_at: str = "2026-06-26T13:00:00+00:00") -> Alert:
    return Alert(
        row_id=1,
        job_id="x",
        job_name="X",
        status="error",
        severity="error",
        started_at=started_at,
        error_excerpt="boom",
        dedup_key=key,
        first_seen_utc="2026-06-26T13:00:00+00:00",
    )


class TestFilterByCooldown:
    def test_no_prior_state_keeps_all(self, fixed_now):
        alerts = [_make_alert("k1"), _make_alert("k2")]
        kept, suppressed = filter_by_cooldown(
            alerts, empty_state(), cooldown_seconds=1800, now_utc=fixed_now
        )
        assert len(kept) == 2
        assert suppressed == 0

    def test_within_cooldown_suppresses(self, fixed_now):
        # fixed_now is 14:00, last seen at 13:30 -> delta 1800s, NOT within 1800s
        # (use delta < cooldown to test suppression)
        state = {"last_alerts": {"k1": "2026-06-26T13:59:00+00:00"}}
        alerts = [_make_alert("k1"), _make_alert("k2")]
        kept, suppressed = filter_by_cooldown(
            alerts, state, cooldown_seconds=1800, now_utc=fixed_now
        )
        assert len(kept) == 1
        assert kept[0].dedup_key == "k2"
        assert suppressed == 1

    def test_after_cooldown_passes_through(self, fixed_now):
        state = {"last_alerts": {"k1": "2026-06-26T12:00:00+00:00"}}  # 2h ago
        alerts = [_make_alert("k1")]
        kept, suppressed = filter_by_cooldown(
            alerts, state, cooldown_seconds=1800, now_utc=fixed_now
        )
        assert len(kept) == 1
        assert suppressed == 0

    def test_cooldown_disabled(self, fixed_now):
        state = {"last_alerts": {"k1": fixed_now.isoformat()}}
        alerts = [_make_alert("k1")]
        kept, suppressed = filter_by_cooldown(
            alerts, state, cooldown_seconds=0, now_utc=fixed_now
        )
        assert len(kept) == 1
        assert suppressed == 0


# ---------------------------------------------------------------------------
# cap_alerts
# ---------------------------------------------------------------------------


class TestCapAlerts:
    def test_no_cap_when_under(self):
        alerts = [_make_alert(f"k{i}") for i in range(3)]
        kept, dropped = cap_alerts(alerts, max_alerts=5)
        assert len(kept) == 3
        assert dropped == 0

    def test_cap_to_max(self):
        alerts = [_make_alert(f"k{i}") for i in range(10)]
        kept, dropped = cap_alerts(alerts, max_alerts=3)
        assert len(kept) == 3
        assert dropped == 7
        assert [a.dedup_key for a in kept] == ["k0", "k1", "k2"]

    def test_zero_max_means_no_cap(self):
        alerts = [_make_alert(f"k{i}") for i in range(50)]
        kept, dropped = cap_alerts(alerts, max_alerts=0)
        assert len(kept) == 50
        assert dropped == 0


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------


class TestRenderText:
    def test_no_alerts(self):
        assert render_text([]) == "(no alerts)"

    def test_alerts_block_format(self):
        a = _make_alert("k1", "2026-06-26T13:00:00+00:00")
        out = render_text([a])
        assert "[ERROR]" in out
        assert "k1" in out
        assert "2026-06-26T13:00:00+00:00" in out

    def test_warning_severity_marker(self):
        a = Alert(
            row_id=1, job_id="x", job_name="X", status="weird_status",
            severity="warning", started_at="2026-06-26T13:00:00+00:00",
            error_excerpt="", dedup_key="x|weird_status|abc", first_seen_utc="2026-06-26T13:00:00+00:00",
        )
        out = render_text([a])
        assert "[WARN ]" in out


class TestRenderJson:
    def test_is_valid_json(self):
        a = _make_alert("k1")
        out = render_json([a])
        data = json.loads(out)
        assert isinstance(data, list)
        assert data[0]["dedup_key"] == "k1"

    def test_empty_list(self):
        out = render_json([])
        assert json.loads(out) == []


# ---------------------------------------------------------------------------
# is_within_lookback (Fix 1)
# ---------------------------------------------------------------------------


class TestIsWithinLookback:
    def test_zero_lookback_includes_everything(self, fixed_now):
        row = {"created_at": "2000-01-01T00:00:00+00:00", "started_at": "2000-01-01T00:00:00+00:00"}
        assert is_within_lookback(row, now_utc=fixed_now, lookback_minutes=0) is True

    def test_negative_lookback_includes_everything(self, fixed_now):
        row = {"created_at": "2000-01-01T00:00:00+00:00"}
        assert is_within_lookback(row, now_utc=fixed_now, lookback_minutes=-1) is True

    def test_recent_created_at_is_within_window(self, fixed_now):
        # fixed_now = 2026-06-26T14:00 UTC. created_at 13:30 -> 30 min ago.
        row = {"created_at": "2026-06-26T13:30:00+00:00", "started_at": "2026-06-26T13:30:00+00:00"}
        assert is_within_lookback(row, now_utc=fixed_now, lookback_minutes=60) is True

    def test_old_created_at_is_outside_window(self, fixed_now):
        row = {"created_at": "2026-06-25T14:00:00+00:00", "started_at": "2026-06-25T14:00:00+00:00"}
        assert is_within_lookback(row, now_utc=fixed_now, lookback_minutes=60) is False

    def test_falls_back_to_started_at_when_created_at_missing(self, fixed_now):
        row = {"started_at": "2026-06-26T13:30:00+00:00"}
        assert is_within_lookback(row, now_utc=fixed_now, lookback_minutes=60) is True

    def test_malformed_timestamps_include_conservatively(self, fixed_now):
        # If we cannot parse, we INCLUDE rather than silently drop the row.
        # This protects against the writer producing bad data; the operator
        # must investigate.
        row = {"created_at": "not a date", "started_at": "also not a date"}
        assert is_within_lookback(row, now_utc=fixed_now, lookback_minutes=60) is True

    def test_empty_timestamps_include_conservatively(self, fixed_now):
        row = {"created_at": "", "started_at": ""}
        assert is_within_lookback(row, now_utc=fixed_now, lookback_minutes=60) is True

    def test_works_with_sqlite_row(self, fixed_now):
        # Real sqlite3.Row from fetch_new_rows has .keys() and __getitem__.
        import sqlite3 as _sq
        conn = _sq.connect(":memory:")
        conn.execute("CREATE TABLE t (id INTEGER, created_at TEXT, started_at TEXT)")
        conn.execute("INSERT INTO t VALUES (1, '2026-06-26T13:30:00+00:00', '2026-06-26T13:25:00+00:00')")
        conn.row_factory = _sq.Row
        row = conn.execute("SELECT * FROM t WHERE id=1").fetchone()
        conn.close()
        # created_at is within 60 min of fixed_now (14:00)
        assert is_within_lookback(row, now_utc=fixed_now, lookback_minutes=60) is True


# ---------------------------------------------------------------------------
# End-to-end pipeline (run_alert_pipeline) — Fix 1 (lookback) + Fix 2 (commit/dry-run)
# ---------------------------------------------------------------------------


class TestRunAlertPipeline:
    def test_empty_db_no_alerts(self, empty_db, tmp_path, fixed_now):
        state_path = tmp_path / "state.json"
        result = run_alert_pipeline(
            empty_db, state_path,
            cooldown_seconds=1800, lookback_minutes=60, max_alerts=5,
            now_utc=fixed_now,
        )
        assert result.new_alerts == []
        assert result.rows_scanned == 0
        assert result.suppressed_by_cooldown == 0
        # State must not be written without --commit-state
        assert not state_path.exists()

    def test_only_ok_no_alerts(self, ok_db, tmp_path, fixed_now):
        state_path = tmp_path / "state.json"
        result = run_alert_pipeline(
            ok_db, state_path,
            cooldown_seconds=1800, lookback_minutes=60, max_alerts=5,
            now_utc=fixed_now,
        )
        assert result.new_alerts == []
        assert result.rows_scanned == 2

    def test_mixed_produces_alerts(self, mixed_db, tmp_path, fixed_now):
        state_path = tmp_path / "state.json"
        result = run_alert_pipeline(
            mixed_db, state_path,
            cooldown_seconds=0, lookback_minutes=60, max_alerts=10,
            now_utc=fixed_now,
        )
        # 5 alert-worthy rows (err1 x2 dedup -> 1, err2, err3, warn1)
        # err1 has same error_excerpt, so 1 dedup key from err1's two rows
        # Expect: err1 (1 unique), err2, err3, warn1 = 4 alerts
        assert len(result.new_alerts) == 4
        assert result.suppressed_by_max_alerts == 0
        assert result.rows_scanned == 7

    def test_cooldown_suppresses_duplicates(self, mixed_db, tmp_path, fixed_now):
        # Pre-warm: run once with commit to populate state at fixed_now.
        # lookback_minutes=0 so this test isolates the cooldown behaviour
        # from the time-window filter (which is tested separately above).
        state_path = tmp_path / "state.json"
        run_alert_pipeline(
            mixed_db, state_path,
            cooldown_seconds=1800, lookback_minutes=0, max_alerts=10,
            now_utc=fixed_now, commit_state=True,
        )
        # Now simulate a later run by deleting the cursor but keeping the
        # last_alerts state. This represents "same errors reappeared after
        # some time but still within cooldown".
        data = json.loads(state_path.read_text())
        data["last_seen_id"] = 0  # re-scan everything
        state_path.write_text(json.dumps(data))

        # Run at fixed_now (same wall-clock) -> all dedup keys still in cooldown.
        result = run_alert_pipeline(
            mixed_db, state_path,
            cooldown_seconds=1800, lookback_minutes=0, max_alerts=10,
            now_utc=fixed_now, commit_state=True,
        )
        assert result.rows_scanned == 7  # re-scanned
        assert result.rows_filtered_by_lookback == 0  # lookback disabled for this test
        assert result.new_alerts == []
        # 5 alert-worthy rows in mixed_db all hit the cooldown (err1
        # contributes two rows with the same dedup_key but each row is
        # checked independently before intra-run dedup collapses them).
        assert result.suppressed_by_cooldown == 5

    def test_max_alerts_caps_output(self, mixed_db, tmp_path, fixed_now):
        state_path = tmp_path / "state.json"
        result = run_alert_pipeline(
            mixed_db, state_path,
            cooldown_seconds=0, lookback_minutes=60, max_alerts=2,
            now_utc=fixed_now,
        )
        assert len(result.new_alerts) == 2
        assert result.suppressed_by_max_alerts >= 1

    def test_commit_state_persists_cursor(self, mixed_db, tmp_path, fixed_now):
        state_path = tmp_path / "state.json"
        run_alert_pipeline(
            mixed_db, state_path,
            cooldown_seconds=1800, lookback_minutes=60, max_alerts=5,
            now_utc=fixed_now, commit_state=True,
        )
        assert state_path.exists()
        data = json.loads(state_path.read_text())
        assert data["last_seen_id"] == 7  # max id in fixture
        assert data["last_run_utc"] is not None
        # All emitted alert keys were recorded
        for a in run_alert_pipeline(
            mixed_db, state_path,
            cooldown_seconds=1800, lookback_minutes=60, max_alerts=10,
            now_utc=fixed_now,
        ).new_alerts:
            assert a.dedup_key in data["last_alerts"]

    def test_missing_db_returns_state_error(self, tmp_path, fixed_now):
        missing = tmp_path / "no_such_db.sqlite"
        state_path = tmp_path / "state.json"
        with pytest.raises(FileNotFoundError):
            run_alert_pipeline(
                missing, state_path,
                cooldown_seconds=1800, lookback_minutes=60, max_alerts=5,
                now_utc=fixed_now,
            )

    def test_corrupt_state_raises(self, mixed_db, tmp_path, fixed_now):
        state_path = tmp_path / "state.json"
        state_path.write_text("not valid json")
        with pytest.raises(RuntimeError, match="corrupted"):
            run_alert_pipeline(
                mixed_db, state_path,
                cooldown_seconds=1800, lookback_minutes=60, max_alerts=5,
                now_utc=fixed_now,
            )

    def test_lookback_fresh_state_sees_all_rows(self, mixed_db, tmp_path, fixed_now):
        # No state file -> fresh run, all rows in window should be considered.
        state_path = tmp_path / "does_not_exist.json"
        result = run_alert_pipeline(
            mixed_db, state_path,
            cooldown_seconds=0, lookback_minutes=60, max_alerts=100,
            now_utc=fixed_now,
        )
        # 4 unique alert-worthy rows after dedup
        assert result.rows_scanned == 7

    # ---- Fix 1: real --lookback-minutes behaviour on fresh state ----

    def test_lookback_excludes_old_rows_on_fresh_state(self, date_spaced_db, tmp_path, fixed_now):
        """Old rows (14h ago) must NOT be alerted when state is fresh and
        lookback is 60 minutes."""
        state_path = tmp_path / "does_not_exist.json"
        result = run_alert_pipeline(
            date_spaced_db, state_path,
            cooldown_seconds=0, lookback_minutes=60, max_alerts=100,
            now_utc=fixed_now,
        )
        assert result.rows_scanned == 4
        assert result.rows_filtered_by_lookback == 2  # old_err + med_err
        # Only the two recent rows should produce alerts
        assert len(result.new_alerts) == 2
        alerted_ids = {a.job_id for a in result.new_alerts}
        assert alerted_ids == {"fresh_err", "latest_err"}

    def test_lookback_zero_includes_all_rows(self, date_spaced_db, tmp_path, fixed_now):
        """lookback_minutes=0 means 'no time filter' — all rows are considered
        even on fresh state."""
        state_path = tmp_path / "does_not_exist.json"
        result = run_alert_pipeline(
            date_spaced_db, state_path,
            cooldown_seconds=0, lookback_minutes=0, max_alerts=100,
            now_utc=fixed_now,
        )
        assert result.rows_scanned == 4
        assert result.rows_filtered_by_lookback == 0
        assert len(result.new_alerts) == 4

    def test_lookback_long_enough_includes_all(self, date_spaced_db, tmp_path, fixed_now):
        """lookback_minutes=1440 (24h) covers everything in the fixture."""
        state_path = tmp_path / "does_not_exist.json"
        result = run_alert_pipeline(
            date_spaced_db, state_path,
            cooldown_seconds=0, lookback_minutes=1440, max_alerts=100,
            now_utc=fixed_now,
        )
        assert result.rows_filtered_by_lookback == 0
        assert len(result.new_alerts) == 4

    def test_lookback_skipped_when_cursor_present(self, date_spaced_db, tmp_path, fixed_now):
        """If state already has a cursor, lookback_minutes is ignored and
        all rows past the cursor are considered (by construction they are
        recent)."""
        state_path = tmp_path / "state.json"
        # Pre-warm with commit so a cursor exists.
        run_alert_pipeline(
            date_spaced_db, state_path,
            cooldown_seconds=0, lookback_minutes=60, max_alerts=100,
            now_utc=fixed_now, commit_state=True,
        )
        # Force a re-scan of everything by clearing the cursor in the state
        # file. Wait — that makes it "fresh state" again. To test "cursor
        # present", we need to NOT reset the cursor.
        # Instead: simulate "history already seen, lookback must not apply"
        # by adding an OLD row past the cursor.
        import sqlite3 as _sq
        conn = _sq.connect(str(date_spaced_db))
        try:
            conn.execute(
                """
                INSERT INTO cron_runs
                  (id, job_id, job_name, no_agent, script_path, delivery_mode,
                   started_at, finished_at, duration_ms, status, exit_code,
                   timeout, stdout_excerpt, stderr_excerpt, error_excerpt,
                   created_at)
                VALUES (?, ?, ?, 0, '', '', '2025-01-01T00:00:00+00:00', NULL,
                        NULL, 'error', NULL, 0, NULL, NULL, 'very_old', '2025-01-01T00:00:00+00:00')
                """,
                (99, "very_old_err", "very_old_err"),
            )
            conn.commit()
        finally:
            conn.close()

        # Now run with state cursor present, lookback=60. The new old row
        # has id=99 > last_seen_id=4, so it should be alerted despite being
        # ancient in wall-clock time. This proves the lookback does NOT
        # apply once a cursor is present.
        result = run_alert_pipeline(
            date_spaced_db, state_path,
            cooldown_seconds=0, lookback_minutes=60, max_alerts=100,
            now_utc=fixed_now,
        )
        assert result.rows_scanned == 1  # only id=99 (id > last_seen_id=4)
        assert result.rows_filtered_by_lookback == 0  # cursor present -> no time filter
        assert {a.job_id for a in result.new_alerts} == {"very_old_err"}


# ---------------------------------------------------------------------------
# main() CLI smoke test
# ---------------------------------------------------------------------------


class TestMainCLI:
    def test_dry_run_text_format(self, empty_db, tmp_path, capsys, monkeypatch):
        # Empty DB -> "(no alerts)" with no exit error
        state_path = tmp_path / "state.json"
        monkeypatch.setattr("sys.argv", [
            "cron_history_alert.py",
            "--db", str(empty_db),
            "--state", str(state_path),
            "--dry-run",
            "--print-summary",
        ])
        from orchestrator.scripts import cron_history_alert
        rc = cron_history_alert.main()
        assert rc == 0
        captured = capsys.readouterr()
        assert "(no alerts)" in captured.out
        assert "summary: alerts=0" in captured.err

    def test_mixed_db_text_format(self, mixed_db, tmp_path, capsys, monkeypatch):
        state_path = tmp_path / "state.json"
        # --now-utc pins time to 14:00 UTC so the lookback window
        # (default 60 min, cutoff 13:00) reliably includes all rows.
        monkeypatch.setattr("sys.argv", [
            "cron_history_alert.py",
            "--db", str(mixed_db),
            "--state", str(state_path),
            "--cooldown-seconds", "0",
            "--max-alerts", "10",
            "--dry-run",
            "--now-utc", "2026-06-26T14:00:00+00:00",
        ])
        from orchestrator.scripts import cron_history_alert
        rc = cron_history_alert.main()
        assert rc == 0
        captured = capsys.readouterr()
        assert "[ERROR]" in captured.out or "[WARN ]" in captured.out
        # State file must NOT be written in dry-run mode (default)
        assert not state_path.exists()

    def test_commit_state_persists(self, mixed_db, tmp_path, capsys, monkeypatch):
        state_path = tmp_path / "state.json"
        monkeypatch.setattr("sys.argv", [
            "cron_history_alert.py",
            "--db", str(mixed_db),
            "--state", str(state_path),
            "--cooldown-seconds", "0",
            "--commit-state",
        ])
        from orchestrator.scripts import cron_history_alert
        rc = cron_history_alert.main()
        assert rc == 0
        assert state_path.exists()

    def test_json_format(self, mixed_db, tmp_path, capsys, monkeypatch):
        state_path = tmp_path / "state.json"
        # --now-utc pins time so lookback window is deterministic.
        monkeypatch.setattr("sys.argv", [
            "cron_history_alert.py",
            "--db", str(mixed_db),
            "--state", str(state_path),
            "--cooldown-seconds", "0",
            "--max-alerts", "10",
            "--format", "json",
            "--dry-run",
            "--now-utc", "2026-06-26T14:00:00+00:00",
        ])
        from orchestrator.scripts import cron_history_alert
        rc = cron_history_alert.main()
        assert rc == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert isinstance(data, list)
        assert len(data) >= 1
        assert "dedup_key" in data[0]


    def test_now_utc_invalid_value_exits(self, mixed_db, tmp_path, capsys, monkeypatch):
        state_path = tmp_path / "state.json"
        monkeypatch.setattr("sys.argv", [
            "cron_history_alert.py",
            "--db", str(mixed_db),
            "--state", str(state_path),
            "--now-utc", "not-a-date",
        ])
        from orchestrator.scripts import cron_history_alert
        with pytest.raises(SystemExit):
            cron_history_alert.main()

    def test_missing_db_exits_2(self, tmp_path, capsys, monkeypatch):
        state_path = tmp_path / "state.json"
        monkeypatch.setattr("sys.argv", [
            "cron_history_alert.py",
            "--db", str(tmp_path / "no_such.sqlite"),
            "--state", str(state_path),
        ])
        from orchestrator.scripts import cron_history_alert
        rc = cron_history_alert.main()
        assert rc == 2

    # ---- Fix 2: --dry-run / --commit-state mutual exclusion ----

    def test_dry_run_commit_state_mutually_exclusive(
        self, mixed_db, tmp_path, capsys, monkeypatch
    ):
        """--dry-run and --commit-state together must exit 2 and write
        nothing. This protects an operator who reads "--dry-run" as
        "do not persist" from accidentally writing state."""
        state_path = tmp_path / "state.json"
        monkeypatch.setattr("sys.argv", [
            "cron_history_alert.py",
            "--db", str(mixed_db),
            "--state", str(state_path),
            "--cooldown-seconds", "0",
            "--dry-run",
            "--commit-state",
        ])
        from orchestrator.scripts import cron_history_alert
        rc = cron_history_alert.main()
        assert rc == 2
        assert not state_path.exists()
        captured = capsys.readouterr()
        assert "mutually exclusive" in captured.err

    def test_dry_run_alone_never_writes_state(
        self, mixed_db, tmp_path, capsys, monkeypatch
    ):
        """--dry-run alone (default in many invocations) must not write
        the state file even if alerts are present."""
        state_path = tmp_path / "state.json"
        monkeypatch.setattr("sys.argv", [
            "cron_history_alert.py",
            "--db", str(mixed_db),
            "--state", str(state_path),
            "--cooldown-seconds", "0",
            "--max-alerts", "10",
            "--dry-run",
        ])
        from orchestrator.scripts import cron_history_alert
        rc = cron_history_alert.main()
        assert rc == 0
        # State file MUST NOT be created by a dry-run.
        assert not state_path.exists()

    def test_no_flags_means_no_state_write(
        self, mixed_db, tmp_path, capsys, monkeypatch
    ):
        """With neither --dry-run nor --commit-state, the tool must NOT
        write the state file. State writes require explicit --commit-state."""
        state_path = tmp_path / "state.json"
        monkeypatch.setattr("sys.argv", [
            "cron_history_alert.py",
            "--db", str(mixed_db),
            "--state", str(state_path),
            "--cooldown-seconds", "0",
            "--max-alerts", "10",
        ])
        from orchestrator.scripts import cron_history_alert
        rc = cron_history_alert.main()
        assert rc == 0
        assert not state_path.exists()

    def test_commit_state_alone_writes_state(
        self, mixed_db, tmp_path, capsys, monkeypatch
    ):
        """--commit-state alone must persist state. This is the only path
        that writes the state file."""
        state_path = tmp_path / "state.json"
        monkeypatch.setattr("sys.argv", [
            "cron_history_alert.py",
            "--db", str(mixed_db),
            "--state", str(state_path),
            "--cooldown-seconds", "0",
            "--max-alerts", "10",
            "--commit-state",
        ])
        from orchestrator.scripts import cron_history_alert
        rc = cron_history_alert.main()
        assert rc == 0
        assert state_path.exists()
