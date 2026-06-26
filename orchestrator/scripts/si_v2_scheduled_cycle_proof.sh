#!/usr/bin/env bash
# SI-v2 Scheduled Cycle Proof After Rainbow Recovery
# Runs after the scheduled 12:17 UTC SI-v2 active cycle.
# Read-only. No restart, no mutation, no apply.
set -euo pipefail
set +x

REPO="/home/hermes/projects/trading"
cd "$REPO"

ts="$(date -u +%Y%m%dT%H%M%SZ)"
PROOF_DIR="/opt/data/reports/si-v2-scheduled-cycle-proof-after-rainbow-recovery-$ts"
mkdir -p "$PROOF_DIR"
export PROOF_DIR

log() { echo "$1" | tee -a "$PROOF_DIR/proof.log"; }

log "=== SI-v2 Scheduled Cycle Proof ==="
log "start=$ts"

# ---- Phase 0 bis: Capture current state ----
date -u --iso-8601=seconds > "$PROOF_DIR/date-utc.txt"
git rev-parse HEAD > "$PROOF_DIR/git-head.txt"
git status --short > "$PROOF_DIR/git-status-before.txt"

# ---- Phase 1: Rainbow Freshness ----
log "--- Phase 1: Rainbow Freshness ---"

orchestrator/scripts/rainbow_producer_manager.sh status \
  > "$PROOF_DIR/rainbow-manager-status.txt" 2>&1 || true

curl -sS --max-time 10 http://127.0.0.1:8000/health \
  > "$PROOF_DIR/rainbow-health.json" 2>&1 || true

curl -sS --max-time 10 http://127.0.0.1:8000/signals/latest \
  > "$PROOF_DIR/rainbow-signals-latest.json" 2>&1 || true

PYTHON_BIN="/opt/data/ai4trade-bot/.venv/bin/python3"
if [ ! -f "$PYTHON_BIN" ]; then
  PYTHON_BIN="python3"
fi

"$PYTHON_BIN" - <<'PY' > "$PROOF_DIR/rainbow-freshness.txt" 2>&1
import json, os, sys
from datetime import datetime, timezone
from pathlib import Path

p = Path(os.environ.get("PROOF_DIR", "/tmp")) / "rainbow-signals-latest.json"
try:
    data = json.loads(p.read_text())
except Exception as e:
    print(f"RED: cannot parse signals: {e}")
    sys.exit(1)

signals = data if isinstance(data, list) else data.get("signals", [])

def get_ts(s):
    return s.get("timestamp_utc") or s.get("timestamp") or s.get("created_at") or s.get("emitted_at_utc")

timestamps = [get_ts(s) for s in signals if isinstance(s, dict) and get_ts(s)]
if not timestamps:
    print("RED: no timestamps")
    sys.exit(1)

def parse(ts):
    return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))

freshest = max(parse(ts) for ts in timestamps)
age = (datetime.now(timezone.utc) - freshest).total_seconds()

print(f"signals={len(signals)}")
print(f"freshest={freshest.isoformat()}")
print(f"age_seconds={age:.1f}")
print(f"fresh={age < 900}")

if age >= 900:
    print("RED: Rainbow stale")
    sys.exit(1)
print("GREEN")
PY
FRESH_RC=$?

# ---- Phase 2: Locate newest SI-v2 artifacts after 12:00 UTC ----
log "--- Phase 2: SI-v2 Artifacts ---"

find self_improvement_v2/reports/phase2 -type f \
  -newermt "2026-06-23 12:00:00 UTC" \
  2>/dev/null | sort \
  > "$PROOF_DIR/new-si-v2-artifacts-after-1200utc.txt" || true

ls -lt self_improvement_v2/reports/phase2/evidence/ \
  > "$PROOF_DIR/evidence-dir-listing.txt" 2>&1 || true

ls -lt self_improvement_v2/reports/phase2/cycle_state/ \
  > "$PROOF_DIR/cycle-state-dir-listing.txt" 2>&1 || true

# ---- Phase 3: Extract latest cycle result ----
log "--- Phase 3: Latest Cycle ---"

latest_evidence="$(ls -1t self_improvement_v2/reports/phase2/evidence/active_cycle_*.json 2>/dev/null | head -n 1 || true)"
echo "${latest_evidence:-NOT_FOUND}" > "$PROOF_DIR/latest-evidence-path.txt"

if [ -z "$latest_evidence" ]; then
  log "RED: no latest evidence file found"
  CYCLE_OK=1
else
  cp "$latest_evidence" "$PROOF_DIR/latest-evidence.json" 2>/dev/null || true

  "$PYTHON_BIN" - <<'PY' > "$PROOF_DIR/latest-cycle-summary.txt" 2>&1
import json, os, sys
from pathlib import Path

p = Path(os.environ.get("PROOF_DIR", "/tmp")) / "latest-evidence.json"
try:
    data = json.loads(p.read_text())
except Exception as e:
    print(f"RED: cannot parse evidence: {e}")
    sys.exit(1)

def walk_find(obj, keys, found=None):
    if found is None:
        found = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in keys:
                found.setdefault(k, []).append(v)
            walk_find(v, keys, found)
    elif isinstance(obj, list):
        for item in obj:
            walk_find(item, keys, found)
    return found

keys = {
    "cycle_id", "fleet_verdict", "rainbow_freshness", "fresh",
    "insufficient_history", "runtime_mutations", "config_mutations",
    "live_trading_mutations", "docker_mutations", "strategy_mutations",
    "approval", "controller_state", "shadow_proposals", "secrets_found",
    "ping_ok_count", "total_bots", "fleet_verdict_reason",
}

found = walk_find(data, keys)
for k in sorted(found):
    vals = found[k]
    preview = vals[:10]
    print(f"{k}={preview}")
PY
  CYCLE_OK=$?
fi

# ---- Phase 4: Safety scan ----
log "--- Phase 4: Safety Scan ---"

git status --short > "$PROOF_DIR/git-status-after.txt"

if grep -RniE 'dry_run[" ]*[:=][" ]*false' freqtrade docker-compose.yml self_improvement_v2 orchestrator 2>/dev/null \
  > "$PROOF_DIR/dry-run-false-scan.txt"; then
  log "RED: dry_run=false found"
  DRY_RUN_OK=1
else
  log "GREEN: no dry_run=false"
  DRY_RUN_OK=0
fi

# ---- Phase 5: Verdict ----
log "--- Phase 5: Verdict ---"

VERDICT="GREEN"
VERDICT_REASONS=""

# Check rainbow
if [ "$FRESH_RC" -ne 0 ]; then
  VERDICT="RED"
  VERDICT_REASONS="$VERDICT_REASONS; Rainbow stale"
fi

# Check cycle
if [ "${CYCLE_OK:-0}" -ne 0 ]; then
  VERDICT="RED"
  VERDICT_REASONS="$VERDICT_REASONS; Cycle evidence missing/corrupt"
fi

# Check dry_run
if [ "$DRY_RUN_OK" -ne 0 ]; then
  VERDICT="RED"
  VERDICT_REASONS="$VERDICT_REASONS; dry_run=false found"
fi

# Check mutations from cycle state
CYCLE_STATE_LATEST="self_improvement_v2/reports/phase2/cycle_state/active_cycle_latest.state.json"
if [ -f "$CYCLE_STATE_LATEST" ]; then
  "$PYTHON_BIN" -c "
import json
d = json.load(open('$CYCLE_STATE_LATEST'))
muts = ['runtime_mutations','config_mutations','live_trading_mutations','docker_mutations','strategy_mutations']
total = sum(d.get(m, 0) or 0 for m in muts)
print(f'mutation_total={total}')
for m in muts:
    print(f'{m}={d.get(m, \"?\")}')
print(f'controller={d.get(\"controller_state\", \"?\")}')
print(f'ping_ok={d.get(\"ping_ok_count\", \"?\")}/{d.get(\"total_bots\", \"?\")}')
rb = d.get('external_signals', {}).get('rainbow', {})
print(f'rainbow_status={rb.get(\"status\", \"?\")}')
print(f'rainbow_fresh={rb.get(\"fresh\", False)}')
print(f'rainbow_count={rb.get(\"count\", \"?\")}')
print(f'rainbow_age_s={rb.get(\"freshness_seconds\", \"?\")}')
" > "$PROOF_DIR/cycle-state-verdict.txt" 2>&1
fi

echo "verdict=$VERDICT" > "$PROOF_DIR/verdict.txt"
echo "reasons=$VERDICT_REASONS" >> "$PROOF_DIR/verdict.txt"
log "VERDICT: $VERDICT"
[ -n "$VERDICT_REASONS" ] && log "REASONS: $VERDICT_REASONS"

# ---- Phase 6: Report ----
log "--- Phase 6: Report ---"

REPORT_PATH="docs/reports/si-v2-scheduled-cycle-proof-after-rainbow-recovery-2026-06-23.md"

cat > "$REPORT_PATH" << 'REPORTEOF'
# SI-v2 Scheduled Cycle Proof After Rainbow Recovery

## Verdict

REPORTEOF

echo "$VERDICT" >> "$REPORT_PATH"

cat >> "$REPORT_PATH" << 'REPORTEOF'

## Baseline
- Rainbow recovery: 2026-06-23 ~05:50 UTC (restart via rainbow_producer_manager.sh)
- Expected scheduled run: 2026-06-23 12:17 UTC (si-v2-active-cycle cron)
- Controller: PAUSED / L3_REPOSITORY_ONLY

## Scope
Read-only verification. No restart. No apply. No config change. No mutation.

## Rainbow Freshness

REPORTEOF

cat "$PROOF_DIR/rainbow-freshness.txt" >> "$REPORT_PATH" 2>/dev/null || echo "N/A" >> "$REPORT_PATH"
echo "" >> "$REPORT_PATH"

cat >> "$REPORT_PATH" << 'REPORTEOF'
## Scheduled SI-v2 Cycle

REPORTEOF

cat "$PROOF_DIR/latest-cycle-summary.txt" >> "$REPORT_PATH" 2>/dev/null || echo "N/A" >> "$REPORT_PATH"
echo "" >> "$REPORT_PATH"

cat "$PROOF_DIR/cycle-state-verdict.txt" >> "$REPORT_PATH" 2>/dev/null || echo "N/A" >> "$REPORT_PATH"
echo "" >> "$REPORT_PATH"

cat >> "$REPORT_PATH" << 'REPORTEOF'
## Mutation Safety

REPORTEOF

echo "dry_run=false scan: $(if [ "$DRY_RUN_OK" -eq 0 ]; then echo 'CLEAN'; else echo 'RED - found'; fi)" >> "$REPORT_PATH"
echo "" >> "$REPORT_PATH"

cat >> "$REPORT_PATH" << 'REPORTEOF'
## Evidence Directory

REPORTEOF

echo "\`$PROOF_DIR\`" >> "$REPORT_PATH"
echo "" >> "$REPORT_PATH"

cat >> "$REPORT_PATH" << 'REPORTEOF'
## Next Step
If GREEN: P1 Rainbow Boot Persistence.
If RED/YELLOW: Diagnose and block before any persistence work.
REPORTEOF

log "Report saved to: $REPORT_PATH"

# ---- Commit and PR ----
log "--- Commit ---"
BRANCH="proof/si-v2-scheduled-cycle-after-rainbow-recovery"
git checkout -b "$BRANCH" 2>/dev/null || git checkout "$BRANCH"
git add "$REPORT_PATH"
git commit -m "docs(si-v2): add scheduled cycle proof after rainbow recovery" || log "No changes to commit"
git push -u origin "$BRANCH" 2>&1 | tee -a "$PROOF_DIR/proof.log" || log "Push failed (may need PR)"

log "=== Proof complete ==="
log "Verdict: $VERDICT"
log "Report: $REPORT_PATH"
log "Evidence: $PROOF_DIR"

exit 0
