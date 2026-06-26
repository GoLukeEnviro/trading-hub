#!/usr/bin/env python3
"""Twister Clone cycle wrapper - direct Python execution."""
import subprocess, sys, os
from datetime import datetime, timezone

CLONE_DIR = "/home/hermes/twister-clone"
LOGDIR = os.path.join(CLONE_DIR, "logs")
os.makedirs(LOGDIR, exist_ok=True)

result = subprocess.run(
    ["python3", os.path.join(CLONE_DIR, "src/twister_agent.py"), "--mode", "cycle"],
    cwd=CLONE_DIR, capture_output=True, text=True, timeout=120
)

ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
with open(os.path.join(LOGDIR, "cron_cycle.log"), "a") as f:
    f.write(f"[{ts}] clone-cycle exit={result.returncode}\n")

if result.stdout.strip():
    print(result.stdout.strip())
sys.exit(result.returncode)
