"""SI v2 historical Freqtrade trade reader.

Read-only consumer of the trade store produced by the historical backfill
importer (PR #339). This module:

- Loads every ``historical_trades_<bot_id>.jsonl`` file from a store directory.
- Validates the stamped ``schema_version``.
- Skips corrupt lines with structured warnings instead of crashing.
- Filters by ``bot_id``, time window, trade status (open/closed), or pair.
- Never mutates store files. Never reads runtime Freqtrade DBs.

The reader is purely a data-access layer.  Window aggregation, fleet-level
metrics, and evidence bundle construction live in
:mod:`si_v2.analysis.historical_window_analyzer`.

Hard rules:
- No runtime imports (no ``docker``, ``freqtrade``, ``exchange`` in import lines).
- No live trading.  Dry-run mode must remain enabled.
- No secrets in output.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger("si_v2.backfill.historical_trade_reader")

# The schema version stamped by the backfill importer.  Records carrying a
# different version are surfaced as warnings; the loader never crashes on a
# single bad record.
SUPPORTED_SCHEMA_VERSION = 1


@dataclass
class TradeRecord:
    """A single trade record read from the historical JSONL store.

    The trade record is intentionally permissive: only the fields the
    analyzer actively consumes are declared.  Additional fields carried by
    newer Freqtrade schema versions are preserved on the dict level for
    forward compatibility.
    """

    bot_id: str
    pair: str
    is_open: int
    open_date: str
    close_date: str | None
    close_profit: float | None
    close_profit_abs: float | None
    raw: dict[str, object] = field(default_factory=dict)

    @property
    def is_closed(self) -> bool:
        return int(self.is_open) == 0


@dataclass
class ReadStats:
    """Aggregated counters returned by the reader for evidence and reporting."""

    files_seen: int = 0
    files_loaded: int = 0
    lines_total: int = 0
    lines_kept: int = 0
    lines_skipped_corrupt: int = 0
    lines_skipped_schema: int = 0
    bots: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "files_seen": self.files_seen,
            "files_loaded": self.files_loaded,
            "lines_total": self.lines_total,
            "lines_kept": self.lines_kept,
            "lines_skipped_corrupt": self.lines_skipped_corrupt,
            "lines_skipped_schema": self.lines_skipped_schema,
            "bots": list(self.bots),
        }


def _iter_store_files(store_dir: Path) -> Iterator[Path]:
    """Yield every per-bot JSONL file in ``store_dir`` in deterministic order.

    The summary file (``historical_trades_summary.json``) is excluded; it
    is a sidecar and would otherwise be parsed twice.
    """
    for path in sorted(store_dir.glob("historical_trades_*.jsonl")):
        yield path


def _parse_record(
    line: str,
    *,
    expected_bot_id: str | None,
) -> TradeRecord | None:
    """Parse a single JSONL line.  Returns ``None`` for corrupt or unsupported rows."""
    try:
        raw = json.loads(line)
    except json.JSONDecodeError as e:
        log.warning("corrupt jsonl line skipped: %s", e)
        return None
    if not isinstance(raw, dict):
        log.warning("non-dict jsonl line skipped: %r", raw)
        return None
    schema_version = raw.get("schema_version")
    if schema_version != SUPPORTED_SCHEMA_VERSION:
        log.warning("schema_version=%s skipped (expected %s)", schema_version, SUPPORTED_SCHEMA_VERSION)
        return None
    bot_id = raw.get("bot_id")
    if expected_bot_id is not None and bot_id != expected_bot_id:
        return None
    if bot_id is None or raw.get("pair") is None:
        log.warning("record missing bot_id or pair: %r", raw)
        return None
    return TradeRecord(
        bot_id=str(bot_id),
        pair=str(raw.get("pair", "")),
        is_open=int(raw.get("is_open", 0) or 0),
        open_date=str(raw.get("open_date", "")),
        close_date=(str(raw["close_date"]) if raw.get("close_date") else None),
        close_profit=(float(raw["close_profit"]) if raw.get("close_profit") is not None else None),
        close_profit_abs=(
            float(raw["close_profit_abs"]) if raw.get("close_profit_abs") is not None else None
        ),
        raw=raw,
    )


def _parse_close_timestamp(close_date: str | None) -> float:
    """Return a comparable epoch seconds value from a Freqtrade-formatted timestamp.

    Returns ``float("-inf")`` when ``close_date`` is missing/blank so that
    open trades naturally sort to the end of any time-based filter.
    """
    if not close_date:
        return float("-inf")
    cleaned = close_date.replace("Z", "+00:00")
    # ``datetime.fromisoformat`` accepts both ``YYYY-MM-DD HH:MM:SS`` and
    # ISO-8601 with a ``T`` separator; Freqtrade uses a space separator.
    from datetime import datetime
    try:
        dt = datetime.fromisoformat(cleaned)
    except ValueError:
        return float("-inf")
    if dt.tzinfo is None:
        # SQLite-derived timestamps are naive UTC.  Treat them as such so that
        # string comparisons remain deterministic.
        from datetime import timezone
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def _passes_filter(
    record: TradeRecord,
    *,
    start_utc: str | None,
    end_utc: str | None,
    only_closed: bool,
    only_open: bool,
    pair: str | None,
) -> bool:
    """Apply a time/status/pair filter to a single record."""
    if only_closed and not record.is_closed:
        return False
    if only_open and record.is_closed:
        return False
    if pair is not None and record.pair != pair:
        return False
    if start_utc is not None or end_utc is not None:
        ts = _parse_close_timestamp(record.close_date if record.is_closed else record.open_date)
        if start_utc is not None and ts < _parse_close_timestamp(start_utc):
            return False
        if end_utc is not None:
            # ``end_utc`` is inclusive
            end_ts = _parse_close_timestamp(end_utc)
            if ts > end_ts:
                return False
    return True


def load_store(
    store_dir: Path | str,
    *,
    bot_id: str | None = None,
    start_utc: str | None = None,
    end_utc: str | None = None,
    only_closed: bool = False,
    only_open: bool = False,
    pair: str | None = None,
) -> tuple[list[TradeRecord], ReadStats]:
    """Load all matching records from the historical store.

    Parameters
    ----------
    store_dir:
        Directory containing ``historical_trades_<bot_id>.jsonl`` files.
    bot_id:
        If provided, only records matching this bot are returned.
    start_utc / end_utc:
        Inclusive timestamp boundaries applied to ``close_date`` for closed
        trades and to ``open_date`` for open trades.  Strings must be
        parseable by :func:`datetime.fromisoformat`.
    only_closed / only_open:
        Mutually exclusive status filters.  If neither is set, both
        statuses are returned.
    pair:
        Exact-match pair filter (e.g. ``"BTC/USDT:USDT"``).

    Returns
    -------
    (records, stats)
        The matching trade records (in load order) and aggregate counters.
    """
    if only_closed and only_open:
        raise ValueError("only_closed and only_open are mutually exclusive")

    store = Path(store_dir)
    if not store.is_dir():
        raise FileNotFoundError(f"store_dir not found: {store}")

    stats = ReadStats()
    records: list[TradeRecord] = []
    for path in _iter_store_files(store):
        stats.files_seen += 1
        per_file_bot = path.stem.removeprefix("historical_trades_")
        if bot_id is not None and per_file_bot != bot_id:
            continue
        if per_file_bot not in stats.bots:
            stats.bots.append(per_file_bot)
        loaded_this_file = 0
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            stats.lines_total += 1
            try:
                rec = _parse_record(stripped, expected_bot_id=bot_id)
            except Exception as e:  # pragma: no cover - defensive
                log.warning("unexpected error parsing line: %s", e)
                stats.lines_skipped_corrupt += 1
                continue
            if rec is None:
                # Either corrupt or schema-version mismatch
                if '"schema_version":' in stripped:
                    stats.lines_skipped_schema += 1
                else:
                    stats.lines_skipped_corrupt += 1
                continue
            if not _passes_filter(
                rec,
                start_utc=start_utc,
                end_utc=end_utc,
                only_closed=only_closed,
                only_open=only_open,
                pair=pair,
            ):
                continue
            records.append(rec)
            loaded_this_file += 1
            stats.lines_kept += 1
        if loaded_this_file > 0 or path.exists():
            stats.files_loaded += 1
    return records, stats


def list_bots(store_dir: Path | str) -> list[str]:
    """Return the sorted list of bot_ids present in the store."""
    store = Path(store_dir)
    if not store.is_dir():
        return []
    return sorted(
        p.stem.removeprefix("historical_trades_")
        for p in store.glob("historical_trades_*.jsonl")
    )


def iter_pairs(records: Iterable[TradeRecord]) -> list[str]:
    """Return the unique, sorted list of pairs across ``records``."""
    return sorted({r.pair for r in records if r.pair})


__all__ = [
    "SUPPORTED_SCHEMA_VERSION",
    "TradeRecord",
    "ReadStats",
    "load_store",
    "list_bots",
    "iter_pairs",
]
