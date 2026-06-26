"""Hermes Cron History Alert Reader.

Sprint 2 of the Hermes cron-history repair campaign. This tool reads
``/opt/data/profiles/orchestrator/state/cron_history.sqlite`` (the
DB populated by ``cron_history_writer.py`` since Sprint 1), classifies
non-``ok`` rows, deduplicates them by ``job_id`` + ``status`` + error
fingerprint, and applies a cooldown window so a sustained failure does
not produce alert spam.

CLI::

    python3 orchestrator/scripts/cron_history_alert.py \\
        --db /opt/data/profiles/orchestrator/state/cron_history.sqlite \\
        --state /opt/data/profiles/orchestrator/state/cron_history_alert_state.json \\
        --lookback-minutes 60 \\
        --cooldown-seconds 1800 \\
        --max-alerts 5 \\
        --dry-run

Design notes:

* Pure functions for DB read, classify, dedup, cooldown, render, state
  load/save. Side-effecting ``main`` is the only thing that touches
  the filesystem outside the test fixtures.
* SQLite is opened read-only via URI mode (``file:...?mode=ro``) so we
  never block the writer.
* Schema is discovered via ``PRAGMA table_info(cron_runs)`` at
  startup — we never hardcode a column list. Missing optional
  columns (e.g. ``error_excerpt``) gracefully degrade.
* State file writes are atomic: ``tempfile`` in the same directory,
  then ``os.replace``. ``os.replace`` is atomic on POSIX so we cannot
  end up with a half-written state file under crash.
* No Telegram dispatch in this version. ``--dry-run`` prints alerts
  to stdout (and optionally JSON). A future runtime-deploy phase will
  wire in a dispatcher behind a separate approval token.

For safety:

* ``--dry-run`` is the default for any manual invocation.
* ``--commit-state`` is **off** by default. The state file is only
  written when explicitly enabled (future runtime use).
* Exit codes: ``0`` OK / no alerts, ``2`` DB or state error, ``1``
  unexpected error.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as _dt
import hashlib
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_DB_PATH = Path(
    "/opt/data/profiles/orchestrator/state/cron_history.sqlite"
)
DEFAULT_STATE_PATH = Path(
    "/opt/data/profiles/orchestrator/state/cron_history_alert_state.json"
)
DEFAULT_TABLE = "cron_runs"

# Status values that are always considered alert-worthy.
ERROR_STATUSES = frozenset({"error", "failed", "timeout"})

# Status values we recognise explicitly; anything else triggers a
# "warning" alert (not silent) so the operator can investigate the
# writer if a new status appears.
KNOWN_STATUSES = frozenset({"ok"} | ERROR_STATUSES)

# Bucket size in seconds for the fallback fingerprint when error_excerpt
# is missing. 5 minutes matches the cron_history_writer retention window.
FALLBACK_BUCKET_SECONDS = 300

# Exit codes
EXIT_OK = 0
EXIT_STATE_ERROR = 2
EXIT_UNEXPECTED = 1


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Alert:
    """A single classified alert candidate."""

    row_id: int
    job_id: str
    job_name: str
    status: str
    severity: str  # "error" or "warning"
    started_at: str
    error_excerpt: str  # may be empty
    dedup_key: str
    first_seen_utc: str  # when this dedup key was first emitted


@dataclasses.dataclass(frozen=True)
class RunResult:
    """Result of one alert run."""

    new_alerts: list[Alert]
    suppressed_by_cooldown: int
    suppressed_by_max_alerts: int
    rows_scanned: int
    rows_filtered_by_lookback: int
    last_seen_id: int


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


def open_db(db_path: Path) -> sqlite3.Connection:
    """Open the SQLite DB read-only. Returns a connection with row_factory=Row."""
    if not db_path.exists():
        raise FileNotFoundError(f"DB file missing: {db_path}")
    uri = f"file:{db_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def discover_columns(conn: sqlite3.Connection, table: str = DEFAULT_TABLE) -> dict[str, str]:
    """Return ``{column_name: declared_type}`` for the table.

    Raises ``RuntimeError`` if the table does not exist.
    """
    cur = conn.cursor()
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    )
    if cur.fetchone() is None:
        raise RuntimeError(f"required table missing: {table!r}")
    cols: dict[str, str] = {}
    for row in cur.execute(f"PRAGMA table_info({table})"):
        cols[row[1]] = (row[2] or "").upper()
    return cols


def fetch_new_rows(
    conn: sqlite3.Connection,
    after_id: int,
    *,
    table: str = DEFAULT_TABLE,
    known_columns: dict[str, str] | None = None,
) -> list[sqlite3.Row]:
    """Fetch rows with ``id > after_id`` from the configured table.

    Uses the ``idx_cron_runs_status_time`` index when available; falls
    back to a plain ``WHERE id > ?`` ordering on ``id``.

    Optional columns are selected defensively — if a column does not
    exist in the schema, it is replaced with ``NULL`` so downstream
    code does not break.
    """
    cur = conn.cursor()

    base_cols = ["id", "job_id", "job_name", "status", "started_at"]
    optional_cols = [
        "error_excerpt",
        "stderr_excerpt",
        "exit_code",
        "finished_at",
        "duration_ms",
        "script_path",
        "no_agent",
        "created_at",  # used by lookback-window filter on first run
    ]
    if known_columns is None:
        known_columns = discover_columns(conn, table)

    select_cols = list(base_cols)
    for col in optional_cols:
        if col in known_columns:
            select_cols.append(col)
        else:
            select_cols.append(f"NULL AS {col}")  # placeholder NULL with same name

    select_sql = ", ".join(select_cols)
    sql = f"SELECT {select_sql} FROM {table} WHERE id > ? ORDER BY id ASC"
    cur.execute(sql, (after_id,))
    return list(cur.fetchall())


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


def classify_status(status: str | None) -> tuple[str, str]:
    """Map a row's status to ``(severity, normalised_status)``.

    Returns ``("ok", "ok")`` for ``status == "ok"``. Returns
    ``("error", status)`` for any of ``ERROR_STATUSES``. Returns
    ``("warning", "<unknown:STATUS>")`` for null/empty/unknown.
    """
    if not status:
        return ("warning", "<unknown:empty>")
    s = status.strip().lower()
    if s == "ok":
        return ("ok", "ok")
    if s in ERROR_STATUSES:
        return ("error", s)
    return ("warning", f"<unknown:{s}>")


def build_dedup_key(
    row: sqlite3.Row | dict,
    *,
    now_utc: _dt.datetime | None = None,
    bucket_seconds: int = FALLBACK_BUCKET_SECONDS,
) -> str:
    """Compute a stable dedup key for a row.

    Primary form: ``"<job_id>|<status>|<sha1(error_excerpt)[:12]>"``.
    Fallback (no error_excerpt or empty): bucketed by started_at so
    repeated failures within the same window share one key.
    """
    job_id = row["job_id"] or "<unknown_job>"
    status = (row["status"] or "").strip().lower() or "<empty>"
    error_excerpt = (row["error_excerpt"] or "").strip() if "error_excerpt" in row.keys() else ""
    if error_excerpt:
        h = hashlib.sha1(error_excerpt.encode("utf-8")).hexdigest()[:12]
        return f"{job_id}|{status}|{h}"

    # Fallback bucket by started_at
    started = row["started_at"] if "started_at" in row.keys() else ""
    if started and now_utc is not None:
        try:
            dt = _dt.datetime.fromisoformat(started)
        except ValueError:
            dt = now_utc
    elif now_utc is not None:
        dt = now_utc
    else:
        dt = _dt.datetime.now(_dt.timezone.utc)
    bucket = int(dt.timestamp()) // bucket_seconds
    return f"{job_id}|{status}|bucket:{bucket}"


# ---------------------------------------------------------------------------
# State load / save
# ---------------------------------------------------------------------------


def empty_state() -> dict[str, Any]:
    return {
        "last_seen_id": 0,
        "last_run_utc": None,
        "last_alerts": {},  # dedup_key -> ISO timestamp of last alert
    }


def load_state(state_path: Path) -> dict[str, Any]:
    """Load state from JSON. Missing file -> fresh state. Corrupt file -> error."""
    if not state_path.exists():
        return empty_state()
    try:
        with state_path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            raise ValueError("state root must be a JSON object")
        # Backfill missing keys
        base = empty_state()
        for k, v in base.items():
            data.setdefault(k, v)
        if not isinstance(data.get("last_alerts"), dict):
            data["last_alerts"] = {}
        return data
    except (json.JSONDecodeError, ValueError) as exc:
        raise RuntimeError(
            f"state file corrupted ({state_path}): {exc}"
        ) from exc


def save_state(state_path: Path, state: dict[str, Any]) -> None:
    """Atomically write state JSON. POSIX rename guarantees no torn writes."""
    state_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        prefix=".cron_history_alert_state.",
        suffix=".tmp",
        dir=str(state_path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=2, sort_keys=True)
            fh.write("\n")
            fh.flush()
            try:
                os.fsync(fh.fileno())
            except OSError:
                # fsync may not be supported on all filesystems
                pass
        os.replace(tmp_path, state_path)
    except Exception:
        # Clean up the temp file on failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# Cooldown / dedup logic
# ---------------------------------------------------------------------------


def _dedupe_within_run(alerts: list[Alert]) -> list[Alert]:
    """Collapse alerts with the same dedup_key into one. Keep the row
    with the lowest ``row_id`` (the first occurrence in the DB), so
    operators see the *first* failure in a burst, not the latest.
    """
    seen: dict[str, Alert] = {}
    for a in alerts:
        existing = seen.get(a.dedup_key)
        if existing is None or a.row_id < existing.row_id:
            seen[a.dedup_key] = a
    return list(seen.values())


def filter_by_cooldown(
    alerts: list[Alert],
    state: dict[str, Any],
    *,
    cooldown_seconds: int,
    now_utc: _dt.datetime,
) -> tuple[list[Alert], int]:
    """Drop alerts whose dedup key was seen within ``cooldown_seconds``.

    Returns ``(kept_alerts, suppressed_count)``.
    """
    if cooldown_seconds <= 0:
        return list(alerts), 0

    last_alerts = state.get("last_alerts", {})
    kept: list[Alert] = []
    suppressed = 0
    for alert in alerts:
        last_iso = last_alerts.get(alert.dedup_key)
        if last_iso:
            try:
                last_dt = _dt.datetime.fromisoformat(last_iso)
                delta = (now_utc - last_dt).total_seconds()
                if delta < cooldown_seconds:
                    suppressed += 1
                    continue
            except ValueError:
                # Corrupt timestamp -> treat as fresh
                pass
        kept.append(alert)
    return kept, suppressed


def cap_alerts(alerts: list[Alert], max_alerts: int) -> tuple[list[Alert], int]:
    """Cap the alert list to ``max_alerts`` (deterministic: keep first N)."""
    if max_alerts <= 0 or len(alerts) <= max_alerts:
        return list(alerts), 0
    return list(alerts[:max_alerts]), len(alerts) - max_alerts


def is_within_lookback(
    row: sqlite3.Row | dict,
    *,
    now_utc: _dt.datetime,
    lookback_minutes: int,
) -> bool:
    """Return True if the row's timestamp is within the lookback window.

    Prefers ``created_at`` (writer-set, monotonically the run completion
    time) and falls back to ``started_at``. If both fail to parse, the
    row is **included** conservatively — we never want to silently drop
    an alert because of a malformed timestamp; the operator should
    investigate the writer instead.

    Returns True when ``lookback_minutes <= 0`` (no lookback = no filter).
    """
    if lookback_minutes <= 0:
        return True
    keys = row.keys() if hasattr(row, "keys") else row
    cutoff = now_utc - _dt.timedelta(minutes=lookback_minutes)
    for col in ("created_at", "started_at"):
        ts = row[col] if col in keys else None
        if not ts:
            continue
        try:
            dt = _dt.datetime.fromisoformat(ts)
        except ValueError:
            continue
        return dt >= cutoff
    # Conservative fallback: include. Documented in the runbook.
    return True


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------


def render_text(alerts: Iterable[Alert]) -> str:
    """Render alerts as a human-readable text block (no leading/trailing newline)."""
    lines: list[str] = []
    for a in alerts:
        severity_marker = "ERROR" if a.severity == "error" else "WARN "
        lines.append(
            f"[{severity_marker}] {a.job_id} | status={a.status} | "
            f"row_id={a.row_id} | started_at={a.started_at}"
        )
        if a.job_name:
            lines.append(f"        name: {a.job_name}")
        if a.error_excerpt:
            excerpt = a.error_excerpt[:240].replace("\n", " ")
            lines.append(f"        error_excerpt: {excerpt}")
        lines.append(f"        dedup_key: {a.dedup_key}")
        lines.append(f"        first_seen: {a.first_seen_utc}")
        lines.append("")
    if not lines:
        return "(no alerts)"
    # Drop the trailing blank line
    return "\n".join(lines[:-1])


def render_json(alerts: Iterable[Alert]) -> str:
    """Render alerts as a JSON array (deterministic ordering)."""
    payload = [dataclasses.asdict(a) for a in alerts]
    return json.dumps(payload, indent=2, sort_keys=True)


# ---------------------------------------------------------------------------
# Main run pipeline
# ---------------------------------------------------------------------------


def run_alert_pipeline(
    db_path: Path,
    state_path: Path,
    *,
    cooldown_seconds: int = 1800,
    lookback_minutes: int = 60,
    max_alerts: int = 5,
    now_utc: _dt.datetime | None = None,
    commit_state: bool = False,
) -> RunResult:
    """End-to-end: load state, fetch new rows, classify, dedup, render.

    This is the pure-function pipeline. ``main`` wraps it with
    argparse + output handling + optional state persistence.

    Returns ``RunResult``. Does not write to stdout. Does not modify
    ``state_path`` unless ``commit_state=True``.

    Lookback semantics:

    * When the state file is fresh (``last_seen_id == 0``) AND
      ``lookback_minutes > 0``, only rows whose ``created_at`` (or
      ``started_at`` fallback) is within the lookback window are
      considered. This prevents a fresh-state first run from alerting
      on historical failures from days/weeks ago.
    * When the state file already has a cursor (``last_seen_id > 0``),
      the lookback is irrelevant — only ``id > last_seen_id`` rows
      are considered, which by definition are recent.
    * When ``lookback_minutes <= 0``, no time filter is applied even
      on a fresh state (legacy behaviour; not recommended).
    """
    if now_utc is None:
        now_utc = _dt.datetime.now(_dt.timezone.utc)

    state = load_state(state_path)
    last_seen_id_before = int(state.get("last_seen_id", 0))

    # Cursor strategy:
    # - Fresh state (no cursor): scan from row id 0 but apply time filter
    #   via is_within_lookback() below.
    # - Existing cursor: only consider rows past the cursor (no time
    #   filter — by construction those rows are recent).
    after_id = last_seen_id_before

    rows_scanned = 0
    rows_filtered_by_lookback = 0
    new_alerts: list[Alert] = []
    last_seen_id_after = after_id

    with open_db(db_path) as conn:
        known_cols = discover_columns(conn)
        rows = fetch_new_rows(conn, after_id, known_columns=known_cols)

    rows_scanned = len(rows)
    apply_lookback = (last_seen_id_before == 0 and lookback_minutes > 0)
    for row in rows:
        last_seen_id_after = max(last_seen_id_after, row["id"])
        if apply_lookback and not is_within_lookback(
            row, now_utc=now_utc, lookback_minutes=lookback_minutes
        ):
            rows_filtered_by_lookback += 1
            continue
        severity, _normalised = classify_status(row["status"])
        if severity == "ok":
            continue
        key = build_dedup_key(row, now_utc=now_utc)
        alert = Alert(
            row_id=row["id"],
            job_id=row["job_id"] or "<unknown_job>",
            job_name=row["job_name"] or "",
            status=row["status"] or "",
            severity=severity,
            started_at=row["started_at"] or "",
            error_excerpt=row["error_excerpt"] if "error_excerpt" in row.keys() else "",
            dedup_key=key,
            first_seen_utc=now_utc.isoformat(),
        )
        new_alerts.append(alert)

    kept, suppressed_by_cooldown = filter_by_cooldown(
        new_alerts, state, cooldown_seconds=cooldown_seconds, now_utc=now_utc
    )
    # After cooldown filtering, collapse any remaining alerts that share
    # a dedup_key into a single representative (the lowest row_id).
    kept = _dedupe_within_run(kept)
    kept, suppressed_by_max = cap_alerts(kept, max_alerts)

    if commit_state:
        # Update state for kept alerts only; drop suppressed keys older
        # than the cooldown window so the state file does not grow
        # unbounded.
        new_last_alerts = dict(state.get("last_alerts", {}))
        for a in kept:
            new_last_alerts[a.dedup_key] = now_utc.isoformat()
        # GC: drop entries older than 7 days
        gc_threshold = now_utc - _dt.timedelta(days=7)
        cleaned: dict[str, str] = {}
        for k, iso in new_last_alerts.items():
            try:
                if _dt.datetime.fromisoformat(iso) >= gc_threshold:
                    cleaned[k] = iso
            except ValueError:
                continue
        state["last_alerts"] = cleaned
        state["last_seen_id"] = last_seen_id_after
        state["last_run_utc"] = now_utc.isoformat()
        save_state(state_path, state)

    return RunResult(
        new_alerts=kept,
        suppressed_by_cooldown=suppressed_by_cooldown,
        suppressed_by_max_alerts=suppressed_by_max,
        rows_scanned=rows_scanned,
        rows_filtered_by_lookback=rows_filtered_by_lookback,
        last_seen_id=last_seen_id_after,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="cron_history_alert.py",
        description="Read cron_history.sqlite and emit deduplicated alerts.",
    )
    p.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="SQLite DB path.")
    p.add_argument(
        "--state",
        type=Path,
        default=DEFAULT_STATE_PATH,
        help="Dedup/cooldown state JSON path.",
    )
    p.add_argument(
        "--lookback-minutes",
        type=int,
        default=60,
        help="Lookback window when state is fresh (no cursor yet). 0 = no limit.",
    )
    p.add_argument(
        "--cooldown-seconds",
        type=int,
        default=1800,
        help="Per dedup-key cooldown in seconds. 0 disables.",
    )
    p.add_argument(
        "--max-alerts",
        type=int,
        default=5,
        help="Hard cap on alerts emitted per run. 0 = no cap.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Alias for omitting --commit-state. State is never written. "
        "Mutually exclusive with --commit-state.",
    )
    p.add_argument(
        "--commit-state",
        action="store_true",
        help="Persist state changes after this run. Mutually exclusive with --dry-run.",
    )
    p.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format.",
    )
    p.add_argument(
        "--now-utc",
        type=str,
        default=None,
        help="Override now_utc for deterministic runs (ISO 8601 UTC). "
        "Defaults to current system time. Used by tests and by operators "
        "who want reproducible alert runs against historical data.",
    )
    p.add_argument(
        "--print-summary",
        action="store_true",
        help="Print a one-line summary even when alerts are empty.",
    )
    return p


def _parse_now_utc_arg(value: str | None) -> _dt.datetime | None:
    """Parse --now-utc value. Returns None if value is None."""
    if value is None:
        return None
    try:
        dt = _dt.datetime.fromisoformat(value)
    except ValueError as exc:
        raise SystemExit(f"error: --now-utc value {value!r} is not a valid ISO 8601 timestamp: {exc}")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_dt.timezone.utc)
    return dt


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    # Mutual exclusion: --dry-run and --commit-state are opposites.
    if args.dry_run and args.commit_state:
        print(
            "error: --dry-run and --commit-state are mutually exclusive. "
            "Use --commit-state only when you intend to write the state "
            "file (e.g. inside a scheduled cron job).",
            file=sys.stderr,
        )
        return EXIT_STATE_ERROR

    now_utc = _parse_now_utc_arg(args.now_utc)

    try:
        result = run_alert_pipeline(
            args.db,
            args.state,
            cooldown_seconds=args.cooldown_seconds,
            lookback_minutes=args.lookback_minutes,
            max_alerts=args.max_alerts,
            commit_state=args.commit_state,
            now_utc=now_utc,
        )
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_STATE_ERROR
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_STATE_ERROR
    except Exception as exc:  # pragma: no cover - defensive
        print(f"unexpected error: {exc}", file=sys.stderr)
        return EXIT_UNEXPECTED

    if args.format == "json":
        print(render_json(result.new_alerts))
    else:
        print(render_text(result.new_alerts))

    if args.print_summary or result.new_alerts:
        print(
            f"summary: alerts={len(result.new_alerts)} "
            f"cooldown_suppressed={result.suppressed_by_cooldown} "
            f"max_alerts_suppressed={result.suppressed_by_max_alerts} "
            f"rows_scanned={result.rows_scanned} "
            f"rows_filtered_by_lookback={result.rows_filtered_by_lookback} "
            f"last_seen_id={result.last_seen_id}",
            file=sys.stderr,
        )
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
