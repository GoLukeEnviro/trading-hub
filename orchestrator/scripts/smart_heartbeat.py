#!/usr/bin/env python3
"""smart_heartbeat.py — defensive signal freshness watchdog.

Runs every 10 minutes. If the ai-hedge-fund-crypto signal is missing or older
than SMART_TRIGGER_MIN, trigger ai_hedge_signal_heartbeat.sh. This keeps the
trading_pipeline.py hard stale block (25min) from being reached during normal
operation.

No trading execution. Dry-run safe. Only triggers signal generation.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

PROJECT = Path("/home/hermes/projects/trading")
SIGNAL = PROJECT / "ai-hedge-fund-crypto/output/latest/hermes_signal.json"
HEARTBEAT = PROJECT / "orchestrator/scripts/ai_hedge_signal_heartbeat.sh"
LOG = PROJECT / "orchestrator/logs/smart_heartbeat.log"
SMART_TRIGGER_MIN = 15.0


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a") as f:
        f.write(f"[{ts}] {msg}\n")


def signal_age_min() -> float | None:
    if not SIGNAL.exists():
        return None
    try:
        data = json.loads(SIGNAL.read_text())
        ts_s = data.get("generated_at") or data.get("timestamp_utc") or data.get("timestamp")
        if not ts_s:
            return None
        ts = datetime.fromisoformat(ts_s.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - ts).total_seconds() / 60.0
    except Exception as e:
        log(f"age_check_error={e}")
        return None


def main() -> int:
    age = signal_age_min()
    if age is not None and age <= SMART_TRIGGER_MIN:
        log(f"OK age={age:.1f}min <= {SMART_TRIGGER_MIN:.1f}min")
        return 0

    reason = "missing_or_invalid" if age is None else f"age={age:.1f}min"
    log(f"TRIGGER heartbeat reason={reason}")
    r = subprocess.run(["bash", str(HEARTBEAT)], cwd=str(PROJECT), capture_output=True, text=True, timeout=180)
    out = (r.stdout or "").strip()
    err = (r.stderr or "").strip()
    log(f"heartbeat_exit={r.returncode} stdout={out[:300]} stderr={err[:300]}")
    if r.returncode != 0:
        print(f"smart_heartbeat failed: {reason}; exit={r.returncode}")
        return r.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
