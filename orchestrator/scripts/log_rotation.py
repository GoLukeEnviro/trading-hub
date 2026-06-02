#!/usr/bin/env python3
"""log_rotation.py — rotate oversized log files, keep 3 backups, remove >30d old.

Runs daily via cron (0 3 * * *). Scans all log dirs in the trading hub.
"""
import glob, gzip, os, shutil, time
from pathlib import Path

MAX_SIZE_MB = 5
MAX_BACKUPS = 3
MAX_AGE_DAYS = 30
BASE = "/home/hermes/projects/trading"

LOG_DIRS = [
    f"{BASE}/orchestrator/logs",
    f"{BASE}/ai-hedge-fund-crypto/output/logs",
    f"{BASE}/freqtrade/logs",
]

def rotate_file(path: str) -> bool:
    """Rotate a log file: compress and rotate if > MAX_SIZE_MB."""
    try:
        size_mb = os.path.getsize(path) / (1024 * 1024)
    except FileNotFoundError:
        return False
    if size_mb < MAX_SIZE_MB:
        return False

    # Remove oldest backup if exists
    oldest = f"{path}.{MAX_BACKUPS}.gz"
    if os.path.exists(oldest):
        os.remove(oldest)

    # Shift existing backups
    for i in range(MAX_BACKUPS - 1, 0, -1):
        src = f"{path}.{i}.gz"
        if os.path.exists(src):
            shutil.move(src, f"{path}.{i + 1}.gz")

    # Compress current file to .1.gz
    try:
        with open(path, "rb") as f_in:
            with gzip.open(f"{path}.1.gz", "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
        # Truncate original
        with open(path, "w") as f:
            f.truncate(0)
        print(f"  Rotated: {path} ({size_mb:.1f} MB -> .1.gz)")
        return True
    except Exception as e:
        print(f"  ERROR rotating {path}: {e}")
        return False

def clean_old_files(directory: str, max_age_days: int = MAX_AGE_DAYS) -> int:
    """Remove log files older than max_age_days (only .gz backup files)."""
    removed = 0
    now = time.time()
    cutoff = now - (max_age_days * 86400)
    for f in glob.glob(f"{directory}/**/*.gz", recursive=True):
        try:
            if os.path.getmtime(f) < cutoff:
                os.remove(f)
                removed += 1
        except (FileNotFoundError, OSError):
            continue
    return removed

def main():
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Log rotation started")
    total_rotated = 0
    total_cleaned = 0

    for log_dir in LOG_DIRS:
        if not os.path.isdir(log_dir):
            continue
        print(f"--- {log_dir} ---")
        # Rotate .log files
        for f in sorted(glob.glob(f"{log_dir}/*.log")):
            if rotate_file(f):
                total_rotated += 1
        # Rotate .jsonl files
        for f in sorted(glob.glob(f"{log_dir}/*.jsonl")):
            if rotate_file(f):
                total_rotated += 1
        # Clean old gz backups
        cleaned = clean_old_files(log_dir)
        total_cleaned += cleaned
        if cleaned:
            print(f"  Cleaned {cleaned} old .gz files")

    print(f"Done: {total_rotated} rotated, {total_cleaned} old backups removed")

if __name__ == "__main__":
    main()
