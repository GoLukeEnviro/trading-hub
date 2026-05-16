#!/usr/bin/env python3
"""
trading_hub_sync.py — Persistent bridge between ai-hedge-fund-crypto signals
and the FreqForge ShadowLogger.

Watches the signal file for updates (mtime-based). When a new signal arrives,
triggers a ShadowLogger poll cycle so every bot trade gets evaluated against
the fresh signal deck.

Usage:
    python3 trading_hub_sync.py                    # daemon, polls every 120s
    python3 trading_hub_sync.py --interval 60      # custom interval
    python3 trading_hub_sync.py --once             # single sync cycle
    python3 trading_hub_sync.py --status           # print status and exit

Data flow:
    ai-hedge-fund-crypto container
        → /output/latest/hermes_signal.json  (signal file)
        → this script detects change
        → invokes freqforge_shadow.run_poll()
        → shadow_decisions.jsonl updated
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
import logging
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

# ── Paths ──────────────────────────────────────────────────────────────
TRADING_ROOT = Path("/home/hermes/projects/trading")
SIGNAL_FILE = TRADING_ROOT / "ai-hedge-fund-crypto" / "output" / "latest" / "hermes_signal.json"
SHADOW_SCRIPT = TRADING_ROOT / "tools" / "freqforge" / "freqforge_shadow.py"
SHADOW_DECISIONS = TRADING_ROOT / "var" / "freqforge" / "shadow_decisions.jsonl"
SYNC_STATE_FILE = TRADING_ROOT / "var" / "freqforge" / "sync_state.json"
SYNC_LOG_DIR = TRADING_ROOT / "orchestrator" / "logs"
SYNC_LOG = SYNC_LOG_DIR / "trading_hub_sync.log"

# ── Defaults ───────────────────────────────────────────────────────────
DEFAULT_INTERVAL = 120  # seconds between checks

# ── Logging ────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] hub-sync: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stderr),
    ],
)
logger = logging.getLogger("hub-sync")


def setup_file_logging():
    SYNC_LOG_DIR.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(SYNC_LOG)
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(fh)


# ── State ──────────────────────────────────────────────────────────────
_run = True


def _handle_signal(signum, frame):
    global _run
    _run = False
    logger.info("Received shutdown signal, exiting gracefully...")


signal.signal(signal.SIGTERM, _handle_signal)
signal.signal(signal.SIGINT, _handle_signal)


class SyncState:
    """Persistent state for the bridge."""

    def __init__(self):
        self.last_signal_mtime: float = 0.0
        self.last_signal_ts: str = ""
        self.last_poll_ts: str = ""
        self.poll_count: int = 0
        self.poll_errors: int = 0
        self.skipped_count: int = 0
        self.start_time: str = datetime.now(timezone.utc).isoformat()

    def load(self) -> "SyncState":
        if SYNC_STATE_FILE.exists():
            try:
                data = json.loads(SYNC_STATE_FILE.read_text())
                self.last_signal_mtime = data.get("last_signal_mtime", 0.0)
                self.last_signal_ts = data.get("last_signal_ts", "")
                self.last_poll_ts = data.get("last_poll_ts", "")
                self.poll_count = data.get("poll_count", 0)
                self.poll_errors = data.get("poll_errors", 0)
                self.skipped_count = data.get("skipped_count", 0)
                self.start_time = data.get("start_time", self.start_time)
            except (json.JSONDecodeError, OSError):
                pass
        return self

    def save(self):
        SYNC_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "last_signal_mtime": self.last_signal_mtime,
            "last_signal_ts": self.last_signal_ts,
            "last_poll_ts": self.last_poll_ts,
            "poll_count": self.poll_count,
            "poll_errors": self.poll_errors,
            "skipped_count": self.skipped_count,
            "start_time": self.start_time,
        }
        tmp = SYNC_STATE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2))
        tmp.rename(SYNC_STATE_FILE)


# ── Signal detection ───────────────────────────────────────────────────

def read_signal_metadata() -> Dict[str, Any]:
    """Read signal file, return metadata without parsing full content."""
    if not SIGNAL_FILE.exists():
        return {"exists": False}
    try:
        mtime = SIGNAL_FILE.stat().st_mtime
        data = json.loads(SIGNAL_FILE.read_text())
        return {
            "exists": True,
            "mtime": mtime,
            "timestamp_utc": data.get("timestamp_utc", "unknown"),
            "pairs": list(data.get("pairs", {}).keys()),
            "global_risk_mode": data.get("global_risk_mode", "unknown"),
        }
    except (json.JSONDecodeError, OSError) as e:
        return {"exists": True, "error": str(e)}


def signal_has_changed(state: SyncState) -> bool:
    """Check if signal file has been updated since last poll."""
    if not SIGNAL_FILE.exists():
        return False
    try:
        mtime = SIGNAL_FILE.stat().st_mtime
        return mtime > state.last_signal_mtime
    except OSError:
        return False


# ── Shadow poll invocation ────────────────────────────────────────────

def run_shadow_poll() -> Dict[str, Any]:
    """Run freqforge_shadow.py as a subprocess and capture output."""
    cmd = [sys.executable, str(SHADOW_SCRIPT)]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(TRADING_ROOT / "tools" / "freqforge"),
        )
        if result.returncode != 0:
            logger.error("Shadow poll stderr: %s", result.stderr[:500])
            return {"ok": False, "error": result.stderr[:200]}

        try:
            summary = json.loads(result.stdout)
        except json.JSONDecodeError:
            summary = {"raw_output": result.stdout[:500]}

        return {"ok": True, "summary": summary}

    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Shadow poll timed out (60s)"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── Single sync cycle ──────────────────────────────────────────────────

def sync_cycle(state: SyncState) -> bool:
    """Execute one sync cycle. Returns True if poll was triggered."""
    meta = read_signal_metadata()

    if not meta.get("exists"):
        logger.warning("Signal file not found: %s", SIGNAL_FILE)
        return False

    if "error" in meta:
        logger.warning("Signal file unreadable: %s", meta["error"])
        return False

    if not signal_has_changed(state):
        state.skipped_count += 1
        return False

    signal_ts = meta.get("timestamp_utc", "unknown")
    logger.info(
        "New signal detected (ts=%s, mtime=%.1f). Triggering shadow poll...",
        signal_ts, meta["mtime"],
    )

    result = run_shadow_poll()
    now = datetime.now(timezone.utc).isoformat()

    if result["ok"]:
        state.poll_count += 1
        state.last_poll_ts = now
        state.last_signal_mtime = meta["mtime"]
        state.last_signal_ts = signal_ts
        summary = result.get("summary", {})
        events = summary.get("new_events", 0)
        bots = summary.get("bots_polled", 0)
        logger.info("Poll complete: %d bots, %d new events", bots, events)
    else:
        state.poll_errors += 1
        logger.error("Poll failed: %s", result.get("error", "unknown"))

    state.save()
    return True


# ── Status output ──────────────────────────────────────────────────────

def print_status(state: SyncState):
    """Print current status of the bridge."""
    meta = read_signal_metadata()
    print("## Trading Hub Sync Status")
    print(f"  Signal file:     {SIGNAL_FILE}")
    print(f"  Signal exists:   {meta.get('exists', False)}")
    if meta.get("exists") and "error" not in meta:
        print(f"  Signal ts:       {meta.get('timestamp_utc', 'unknown')}")
        print(f"  Signal pairs:    {', '.join(meta.get('pairs', []))}")
        print(f"  Risk mode:       {meta.get('global_risk_mode', 'unknown')}")

    print(f"  Shadow script:   {SHADOW_SCRIPT}")
    print(f"  Decisions log:   {SHADOW_DECISIONS}")
    print(f"  Decisions exist: {SHADOW_DECISIONS.exists()}")
    if SHADOW_DECISIONS.exists():
        lines = SHADOW_DECISIONS.read_text().strip().split("\n")
        print(f"  Decisions count: {len(lines)}")

    print(f"\n  Bridge state:")
    print(f"    Last signal mtime:  {state.last_signal_mtime}")
    print(f"    Last signal ts:     {state.last_signal_ts}")
    print(f"    Last poll ts:       {state.last_poll_ts}")
    print(f"    Total polls:        {state.poll_count}")
    print(f"    Poll errors:        {state.poll_errors}")
    print(f"    Skipped (no change): {state.skipped_count}")
    print(f"    Running since:      {state.start_time}")


# ── Main ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Trading Hub Sync — bridge ai-hedge-fund-crypto signals to ShadowLogger"
    )
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL,
                        help=f"Poll interval in seconds (default: {DEFAULT_INTERVAL})")
    parser.add_argument("--once", action="store_true",
                        help="Run a single sync cycle and exit")
    parser.add_argument("--status", action="store_true",
                        help="Print current status and exit")
    args = parser.parse_args()

    setup_file_logging()
    state = SyncState().load()

    if args.status:
        print_status(state)
        return

    if args.once:
        logger.info("Running single sync cycle...")
        # Force poll even if mtime hasn't changed
        if SIGNAL_FILE.exists():
            state.last_signal_mtime = 0.0
        sync_cycle(state)
        return

    logger.info(
        "Starting Trading Hub Sync daemon (interval=%ds, signal=%s)",
        args.interval, SIGNAL_FILE,
    )

    while _run:
        try:
            sync_cycle(state)
        except Exception:
            logger.error("Unexpected error in sync cycle:\n%s", traceback.format_exc())
            state.poll_errors += 1
            state.save()

        # Sleep in small increments for responsive shutdown
        for _ in range(args.interval):
            if not _run:
                break
            time.sleep(1)

    logger.info(
        "Shutdown complete. polls=%d, errors=%d, skipped=%d",
        state.poll_count, state.poll_errors, state.skipped_count,
    )


if __name__ == "__main__":
    main()
