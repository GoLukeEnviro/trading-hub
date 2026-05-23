#!/usr/bin/env python3
"""
backup_rotation.py — Daily rolling backup for Trading Hub
Saves bot configs, state files, logs. Retains 7 days.
Runs daily at 02:00 UTC via Hermes cron.
"""

import json, os, shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE = Path("/home/hermes/projects/trading/orchestrator")
BACKUP_ROOT = BASE / "backups"
RETENTION_DAYS = 7

# What to back up
BOT_CONFIG_DIRS = {
    "freqforge": Path("/home/hermes/projects/trading/freqforge/config"),
    "canary": Path("/home/hermes/projects/trading/freqforge-canary/config"),
    "regime": Path("/home/hermes/projects/trading/freqtrade/bots/regime-hybrid/config"),
    "momentum": Path("/home/hermes/projects/trading/freqtrade/bots/momentum/config"),
}
STATE_DIR = BASE / "state"
SHADOW_LOG = BASE / "logs" / "shadow_decisions.jsonl"
PIPELINE_LOG = BASE / "logs" / "trading_pipeline.log"
SIGNAL_FILE = Path("/home/hermes/projects/trading/ai-hedge-fund-crypto/output/latest/hermes_signal.json")


def main():
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    backup_dir = BACKUP_ROOT / f"{today}-daily"
    backup_dir.mkdir(parents=True, exist_ok=True)

    backed_up = 0

    # Bot configs
    for label, cfg_path in BOT_CONFIG_DIRS.items():
        if cfg_path.is_dir():
            dst = backup_dir / "configs" / label
            dst.mkdir(parents=True, exist_ok=True)
            for f in cfg_path.glob("*.json"):
                shutil.copy2(f, dst / f.name)
                backed_up += 1

    # State files
    state_dst = backup_dir / "state"
    state_dst.mkdir(parents=True, exist_ok=True)
    if STATE_DIR.is_dir():
        for f in STATE_DIR.glob("*.json"):
            shutil.copy2(f, state_dst / f.name)
            backed_up += 1

    # Key logs
    logs_dst = backup_dir / "logs"
    logs_dst.mkdir(parents=True, exist_ok=True)
    for src in [SHADOW_LOG, PIPELINE_LOG]:
        if src.exists():
            shutil.copy2(src, logs_dst / src.name)
            backed_up += 1

    # Signal file
    if SIGNAL_FILE.exists():
        shutil.copy2(SIGNAL_FILE, backup_dir / "hermes_signal.json")
        backed_up += 1

    # Cleanup old backups (older than RETENTION_DAYS)
    removed = 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)
    for d in BACKUP_ROOT.iterdir():
        if d.is_dir() and d.name.endswith("-daily"):
            # Parse date from name
            try:
                date_str = d.name.split("-")[0]
                d_date = datetime.strptime(date_str, "%Y%m%d").replace(tzinfo=timezone.utc)
                if d_date < cutoff:
                    shutil.rmtree(d)
                    removed += 1
            except (ValueError, IndexError):
                pass  # Skip non-date dirs

    # Skip backup dirs that aren't daily rotation (keep manual backups)
    result = {
        "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
        "backup_dir": str(backup_dir),
        "files_backed_up": backed_up,
        "old_backups_removed": removed,
        "retention_days": RETENTION_DAYS,
    }

    # Write manifest
    with open(backup_dir / "manifest.json", "w") as f:
        json.dump(result, f, indent=2)

    print(f"Backup complete: {backed_up} files -> {backup_dir.name} | Removed {removed} old backups")
    return result


if __name__ == "__main__":
    main()
