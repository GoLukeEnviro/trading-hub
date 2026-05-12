#!/usr/bin/env python3
"""
hermes_primo_bridge.py — Hermes ↔ PrimoAgent signal bridge (per-pair).

Runs in its own Docker container (hermes-bridge).
Polls PrimoAgent every 60s for ALL allowed pairs, validates signals,
writes approved signals to per-pair JSON files on the shared signal bus.

Signal files:
  /shared/signals/BTC_USDT_USDT.json
  /shared/signals/ETH_USDT_USDT.json
  /shared/signals/SOL_USDT_USDT.json

Also writes latest_signal.json as debug summary only (not used by strategy).
"""

from __future__ import annotations

import os
import sys
import json
import time
import signal as signal_module
import logging
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

# ── config ──────────────────────────────────────────────────────────
PRIMO_URL = os.environ.get("PRIMO_URL", "http://primo-agent:8420")
BRIDGE_PORT = int(os.environ.get("HERMES_BRIDGE_PORT", "9118"))
SIGNAL_BUS_DIR = Path(os.environ.get(
    "SIGNAL_BUS_DIR",
    "/shared/signals"
))
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "60"))
SIGNAL_FRESHNESS = int(os.environ.get("SIGNAL_FRESHNESS_SECONDS", "90"))
MAX_RETRIES = int(os.environ.get("MAX_RETRIES", "3"))

ALLOWED_PAIRS = os.environ.get(
    "ALLOWED_PAIRS",
    "BTC/USDT:USDT,ETH/USDT:USDT,SOL/USDT:USDT"
).split(",")

# ── pair → filename mapping ─────────────────────────────────────────
def _pair_to_filename(pair: str) -> str:
    """BTC/USDT:USDT → BTC_USDT_USDT.json"""
    return pair.replace("/", "_").replace(":", "_") + ".json"


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
    "per_pair_signals": {},       # pair → signal dict
    "signal_ages_seconds": {},    # pair → age in seconds
    "last_error": None,
    "last_error_time": None,
    "polls_total": 0,
    "polls_success": 0,
    "polls_failed": 0,
    "uptime_start": datetime.now(timezone.utc).isoformat(),
}


def _set_error(msg: str) -> None:
    _state["last_error"] = msg
    _state["last_error_time"] = datetime.now(timezone.utc).isoformat()
    logger.error(msg)


def _clear_error() -> None:
    _state["last_error"] = None
    _state["last_error_time"] = None


# ── graceful shutdown ───────────────────────────────────────────────
_shutdown = False

def _handle_signal(sig, frame):
    global _shutdown
    logger.info(f"Received signal {sig}, shutting down...")
    _shutdown = True


signal_module.signal(signal_module.SIGTERM, _handle_signal)
signal_module.signal(signal_module.SIGINT, _handle_signal)


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
    """Fetch signals for ALL pairs from PrimoAgent, validate each, write per-pair files."""
    _state["polls_total"] += 1

    # Check Primo health first
    health = _http_get(f"{PRIMO_URL}/health")
    if health and health.get("status") == "healthy":
        _state["primo_health"] = "healthy"
    else:
        _state["primo_health"] = "unreachable"
        _set_error("PrimoAgent health check failed")
        return

    successes = 0
    for pair in ALLOWED_PAIRS:
        data = _http_get(f"{PRIMO_URL}/signal?pair={pair}")
        if data is None:
            logger.warning(f"Signal fetch failed for {pair}")
            _state["per_pair_signals"].pop(pair, None)
            continue

        if validate_signal(data):
            data["approved_by"] = "hermes"
            _state["per_pair_signals"][pair] = data

            age = (
                datetime.now(timezone.utc) -
                datetime.fromisoformat(data["timestamp_utc"])
            ).total_seconds()
            _state["signal_ages_seconds"][pair] = round(age, 1)

            # Write per-pair signal file atomically
            filename = _pair_to_filename(pair)
            signal_file = SIGNAL_BUS_DIR / filename
            SIGNAL_BUS_DIR.mkdir(parents=True, exist_ok=True)
            tmp = signal_file.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, indent=2))
            tmp.rename(signal_file)

            logger.info(
                f"[{pair}] Signal {data['direction']} conf={data['confidence']:.4f} "
                f"→ {signal_file}"
            )
            successes += 1
        else:
            logger.warning(f"[{pair}] Signal validation FAILED")
            _state["per_pair_signals"].pop(pair, None)
            # Remove stale signal file so Freqtrade fails closed
            stale_file = SIGNAL_BUS_DIR / _pair_to_filename(pair)
            if stale_file.exists():
                stale_file.unlink()
                logger.info(f"Removed stale signal file for {pair}")

    if successes > 0:
        _state["polls_success"] += successes
        _clear_error()

    # Write debug summary (not consumed by strategy)
    _write_debug_summary()


def _write_debug_summary() -> None:
    """Write latest_signal.json as a human-readable debug summary only."""
    summary = {
        "schema_version": "1.0/debug",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "source": "hermes-bridge",
        "polls_total": _state["polls_total"],
        "polls_success": _state["polls_success"],
        "polls_failed": _state["polls_failed"],
        "primo_health": _state["primo_health"],
        "signals": _state["per_pair_signals"],
    }
    debug_file = SIGNAL_BUS_DIR / "latest_signal.json"
    tmp = debug_file.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(summary, indent=2))
        tmp.rename(debug_file)
    except (OSError, IOError) as exc:
        logger.warning(f"Cannot write debug summary: {exc}")


def _check_freqtrade() -> None:
    """Basic check that shared volume is writable."""
    if SIGNAL_BUS_DIR.exists() and os.access(SIGNAL_BUS_DIR, os.W_OK):
        _state["freqtrade_health"] = "shared_volume_ok"
    else:
        _state["freqtrade_health"] = "shared_volume_missing"


def run_loop() -> None:
    """Main polling loop."""
    logger.info(f"Starting Hermes-Primo bridge. Primo={PRIMO_URL}, poll={POLL_INTERVAL}s")
    logger.info(f"Pairs: {ALLOWED_PAIRS}")
    logger.info(f"Signal bus: {SIGNAL_BUS_DIR}")
    _state["hermes_status"] = "running"

    while not _shutdown:
        try:
            _poll_primo()
            _check_freqtrade()
        except Exception as exc:
            _state["polls_failed"] += 1
            _set_error(f"Unexpected poll error: {exc}")
            traceback.print_exc()

        for _ in range(POLL_INTERVAL):
            if _shutdown:
                break
            time.sleep(1)


# ── /status and /health endpoint ────────────────────────────────────

def _serve_status():
    """HTTP status server for health checks and monitoring."""
    from http.server import HTTPServer, BaseHTTPRequestHandler

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/status":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(_state, indent=2, default=str).encode())
            elif self.path == "/health":
                is_ok = _state["hermes_status"] == "running"
                self.send_response(200 if is_ok else 503)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                payload = {
                    "status": "ok" if is_ok else "degraded",
                    "primo_health": _state["primo_health"],
                    "freqtrade_health": _state["freqtrade_health"],
                    "polls_total": _state["polls_total"],
                    "polls_failed": _state["polls_failed"],
                }
                self.wfile.write(json.dumps(payload).encode())
            elif self.path == "/":
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"Hermes Bridge - status at /status, health at /health")
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format, *args):
            pass  # suppress access logs

    server = HTTPServer(("0.0.0.0", BRIDGE_PORT), Handler)
    logger.info(f"/status and /health endpoints on :{BRIDGE_PORT}")
    server.serve_forever()


# ── main ─────────────────────────────────────────────────────────────

def main():
    import threading

    # Start status server in a thread
    status_thread = threading.Thread(target=_serve_status, daemon=True)
    status_thread.start()

    # Run main poll loop
    try:
        run_loop()
    except KeyboardInterrupt:
        logger.info("Shutdown requested via keyboard interrupt")
    finally:
        _state["hermes_status"] = "stopped"
        logger.info("Hermes bridge stopped cleanly")


if __name__ == "__main__":
    main()
