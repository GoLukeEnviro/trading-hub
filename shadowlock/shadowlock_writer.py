#!/usr/bin/env python3
"""
shadowlock_writer.py — Lightweight append-only JSONL ledger service.

Implements the Shadowlock Writer spec (docs/specs/shadowlock-writer-spec.md)
as a continuously running poll loop. Picks up JSON files from the inbox
directory, validates, sequences, checksums, and appends them to daily
JSONL log files.

Dependencies: stdlib only. No pip installs required.
"""

import os
import sys
import json
import hashlib
import time
import datetime
import logging
import signal
import glob
import shutil
import pathlib
import subprocess

# ── Platform-specific locking ────────────────────────────────────────────────

_HAS_FCNTL = False
try:
    import fcntl
    _HAS_FCNTL = True
except ImportError:
    pass


# ── Configuration (all via environment variables with defaults) ────────────

POLL_INTERVAL_SECONDS = int(os.environ.get("POLL_INTERVAL_SECONDS", "60"))
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
SHADOWLOCK_BASE_DIR = os.environ.get("SHADOWLOCK_BASE_DIR", "var/trading-shadowlock")
HEARTBEAT_INTERVAL_SECONDS = int(os.environ.get("HEARTBEAT_INTERVAL_SECONDS", "300"))

SCHEMA_VERSION = "1.0"

# Required fields per event type
REQUIRED_FIELDS = {
    "default": ["schema_version", "event_type", "timestamp_utc", "bot_name"],
    "episode_start": ["schema_version", "event_type", "timestamp_utc",
                       "target_bot", "episode_id"],
    "self_improvement_episode": ["schema_version", "event_type", "timestamp_utc",
                                  "target_bot", "episode_id"],
    "episode_error": ["schema_version", "event_type", "timestamp_utc",
                       "target_bot", "episode_id"],
    "active_file_modified": ["schema_version", "event_type", "timestamp_utc",
                              "target_bot", "episode_id"],
    "forensics_trigger": ["schema_version", "event_type", "timestamp_utc",
                           "bot_name", "reason", "episode_id"],
    "orchestrator_no_candidates": ["schema_version", "event_type", "timestamp_utc",
                                    "bot_name"],
    "episode_lock_released": ["schema_version", "event_type", "timestamp_utc",
                               "bot_name", "reason"],
}

# Subdirectories to ensure exist
REQUIRED_SUBDIRS = [
    "logs",
    "processed",
    "quarantine",
    "dead-letter",
    "inbox",
    "archive",
    "state",
    "backtests",
]


# ── Logging Setup ───────────────────────────────────────────────────────────

def setup_logging():
    """Configure stdlib logging with ISO timestamp UTC format."""
    logger = logging.getLogger("shadowlock")
    handler = logging.StreamHandler(sys.stdout)

    class ISOTimestampFormatter(logging.Formatter):
        def formatTime(self, record, datefmt=None):
            dt = datetime.datetime.utcfromtimestamp(record.created)
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    fmt = ISOTimestampFormatter("%(asctime)s | %(levelname)s | %(message)s")
    handler.setFormatter(fmt)
    logger.addHandler(handler)
    logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
    return logger


log = setup_logging()


# ── File Locking ────────────────────────────────────────────────────────────

class FileLock:
    """Cross-platform file lock using fcntl.flock on Linux, .lock sidecar on others."""

    def __init__(self, target_path):
        self.target_path = target_path
        if _HAS_FCNTL:
            self._lock_path = target_path
            self._fd = None
            self._use_fcntl = True
        else:
            self._lock_path = str(pathlib.Path(str(target_path) + ".lock"))
            self._fd = None
            self._use_fcntl = False

    def acquire(self):
        """Acquire exclusive lock. Blocks until acquired."""
        if self._use_fcntl:
            self._fd = os.open(self._lock_path, os.O_RDWR | os.O_CREAT)
            fcntl.flock(self._fd, fcntl.LOCK_EX)
        else:
            # Fallback: create lock sidecar file exclusively
            while True:
                try:
                    self._fd = os.open(self._lock_path,
                                       os.O_CREAT | os.O_EXCL | os.O_RDWR)
                    break
                except (OSError, IOError):
                    time.sleep(0.1)

    def release(self):
        """Release the lock."""
        if self._fd is not None:
            if self._use_fcntl:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
                os.close(self._fd)
            else:
                os.close(self._fd)
                try:
                    os.unlink(self._lock_path)
                except (OSError, IOError):
                    pass
            self._fd = None


# ── Path Management ─────────────────────────────────────────────────────────

def resolve_base_dir():
    """Resolve and validate the shadowlock base directory."""
    base = os.path.abspath(SHADOWLOCK_BASE_DIR)
    os.makedirs(base, exist_ok=True)
    return base


def ensure_subdirs(base_dir):
    """Create all required subdirectories (idempotent)."""
    for sub in REQUIRED_SUBDIRS:
        path = os.path.join(base_dir, sub)
        os.makedirs(path, exist_ok=True)

    # Create YYYY/MM subdir under logs
    today = datetime.date.today()
    log_subdir = os.path.join(base_dir, "logs", str(today.year), f"{today.month:02d}")
    os.makedirs(log_subdir, exist_ok=True)


def log_path_for_timestamp(base_dir, dt):
    """Return the JSONL log path for a given datetime."""
    return os.path.join(
        base_dir,
        "logs",
        str(dt.year),
        f"{dt.month:02d}",
        f"{dt.day:02d}.jsonl",
    )


# ── Sequence Number Management ──────────────────────────────────────────────

def read_sequence(base_dir, bot_name):
    """Read the current sequence number for a bot. Returns int (default 0)."""
    path = os.path.join(base_dir, "state", f"{bot_name}.seq")
    try:
        with open(path, "r") as f:
            return int(f.read().strip())
    except (FileNotFoundError, ValueError):
        return 0


def write_sequence(base_dir, bot_name, seq):
    """Write the sequence number for a bot atomically (via rename)."""
    state_dir = os.path.join(base_dir, "state")
    os.makedirs(state_dir, exist_ok=True)
    path = os.path.join(state_dir, f"{bot_name}.seq")
    tmp_path = path + ".tmp"
    with open(tmp_path, "w") as f:
        f.write(str(seq))
    os.rename(tmp_path, path)


# ── SHA-256 Computation ─────────────────────────────────────────────────────

def compute_entry_sha256(entry):
    """Compute SHA-256 of the entry with entry_sha256 set to empty string.

    Returns (entry_with_hash, sha256_hex).
    """
    # Deep copy to avoid mutating the original
    copy = json.loads(json.dumps(entry))
    copy["entry_sha256"] = ""
    # Canonical JSON: sort keys, no extra whitespace
    canonical = json.dumps(copy, sort_keys=True, separators=(",", ":"))
    sha = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    copy["entry_sha256"] = sha
    return copy, sha


# ── Inbox Processing ────────────────────────────────────────────────────────

def validate_entry(entry):
    """Validate required fields for the entry's event_type.

    Returns (is_valid, error_reason).
    """
    if not isinstance(entry, dict):
        return False, "entry is not a JSON object"

    event_type = entry.get("event_type", "")

    # Determine the required fields set for this event type
    required = REQUIRED_FIELDS.get(event_type, REQUIRED_FIELDS["default"])

    missing = [f for f in required if f not in entry or entry.get(f) is None or entry.get(f) == ""]
    if missing:
        return False, f"missing required fields: {', '.join(missing)}"

    # Validate timestamp_utc format (must end with Z and parse)
    ts = entry.get("timestamp_utc", "")
    if not ts.endswith("Z"):
        return False, "timestamp_utc must end with Z (UTC)"
    try:
        datetime.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        try:
            datetime.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S.%fZ")
        except ValueError:
            return False, f"timestamp_utc has invalid format: {ts}"

    # Validate schema_version
    sv = entry.get("schema_version", "")
    if sv != SCHEMA_VERSION:
        # Log warning but don't reject
        log.warning("Entry %s has unknown schema_version '%s' (expected '%s')",
                     entry.get("event_type", "unknown"), sv, SCHEMA_VERSION)

    return True, None


def process_inbox_file(base_dir, filepath):
    """Process a single inbox JSON file.

    Returns True if processed successfully, False if quarantined or dead-lettered.
    Never raises an exception — all errors are handled internally.
    """
    filename = os.path.basename(filepath)
    today_str = datetime.date.today().strftime("%Y-%m-%d")

    try:
        with open(filepath, "r") as f:
            raw = f.read()
        entry = json.loads(raw)
    except (json.JSONDecodeError, IOError) as e:
        # Unparseable JSON → quarantine
        dest = os.path.join(base_dir, "quarantine", f"{today_str}-{filename}")
        try:
            shutil.move(filepath, dest)
        except (OSError, IOError) as move_err:
            log.error("Failed to move unparseable file to quarantine: %s — %s",
                       filepath, move_err)
        log.warning("Quarantined unparseable file: %s — %s", filename, e)
        return False

    # Validate required fields
    is_valid, reason = validate_entry(entry)
    if not is_valid:
        dest = os.path.join(base_dir, "quarantine", f"{today_str}-{filename}")
        try:
            shutil.move(filepath, dest)
        except (OSError, IOError) as move_err:
            log.error("Failed to move invalid entry to quarantine: %s — %s",
                       filepath, move_err)
        log.warning("Quarantined invalid entry %s — %s", filename, reason)
        return False

    # Determine bot name (target_bot for episode events)
    bot_name = entry.get("bot_name") or entry.get("target_bot", "unknown")

    # Compute entry SHA-256
    entry_with_hash, sha256_hex = compute_entry_sha256(entry)
    entry_with_hash["entry_sha256"] = sha256_hex

    # Read and increment sequence number
    seq = read_sequence(base_dir, bot_name) + 1
    entry_with_hash["sequence_number"] = seq

    # Determine log path from timestamp_utc in the entry
    ts_str = entry_with_hash.get("timestamp_utc", "")
    try:
        ts = datetime.datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        try:
            ts = datetime.datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%S.%fZ")
        except ValueError:
            # Fallback: use current time
            ts = datetime.datetime.utcnow()
            log.warning("Could not parse timestamp '%s', using current UTC time", ts_str)

    log_path = log_path_for_timestamp(base_dir, ts)
    log_dir = os.path.dirname(log_path)
    os.makedirs(log_dir, exist_ok=True)

    # Write to log file with lock and retry
    success = write_with_retry(log_path, entry_with_hash, seq)

    if not success:
        # All retries exhausted → dead-letter
        dest = os.path.join(base_dir, "dead-letter", f"{today_str}-{filename}")
        try:
            shutil.move(filepath, dest)
        except (OSError, IOError) as move_err:
            log.error("Failed to move entry to dead-letter: %s — %s",
                       filepath, move_err)
        log.error("Dead-lettered entry after exhausting retries: %s", filename)
        return False

    # Write sequence number back (after successful log write)
    write_sequence(base_dir, bot_name, seq)

    # Move inbox file to processed/
    dest = os.path.join(base_dir, "processed", f"{today_str}-{filename}")
    try:
        shutil.move(filepath, dest)
    except (OSError, IOError) as move_err:
        log.error("Failed to move processed file: %s — %s", filepath, move_err)
        # Non-fatal: entry is already in the log

    log.info("Processed %s → seq=%d sha256=%s log=%s",
             filename, seq, sha256_hex[:16], log_path)
    return True


def write_with_retry(log_path, entry, seq):
    """Write a JSON line to the log file with file locking and retries.

    Returns True on success, False if all retries failed.
    """
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            lock = FileLock(log_path)
            lock.acquire()
            try:
                line = json.dumps(entry, sort_keys=True) + "\n"
                with open(log_path, "a") as f:
                    f.write(line)
            finally:
                lock.release()
            # Non-blocking indexer trigger
            _trigger_indexer()
            return True
        except (OSError, IOError) as e:
            if attempt < max_retries:
                delay = 2 ** (attempt - 1)  # 1s, 2s, 4s
                log.warning("Write failed (attempt %d/%d) for seq=%d: %s. "
                            "Retrying in %ds...",
                            attempt, max_retries, seq, e, delay)
                time.sleep(delay)
            else:
                log.error("Write failed after %d attempts for seq=%d: %s",
                          max_retries, seq, e)
    return False




def _trigger_indexer():
    """Non-blocking indexer call. Best-effort, never fails the write."""
    try:
        subprocess.run(
            [sys.executable, "shadowlock_indexer.py", "--update"],
            cwd=os.path.dirname(os.path.abspath(__file__)),
            timeout=10,
            capture_output=True,
        )
    except Exception:
        pass


# ── Heartbeat ───────────────────────────────────────────────────────────────

class HeartbeatManager:
    """Manages periodic heartbeat emission to the JSONL ledger."""

    def __init__(self, base_dir, interval):
        self.base_dir = base_dir
        self.interval = interval
        self.last_heartbeat = 0.0

    def should_emit(self):
        """Return True if enough time has elapsed since last heartbeat."""
        return (time.time() - self.last_heartbeat) >= self.interval

    def emit(self, seq_num):
        """Write a heartbeat entry to today's log file."""
        now = datetime.datetime.utcnow()
        ts = now.strftime("%Y-%m-%dT%H:%M:%SZ")

        entry = {
            "schema_version": SCHEMA_VERSION,
            "event_type": "shadowlock_heartbeat",
            "bot_name": "shadowlock-writer",
            "timestamp_utc": ts,
            "sequence_number": seq_num,
        }

        entry_with_hash, sha256_hex = compute_entry_sha256(entry)
        entry_with_hash["entry_sha256"] = sha256_hex

        log_path = log_path_for_timestamp(self.base_dir, now)
        log_dir = os.path.dirname(log_path)
        os.makedirs(log_dir, exist_ok=True)

        success = write_with_retry(log_path, entry_with_hash, seq_num)
        if success:
            self.last_heartbeat = time.time()
            log.info("Heartbeat seq=%d sha256=%s", seq_num, sha256_hex[:16])
        else:
            log.error("Failed to write heartbeat entry")
        return success


# ── Service Lifecycle ───────────────────────────────────────────────────────

class ShadowlockService:
    """Main service orchestrating the poll loop."""

    def __init__(self):
        self.base_dir = resolve_base_dir()
        self.running = False
        self.shutdown_requested = False
        self.heartbeat_mgr = HeartbeatManager(self.base_dir, HEARTBEAT_INTERVAL_SECONDS)
        self.heartbeat_seq = 0

    def startup(self):
        """Perform startup sequence."""
        log.info("=" * 60)
        log.info("Shadowlock Writer v%s starting", SCHEMA_VERSION)
        log.info("=" * 60)
        log.info("Config:")
        log.info("  POLL_INTERVAL_SECONDS = %d", POLL_INTERVAL_SECONDS)
        log.info("  HEARTBEAT_INTERVAL_SECONDS = %d", HEARTBEAT_INTERVAL_SECONDS)
        log.info("  LOG_LEVEL = %s", LOG_LEVEL)
        log.info("  SHADOWLOCK_BASE_DIR = %s", self.base_dir)
        log.info("Paths:")
        log.info("  inbox:      %s", os.path.join(self.base_dir, "inbox"))
        log.info("  processed:  %s", os.path.join(self.base_dir, "processed"))
        log.info("  quarantine: %s", os.path.join(self.base_dir, "quarantine"))
        log.info("  dead-letter: %s", os.path.join(self.base_dir, "dead-letter"))
        log.info("  state:      %s", os.path.join(self.base_dir, "state"))
        log.info("  logs:       %s/logs/YYYY/MM/DD.jsonl", self.base_dir)
        log.info("  backtests:  %s", os.path.join(self.base_dir, "backtests"))
        log.info("  archive:    %s", os.path.join(self.base_dir, "archive"))

        ensure_subdirs(self.base_dir)

        # Read heartbeat seq from state file (use a special bot name)
        self.heartbeat_seq = read_sequence(self.base_dir, "shadowlock-writer")

        log.info("Startup complete. Entering main poll loop.")
        self.running = True

    def shutdown(self, signum=None, frame=None):
        """Initiate graceful shutdown."""
        if self.shutdown_requested:
            log.warning("Forced shutdown (second signal)")
            sys.exit(1)
        log.info("Shutdown requested (signal %s). Completing current file...", signum)
        self.shutdown_requested = True
        self.running = False

    def run(self):
        """Main poll loop."""
        self.startup()

        while not self.shutdown_requested:
            try:
                self._poll_once()
            except Exception as e:
                log.error("Unhandled error in poll loop: %s", e, exc_info=True)
                # Continue running — never crash the service

            # Sleep with interrupt support
            for _ in range(POLL_INTERVAL_SECONDS):
                if self.shutdown_requested:
                    break
                time.sleep(1)

        self._finalize()

    def _poll_once(self):
        """Single iteration of the poll loop."""
        inbox_dir = os.path.join(self.base_dir, "inbox")

        # Scan for JSON files, sorted by mtime (oldest first)
        pattern = os.path.join(inbox_dir, "*.json")
        try:
            files = sorted(
                glob.glob(pattern),
                key=os.path.getmtime,
            )
        except OSError as e:
            log.error("Cannot scan inbox: %s", e)
            return

        for filepath in files:
            if self.shutdown_requested:
                return
            process_inbox_file(self.base_dir, filepath)

        # Emit heartbeat if due
        self.heartbeat_seq = read_sequence(self.base_dir, "shadowlock-writer")
        if self.heartbeat_mgr.should_emit():
            self.heartbeat_seq += 1
            self.heartbeat_mgr.emit(self.heartbeat_seq)
            write_sequence(self.base_dir, "shadowlock-writer", self.heartbeat_seq)

    def _finalize(self):
        """Log shutdown and write final heartbeat."""
        last_seqs = {}
        state_dir = os.path.join(self.base_dir, "state")
        try:
            for f in glob.glob(os.path.join(state_dir, "*.seq")):
                bot = os.path.splitext(os.path.basename(f))[0]
                last_seqs[bot] = read_sequence(self.base_dir, bot)
        except OSError:
            pass

        log.info("Shutdown complete. Last sequence numbers: %s", last_seqs)


# ── Entry Point ─────────────────────────────────────────────────────────────

def main():
    signal.signal(signal.SIGTERM, lambda s, f: svc.shutdown(s, f))
    signal.signal(signal.SIGINT, lambda s, f: svc.shutdown(s, f))

    svc = ShadowlockService()
    svc.run()


if __name__ == "__main__":
    main()
