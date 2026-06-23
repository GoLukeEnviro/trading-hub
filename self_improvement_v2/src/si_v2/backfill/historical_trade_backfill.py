"""SI v2 historical Freqtrade SQLite trade backfill.

Read-only importer for closed and open trades from the four on-disk Freqtrade
``tradesv3`` SQLite databases into a SI v2 historical trade store.

Hard rules (enforced via ``mode='ro'`` URI and a dedicated writer):
- Read-only against source DBs (no mutations to the runtime trade files).
- No bot restart, no Docker/Compose mutation, no config or strategy mutation.
- No live trading. Dry-run mode must remain enabled.
- No secrets in output.

Store layout:
    self_improvement_v2/state/historical_trades/
        historical_trades_<bot_id>.jsonl
        historical_trades_summary.json
        historical_trades_import.log
"""
from __future__ import annotations

import contextlib
import json
import logging
import os
import sqlite3
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

SCHEMA_VERSION = 1

# Stable column order extracted from a real Freqtrade 2026.3 tradesv3 DB.
# Add new columns explicitly when Freqtrade schema changes.
TRADE_COLUMNS: tuple[str, ...] = (
    "id",
    "exchange",
    "pair",
    "base_currency",
    "stake_currency",
    "is_open",
    "fee_open",
    "fee_open_cost",
    "fee_open_currency",
    "fee_close",
    "fee_close_cost",
    "fee_close_currency",
    "open_rate",
    "open_rate_requested",
    "open_trade_value",
    "close_rate",
    "close_rate_requested",
    "realized_profit",
    "close_profit",
    "close_profit_abs",
    "stake_amount",
    "max_stake_amount",
    "amount",
    "amount_requested",
    "open_date",
    "close_date",
    "stop_loss",
    "stop_loss_pct",
    "initial_stop_loss",
    "initial_stop_loss_pct",
    "is_stop_loss_trailing",
    "max_rate",
    "min_rate",
    "exit_reason",
    "exit_order_status",
    "strategy",
    "enter_tag",
    "timeframe",
    "trading_mode",
    "amount_precision",
    "price_precision",
    "precision_mode",
    "precision_mode_price",
    "contract_size",
    "leverage",
    "is_short",
    "liquidation_price",
    "interest_rate",
    "funding_fees",
    "funding_fee_running",
    "record_version",
)

# Default per-bot DB config for the trading-hub deployment.
# ``path`` points at the host-bind-mounted SQLite file.  ``bot_id`` matches the
# SI v2 read-only registry key.
DEFAULT_BOT_DBS: tuple[dict[str, str], ...] = (
    {
        "bot_id": "freqtrade-freqforge",
        "db_path": "freqforge/user_data/tradesv3.freqforge.dryrun.sqlite",
    },
    {
        "bot_id": "freqtrade-freqforge-canary",
        "db_path": "freqforge-canary/user_data/tradesv3.freqforge_canary.dryrun.sqlite",
    },
    {
        "bot_id": "freqtrade-regime-hybrid",
        "db_path": "freqtrade/bots/regime-hybrid/user_data/tradesv3.regime_hybrid.dryrun.sqlite",
    },
    {
        "bot_id": "freqai-rebel",
        "db_path": "freqtrade/bots/freqai-rebel/user_data/tradesv3.freqai_rebel.dryrun.sqlite",
    },
)

log = logging.getLogger("si_v2.backfill.historical_trade")


@dataclass
class BackfillBotResult:
    """Per-bot import statistics."""

    bot_id: str
    source_db: str
    schema_version: int
    found_trades: int
    imported_trades: int
    open_trades: int
    closed_trades: int
    oldest_open_date: str | None
    newest_close_date: str | None
    oldest_trade_id: int | None
    newest_trade_id: int | None
    sum_close_profit_abs: float
    wins: int
    losses: int
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "bot_id": self.bot_id,
            "source_db": self.source_db,
            "schema_version": self.schema_version,
            "found_trades": self.found_trades,
            "imported_trades": self.imported_trades,
            "open_trades": self.open_trades,
            "closed_trades": self.closed_trades,
            "oldest_open_date": self.oldest_open_date,
            "newest_close_date": self.newest_close_date,
            "oldest_trade_id": self.oldest_trade_id,
            "newest_trade_id": self.newest_trade_id,
            "sum_close_profit_abs": self.sum_close_profit_abs,
            "wins": self.wins,
            "losses": self.losses,
            "errors": list(self.errors),
        }


@dataclass
class BackfillSummary:
    """Aggregate of every per-bot backfill run."""

    generated_at_utc: str
    repo_root: str
    store_root: str
    schema_version: int
    bots: list[BackfillBotResult]
    totals: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return {
            "generated_at_utc": self.generated_at_utc,
            "repo_root": self.repo_root,
            "store_root": self.store_root,
            "schema_version": self.schema_version,
            "bots": [b.to_dict() for b in self.bots],
            "totals": dict(self.totals),
        }


def _resolve_db(repo_root: Path, db_path: str) -> Path:
    """Return an absolute path to a candidate SQLite DB.

    ``db_path`` may be relative to ``repo_root`` or absolute.  Existence is
    the caller's responsibility.
    """
    p = Path(db_path)
    if p.is_absolute():
        return p
    return (repo_root / p).resolve()


def _connect_ro(db: Path) -> sqlite3.Connection:
    """Open a SQLite connection in strict read-only mode."""
    uri = f"file:{db}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    # Defense in depth: even though mode=ro, forbid writes.
    conn.execute("PRAGMA query_only = ON")
    return conn


def _table_has_trades(conn: sqlite3.Connection) -> bool:
    cur = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='trades' LIMIT 1"
    )
    return cur.fetchone() is not None


def _fetch_trades(
    conn: sqlite3.Connection, columns: Iterable[str]
) -> tuple[list[sqlite3.Row], list[str]]:
    """Return all trade rows.  Whitelist the columns to avoid surprises."""
    select_cols = ", ".join(f'"{c}"' for c in columns)
    rows = conn.execute(f"SELECT {select_cols} FROM trades ORDER BY id").fetchall()
    missing: list[str] = []
    existing = {
        r[1]
        for r in conn.execute("PRAGMA table_info(trades)").fetchall()
    }
    for c in columns:
        if c not in existing:
            missing.append(c)
    return rows, missing


def backfill_bot(
    bot_id: str,
    db_path: str | os.PathLike[str],
    *,
    repo_root: Path,
    output_dir: Path,
) -> BackfillBotResult:
    """Backfill a single bot's trades into ``output_dir``.

    The output file is written atomically via ``tempfile`` + ``os.replace``.
    The result is also returned as a ``BackfillBotResult`` for the caller.
    """
    repo_root = repo_root.resolve()
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    abs_db = _resolve_db(repo_root, str(db_path))

    errors: list[str] = []
    if not abs_db.exists():
        return BackfillBotResult(
            bot_id=bot_id,
            source_db=str(abs_db),
            schema_version=SCHEMA_VERSION,
            found_trades=0,
            imported_trades=0,
            open_trades=0,
            closed_trades=0,
            oldest_open_date=None,
            newest_close_date=None,
            oldest_trade_id=None,
            newest_trade_id=None,
            sum_close_profit_abs=0.0,
            wins=0,
            losses=0,
            errors=[f"db_not_found: {abs_db}"],
        )

    result = BackfillBotResult(
        bot_id=bot_id,
        source_db=str(abs_db.relative_to(repo_root)) if abs_db.is_relative_to(repo_root) else str(abs_db),
        schema_version=SCHEMA_VERSION,
        found_trades=0,
        imported_trades=0,
        open_trades=0,
        closed_trades=0,
        oldest_open_date=None,
        newest_close_date=None,
        oldest_trade_id=None,
        newest_trade_id=None,
        sum_close_profit_abs=0.0,
        wins=0,
        losses=0,
        errors=errors,
    )

    try:
        conn = _connect_ro(abs_db)
    except sqlite3.OperationalError as e:
        errors.append(f"open_failed: {e}")
        return result

    try:
        if not _table_has_trades(conn):
            errors.append("no_trades_table")
            return result
        rows, missing = _fetch_trades(conn, TRADE_COLUMNS)
        if missing:
            errors.append("missing_columns:" + ",".join(missing))
        result.found_trades = len(rows)
    except sqlite3.DatabaseError as e:
        errors.append(f"query_failed: {e}")
        conn.close()
        return result
    finally:
        conn.close()

    # Build import stream
    imported_at = datetime.now(UTC).isoformat()
    out_path = output_dir / f"historical_trades_{bot_id}.jsonl"
    tmp_fd, tmp_path = tempfile.mkstemp(
        prefix=f".historical_trades_{bot_id}.", suffix=".tmp", dir=output_dir
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as tmp_f:
            for row in rows:
                record: dict[str, object] = {
                    "schema_version": SCHEMA_VERSION,
                    "imported_at_utc": imported_at,
                    "bot_id": bot_id,
                    "source_db": result.source_db,
                }
                for c, v in zip(TRADE_COLUMNS, row, strict=True):
                    record[c] = v
                tmp_f.write(json.dumps(record, sort_keys=True, default=str))
                tmp_f.write("\n")
                result.imported_trades += 1
                if int(record.get("is_open", 0)) == 1:
                    result.open_trades += 1
                else:
                    result.closed_trades += 1
                # Aggregate fields
                od = record.get("open_date")
                if od and (result.oldest_open_date is None or str(od) < result.oldest_open_date):
                    result.oldest_open_date = str(od)
                cd = record.get("close_date")
                if cd and (result.newest_close_date is None or str(cd) > result.newest_close_date):
                    result.newest_close_date = str(cd)
                tid = record.get("id")
                if tid is not None:
                    if result.oldest_trade_id is None or int(tid) < result.oldest_trade_id:
                        result.oldest_trade_id = int(tid)
                    if result.newest_trade_id is None or int(tid) > result.newest_trade_id:
                        result.newest_trade_id = int(tid)
                cp = record.get("close_profit")
                if cp is not None and not record.get("is_open"):
                    try:
                        result.sum_close_profit_abs += float(record.get("close_profit_abs") or 0.0)
                        if float(cp) > 0:
                            result.wins += 1
                        else:
                            result.losses += 1
                    except (TypeError, ValueError):
                        pass
        os.replace(tmp_path, out_path)
    except Exception:
        # On any failure, remove the partial temp file
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise

    return result


def backfill_all(
    bot_dbs: Iterable[dict[str, str]] | None = None,
    *,
    repo_root: Path | None = None,
    output_dir: Path | None = None,
) -> BackfillSummary:
    """Backfill all configured bots and return a summary."""
    repo_root = (repo_root or Path("/home/hermes/projects/trading")).resolve()
    if output_dir is None:
        output_dir = repo_root / "self_improvement_v2" / "state" / "historical_trades"
    output_dir = output_dir.resolve()
    bot_dbs = list(bot_dbs) if bot_dbs is not None else list(DEFAULT_BOT_DBS)

    bot_results: list[BackfillBotResult] = []
    for entry in bot_dbs:
        bot_id = entry["bot_id"]
        db_path = entry["db_path"]
        log.info("backfilling %s from %s", bot_id, db_path)
        bot_results.append(
            backfill_bot(
                bot_id, db_path, repo_root=repo_root, output_dir=output_dir
            )
        )

    totals = {
        "bots_configured": len(bot_dbs),
        "bots_imported": sum(1 for b in bot_results if b.imported_trades > 0),
        "bots_skipped": sum(1 for b in bot_results if b.imported_trades == 0),
        "total_imported_trades": sum(b.imported_trades for b in bot_results),
        "total_open_trades": sum(b.open_trades for b in bot_results),
        "total_closed_trades": sum(b.closed_trades for b in bot_results),
        "total_errors": sum(len(b.errors) for b in bot_results),
    }

    summary = BackfillSummary(
        generated_at_utc=datetime.now(UTC).isoformat(),
        repo_root=str(repo_root),
        store_root=str(output_dir),
        schema_version=SCHEMA_VERSION,
        bots=bot_results,
        totals=totals,
    )

    # Persist summary atomically
    summary_path = output_dir / "historical_trades_summary.json"
    tmp_fd, tmp_path = tempfile.mkstemp(
        prefix=".historical_trades_summary.", suffix=".tmp", dir=output_dir
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as tmp_f:
            json.dump(summary.to_dict(), tmp_f, indent=2, sort_keys=True, default=str)
            tmp_f.write("\n")
        os.replace(tmp_path, summary_path)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise

    return summary


def load_summary(store_root: Path | str) -> dict[str, object] | None:
    """Read a previously-written summary JSON.  Returns ``None`` if missing."""
    p = Path(store_root) / "historical_trades_summary.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


__all__ = [
    "DEFAULT_BOT_DBS",
    "SCHEMA_VERSION",
    "TRADE_COLUMNS",
    "BackfillBotResult",
    "BackfillSummary",
    "backfill_all",
    "backfill_bot",
    "load_summary",
]
