#!/usr/bin/env bash
set -euo pipefail
python3 /home/hermes/projects/trading/freqtrade/shared/update_fleet_equity.py >> /opt/data/profiles/orchestrator/logs/fleet_risk_update.log 2>&1
