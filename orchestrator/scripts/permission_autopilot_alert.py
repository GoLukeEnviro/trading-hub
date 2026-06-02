#!/usr/bin/env python3
"""CRITICAL-only alert wrapper for permission_autopilot.sh.

Runs as hermes, never applies fixes, and alerts only when new/changed
CRITICAL permission drift appears or the last alert is older than 60 minutes.
"""

from __future__ import annotations

import base64
import fcntl
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


SCRIPT = Path("/home/hermes/projects/trading/orchestrator/scripts/permission_autopilot.sh")
STATE_FILE = Path("/home/hermes/state/perm_autopilot_last_alert.json")
ALERT_LOG = Path("/home/hermes/logs/perm_autopilot_alert.log")
LOCK_FILE = Path("/home/hermes/state/perm_autopilot_alert.lock")

LINE_RE = re.compile(
    r"PERM_AUTOPILOT SCAN severity=(?P<severity>\w+) root=(?P<root>\S+) "
    r"total=(?P<total>\d+) drift_uid0_1337=(?P<drift>\d+) target_uid=(?P<target>\d+)"
)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return now_utc().isoformat(timespec="seconds")


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def append_log(message: str) -> None:
    ensure_parent(ALERT_LOG)
    line = f"[{iso_now()}] {message}"
    with ALERT_LOG.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def load_state() -> dict[str, Any] | None:
    if not STATE_FILE.exists():
        return None
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None


def save_state(payload: dict[str, Any]) -> None:
    ensure_parent(STATE_FILE)
    STATE_FILE.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        ts = datetime.fromisoformat(value)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts.astimezone(timezone.utc)
    except Exception:
        return None


def get_telegram_creds() -> tuple[str, str]:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

    if not token:
        b64 = os.environ.get("TELEGRAM_BOT_TOKEN_B64", "").strip()
        if b64:
            try:
                token = base64.b64decode(b64).decode("utf-8").strip()
            except Exception:
                token = ""

    if not chat_id:
        chat_id = os.environ.get("CHAT_ID", "").strip()
    if not chat_id:
        chat_id = os.environ.get("TELEGRAM_HOME_CHANNEL", "").strip("'\"")

    return token, chat_id


def run_summary() -> tuple[int, list[dict[str, Any]], str]:
    if not SCRIPT.exists():
        return 1, [], f"missing script: {SCRIPT}"

    try:
        proc = subprocess.run(
            [str(SCRIPT), "--summary"],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    except Exception as exc:
        return 1, [], f"summary execution failed: {exc}"

    if proc.returncode != 0:
        return proc.returncode, [], proc.stdout.strip() or proc.stderr.strip() or "summary failed"

    scans: list[dict[str, Any]] = []
    for line in proc.stdout.splitlines():
        match = LINE_RE.search(line)
        if not match:
            continue
        scans.append(
            {
                "severity": match.group("severity"),
                "root": match.group("root"),
                "total": int(match.group("total")),
                "drift": int(match.group("drift")),
                "target": int(match.group("target")),
            }
        )

    if proc.stdout.strip() and not scans:
        append_log("summary parse failed: no scan lines matched expected format")
        return 0, [], "parse failed"

    return 0, scans, ""


def dedupe_paths(scans: list[dict[str, Any]]) -> list[str]:
    seen: set[str] = set()
    roots: list[str] = []
    for scan in scans:
        if scan.get("severity") != "CRITICAL":
            continue
        root = str(scan.get("root", "")).strip()
        if not root or root in seen:
            continue
        seen.add(root)
        roots.append(root)
    return roots


def build_message(critical_roots: list[str], warn_count: int, critical_count: int) -> str:
    lines = [
        "[HERMES ALERT] CRITICAL Permission Drift Detected",
        "",
        f"CRITICAL: {critical_count}",
        f"WARN: {warn_count}",
        "",
        "Paths:",
    ]

    max_paths = 20
    for root in critical_roots[:max_paths]:
        lines.append(f"- {root}")
    if len(critical_roots) > max_paths:
        lines.append(f"- (+{len(critical_roots) - max_paths} more)")

    lines.extend(
        [
            "",
            "Action:",
            "Manual review required.",
            "No automatic fix applied.",
            "",
            f"Timestamp: {iso_now()}",
        ]
    )
    return "\n".join(lines)


def send_telegram(message: str) -> bool:
    token, chat_id = get_telegram_creds()
    if not token or not chat_id:
        return False

    payload = urlencode(
        {
            "chat_id": chat_id,
            "text": message,
            "disable_web_page_preview": "true",
        }
    ).encode("utf-8")
    req = Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=15) as resp:
            return getattr(resp, "status", 200) == 200
    except Exception as exc:
        append_log(f"telegram send failed: {exc}")
        return False


def acquire_lock() -> Any:
    ensure_parent(LOCK_FILE)
    fh = LOCK_FILE.open("a+")
    fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    return fh


def main() -> int:
    try:
        lock_fh = acquire_lock()
    except BlockingIOError:
        return 0
    except Exception as exc:
        append_log(f"lock acquisition failed: {exc}")
        return 0

    with lock_fh:
        rc, scans, error = run_summary()
        if rc != 0:
            append_log(f"summary failure: {error}")
            return 0
        if error == "parse failed":
            return 0

        critical_roots = dedupe_paths(scans)
        critical_count = len(critical_roots)
        warn_count = sum(1 for scan in scans if scan.get("severity") == "WARN")

        if critical_count == 0:
            return 0

        state = load_state() or {}
        previous_roots = set(state.get("critical_roots", [])) if isinstance(state, dict) else set()
        previous_count = int(state.get("critical_count", 0) or 0) if isinstance(state, dict) else 0
        previous_at = parse_timestamp(state.get("timestamp") if isinstance(state, dict) else None)
        age_seconds = (
            (now_utc() - previous_at).total_seconds() if previous_at is not None else None
        )

        current_roots = set(critical_roots)
        should_alert = False
        if not state:
            should_alert = True
        elif age_seconds is None or age_seconds >= 3600:
            should_alert = True
        elif critical_count > previous_count:
            should_alert = True
        elif current_roots != previous_roots:
            should_alert = True

        if not should_alert:
            return 0

        message = build_message(critical_roots, warn_count, critical_count)
        sent = send_telegram(message)
        if sent:
            append_log(f"telegram alert sent critical={critical_count} warn={warn_count} roots={len(critical_roots)}")
        if not sent:
            append_log(message)

        save_state(
            {
                "timestamp": iso_now(),
                "critical_count": critical_count,
                "warn_count": warn_count,
                "critical_roots": critical_roots,
                "signature": hashlib.sha256("\n".join(sorted(critical_roots)).encode("utf-8")).hexdigest(),
            }
        )

        return 0


if __name__ == "__main__":
    raise SystemExit(main())
