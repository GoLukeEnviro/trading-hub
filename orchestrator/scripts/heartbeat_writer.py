#!/usr/bin/env python3
"""
heartbeat_writer.py v2
Polls all active Freqtrade bots via REST API (direct or via docker exec),
writes results into a SQLite heartbeat database.

v2 Changes (2026-05-22 Cron Wiring Repair):
  - Docker-availability detection
  - Direct REST API calls as primary method
  - Docker exec as fallback (when Docker socket available)
  - Graceful degradation: no false "unreachable" when Docker absent

Usage: python3 heartbeat_writer.py
  - stderr: log messages
  - stdout: silent when all OK
  - exit 0 always (never crashes)
"""

import json
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError

from fleet_api_client import freqtrade_api_get, INTER_BOT_DELAY

DB_PATH = Path("/home/hermes/projects/trading/orchestrator/state/hermes_heartbeat.sqlite")

BOTS = [
    {
        "bot_name": "freqforge",
        "container_name": "freqtrade-freqforge",
        "api_port": 8086,
    },
    {
        "bot_name": "regime-hybrid",
        "container_name": "freqtrade-regime-hybrid",
        "api_port": 8085,
    },
    {
        "bot_name": "momentum",
        "container_name": "freqtrade-momentum",
        "api_port": 8082,
    },
    {
        "bot_name": "freqforge-canary",
        "container_name": "freqtrade-freqforge-canary",
        "api_port": 8081,
    },
    {
        "bot_name": "freqai-rebel",
        "container_name": "freqai-rebel",
        "api_port": 8080,
    },
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS heartbeats (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp     TEXT    NOT NULL,
    bot_name      TEXT    NOT NULL,
    container_name TEXT   NOT NULL,
    api_port      INTEGER NOT NULL,
    api_ok        INTEGER,
    status        TEXT,
    open_trades   INTEGER,
    raw_json      TEXT
);
"""

# Docker availability cache
_docker_available = None


def log(msg: str) -> None:
    """Log to stderr."""
    print(f"[heartbeat] {msg}", file=sys.stderr)


def detect_docker() -> bool:
    """Check if Docker socket exists and daemon is reachable."""
    global _docker_available
    if _docker_available is not None:
        return _docker_available

    if not Path("/var/run/docker.sock").is_socket():
        _docker_available = False
        return False

    try:
        r = subprocess.run(["docker", "info"], capture_output=True, text=True, timeout=5)
        _docker_available = r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        _docker_available = False

    return _docker_available


def rest_api_get(host: str, port: int, endpoint: str, timeout: int = 3) -> str | None:
    """Direct REST API call with retry/backoff. Returns response text or None."""
    return freqtrade_api_get(host, port, endpoint, timeout=timeout)


def docker_curl(container: str, port: int, endpoint: str, timeout: int = 10) -> str | None:
    """
    Run curl inside a container via docker exec.
    Returns stdout string on success, None on any failure.
    """
    url = f"http://localhost:{port}{endpoint}"
    try:
        result = subprocess.run(
            [
                "docker", "exec", container,
                "curl", "-s", "--max-time", str(timeout), url,
            ],
            capture_output=True,
            text=True,
            timeout=timeout + 5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        return None
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
        log(f"docker exec failed for {container} {url}: {exc}")
        return None


def api_get(container: str, port: int, endpoint: str) -> str | None:
    """Try direct REST API first, then Docker exec fallback."""
    # Try direct REST API on multiple host addresses
    for host in ["127.0.0.1", "172.18.0.1", "172.19.0.1", "172.20.0.1"]:
        result = rest_api_get(host, port, endpoint, timeout=3)
        if result is not None:
            return result

    # Fallback to Docker exec if available
    if detect_docker():
        return docker_curl(container, port, endpoint)

    return None


def ping_bot(container: str, port: int) -> bool:
    """Return True if the bot responds with pong to /api/v1/ping."""
    raw = api_get(container, port, "/api/v1/ping")
    if raw is None:
        return False
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data.get("status") == "pong"
        return "pong" in raw.lower()
    except json.JSONDecodeError:
        return "pong" in raw.lower()


def fetch_status(container: str, port: int) -> list:
    """Fetch open trades from /api/v1/status."""
    raw = api_get(container, port, "/api/v1/status")
    if raw is None:
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return data
        return []
    except json.JSONDecodeError:
        return []


def fetch_count(container: str, port: int) -> dict | None:
    """Fetch trade count from /api/v1/count."""
    raw = api_get(container, port, "/api/v1/count")
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def init_db() -> sqlite3.Connection:
    """Ensure DB and table exist, return connection."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(SCHEMA)
    conn.commit()
    return conn


def poll_bot(bot: dict) -> dict:
    """Poll a single bot and return a row dict for insertion."""
    container = bot["container_name"]
    port = bot["api_port"]
    now = datetime.now(timezone.utc).isoformat()

    row = {
        "timestamp": now,
        "bot_name": bot["bot_name"],
        "container_name": container,
        "api_port": port,
        "api_ok": 0,
        "status": "unreachable",
        "open_trades": 0,
        "raw_json": None,
    }

    # Step 1: ping
    if not ping_bot(container, port):
        docker_ok = detect_docker()
        if not docker_ok:
            log(f"{bot['bot_name']} ({container}): no Docker + no REST — skipping (infrastructure limitation)")
            row["status"] = "no_access"
        else:
            log(f"{bot['bot_name']} ({container}): ping failed, marking unreachable")
        return row

    row["api_ok"] = 1
    row["status"] = "running"

    # Step 2: status (open trades)
    trades = fetch_status(container, port)
    row["open_trades"] = len(trades)

    # Step 3: count
    count_data = fetch_count(container, port)

    # Combine raw data
    combined = {
        "status": trades,
        "count": count_data,
    }
    try:
        row["raw_json"] = json.dumps(combined)
    except (TypeError, ValueError):
        row["raw_json"] = None

    log(f"{bot['bot_name']} ({container}): OK, {row['open_trades']} open trades")
    return row


def insert_row(conn: sqlite3.Connection, row: dict) -> None:
    """Insert one heartbeat row."""
    conn.execute(
        """
        INSERT INTO heartbeats (timestamp, bot_name, container_name, api_port, api_ok, status, open_trades, raw_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            row["timestamp"],
            row["bot_name"],
            row["container_name"],
            row["api_port"],
            row["api_ok"],
            row["status"],
            row["open_trades"],
            row["raw_json"],
        ),
    )
    conn.commit()


def main() -> None:
    try:
        docker_ok = detect_docker()
        mode = "docker" if docker_ok else "rest-api-only"
        log(f"Mode: {mode}")

        conn = init_db()
        log(f"DB initialized at {DB_PATH}")

        for bot in BOTS:
            try:
                row = poll_bot(bot)
                insert_row(conn, row)
            except Exception as exc:
                log(f"Error polling {bot['bot_name']}: {exc}")
            time.sleep(INTER_BOT_DELAY)

        conn.close()
        log("Heartbeat cycle complete")
    except Exception as exc:
        log(f"Fatal error (still exiting 0): {exc}")

    # Always exit 0
    sys.exit(0)


if __name__ == "__main__":
    main()
