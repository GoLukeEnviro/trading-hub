#!/usr/bin/env bash
set -euo pipefail

# run_trading_cycle.sh v0.2 — Full Safety Chain with Bridge + Healthcheck
# 
# Sequences: PrimoAgent → RiskGuard → ShadowLogger → Risk-Aware Bridge → Fleet Healthcheck
# Does NOT modify cronjobs, configs, strategies, or containers
# Dry-run only, no live trading

TRADING_ROOT="/home/hermes/projects/trading"
PRIMO_ROOT="/home/hermes/primoagent"
FREQTRADE_ROOT="$TRADING_ROOT/freqtrade"
SIGNAL_FILE="$PRIMO_ROOT/output/signals/primo_multi_signal_latest.json"
RISK_FILE="$PRIMO_ROOT/output/signals/primo_risk_filtered_latest.json"
SHADOW_LOG="$PRIMO_ROOT/output/shadow/primo_shadow_log.jsonl"
BRIDGE_SCRIPT="$FREQTRADE_ROOT/tools/primo_signal_bridge.py"
HEALTHCHECK_SCRIPT="$TRADING_ROOT/orchestrator/scripts/fleet_healthcheck.py"
LOG_DIR="$TRADING_ROOT/orchestrator/logs"
RUN_ID="$(date -u +'%Y%m%dT%H%M%SZ')"
LOG_FILE="$LOG_DIR/trading_cycle_${RUN_ID}.log"

mkdir -p "$LOG_DIR"

log() {
  echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] $*" | tee -a "$LOG_FILE"
}

log "START trading cycle v0.2 (full safety chain)"
log "RUN_ID=$RUN_ID"
log "TRADING_ROOT=$TRADING_ROOT"
log "PRIMO_ROOT=$PRIMO_ROOT"
log "FREQTRADE_ROOT=$FREQTRADE_ROOT"
log "LOG_FILE=$LOG_FILE"

cd "$PRIMO_ROOT"

# Step 1: Run PrimoAgent signal pipeline (if exists)
if [[ -f "$PRIMO_ROOT/run_primo_crypto_pipeline.py" ]]; then
  log "Step 1: Running PrimoAgent signal pipeline"
  if python3 "$PRIMO_ROOT/run_primo_crypto_pipeline.py" 2>&1 | tee -a "$LOG_FILE"; then
    log "Step 1: COMPLETE"
  else
    log "Step 1: WARNING — pipeline failed, using existing signal file"
  fi
else
  log "Step 1: SKIP — run_primo_crypto_pipeline.py not found (using existing signal file)"
fi

# Step 1b: Verify signal file exists before continuing
log "Step 1b: Verify signal file exists"
if [[ ! -f "$SIGNAL_FILE" ]]; then
  log "Step 1b: FAIL — signal file missing: $SIGNAL_FILE"
  exit 1
fi
log "Step 1b: PASS — signal file exists"

# Step 2: Validate raw signal JSON
log "Step 2: Validate raw signal JSON"
if python3 -m json.tool "$SIGNAL_FILE" >/dev/null 2>&1; then
  log "Step 2: PASS — raw signal JSON valid"
else
  log "Step 2: FAIL — raw signal JSON invalid"
  exit 1
fi

# Step 3: Run RiskGuard
log "Step 3: Run RiskGuard"
python3 "$PRIMO_ROOT/risk_guard_v0_1.py" \
  --input "$SIGNAL_FILE" \
  --output "$RISK_FILE" 2>&1 | tee -a "$LOG_FILE"

# Step 4: Validate RiskGuard output JSON
log "Step 4: Validate RiskGuard output JSON"
if python3 -m json.tool "$RISK_FILE" >/dev/null 2>&1; then
  log "Step 4: PASS — risk-filtered JSON valid"
else
  log "Step 4: FAIL — risk-filtered JSON invalid"
  exit 1
fi

# Step 5: Run ShadowLogger
log "Step 5: Run ShadowLogger"
python3 "$PRIMO_ROOT/shadow_logger_v0_1.py" \
  --signals "$SIGNAL_FILE" \
  --risk "$RISK_FILE" 2>&1 | tee -a "$LOG_FILE"

# Step 6: Validate shadow log
log "Step 6: Validate shadow log"
if [[ -s "$SHADOW_LOG" ]]; then
  log "Step 6: PASS — shadow log non-empty"
else
  log "Step 6: FAIL — shadow log empty or missing"
  exit 1
fi

# Step 7: Run Risk-Aware Bridge
log "Step 7: Run Risk-Aware Bridge"
python3 "$BRIDGE_SCRIPT" \
  --risk-input "$RISK_FILE" \
  2>&1 | tee -a "$LOG_FILE"

# Step 8: Validate state files written
log "Step 8: Validate state files written"
STATE_COUNT=$(find "$FREQTRADE_ROOT/bots" -maxdepth 6 -type f -name 'primo_signal_state.json' 2>/dev/null | wc -l)
if [[ "$STATE_COUNT" -ge 3 ]]; then
  log "Step 8: PASS — $STATE_COUNT state files written"
else
  log "Step 8: WARNING — only $STATE_COUNT state files found (expected 3)"
fi

# Step 9: Run Fleet Healthcheck
log "Step 9: Run Fleet Healthcheck"
python3 "$HEALTHCHECK_SCRIPT" 2>&1 | tee -a "$LOG_FILE"
HEALTHCHECK_EXIT=$?

if [[ $HEALTHCHECK_EXIT -eq 0 ]]; then
  log "Step 9: PASS — Fleet healthcheck GREEN"
elif [[ $HEALTHCHECK_EXIT -eq 1 ]]; then
  log "Step 9: WARNING — Fleet healthcheck YELLOW"
else
  log "Step 9: FAIL — Fleet healthcheck RED (exit code: $HEALTHCHECK_EXIT)"
  exit 1
fi

log "DONE trading cycle v0.2 (full safety chain)"
log "RUN_ID=$RUN_ID completed successfully"

exit 0
