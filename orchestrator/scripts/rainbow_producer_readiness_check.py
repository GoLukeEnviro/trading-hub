#!/usr/bin/env python3
"""
Rainbow Producer Readiness Checker — read-only, no mutation.

Checks:
  - GET /health
  - GET /signals/latest
  - signal count > 0
  - freshest timestamp age <= freshness_max_seconds (default 900s)

Exit codes:
  0 → GREEN  (all checks passed)
  1 → RED/YELLOW (readiness failure, stale, unreachable, or empty)
  2 → Invalid arguments or configuration

Usage:
  python3 rainbow_producer_readiness_check.py
  python3 rainbow_producer_readiness_check.py --base-url http://127.0.0.1:8000
  python3 rainbow_producer_readiness_check.py --freshness-max-seconds 600
  python3 rainbow_producer_readiness_check.py --json
"""

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone


def _iso_to_dt(ts: str) -> datetime:
    """Parse ISO-8601 timestamp to timezone-aware datetime.
    Handles both 'Z' suffix and '+00:00' offset."""
    ts = ts.strip()
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    return datetime.fromisoformat(ts)


def _fetch_json(url: str, timeout: int = 10) -> dict | list | None:
    """GET a JSON endpoint. Returns parsed JSON or None on failure."""
    req = urllib.request.Request(url, method="GET")
    # No auth headers — read-only public endpoint.
    # If the endpoint requires auth, the caller should set --base-url accordingly.
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body)
    except urllib.error.URLError:
        return None
    except (json.JSONDecodeError, OSError):
        return None


def check_health(base_url: str) -> dict:
    """Check /health endpoint. Returns a dict with health check result."""
    url = f"{base_url.rstrip('/')}/health"
    data = _fetch_json(url)
    if data is None:
        return {"reachable": False, "status": "unreachable", "error": f"GET {url} failed"}
    status = data.get("status", "unknown") if isinstance(data, dict) else "unexpected_type"
    return {"reachable": True, "status": status, "raw": data}


def check_signals(base_url: str) -> dict:
    """Check /signals/latest. Returns dict with signal stats."""
    url = f"{base_url.rstrip('/')}/signals/latest"
    data = _fetch_json(url)
    if data is None:
        return {"reachable": False, "error": f"GET {url} failed"}

    signals = data if isinstance(data, list) else data.get("signals", [])
    if not isinstance(signals, list):
        return {"reachable": True, "count": 0, "error": "signals not a list"}

    timestamps = []
    for s in signals:
        if isinstance(s, dict):
            ts = s.get("timestamp", "")
            if ts:
                timestamps.append(ts)

    if not timestamps:
        return {"reachable": True, "count": len(signals), "freshest_ts": None, "error": "no timestamps in signals"}

    freshest_ts = max(timestamps)
    try:
        freshest_dt = _iso_to_dt(freshest_ts)
        now = datetime.now(timezone.utc)
        age_seconds = (now - freshest_dt).total_seconds()
    except ValueError:
        return {"reachable": True, "count": len(signals), "freshest_ts": freshest_ts, "error": f"unparseable timestamp: {freshest_ts}"}

    has_future = any(
        (isinstance(s, dict) and s.get("timestamp") and _iso_to_dt(s["timestamp"]) > now)
        for s in signals
    )

    return {
        "reachable": True,
        "count": len(signals),
        "freshest_ts": freshest_ts,
        "freshest_iso": freshest_dt.isoformat(),
        "age_seconds": round(age_seconds, 1),
        "has_future_timestamps": has_future,
        "first_signal_ts": min(timestamps) if timestamps else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rainbow Producer Readiness Checker — read-only",
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="Rainbow producer base URL (default: http://127.0.0.1:8000)",
    )
    parser.add_argument(
        "--freshness-max-seconds",
        type=int,
        default=900,
        help="Maximum age in seconds for freshest signal (default: 900)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output JSON instead of human-readable text",
    )
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")
    max_age = args.freshness_max_seconds

    if max_age <= 0:
        print("ERROR: --freshness-max-seconds must be positive", file=sys.stderr)
        return 2

    health_result = check_health(base_url)
    signals_result = check_signals(base_url)

    health_ok = health_result.get("reachable", False)
    signals_ok = signals_result.get("reachable", False) and signals_result.get("count", 0) > 0
    has_ts = signals_result.get("freshest_ts") is not None
    age = signals_result.get("age_seconds")
    fresh = age is not None and age <= max_age
    has_future = signals_result.get("has_future_timestamps", False)

    if not health_ok:
        verdict = "RED"
    elif not signals_ok or not has_ts:
        verdict = "RED"
    elif has_future:
        verdict = "YELLOW"
    elif fresh:
        verdict = "GREEN"
    else:
        verdict = "RED"

    exit_code = 0 if verdict == "GREEN" else 1

    if args.json:
        output = {
            "verdict": verdict,
            "health": health_result,
            "signals": signals_result,
            "freshness_max_seconds": max_age,
            "fresh": fresh,
        }
        print(json.dumps(output, default=str, indent=2))
    else:
        print(f"Verdict       : {verdict}")
        print(f"Health        : {health_result.get('status', 'unreachable')}")
        print(f"Signal count  : {signals_result.get('count', 0)}")
        print(f"Freshest ts   : {signals_result.get('freshest_ts', 'N/A')}")
        if age is not None:
            print(f"Age (seconds) : {age}")
        print(f"Freshness max : {max_age}s")
        print(f"Fresh         : {fresh}")
        if has_future:
            print(f"Future ts     : YES (YELLOW)")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
