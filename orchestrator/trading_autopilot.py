#!/usr/bin/env python3
"""Trading Hub Autopilot v0 — Safe autonomous fleet monitor.

MODES:
  monitor          — Read-only fleet snapshot, signal check, write report + decision queue
  daily-report     — Extended daily summary with trend analysis
  approval-preview — Show pending approval items from decision queue

SAFETY:
  - Read-only. Never modifies configs, containers, strategies, or runtime state.
  - Never prints secrets, tokens, passwords, or API keys.
  - All runtime-changing recommendations go into decision_queue.json for human approval.

ARCHITECTURE:
  - Reuses existing scripts: fleet_healthcheck.py, freqtrade_monitor.py, ai_hedge_signal_heartbeat.sh
  - Outputs: docs/state/autopilot/latest.md, orchestrator/state/decision_queue.json
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

# --- Constants ---
PROJECT_ROOT = Path("/home/hermes/projects/trading")
SIGNAL_PATH = PROJECT_ROOT / "ai-hedge-fund-crypto" / "output" / "hermes_signal.json"
HEARTBEAT_LOG = PROJECT_ROOT / "ai-hedge-fund-crypto" / "output" / "logs" / "heartbeat.log"
DECISION_QUEUE_PATH = PROJECT_ROOT / "orchestrator" / "state" / "decision_queue.json"
REPORT_DIR = PROJECT_ROOT / "docs" / "state" / "autopilot"
REPORT_MD = REPORT_DIR / "latest.md"
FLEET_HEALTH_SCRIPT = PROJECT_ROOT / "orchestrator" / "scripts" / "fleet_healthcheck.py"
FREQTRADE_MONITOR_SCRIPT = PROJECT_ROOT / "orchestrator" / "scripts" / "freqtrade_monitor.py"
SIGNAL_MAX_AGE_MINUTES = 60  # Signal older than this = YELLOW
SIGNAL_STALE_MINUTES = 120   # Signal older than this = ORANGE

# Expected active containers
EXPECTED_CONTAINERS = {
    "freqtrade-freqforge": {"role": "active-bot", "dry_run_required": True},
    "freqtrade-freqforge-canary": {"role": "canary-bot", "dry_run_required": True},
    "freqtrade-regime-hybrid": {"role": "active-bot", "dry_run_required": True},
    "freqtrade-momentum": {"role": "frozen-bot", "dry_run_required": True},
    "freqai-rebel": {"role": "active-bot", "dry_run_required": True},
    "ai-hedge-fund-crypto": {"role": "signal-layer", "dry_run_required": False},
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(ts: Optional[datetime] = None) -> str:
    return (ts or utc_now()).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_cmd(cmd: List[str], timeout: int = 30) -> tuple[int, str]:
    """Run command, return (exit_code, stdout)."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout.strip()
    except Exception as e:
        return -1, str(e)


# --- Data Sources ---

def get_container_status() -> Dict[str, Dict]:
    """Query docker for container state. Read-only."""
    result = {}
    code, out = run_cmd(["docker", "ps", "-a", "--format", "{{.Names}}|{{.Status}}|{{.Ports}}"])
    if code != 0:
        return {"error": out}
    for line in out.splitlines():
        if "|" not in line:
            continue
        parts = line.split("|", 2)
        name = parts[0].strip()
        status = parts[1].strip() if len(parts) > 1 else "?"
        ports = parts[2].strip() if len(parts) > 2 else ""
        result[name] = {"status": status, "ports": ports}
    return result


def get_signal() -> Optional[Dict]:
    """Read ai-hedge signal file. Returns None if missing/unreadable."""
    try:
        if not SIGNAL_PATH.exists():
            # Try inside container via docker exec
            code, out = run_cmd([
                "docker", "exec", "ai-hedge-fund-crypto",
                "cat", "/app/output/hermes_signal.json"
            ])
            if code == 0 and out:
                return json.loads(out)
            return None
        with open(SIGNAL_PATH, "r") as f:
            return json.load(f)
    except Exception:
        return None


def get_signal_age_minutes(signal: Optional[Dict]) -> Optional[float]:
    """Calculate signal age in minutes."""
    if not signal:
        return None
    ts_str = signal.get("timestamp_utc", "")
    if not ts_str:
        return None
    try:
        # Handle ISO format with or without timezone
        ts_str = ts_str.replace("Z", "+00:00")
        if "+" not in ts_str[10:] and "-" not in ts_str[10:]:
            ts_str += "+00:00"
        from datetime import datetime as dt
        sig_ts = dt.fromisoformat(ts_str)
        age = (utc_now() - sig_ts).total_seconds() / 60.0
        return max(0.0, age)
    except Exception:
        return None


def get_heartbeat_status() -> Dict:
    """Check ai-hedge heartbeat log for last entry."""
    try:
        code, out = run_cmd([
            "docker", "exec", "ai-hedge-fund-crypto",
            "tail", "-5", "/app/output/logs/heartbeat.log"
        ])
        if code != 0 or not out:
            return {"status": "unknown", "detail": "no heartbeat log"}
        lines = [l for l in out.splitlines() if l.strip()]
        if not lines:
            return {"status": "unknown", "detail": "empty log"}
        last_line = lines[-1]
        is_ok = "OK" in last_line
        return {
            "status": "ok" if is_ok else "warn",
            "last_line": last_line[:120],
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)[:80]}


def query_bot_via_jwt(container: str) -> Optional[Dict]:
    """Query a Freqtrade bot's status via internal JWT auth. Read-only."""
    # Build JWT and query inside the container
    script = """
import json, time, jwt, urllib.request, glob, sys

c = None
for f in glob.glob('/freqtrade/config/config*.json') + glob.glob('/freqtrade/user_data/config*.json'):
    try:
        d = json.load(open(f))
        if d.get('api_server', {}).get('enabled'):
            c = d
            break
    except:
        pass

if not c:
    print(json.dumps({"error": "no api config"}))
    sys.exit()

api = c['api_server']
secret = api['jwt_secret_key']
port = api['listen_port']
token = jwt.encode({'identity': {'u': api['username']}, 'exp': int(time.time()) + 600, 'type': 'access'}, secret, algorithm='HS256')
auth = {'Authorization': f'Bearer {token}'}

result = {}
try:
    r1 = urllib.request.Request(f'http://localhost:{port}/api/v1/status', headers=auth)
    trades = json.loads(urllib.request.urlopen(r1, timeout=5).read())
    result['open_trades'] = len(trades)
except:
    result['open_trades'] = None

try:
    r2 = urllib.request.Request(f'http://localhost:{port}/api/v1/profit', headers=auth)
    prof = json.loads(urllib.request.urlopen(r2, timeout=5).read())
    result['total_trades'] = prof.get('trade_count', 0)
    result['closed_profit'] = float(prof.get('profit_closed_coin', 0))
except:
    result['total_trades'] = None
    result['closed_profit'] = None

try:
    r3 = urllib.request.Request(f'http://localhost:{port}/api/v1/show_config', headers=auth)
    conf = json.loads(urllib.request.urlopen(r3, timeout=5).read())
    if isinstance(conf, dict):
        result['strategy'] = conf.get('strategy', '?')
        result['dry_run'] = conf.get('dry_run', None)
        result['max_open_trades'] = conf.get('max_open_trades', None)
except:
    pass

print(json.dumps(result))
"""
    code, out = run_cmd(["docker", "exec", container, "python3", "-c", script], timeout=30)
    if code != 0 or not out:
        return None
    try:
        # Take last line that looks like JSON
        lines = [l for l in out.splitlines() if l.strip().startswith("{")]
        if not lines:
            return None
        return json.loads(lines[-1])
    except Exception:
        return None


# --- Classification ---

def classify_signal(signal: Optional[Dict], age_min: Optional[float]) -> str:
    """GREEN / YELLOW / ORANGE / RED for signal layer."""
    if signal is None:
        return "RED"
    if age_min is None:
        return "ORANGE"
    if age_min > SIGNAL_STALE_MINUTES:
        return "ORANGE"
    if age_min > SIGNAL_MAX_AGE_MINUTES:
        return "YELLOW"
    return "GREEN"


def classify_container(name: str, info: Dict, expected: Dict) -> tuple[str, str]:
    """Return (color, detail) for one container."""
    status = info.get("status", "?")
    if "Up" in status:
        return "GREEN", status
    elif "Exited" in status or "Stopped" in status:
        return "RED", status
    else:
        return "ORANGE", status


# --- Report Generation ---

def build_monitor_report() -> Dict:
    """Build full monitor snapshot. All read-only."""
    now = utc_now()

    # Containers
    containers = get_container_status()

    # Signal
    signal = get_signal()
    sig_age = get_signal_age_minutes(signal)
    sig_color = classify_signal(signal, sig_age)

    # Heartbeat
    heartbeat = get_heartbeat_status()

    # Bot details
    bot_details = {}
    for name in ["freqtrade-freqforge", "freqtrade-freqforge-canary",
                 "freqtrade-regime-hybrid", "freqtrade-momentum", "freqai-rebel"]:
        detail = query_bot_via_jwt(name)
        if detail:
            bot_details[name] = detail

    # Fleet classification
    fleet_colors = {}
    fleet_details = {}
    for name, expected in EXPECTED_CONTAINERS.items():
        info = containers.get(name, {})
        color, detail = classify_container(name, info, expected)
        fleet_colors[name] = color
        fleet_details[name] = detail

    # Momentum check: still halted?
    momentum_halted = False
    mom_detail = bot_details.get("freqtrade-momentum", {})
    if mom_detail.get("max_open_trades") == 0:
        momentum_halted = True

    # Rebel observation
    rebel_detail = bot_details.get("freqai-rebel", {})
    rebel_trades = rebel_detail.get("total_trades")

    # Overall verdict: worst color
    all_colors = list(fleet_colors.values()) + [sig_color]
    color_rank = {"GREEN": 0, "YELLOW": 1, "ORANGE": 2, "RED": 3}
    overall = max(all_colors, key=lambda c: color_rank.get(c, 0))

    # Decision queue
    approval_items = []

    # Check: signal stale
    if sig_age is not None and sig_age > SIGNAL_STALE_MINUTES:
        approval_items.append({
            "priority": "HIGH",
            "target": "ai-hedge-fund-crypto",
            "action": "restart_container",
            "reason": f"Signal stale: {sig_age:.0f} minutes old"
        })

    # Check: Rebel still 0 trades after 24h (we track in state)
    if rebel_trades is not None and rebel_trades == 0:
        approval_items.append({
            "priority": "MEDIUM",
            "target": "freqai-rebel",
            "action": "increase_DI_threshold_to_2_0",
            "reason": "0 trades — consider further DI threshold increase"
        })

    # Check: container down
    for name, color in fleet_colors.items():
        if color == "RED":
            approval_items.append({
                "priority": "HIGH",
                "target": name,
                "action": "restart_container",
                "reason": f"Container not running: {fleet_details.get(name, '?')}"
            })

    decision_queue = {
        "generated_at": iso(now),
        "safe_actions_executed": ["fleet_snapshot_taken", "signal_validated", "report_written"],
        "approval_required": approval_items,
    }

    # Build markdown report
    md_lines = [
        f"# Trading Hub Autopilot Report",
        f"",
        f"**Generated:** {iso(now)}",
        f"**Overall Status:** **{overall}**",
        f"",
        f"## Signal Layer",
        f"",
        f"| Check | Result |",
        f"|-------|--------|",
        f"| Signal File | {'Present' if signal else 'MISSING'} |",
        f"| Signal Age | {f'{sig_age:.1f} min' if sig_age is not None else 'UNKNOWN'} |",
        f"| Signal Status | {sig_color} |",
        f"| Heartbeat | {heartbeat.get('status', '?')} |",
    ]

    if signal and "pairs" in signal:
        for pair, data in signal.get("pairs", {}).items():
            if "/" in pair:
                md_lines.append(f"| {pair} | {data.get('action', '?')} conf={data.get('confidence', '?')} |")

    md_lines += [
        f"",
        f"## Fleet Status",
        f"",
        f"| Bot | Color | Container | Strategy | Trades | Profit | Open | Detail |",
        f"|-----|-------|-----------|----------|--------|---------|------|--------|",
    ]

    for name in EXPECTED_CONTAINERS:
        color = fleet_colors.get(name, "?")
        detail = fleet_details.get(name, "?")
        bd = bot_details.get(name, {})
        strategy = bd.get("strategy", "N/A")
        trades = bd.get("total_trades", "?")
        profit = f"{bd.get('closed_profit', 0):.4f}" if bd.get("closed_profit") is not None else "?"
        open_t = bd.get("open_trades", "?")
        md_lines.append(f"| {name} | {color} | {detail} | {strategy} | {trades} | {profit} | {open_t} | |")

    md_lines += [
        f"",
        f"## Special Checks",
        f"",
        f"| Check | Status |",
        f"|-------|--------|",
        f"| Momentum Entries Halted | {'YES' if momentum_halted else 'NO - CHECK!'} |",
        f"| Rebel Total Trades | {rebel_trades if rebel_trades is not None else 'N/A'} |",
        f"",
    ]

    if approval_items:
        md_lines += [
            f"## Approval Required",
            f"",
        ]
        for item in approval_items:
            md_lines.append(
                f"- [{item['priority']}] **{item['target']}**: {item['action']} — {item['reason']}"
            )
    else:
        md_lines += [
            f"## Approval Required",
            f"",
            f"None — all clear.",
        ]

    md_lines += [
        f"",
        f"---",
        f"*Autopilot v0 — read-only monitor*",
    ]

    report_md = "\n".join(md_lines)

    return {
        "overall": overall,
        "signal_color": sig_color,
        "fleet_colors": fleet_colors,
        "bot_details": bot_details,
        "decision_queue": decision_queue,
        "report_md": report_md,
        "momentum_halted": momentum_halted,
        "rebel_trades": rebel_trades,
    }


def build_daily_report(monitor: Dict) -> str:
    """Extended daily report with summary."""
    now = utc_now()
    md = monitor["report_md"]

    # Add daily summary section
    daily = [
        "",
        "## Daily Summary",
        "",
        f"**Date:** {now.strftime('%Y-%m-%d')}",
        "",
        "### Fleet Health at a Glance",
        "",
    ]

    colors = monitor["fleet_colors"]
    green_count = sum(1 for c in colors.values() if c == "GREEN")
    total = len(colors)
    daily.append(f"- {green_count}/{total} containers GREEN")
    daily.append(f"- Signal: {monitor['signal_color']}")
    daily.append(f"- Momentum entries blocked: {'Yes' if monitor['momentum_halted'] else 'NO'}")
    daily.append(f"- Rebel trades: {monitor['rebel_trades'] if monitor['rebel_trades'] is not None else 'N/A'}")

    if monitor["decision_queue"]["approval_required"]:
        daily.append("")
        daily.append("### Pending Approvals")
        for item in monitor["decision_queue"]["approval_required"]:
            daily.append(f"- [{item['priority']}] {item['target']}: {item['action']}")

    daily += [
        "",
        "---",
        f"*Daily report — {iso(now)}*",
    ]

    return md + "\n".join(daily)


# --- Main ---

def main():
    mode = "monitor"
    if len(sys.argv) > 1 and sys.argv[1] == "--mode":
        if len(sys.argv) > 2:
            mode = sys.argv[2]

    if mode not in ("monitor", "daily-report", "approval-preview"):
        print(f"Usage: {sys.argv[0]} --mode monitor|daily-report|approval-preview")
        sys.exit(1)

    # Ensure output dirs exist
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    DECISION_QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Build monitor data
    monitor = build_monitor_report()

    if mode == "monitor":
        # Write report
        with open(REPORT_MD, "w") as f:
            f.write(monitor["report_md"])

        # Write decision queue
        with open(DECISION_QUEUE_PATH, "w") as f:
            json.dump(monitor["decision_queue"], f, indent=2)

        # Print summary to stdout
        print(f"TARGET_OVERALL={monitor['overall']}")
        print(f"SIGNAL={monitor['signal_color']}")
        for name, color in monitor["fleet_colors"].items():
            short = name.replace("freqtrade-", "").replace("freqforge-", "ff-")
            print(f"FLEET_{short}={color}")
        print(f"MOMENTUM_HALTED={'YES' if monitor['momentum_halted'] else 'NO'}")
        print(f"REBEL_TRADES={monitor['rebel_trades']}")
        n_pending = len(monitor["decision_queue"]["approval_required"])
        print(f"APPROVAL_PENDING={n_pending}")
        if n_pending > 0:
            print("APPROVAL_ITEMS:")
            for item in monitor["decision_queue"]["approval_required"]:
                print(f"  [{item['priority']}] {item['target']}: {item['action']}")
        print(f"\nReport: {REPORT_MD}")
        print(f"Decisions: {DECISION_QUEUE_PATH}")

    elif mode == "daily-report":
        daily = build_daily_report(monitor)
        daily_path = REPORT_DIR / f"daily_{utc_now().strftime('%Y%m%d')}.md"
        with open(daily_path, "w") as f:
            f.write(daily)
        with open(REPORT_MD, "w") as f:
            f.write(daily)
        with open(DECISION_QUEUE_PATH, "w") as f:
            json.dump(monitor["decision_queue"], f, indent=2)
        print(f"Daily report: {daily_path}")

    elif mode == "approval-preview":
        dq = monitor["decision_queue"]
        if not dq["approval_required"]:
            print("No pending approval items. All clear.")
        else:
            print(f"Pending approvals ({len(dq['approval_required'])}):")
            for item in dq["approval_required"]:
                print(f"  [{item['priority']}] {item['target']}: {item['action']}")
                print(f"    Reason: {item['reason']}")
                # Generate approval command
                safe_name = item['target'].replace("freqtrade-", "").replace("freqai-", "")
                safe_action = item['action'].replace("_", "-")
                print(f"    Approve: approve {safe_name}-{safe_action}")


if __name__ == "__main__":
    main()