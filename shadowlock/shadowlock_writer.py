#!/usr/bin/env python3
"""Shadowlock writer service.

Polls a JSON inbox and appends validated entries to date-partitioned JSONL logs.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None

BASE_DIR = Path(__file__).resolve().parent.parent / "var" / "trading-shadowlock"
INBOX_DIR = BASE_DIR / "inbox"
PROCESSED_DIR = BASE_DIR / "processed"
QUARANTINE_DIR = BASE_DIR / "quarantine"
DEAD_LETTER_DIR = BASE_DIR / "dead-letter"
STATE_DIR = BASE_DIR / "state"
LOGS_DIR = BASE_DIR / "logs"

KNOWN_SCHEMA_VERSIONS = {"1.0"}
REQUIRED_FIELDS = {"timestamp_utc", "event_type", "bot_name", "schema_version"}
HEARTBEAT_INTERVAL_SECONDS = 300
MAX_WRITE_ATTEMPTS = 3


class ValidationError(Exception):
    """Raised when an inbox entry is invalid."""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def configure_logging() -> None:
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(message)s",
    )


def ensure_directories() -> None:
    for path in [
        INBOX_DIR,
        PROCESSED_DIR,
        QUARANTINE_DIR,
        DEAD_LETTER_DIR,
        STATE_DIR,
        LOGS_DIR,
    ]:
        path.mkdir(parents=True, exist_ok=True)


def parse_json_file(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"Invalid JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise ValidationError("Entry must be a JSON object")

    return payload


def validate_entry(entry: dict[str, Any]) -> None:
    missing = sorted(REQUIRED_FIELDS - set(entry.keys()))
    if missing:
        raise ValidationError(f"Missing required fields: {', '.join(missing)}")

    bot_name = entry.get("bot_name")
    if not isinstance(bot_name, str) or not bot_name.strip():
        raise ValidationError("bot_name must be a non-empty string")

    event_type = entry.get("event_type")
    if not isinstance(event_type, str) or not event_type.strip():
        raise ValidationError("event_type must be a non-empty string")

    schema_version = entry.get("schema_version")
    if not isinstance(schema_version, str) or not schema_version.strip():
        raise ValidationError("schema_version must be a non-empty string")

    timestamp_utc = entry.get("timestamp_utc")
    if not isinstance(timestamp_utc, str) or not timestamp_utc.strip():
        raise ValidationError("timestamp_utc must be a non-empty string")


def compute_entry_sha256(entry: dict[str, Any]) -> str:
    canonical = dict(entry)
    canonical.pop("entry_sha256", None)
    canonical.pop("sha256", None)
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def bot_state_path(bot_name: str) -> Path:
    return STATE_DIR / f"{bot_name}.seq"


def next_sequence_number(bot_name: str) -> int:
    state_path = bot_state_path(bot_name)
    current = 0
    if state_path.exists():
        try:
            current = int(state_path.read_text(encoding="utf-8").strip() or "0")
        except (OSError, ValueError):
            current = 0

    value = current + 1
    state_path.write_text(str(value), encoding="utf-8")
    return value


def partitioned_log_path(timestamp_utc: str) -> Path:
    parsed = datetime.fromisoformat(timestamp_utc.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    parsed = parsed.astimezone(timezone.utc)
    target = LOGS_DIR / parsed.strftime("%Y") / parsed.strftime("%m")
    target.mkdir(parents=True, exist_ok=True)
    return target / f"{parsed.strftime('%d')}.jsonl"


def append_jsonl_with_lock(path: Path, entry: dict[str, Any]) -> None:
    line = json.dumps(entry, ensure_ascii=False, sort_keys=True)
    with path.open("a", encoding="utf-8") as handle:
        if fcntl is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            handle.write(line + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        finally:
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def move_file(src: Path, dest_dir: Path) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    destination = dest_dir / src.name
    if destination.exists():
        stamped = f"{src.stem}-{int(time.time())}{src.suffix}"
        destination = dest_dir / stamped
    shutil.move(str(src), str(destination))


def write_entry_with_retries(entry: dict[str, Any]) -> None:
    log_path = partitioned_log_path(entry["timestamp_utc"])

    attempt = 0
    delay_seconds = 1
    last_error: Exception | None = None

    while attempt < MAX_WRITE_ATTEMPTS:
        attempt += 1
        try:
            append_jsonl_with_lock(log_path, entry)
            return
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            logging.exception(
                "Write attempt %s/%s failed for %s (%s)",
                attempt,
                MAX_WRITE_ATTEMPTS,
                log_path,
                type(exc).__name__,
            )
            if attempt >= MAX_WRITE_ATTEMPTS:
                break
            time.sleep(delay_seconds)
            delay_seconds *= 2

    assert last_error is not None
    raise last_error


def process_inbox_file(path: Path) -> None:
    try:
        entry = parse_json_file(path)
        validate_entry(entry)
    except ValidationError as exc:
        logging.warning("Validation failed for %s: %s", path.name, exc)
        move_file(path, QUARANTINE_DIR)
        return

    schema_version = entry.get("schema_version")
    if schema_version not in KNOWN_SCHEMA_VERSIONS:
        logging.warning("Unknown schema_version '%s' in %s", schema_version, path.name)

    entry["entry_sha256"] = compute_entry_sha256(entry)
    entry["sequence_number"] = next_sequence_number(entry["bot_name"])
    entry["ingested_at_utc"] = utc_now_iso()

    try:
        write_entry_with_retries(entry)
    except Exception as exc:  # noqa: BLE001
        logging.error(
            "Write failed after %s retries for %s (%s): %s",
            MAX_WRITE_ATTEMPTS,
            path.name,
            type(exc).__name__,
            exc,
        )
        move_file(path, DEAD_LETTER_DIR)
        return

    move_file(path, PROCESSED_DIR)
    logging.info("Processed %s", path.name)


def emit_heartbeat() -> None:
    bot_name = "shadowlock-writer"
    entry = {
        "timestamp_utc": utc_now_iso(),
        "event_type": "shadowlock_heartbeat",
        "bot_name": bot_name,
        "schema_version": "1.0",
        "message": "service_alive",
    }
    entry["entry_sha256"] = compute_entry_sha256(entry)
    entry["sequence_number"] = next_sequence_number(bot_name)
    entry["ingested_at_utc"] = utc_now_iso()
    write_entry_with_retries(entry)


def run() -> int:
    configure_logging()
    ensure_directories()

    poll_interval = int(os.getenv("POLL_INTERVAL_SECONDS", "60"))
    next_heartbeat_at = time.time()

    logging.info("Shadowlock writer started (poll interval: %ss)", poll_interval)

    while True:
        now = time.time()
        if now >= next_heartbeat_at:
            try:
                emit_heartbeat()
            except Exception as exc:  # noqa: BLE001
                logging.error("Failed to emit heartbeat: %s", exc)
            next_heartbeat_at = now + HEARTBEAT_INTERVAL_SECONDS

        for inbox_file in sorted(INBOX_DIR.glob("*.json")):
            process_inbox_file(inbox_file)

        time.sleep(max(1, poll_interval))


def main() -> int:
    try:
        return run()
    except KeyboardInterrupt:
        logging.info("Shadowlock writer stopped by user")
        return 0


if __name__ == "__main__":
    sys.exit(main())
