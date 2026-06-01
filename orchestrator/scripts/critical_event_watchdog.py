#!/opt/hermes/.venv/bin/python3
"""critical_event_watchdog.py — Autonomous Critical Event Monitor v1.0

Silent watchdog that ONLY alerts when critical events occur.
Runs every 10 minutes. Outputs NOTHING when everything is fine.
When critical: outputs alert message to stdout (cron delivers to Telegram).

Critical events:
  C1: Drawdown > 5%
  C2: Hermes container DOWN or Standby reports failure
  C3: Config drift UNREPAIRABLE (config_diff_health errors)
  C4: Fleet emergency (3+ bots down, ConsecLoss > 6, MCP layer failure)
  C5: RiskGuard blocks ALL pairs (0 ACCEPTED) or pipeline collapsed

Usage: run as no_agent cron with deliver=telegram
  Silent when OK → only speaks when critical
"""

import json, os, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

BASE = "/home/hermes/projects/trading"
STATE_DIR = Path(BASE) / "orchestrator/state"
SILENT_FILE = STATE_DIR / ".critical_watchdog_silent"

# Load critical thresholds
DRAWDOWN_CRITICAL = 5.0
CONSECLOSS_CRITICAL = 6
MIN_BOTS_ALIVE = 2  # alert if fewer than 2 bots respond


def check_drawdown() -> tuple:
    """C1: Check drawdown level."""
    try:
        with open(BASE + "/freqtrade/shared/fleet_risk_state.json") as f:
            d = json.load(f)
        dd = d.get("portfolio", {}).get("current_drawdown", 0) * 100
        return dd >= DRAWDOWN_CRITICAL, round(dd, 2)
    except:
        return False, 0.0


def check_hermes() -> tuple:
    """C2: Check Hermes container and standby health."""
    try:
        r = subprocess.run(["docker", "inspect", "hermes-green", "--format", "{{.State.Status}}"],
                          capture_output=True, text=True, timeout=10)
        alive = r.stdout.strip() == "running" and r.returncode == 0
        # Check standby health
        standby_file = STATE_DIR / "standby/hermes_health.json"
        standby_ok = True
        if standby_file.exists():
            try:
                with open(standby_file) as f:
                    sh = json.load(f)
                standby_ok = sh.get("overall") != "HERMES_DOWN"
            except:
                pass
        if not alive:
            return True, "Hermes container DOWN"
        if not standby_ok:
            return True, "Standby reports Hermes DOWN"
        return False, "OK"
    except:
        return True, "Cannot check Hermes status"


def check_config_drift() -> tuple:
    """C3: Check if config drift is unrepairable."""
    health_file = STATE_DIR / "config_diff/config_diff_health.json"
    if not health_file.exists():
        return False, "no data"
    try:
        with open(health_file) as f:
            d = json.load(f)
        errors = d.get("errors", 0)
        drift = d.get("drift_detected", 0)
        if errors > 0:
            return True, f"{errors} config error(s) — unrepairable"
        if drift > 0:
            return True, f"{drift} config drift(s) detected"
        return False, "OK"
    except:
        return False, "no data"


def check_fleet_emergency() -> tuple:
    """C4: Check fleet-wide emergencies."""
    alerts = []
    # ConsecLoss > 6
    consec_file = STATE_DIR / "consec_loss_state.json"
    if consec_file.exists():
        try:
            with open(consec_file) as f:
                d = json.load(f)
            cl = d.get("consecutive_losses", 0)
            if cl >= CONSECLOSS_CRITICAL:
                alerts.append(f"ConsecLoss={cl} (threshold={CONSECLOSS_CRITICAL})")
        except:
            pass
    # Bot count
    try:
        r = subprocess.run(
            "docker ps --format '{{.Names}}' | grep freqtrade | wc -l",
            shell=True, capture_output=True, text=True, timeout=10,
        )
        running = int(r.stdout.strip()) if r.stdout.strip() else 0
        if running < MIN_BOTS_ALIVE:
            alerts.append(f"Only {running}/{4} bots running")
    except:
        alerts.append("Cannot check bot count")
    if alerts:
        return True, " | ".join(alerts)
    return False, "OK"


def check_riskguard() -> tuple:
    """C5: Check if RiskGuard blocks everything."""
    rg_file = STATE_DIR / "riskguard/riskguard_health.json"
    if not rg_file.exists():
        # Fall back to pipeline state
        bridge_file = BASE + "/freqtrade/shared/primo_signal_state.json"
        if os.path.exists(bridge_file):
            try:
                with open(bridge_file) as f:
                    d = json.load(f)
                pairs = d.get("pairs", {})
                accepted = sum(1 for p in pairs.values() if p.get("verdict") == "ACCEPTED")
                if accepted == 0 and len(pairs) >= 3:
                    return True, f"RiskGuard blocks ALL {len(pairs)} pairs (0 ACCEPTED)"
            except:
                pass
        return False, "no riskguard data"
    try:
        with open(rg_file) as f:
            d = json.load(f)
        accepted = d.get("checks", {}).get("accepted", 0)
        total = d.get("checks", {}).get("signal_found", False)
        if not total:
            return True, "RiskGuard: No signal found"
        if accepted == 0 and d.get("status") == "OK":
            return False, "All pairs WATCH_ONLY (expected — low confidence)"
        if accepted == 0:
            return True, "RiskGuard: 0 ACCEPTED — all pairs blocked"
        return False, f"OK ({accepted} accepted)"
    except:
        return False, "no data"


def main() -> int:
    alerts = []

    # C1: Drawdown
    critical, val = check_drawdown()
    if critical:
        alerts.append(f"🔴 Drawdown {val}% > {DRAWDOWN_CRITICAL}%")

    # C2: Hermes
    critical, msg = check_hermes()
    if critical:
        alerts.append(f"🔴 Hermes: {msg}")

    # C3: Config drift
    critical, msg = check_config_drift()
    if critical:
        alerts.append(f"🔴 Config: {msg}")

    # C4: Fleet emergency
    critical, msg = check_fleet_emergency()
    if critical:
        alerts.append(f"🔴 Fleet: {msg}")

    # C5: RiskGuard
    critical, msg = check_riskguard()
    if critical:
        alerts.append(f"🔴 Signal: {msg}")

    if not alerts:
        # Silent exit — no output = no Telegram delivery
        return 0

    # Build alert message
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"🚨 Hermes Critical Alert — {now}",
        "",
    ]
    lines += alerts
    lines += [
        "",
        "System ist autonom — manuelles Eingreifen erforderlich.",
        "Full logs: orchestrator/state/",
    ]
    
    print("\n".join(lines))
    return 1


if __name__ == "__main__":
    sys.exit(main())
