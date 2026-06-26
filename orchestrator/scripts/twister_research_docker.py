#!/usr/bin/env python3
"""Twister Lab research wrapper - direct Python execution."""
import subprocess, sys, os
from datetime import datetime

LAB_DIR = "/home/hermes/twister-lab"
LOGDIR = os.path.join(LAB_DIR, "logs")
os.makedirs(LOGDIR, exist_ok=True)

result = subprocess.run(
    ["python3", os.path.join(LAB_DIR, "src/twister_agent.py"), "--mode", "research"],
    cwd=LAB_DIR, capture_output=True, text=True, timeout=180
)

ts = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
with open(os.path.join(LOGDIR, "cron_research.log"), "a") as f:
    f.write(f"[{ts}] research exit={result.returncode}\n")

if result.stdout.strip():
    print(result.stdout.strip())
sys.exit(result.returncode)
