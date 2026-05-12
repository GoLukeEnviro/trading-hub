#!/usr/bin/env python3
"""
hermes_primo_bridge.py — Hermes ↔ PrimoAgent signal bridge.

Runs inside the hermes-agent container (or host venv).
Polls PrimoAgent every 60s via HTTP, validates signals, writes approved
signals to the Freqtrade shared signal bus.
"""

from __future__ import annotations

import os
import sys
import json
import time
import signal
import logging
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

# ── config ──────────────────────────────────────────────────────────
PRIMO_URL = os.environ.get("PRIMO_URL", "http://primo-agent:8420")
HERMES_PORT = int(os.environ.get("HERMES_BRIDGE_PORT", "9119"))
SIGNAL_BUS_DIR = Path(os.environ.get(
    "SIGNAL_BUS_DIR",
    "/home/hermes/projects/trading/freqtrade/shared/signals"
))
SIGNAL_BUS_FILE = SIGNAL_BUS_DIR / "latest_signal.json"
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "60"))
SIGNAL_FRESHNESS = int(os.environ.get("SIGNAL_FRESHNESS_SECONDS", "90"))
MAX_RETRIES = int(os.environ.get("MAX_RETRIES", "3"))

ALLOWED_PAIRS = os.environ.get(
    "ALLOWED_PAIRS",
    "BTC/USDT:USDT,ETH/USDT:USDT,SOL/USDT:USDT"
).split(",")

# ── logging ─────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] hermes-bridge: %(message)s",
    handlers=[logging.StreamHandler(sys.stderr)],
)
logger = logging.getLogger("hermes-bridge")

# ── state (in-memory for /status) ───────────────────────────────────
_state: Dict[str, Any] = {
    "hermes_status": "initializing",
    "primo_health": "unknown",
    "freqtrade_health": "unknown",
    "latest_signal": None,
    "signal_age_seconds": None,
    "last_error": None,
    "last_error_time": None,
    "polls_total": 0,
    "polls_success": 0,
    "uptime_start": datetime.now(timezone.utc).isoformat(),
}


def _set_error(msg: str) -> None:
    _state["last_error"] = msg
    _state["last_error_time"] = datetime.now(timezone.utc).isoformat()
    logger.error(msg)


def _clear_error() -> None:
    _state["last_error"] = None
    _state["last_error_time"] = None


# ── HTTP helpers ─────────────────────────────────────────────────────

def _http_get(url: str, timeout: int = 15) -> Optional[Dict[str, Any]]:
    """GET request with retries."""
    last_err = None
    for attempt in range(MAX_RETRIES):
        try:
            req = Request(url, headers={"Accept": "application/json"})
            with urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode())
        except (HTTPError, URLError, json.JSONDecodeError, OSError) as exc:
            last_err = exc
            wait = 2 ** attempt
            logger.warning(f"HTTP GET {url} attempt {attempt+1}/{MAX_RETRIES} failed: {exc}, waiting {wait}s")
            time.sleep(wait)
    _set_error(f"HTTP GET {url} failed after {MAX_RETRIES} attempts: {last_err}")
    return None


# ── signal validation ───────────────────────────────────────────────

def validate_signal(signal: Dict[str, Any]) -> bool:
    """
    Validate signal against the schema:
    - timestamp_utc: valid ISO-8601 UTC
    - freshness: <= SIGNAL_FRESHNESS seconds
    - pair: one of ALLOWED_PAIRS
    - direction: "long" or "none"
    - confidence: numeric 0.0..1.0
    - veto: False → ok, True → invalid
    - risk_cap_percent: <= 1.0
    """
    if not isinstance(signal, dict):
        logger.warning("Signal is not a dict")
        return False

    # timestamp_utc validity
    ts_str = signal.get("timestamp_utc", "")
    try:
        ts = datetime.fromisoformat(ts_str)
        age = (datetime.now(timezone.utc) - ts).total_seconds()
        if age > SIGNAL_FRESHNESS:
            logger.warning(f"Signal stale: age={age:.1f}s > {SIGNAL_FRESHNESS}s")
            return False
    except (ValueError, TypeError) as exc:
        logger.warning(f"Invalid timestamp_utc: {ts_str!r} ({exc})")
        return False

    # pair
    if signal.get("pair") not in ALLOWED_PAIRS:
        logger.warning(f"Pair not allowed: {signal.get('pair')!r}")
        return False

    # direction
    if signal.get("direction") not in ("long", "none"):
        logger.warning(f"Invalid direction: {signal.get('direction')!r}")
        return False

    # confidence
    try:
        conf = float(signal.get("confidence", -1))
        if not (0.0 <= conf <= 1.0):
            logger.warning(f"Confidence out of range: {conf}")
            return False
    except (ValueError, TypeError):
        logger.warning(f"Non-numeric confidence: {signal.get('confidence')!r}")
        return False

    # veto
    if signal.get("veto") is True:
        logger.info("Signal vetoed — not forwarding")
        return False

    # risk_cap_percent
    try:
        rcp = float(signal.get("risk_cap_percent", 2.0))
        if rcp > 1.0:
            logger.warning(f"risk_cap_percent exceeds 1.0: {rcp}")
            return False
    except (ValueError, TypeError):
        pass  # non-critical field

    return True


# ── main loop ────────────────────────────────────────────────────────

def _poll_primo() -> None:
    """Fetch signals from PrimoAgent, validate, write to signal bus."""
    _state["polls_total"] += 1

    # Check Primo health first
    health = _http_get(f"{PRIMO_URL}/health")
    if health and health.get("status") == "healthy":
        _state["primo_health"] = "healthy"
    else:
        _state["primo_health"] = "unreachable"
        _set_error("PrimoAgent health check failed")
        return

    # Get signals for all pairs
    data = _http_get(f"{PRIMO_URL}/signal?pair=BTC/USDT:USDT")
    if data is None:
        _set_error("PrimoAgent signal endpoint unreachable")
        return

    # Validate
    if validate_signal(data):
        data["approved_by"] = "hermes"
        _state["latest_signal"] = data
        _state["signal_age_seconds"] = (
            datetime.now(timezone.utc) -
            datetime.fromisoformat(data["timestamp_utc"])
        ).total_seconds()
        _state["polls_success"] += 1

        # Write atomically to signal bus
        SIGNAL_BUS_DIR.mkdir(parents=True, exist_ok=True)
        tmp = SIGNAL_BUS_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2))
        tmp.rename(SIGNAL_BUS_FILE)

        logger.info(
            f"Signal {data['direction']} conf={data['confidence']:.4f} "
            f"→ {SIGNAL_BUS_FILE}"
        )
        _clear_error()
    else:
        logger.info(f"Signal validation FAILED for {data.get('pair', '?')}")
        _state["latest_signal"] = None


def _check_freqtrade() -> None:
    """Basic check that shared volume is writable."""
    if SIGNAL_BUS_DIR.exists() and os.access(SIGNAL_BUS_DIR, os.W_OK):
        _state["freqtrade_health"] = "shared_volume_ok"
    else:
        _state["freqtrade_health"] = "shared_volume_missing"


def run_loop() -> None:
    """Main polling loop."""
    logger.info(f"Starting Hermes-Primo bridge. Primo={PRIMO_URL}, poll={POLL_INTERVAL}s")
    _state["hermes_status"] = "running"

    while True:
        try:
            _poll_primo()
            _check_freqtrade()
        except Exception as exc:
            _set_error(f"Unexpected poll error: {exc}")
            traceback.print_exc()

        time.sleep(POLL_INTERVAL)


# ── /status endpoint (HTTP inside hermes-agent) ─────────────────────

def _serve_status():
    """Poor man's HTTP status server."""
    from http.server import HTTPServer, BaseHTTPRequestHandler

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/status":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(_state, indent=2, default=str).encode())
            elif self.path == "/health":
                self.send_response(200 if _state["hermes_status"] == "running" else 503)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                payload = {
                    "status": "ok" if _state["hermes_status"] == "running" else "degraded",
                    "primo_health": _state["primo_health"],
                    "freqtrade_health": _state["freqtrade_health"],
                }
                self.wfile.write(json.dumps(payload).encode())
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format, *args):
            pass  # suppress access logs

    server = HTTPServer(("0.0.0.0", HERMES_PORT), Handler)
    logger.info(f"/status endpoint on :{HERMES_PORT}")
    server.serve_forever()


# ── main ─────────────────────────────────────────────────────────────

def main():
    import threading

    # Start status server in a thread
    status_thread = threading.Thread(target=_serve_status, daemon=True)
    status_thread.start()

    # Run main poll loop
    run_loop()


if __name__ == "__main__":
    main()
