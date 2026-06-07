#!/usr/bin/env python3
"""Shadowlock Writer — Docker HEALTHCHECK script.

Exits 0 (healthy) if a shadowlock_heartbeat entry was written to the
daily JSONL log within the last 10 minutes.
Exits 1 (unhealthy) otherwise.

Used by Dockerfile HEALTHCHECK only. Not part of the service runtime.
"""
import os
import sys
import json
import glob
import datetime

BASEDIR = os.environ.get("SHADOWLOCK_BASE_DIR", "/app/var/trading-shadowlock")
CUTOFF_SECONDS = 600  # 10 minutes


def main() -> int:
    now = datetime.datetime.utcnow()
    cutoff = now - datetime.timedelta(seconds=CUTOFF_SECONDS)

    logdir = os.path.join(BASEDIR, "logs", str(now.year), f"{now.month:02d}")
    if not os.path.isdir(logdir):
        print(f"NO_LOG_DIR: {logdir}")
        return 1

    files = sorted(glob.glob(os.path.join(logdir, "*.jsonl")), reverse=True)
    if not files:
        print(f"NO_LOG_FILES in {logdir}")
        return 1

    # Check today's log first, then yesterday's as fallback
    for logfile in files[:2]:
        try:
            with open(logfile, "r") as f:
                lines = f.readlines()
        except OSError as e:
            print(f"CANNOT_READ: {logfile}: {e}")
            continue

        # Read in reverse — most recent entry first
        for raw in reversed(lines):
            raw = raw.strip()
            if not raw:
                continue
            try:
                entry = json.loads(raw)
            except json.JSONDecodeError:
                continue

            if entry.get("event_type") != "shadowlock_heartbeat":
                continue

            ts = entry.get("timestamp_utc", "")
            if not ts.endswith("Z"):
                continue

            try:
                hb_time = datetime.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")
            except ValueError:
                continue

            if hb_time >= cutoff:
                print(f"HEALTHY: last heartbeat at {ts}")
                return 0
            else:
                # Most recent heartbeat is too old — no point reading further
                print(f"STALE_HEARTBEAT: last at {ts}, cutoff {cutoff.strftime('%Y-%m-%dT%H:%M:%SZ')}")
                return 1

    print("NO_RECENT_HEARTBEAT")
    return 1


if __name__ == "__main__":
    sys.exit(main())
