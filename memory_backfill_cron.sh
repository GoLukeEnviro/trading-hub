#!/bin/bash
# Memory Backfill Cron Wrapper — called by Hermes Cron every 2h
# Uses --since=3 for 150% coverage (no gaps with 2h interval)
cd /opt/data/profiles/orchestrator/scripts
exec python3 memory_backfill.py --since 3 "$@"
