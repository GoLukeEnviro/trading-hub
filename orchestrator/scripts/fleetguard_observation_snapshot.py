
#!/usr/bin/env python3
"""
FleetGuard Observation Snapshot — Phase 24B
Captures fleet state for the 12h observation window.
Outputs JSON snapshot to orchestrator/state/observation-24b/
"""
import json
import os
import sqlite3
import subprocess
from datetime import datetime, timezone

STATE_DIR = "/home/hermes/projects/trading/orchestrator/state/observation-24b"
os.makedirs(STATE_DIR, exist_ok=True)

def run(cmd):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
    return r.stdout.strip()

def sqlite_query(container, db_path, query):
    cmd = f"docker exec {container} sqlite3 {db_path} '{query}'"
    return run(cmd)

def get_bot_state(container, db_path):
    state = {"container": container, "open_trades": 0, "open_details": [], "closed_today": 0, "total_pnl": 0}
    # Open trades
    result = sqlite_query(container, db_path, "SELECT count(*) FROM trades WHERE is_open=1;")
    state["open_trades"] = int(result) if result.isdigit() else 0
    
    # Open trade details
    if state["open_trades"] > 0:
        details = sqlite_query(container, db_path,
            "SELECT pair, is_short, open_rate, enter_tag FROM trades WHERE is_open=1;")
        for line in details.split("\n"):
            if "|" in line:
                parts = line.split("|")
                if len(parts) >= 4:
                    state["open_details"].append({
                        "pair": parts[0],
                        "is_short": parts[1] == "1",
                        "open_rate": parts[2],
                        "enter_tag": parts[3]
                    })
    
    # Closed today count
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    result = sqlite_query(container, db_path,
        f"SELECT count(*), round(sum(close_profit_abs),4) FROM trades WHERE is_open=0 AND close_date >= '{today}';")
    if result and "|" in result:
        parts = result.split("|")
        state["closed_today"] = int(parts[0]) if parts[0].isdigit() else 0
        try: state["today_pnl"] = float(parts[1])
        except: state["today_pnl"] = 0
    
    # Total closed PnL
    result = sqlite_query(container, db_path, "SELECT round(sum(close_profit_abs),4) FROM trades WHERE is_open=0;")
    try: state["total_pnl"] = float(result)
    except: state["total_pnl"] = 0
    
    return state

# Container status
containers_raw = run("docker ps --format '{{.Names}}|{{.Status}}' | grep freqtrade")
containers = {}
for line in containers_raw.split("\n"):
    if "|" in line:
        name, status = line.split("|", 1)
        containers[name] = status

# Bot states
bots = {
    "freqtrade-rsi": {"db": "/freqtrade/tradesv3.dryrun.sqlite", "container": "freqtrade-rsi"},
    "freqtrade-momentum": {"db": "/freqtrade/tradesv3.dryrun.sqlite", "container": "freqtrade-momentum"},
    "trading-freqtrade-regime-hybrid-1": {"db": "/freqtrade/user_data/tradesv3.regime_hybrid.dryrun.sqlite", "container": "trading-freqtrade-regime-hybrid-1"},
}

snapshot = {
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "containers": containers,
    "bots": {},
}

for name, info in bots.items():
    snapshot["bots"][name] = get_bot_state(info["container"], info["db"])

# FleetGuard logs — check for REJECT messages
fg_logs = {}
for container in ["freqtrade-momentum", "trading-freqtrade-regime-hybrid-1"]:
    logs = run(f"docker logs --since 4h {container} 2>&1 | grep -i FleetGuard || echo NONE")
    fg_logs[container] = logs
snapshot["fleetguard_logs"] = fg_logs

# RSI quarantine check — should have no NEW entries since restart
rsi_new = run("docker logs --since 4h freqtrade-rsi 2>&1 | grep -c 'enter_long\|enter_short' || echo 0")
snapshot["rsi_new_entries"] = rsi_new

# Errors
errors = {}
for container in ["freqtrade-rsi", "freqtrade-momentum", "trading-freqtrade-regime-hybrid-1"]:
    errs = run(f"docker logs --since 4h {container} 2>&1 | grep -icE 'traceback|error|exception' || echo 0")
    errors[container] = errs
snapshot["errors"] = errors

# Write snapshot
ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
outpath = os.path.join(STATE_DIR, f"snapshot_{ts}.json")
with open(outpath, "w") as f:
    json.dump(snapshot, f, indent=2)

# Summary line
total_open = sum(b["open_trades"] for b in snapshot["bots"].values())
total_pnl = sum(b.get("total_pnl", 0) for b in snapshot["bots"].values())
print(f"SNAPSHOT {ts}: {total_open} open trades, {total_pnl:.2f} USDT total PnL, FG logs: {sum(1 for v in fg_logs.values() if v != 'NONE')}/2 bots")
print(json.dumps(snapshot, indent=2))
