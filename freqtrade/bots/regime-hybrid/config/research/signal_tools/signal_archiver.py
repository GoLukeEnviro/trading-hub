#!/usr/bin/env python3
"""
Research Signal Archiver for Freqtrade/Primo signal state.

Polls a signal state JSON file (default: /freqtrade/user_data/primo_signal_state.json)
and appends a JSONL record to historical_signals.jsonl only when the content changes.

Manual start examples:
  python3 signal_archiver.py
  python3 signal_archiver.py --once
  screen -S signal-archiver
  python3 /freqtrade/config/research/signal_tools/signal_archiver.py

No orders are placed. This is read/write logging only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

DEFAULT_SIGNAL_SOURCE = Path("/freqtrade/user_data/primo_signal_state.json")
DEFAULT_ARCHIVE_FILE = Path("/freqtrade/user_data/signals/historical_signals.jsonl")
DEFAULT_SLEEP_SEC = 30.0

_SHOULD_STOP = False


def utc_now_iso() -> str:
    """Return an ISO-8601 UTC timestamp with timezone."""
    return datetime.now(timezone.utc).isoformat()


def canonical_hash(data: dict[str, Any]) -> str:
    """Stable SHA256 hash for JSON-compatible dictionaries."""
    payload = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def read_json_file(path: Path) -> Optional[dict[str, Any]]:
    """Read a JSON object from path. Return None for missing/empty/invalid files."""
    try:
        if not path.exists():
            logging.warning("signal source missing: %s", path)
            return None
        if path.stat().st_size == 0:
            logging.warning("signal source empty: %s", path)
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            logging.warning("signal source is not a JSON object: %s", path)
            return None
        return data
    except json.JSONDecodeError as exc:
        logging.warning("signal source invalid JSON: %s (%s)", path, exc)
        return None
    except OSError as exc:
        logging.warning("signal source read failed: %s (%s)", path, exc)
        return None


def load_last_archive_hash(archive_file: Path) -> Optional[str]:
    """Return the last archived source hash, if the archive exists and is valid enough."""
    if not archive_file.exists() or archive_file.stat().st_size == 0:
        return None
    try:
        with archive_file.open("rb") as fh:
            # Efficient enough for small/medium JSONL files; robust to trailing blank lines.
            lines = fh.readlines()[-50:]
        for raw in reversed(lines):
            line = raw.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            rec = json.loads(line)
            h = rec.get("source_hash") or rec.get("hash")
            if isinstance(h, str) and h:
                return h
            data = rec.get("data")
            if isinstance(data, dict):
                return canonical_hash(data)
    except Exception as exc:  # pragma: no cover - defensive startup path
        logging.warning("could not read last archive hash from %s: %s", archive_file, exc)
    return None


def build_archive_record(data: dict[str, Any], source_hash: str) -> dict[str, Any]:
    """Build one append-only archive record."""
    pairs = data.get("pairs") if isinstance(data.get("pairs"), dict) else {}
    return {
        "timestamp_utc": utc_now_iso(),
        "source_hash": source_hash,
        "fresh": data.get("fresh"),
        "stale": data.get("stale"),
        "age_minutes": data.get("age_minutes"),
        "pairs_count": len(pairs),
        "pair_keys": sorted(str(k) for k in pairs.keys()),
        "data": data,
    }


def append_jsonl(archive_file: Path, record: dict[str, Any]) -> None:
    """Append a JSON record as one JSONL line, creating parent directories."""
    archive_file.parent.mkdir(parents=True, exist_ok=True)
    with archive_file.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        fh.flush()


def archive_if_changed(
    data: dict[str, Any],
    archive_file: Path,
    last_hash: Optional[str],
    include_stale: bool = True,
) -> tuple[Optional[str], bool]:
    """Archive data if changed. Return (new_last_hash, wrote_record)."""
    if not include_stale and bool(data.get("stale", False)):
        logging.info("signal is stale; skipping due to --skip-stale")
        return last_hash, False

    current_hash = canonical_hash(data)
    if current_hash == last_hash:
        return last_hash, False

    record = build_archive_record(data, current_hash)
    append_jsonl(archive_file, record)
    logging.info(
        "archived signal timestamp=%s hash=%s fresh=%s stale=%s pairs=%s",
        record["timestamp_utc"],
        current_hash[:12],
        record["fresh"],
        record["stale"],
        record["pairs_count"],
    )
    return current_hash, True


def _handle_signal(signum: int, _frame: object) -> None:
    global _SHOULD_STOP
    logging.info("received signal %s; stopping after current loop", signum)
    _SHOULD_STOP = True


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Archive primo_signal_state.json changes to JSONL.")
    parser.add_argument("--source", type=Path, default=DEFAULT_SIGNAL_SOURCE, help="Signal JSON source path")
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE_FILE, help="Archive JSONL output path")
    parser.add_argument("--sleep-sec", type=float, default=DEFAULT_SLEEP_SEC, help="Polling interval seconds")
    parser.add_argument("--once", action="store_true", help="Run one poll and exit")
    parser.add_argument("--skip-stale", action="store_true", help="Do not archive records with stale=true")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="[%(asctime)s] %(levelname)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%SZ",
    )
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    last_hash = load_last_archive_hash(args.archive)
    if last_hash:
        logging.info("loaded last archive hash=%s from %s", last_hash[:12], args.archive)
    logging.info("signal archiver started source=%s archive=%s interval=%.1fs", args.source, args.archive, args.sleep_sec)

    while not _SHOULD_STOP:
        data = read_json_file(args.source)
        if data is not None:
            last_hash, _ = archive_if_changed(
                data=data,
                archive_file=args.archive,
                last_hash=last_hash,
                include_stale=not args.skip_stale,
            )
        if args.once:
            break
        time.sleep(max(args.sleep_sec, 0.1))

    logging.info("signal archiver stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
