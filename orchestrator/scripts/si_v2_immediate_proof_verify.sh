#!/usr/bin/env bash
#
# SI v2 Immediate Scheduler Proof — Verification Script
# One-shot read-only verification. No mutations.
set -euo pipefail

PREV_CYCLE_ID="20260613T191504Z"
PREV_CYCLES_SCANNED=14

echo "=== SI v2 Immediate Scheduler Proof Verification ==="
date
date -u
echo

echo "== time =="
date
date -u
echo

echo "== logs =="
ls -lah /opt/data/logs/si-v2-active-cycle/
echo "--- cron.log (tail 120) ---"
tail -120 /opt/data/logs/si-v2-active-cycle/cron.log || true
echo

echo "== secret scan logs =="
# Look for actual secret VALUES, not SET/MISSING markers
grep -RInE "(password|secret|token|access_token|refresh_token|exchange_key|api_key).*=.[A-Za-z0-9+/]{8,}" \
  /opt/data/logs/si-v2-active-cycle/ \
  || echo "(no secret values found)"
echo

echo "== latest state + measurement summary =="
cd /home/hermes/projects/trading/self_improvement_v2
.venv/bin/python - <<'PY'
import json
from pathlib import Path

state_link = Path("reports/phase2/cycle_state/active_cycle_latest.state.json")
summary_path = Path("reports/phase2/measurement/measurement_summary.json")

print("latest_state_exists=", state_link.exists())
if state_link.exists():
    data = json.loads(state_link.read_text())
    print("cycle_id=", data.get("cycle_id"))
    print("fleet_verdict=", data.get("fleet_verdict"))
    print("controller_state=", data.get("controller_state"))
    print("ping_ok=", data.get("ping_ok_count"), "/", data.get("total_bots"))
    print("runtime_mutations=", data.get("runtime_mutations"))
    print("config_mutations=", data.get("config_mutations"))
    print("live_trading_mutations=", data.get("live_trading_mutations"))
    print("docker_mutations=", data.get("docker_mutations"))
    print("strategy_mutations=", data.get("strategy_mutations"))

print("measurement_summary_exists=", summary_path.exists())
if summary_path.exists():
    summary = json.loads(summary_path.read_text())
    print("cycles_scanned=", summary.get("total_cycles_scanned"))
    print("bot_measurement_points=", summary.get("total_bot_points"))
    print("proposal_records=", summary.get("total_proposal_records"))
    print("mutations_all_zero=", summary.get("mutations_all_zero"))
    print("secrets_found=", summary.get("secrets_found"))
PY
echo

echo "== worktree =="
cd /home/hermes/projects/trading
git status --short
echo

echo "=== verification complete ==="
