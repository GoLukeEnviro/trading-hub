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

v2.1 Changes (2026-06-26 Cron History Repair):
  - DB_PATH moved from read-only Git mount to canonical state directory
  - Added HERMES_HEARTBEAT_DB_PATH env var override
  - Clear PermissionError on unwritable path

Usage: python3 heartbeat_writer.py
  - stderr: log messages
  - stdout: silent when all OK
  - exit 0 always (never crashes)
"""

import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError

# Canonical DB path in writable state directory
# Override via HERMES_HEARTBEAT_DB_PATH env var for testing
DB_PATH = Path(os.environ.get(
    "HERMES_HEARTBEAT_DB_PATH",
    "/opt/data/profiles/orchestrator/state/hermes_heartbeat.sqlite"
))

BOTS = [
    {
        "bot_name": "freqforge",
        "container_name": "trading-freqtrade-freqforge-1",
        "api_port": 8080,  # internal container port (Docker network)
    },
    {
        "bot_name": "regime-hybrid",
        "container_name": "trading-freqtrade-regime-hybrid-1",
        "api_port": 8080,
    },
    {
        "bot_name": "freqforge-canary",
        "container_name": "trading-freqtrade-freqforge-canary-1",
        "api_port": 8080,
    },
    {
        "bot_name": "trading-freqai-rebel-1",
        "container_name": "trading-freqai-rebel-1",
        "api_port": 8080,
    },
]

# Cache for Docker network IPs (resolved dynamically)
_docker_ip_cache: dict[str, str | None] = {}


def resolve_docker_ip(container_name: str) -> str | None:
    """Resolve container IP on trading_hermes-net via docker inspect (read-only)."""
    if container_name in _docker_ip_cache:
        return _docker_ip_cache[container_name]
    try:
        r = subprocess.run(
            ["docker", "inspect", container_name, "--format",
             '{{range $k,$v := .NetworkSettings.Networks}}{{$k}}={{$v.IPAddress}}\n{{end}}'],
            capture_output=True, text=True, timeout=5,
        )
        for line in r.stdout.strip().splitlines():
            parts = line.split("=", 1)
            if len(parts) == 2 and ("hermes-net" in parts[0]):
                ip = parts[1].strip()
                _docker_ip_cache[container_name] = ip
                return ip
    except Exception:
        pass
    _docker_ip_cache[container_name] = None
    return None

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


def rest_api_get(host: str, port: int, endpoint: str, timeout: int = 10) -> str | None:
    """Direct REST API call (no Docker). Returns response text or None."""
    url = f"http://{host}:{port}{endpoint}"
    try:
        req = Request(url)
        resp = urlopen(req, timeout=timeout)
        if resp.status == 200:
            return resp.read().decode()
    except Exception:
        pass
    return None


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
    """Reach bot via Docker network IP first, then fallback to docker exec."""
    # 1. Try Docker network IP (bots are on trading_hermes-net, port 8080)
    docker_ip = resolve_docker_ip(container)
    if docker_ip:
        result = rest_api_get(docker_ip, port, endpoint, timeout=5)
        if result is not None:
            return result

    # 2. Try localhost (host port mapping, works if network=host)
    result = rest_api_get("127.0.0.1", port, endpoint, timeout=2)
    if result is not None:
        return result

    # 3. Docker exec fallback (blocked by EXEC=0 proxy but keep for compat)
    if detect_docker():
        return docker_curl(container, port, endpoint)

    log(f"No path to {container}:{port} — all methods failed")
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

        conn.close()
        log("Heartbeat cycle complete")
    except Exception as exc:
        log(f"Fatal error (still exiting 0): {exc}")

    # Always exit 0
    sys.exit(0)


if __name__ == "__main__":
    main()
