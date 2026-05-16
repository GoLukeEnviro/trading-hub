#!/usr/bin/env python3
import json
import os
import subprocess
from datetime import datetime

TRADING_ROOT = "/home/hermes/projects/trading"
SIGNAL_PATH = f"{TRADING_ROOT}/ai-hedge-fund-crypto/output/hermes_signal.json"
SHADOW_LOG = f"{TRADING_ROOT}/var/freqforge/shadow_decisions.jsonl"

def get_signal():
    try:
        with open(SIGNAL_PATH, 'r') as f:
            return json.load(f)
    except Exception as e:
        return {"error": str(e)}

def get_container_status():
    try:
        cmd = ["docker", "ps", "--format", "{{.Names}}|{{.Status}}|{{.RunningFor}}", "--filter", "name=freqtrade", "--filter", "name=ai-hedge"]
        res = subprocess.check_output(cmd).decode().strip()
        lines = res.split('\n')
        status_list = []
        for line in lines:
            if '|' in line:
                name, status, uptime = line.split('|')
                status_list.append({"name": name, "status": status, "uptime": uptime})
        return status_list
    except Exception as e:
        return [{"error": str(e)}]

def get_shadow_logs(n=10):
    try:
        if not os.path.exists(SHADOW_LOG):
            return []
        with open(SHADOW_LOG, 'r') as f:
            lines = f.readlines()
            return [json.loads(line) for line in lines[-n:]]
    except Exception as e:
        return [{"error": str(e)}]

def main():
    print(f"## Trading Hub Strategy Audit - {datetime.now().isoformat()}")
    
    print("\n### 1. Signal Status (ai-hedge-fund-crypto)")
    sig = get_signal()
    print("```json")
    print(json.dumps(sig, indent=2))
    print("```")
    
    print("\n### 2. Fleet Connectivity")
    containers = get_container_status()
    print("| Container | Status | Uptime |")
    print("|-----------|--------|--------|")
    for c in containers:
        if "error" in c:
            print(f"| ERROR | {c['error']} | - |")
        else:
            print(f"| {c['name']} | {c['status']} | {c['uptime']} |")
            
    print("\n### 3. ShadowLogger Activity (Last 5)")
    shadow = get_shadow_logs(5)
    print("```json")
    print(json.dumps(shadow, indent=2))
    print("```")

if __name__ == "__main__":
    main()
